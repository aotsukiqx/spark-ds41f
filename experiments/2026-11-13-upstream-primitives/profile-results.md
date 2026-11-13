# Decode-step profile: the step is GPU-saturated (2026-11-13)

One profiled boot of the promoted `1107` recipe with `--profiler-config`
(`profile-resolved.json`, identical to production otherwise), c1 and c8 rounds of
the bench's code prompt after a warm-up, rank 0's trace. Profiling was bracketed
with `/start_profile` and `/stop_profile`; each round also ran once unprofiled as
a control.

| Round | Steps | Window/step | GPU busy/step | Idle/step | Idle share |
| --- | ---: | ---: | ---: | ---: | ---: |
| c1 | 26 | 43.4 ms | 42.9 ms | 0.49 ms | **1.12%** |
| c8 | 23.6 | 102.6 ms | 101.9 ms | 0.77 ms | **0.75%** |

Kernel union, not the sum: overlapping launches on different streams count once
(`analyze_trace.py`). The absolute step times are this boot's short-prompt shape,
not the bench points; the ratio is the measurement.

The largest idle gaps, by the kernel that ran last before each, are metadata
kernels — `metadata_builder_kernel`, `fill_rows_kernel`, `padding_rows_kernel`,
`apply_write_kernel`, `ced_requests_kernel`, `compute_slot_mappings_kernel` — at
0.1–0.3 ms of the whole window each, i.e. a handful of launches per step, not a
structural stall between the GEMMs.

## What this decides

**Item 5 (second stream in the decode graph): closed.** A second stream can only
recover time the GPU spends idle, and there is 0.75–1.1% of it, in per-step host
metadata launches that a stream cannot overlap into anything. The TODO's own gate
("if it is under ~1%, the second stream is not worth implementing") is met.

**Item 1's residual (persistent residency across `FC1 -> SwiGLU -> FC2`): ~1% at
most.** The kernel boundaries that residency would remove are inside an already
98.9%-busy GPU; the epilogue half of the lever was banked by `0756` (see
`TODO.md`). It is not a 2.4–3.5% item any more.

**The levers that survive remove GPU work rather than fill gaps:** direct producer
writes into the registered RoCE buffer (`roce_all_reduce` still stages a copy per
call) and the vocabulary head's greedy argmax epilogue (~12 MB less written and
read per TP4 call). Both are measured against busy time, not against idle time.

Artifacts: `profile_drive.py` (one profiled round plus its unprofiled control),
`analyze_trace.py` (kernel union, idle share, gap attribution), and the two
traces, kept node-side at `~/nvmodels/spark-ds41f/cache/profiles/d1107/` with the
sizes and results recorded here.

## Per-family kernel time in the same traces

Kernel time summed by name (row sums, so overlapped launches on different
streams are counted twice; the union above is the busy measure):

| Kernel | c1 ms/step | c1 calls/step | c8 ms/step | c8 calls/step |
| --- | ---: | ---: | ---: | ---: |
| `moe_grouped_fp8_fp4_gemm_kernel` | 23.14 | 99.2 | 50.90 | 134.8 |
| `l2_prefetch_kernel` | 12.22 | 148.7 | 18.49 | 197.9 |
| `gemm_mxfp8_kernel` | 6.10 | 251.5 | 12.32 | 349.8 |
| `oneshot_allreduce_kernel` | 4.15 | 101.5 | 15.43 | 134.5 |
| `vocab_packed_projection_kernel` | 2.70 | 8.1 | 4.26 | 9.6 |
| `moe_swiglu_cast_kernel_kernel` | 1.14 | 49.6 | — | — |

Two readings that change the lever list:

- **The vocabulary head is 2.7 ms of a 43 ms c1 step and 4.26 ms of a 102 ms c8
  step** — a weight-read cost (the 248 MB shard), not a logits-write cost.
  Device-to-device copies total **0.017 ms/step** over 7.5 copies, so the "12 MB
  of logits written and read" is not what the head spends its time on; the
  128-row tile (the other half of TODO item 4) is the part that matters, and only
  where a head call exceeds 64 rows.
- **`roce_all_reduce`'s staging copy is not a per-step memcpy fleet.** The trace
  shows 7.5 device copies a step in total (0.017 ms), against 101–135
  `oneshot_allreduce_kernel` launches a step: the copy happens *inside* the
  collective kernel. TODO item 2 therefore removes an intra-kernel copy and a
  producer→send dependency, not 116 launches, and its value can only be settled
  by an A/B of the changed kernel.

## Item 4 is banked, not open

`vocab.py` carries the whole ladder: `ROW_TILES = (16, 32, 64, 128)`,
`TILE_CONFIGS[128] = dict(block_N=32, threads=256, step_groups=1,
num_stages=4, act_stages=2)`, a `BF16_HEAD_CONFIGS[128]` entry, and
`row_tile(rows)` picking the smallest tile that holds the call — so a 65–128-row
head no longer runs a second 64-row tile. The greedy epilogue kernels
(`packed_vocab_greedy_partials`, `packed_vocab_markov_greedy_partials`) run for
the drafter's vocabulary-parallel greedy steps. With the head weight-read bound
and device copies at 0.017 ms a step, TODO item 4 has no open half left.
