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

The all-reduce sizes are bimodal: 1,162 calls carry **10 KB** (`1 x 5120` BF16),
while 29 calls carry 167 MB (`16,288 x 5120`, the chunk-sized SP reduction) and
one carries 123 MB. The large ones are bandwidth work at the fabric's limit and
are not interesting; the small ones are the finding:

- 1,162 calls of 10 KB, about **1.2 ms of CPU time each** (1.4 s in total). Over
  RoCE a 10 KB collective should take tens of microseconds; the one-shot path this
  repository already ships (`SPARKNET_ROCE_ALLREDUCE_DISPATCH_MAX_BYTES=2097152`,
  BF16 supported) would serve them at that cost.
- They are running through NCCL (`ncclDevKernel_SendRecv`, 2,470 launches,
  8,905 ms of kernel time) instead — a ring handshake per call, roughly two
  orders of magnitude above the payload's own cost.

**Hypothesis worth one candidate window:** these per-step, single-row reductions
are being dispatched to NCCL while the graph is captured (or from a communicator
that never saw the RoCE policy), so each pays a ring handshake. Moving them onto
the prepared one-shot path is bit-exact (same sum, same order in the one-shot
protocol's reduction), needs no model change, and the addressable time is the
1.4 s of CPU issue plus their share of the 8.9 s of SendRecv kernel time. Check
`should_allreduce`'s size/dtype gate and where the graph capture registers the
communicator before building anything.
