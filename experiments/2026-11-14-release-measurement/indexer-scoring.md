# The indexer's 22% is one GEMM class, not a fat (2026-11-14)

Read-only analysis of the 484K prefill trace kept from the measurement window
(`~/nvmodels/spark-ds41f/cache/profiles/d1107/…1794613919667201851.pt.trace.json.gz`
on spark-eb1a). No window, no serving change.

`indexer_score_kernel`: 1,650 launches, 15,637 ms total — 22.0% of the 71.06 s
prefill. Split by launch geometry:

| Grid | Time | Share | Launches | Average |
| --- | ---: | ---: | ---: | ---: |
| (128, 256, 1) | 14,647 ms | **93.7%** | 1,248 | 11.74 ms |
| (128, 232, 1) | 847 ms | 5.4% | 81 | 10.45 ms |
| (128, 190, 1) | 49 ms | 0.3% | 3 | 16.49 ms |
| (128, 1024, 1) | 34 ms | 0.2% | 18 | 1.87 ms |
| everything else | 60 ms | 0.4% | 300 | ≤ 6.3 ms |

1,248 = 32 chunk-steps × 39 layers, so the cost is one full-context scoring GEMM
per chunk per layer, at ~11.7 ms each. Per-call durations: p50 9.19 ms, p90 19.55 ms,
max 28.24 ms. The 161 launches with grid (128, 1) cost 7 ms in total and are not
worth any attention.

## What this means for the lever

- The cost is **inherent O(chunk rows × preceding keys)** work at long context,
  already executed as an MXFP4 GEMM with a 128-wide block and 256 K-segments a
  launch. There is no launch overhead, no small-kernel tail and no idle to remove.
- A **bit-exact** change can only come from tiling, occupancy or the FP4 dot's
  instruction mix inside this one kernel; nothing in the trace suggests a cheap
  win, and the same kernel is a decode cost too (`indexer` work appears in the
  decode profile), so any tiling change must be measured on both phases.
- An **algorithmic** change — scoring segments coarsely first and refining only
  the candidates, or a lower-precision pre-filter — would reduce the 93.7%
  directly, but it changes which keys are selected, so it changes model output.
  Under this repository's correctness-first rule that is a model-quality research
  item for the owner, not a performance candidate.

Recorded so the next round does not spend a window on "top-k selection" (1.2%),
which this trace rules out, or on the belief that the scoring pass is
inefficient in shape: it is one kernel, and it is the same kernel per layer.

# Collective payloads in the same trace

| Collective | Calls | CPU time | Payload |
| --- | ---: | ---: | --- |
| `all_gather` | 1,578 | 2,570 ms | avg 7.8 MB |
| `all_reduce` | 1,408 | 1,631 ms | avg 3.6 MB |

## Erratum (2026-11-14, same day, correlation check)

The first reading of this trace claimed the 1,162 ten-kilobyte all-reduces were
running on NCCL's ring handshake. **That was wrong.** Torch's profiler links each
`cpu_op` to its kernel through `External id` / `correlation`; joining the two in
this trace shows:

| Collective calls | Payload | Kernel that ran |
| --- | --- | --- |
| 1,162 | `1 x 5120` BF16 (10 KB) | **`oneshot_allreduce_kernel`** |
| 162 / 40 / 8 / 4 / 2 | `45/128/2/6/3 x 5120` | `oneshot_allreduce_kernel` |
| 580 all-gathers | `1 x 448` | `oneshot_allgather_kernel` |
| 493 all-gathers | `4072 x 1792` (14.6 MB) | `ncclDevKernel_AllGather_RING_LL` |
| 87 each | `4072 x 5120`, `32576 x 128`, `4072 x 512` | `ncclDevKernel_AllGather_RING_LL` |
| 29 all-gathers | `16288 x 5120` (167 MB) | `ncclDevKernel_AllGather_RING_LL` |

So the small collectives are **already on the one-shot path**; what NCCL carries
is the large sequence-parallel exchange, at 14.6 MB and up, which is above the
one-shot dispatch limits (`ALLREDUCE 2 MiB`, `ALLGATHER 4 MiB`) by design.

The earlier "1.2 ms per 10 KB call" figure was CPU-side issue time (`cpu_op`
durations), not a kernel cost, and it is not evidence of a wrong backend.

### What this leaves

The 20% collective share is large-tensor SP exchange at the fabric's rate. Moving
it to the one-shot path is not an obvious win: that path's advantage is small-
message latency, and 14.6–167 MB messages would need a registered capacity two
orders above today's 4 MiB slot. **No clean candidate remains in the collectives**
until either the exchange volume shrinks (fewer/larger tensors, a different
sequence-parallel partition) or the one-shot path gains a multi-slot, large-payload
mode worth its pinned memory.

