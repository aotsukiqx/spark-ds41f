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
