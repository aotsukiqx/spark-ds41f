# Results: one measurement window on spark-ds41f-1107 (2026-11-14)

One boot of the promoted image with the torch profiler enabled, on the
production site, serving nothing else. Every number below is from this window;
the release's own recorded references are quoted only for the validity check.

## 1. Cold start and warm reuse

| Request | TTFT | total | prompt tokens |
| --- | ---: | ---: | ---: |
| first request after the boot | **0.172 s** | 0.296 s | 45 |
| same request again | 0.159 s | 0.282 s | 45 |

**TODO's "first request after a restart is ~0.37 s slower" does not reproduce.**
The gap here is 13 ms on a 45-token prompt, and the absolute TTFT is under
0.2 s. Closed unless a long-context first request shows otherwise.

## 2. Long-context prefill: 484,376 prompt tokens in 71.06 s = 6,816 tok/s

The recorded reference for the same release reads 7,460 tok/s at 524K and 6,012
at 1M, so this window reproduces the release (the profiler is on, which costs a
few percent; the point of the run is attribution, not the rate).

Kernel time by name, row sums over the window (kernels overlap, so the sum
exceeds the 71 s wall):

| Kernel | ms | share of wall | calls |
| --- | ---: | ---: | ---: |
| `indexer_score_kernel` | 15,637 | **22.0%** | 1,650 |
| `moe_grouped_fp8_fp4_gemm_kernel` | 12,908 | 18.2% | 3,954 |
| `sparse_mla_kernel` | 9,299 | 13.1% | 1,977 |
| `ncclDevKernel_SendRecv` | 8,905 | **12.5%** | 2,470 |
| `gemm_mxfp8_kernel` | 5,936 | 8.4% | 12,104 |
| `ncclDevKernel_AllGather_RING_LL` | 5,362 | **7.5%** | 1,440 |
| `moe_combine_kernel` | 4,113 | 5.8% | 8,497 |
| `mhc_project_streams_kernel` | 3,351 | 4.7% | 3,954 |
| `gemm_fp8w_bf16_cast_kernel` | 2,286 | 3.2% | 600 |
| `indexer_topk_segment_kernel` | 882 | **1.2%** | 1,698 |
| `moe_swiglu_cast_kernel_kernel` | 742 | 1.0% | 1,977 |
| `oneshot_exchange_kernel` | 612 | 0.9% | 600 |

### What this decides

- **The indexer is the largest single prefill cost at long context (22%), and it
  is almost entirely MXFP4 scoring.** Top-k selection is 882 ms against 15,637 ms
  of scoring — 5.3% of the indexer, 1.2% of the prefill. TODO's "screen a bounded
  radix top-k" cannot pay: the ceiling is 1.2% and a radix top-k would recover a
  fraction of it. The lever that remains is the scoring GEMM's bytes and tiling at
  200K–1M, not the selection.
- **Collectives are 20% of a long prefill** (`SendRecv` 12.5% + `AllGather RING`
  7.5%). This is the largest *unlisted* lever in TODO: nothing there names the
  sequence-parallel communication volume. It is also the one place where bytes
  moved, not math, is the cost.
- **The MoE body is 25%** (grouped GEMM 18.2% + combine 5.8% + the fused SwiGLU
  1.0%). The fused SwiGLU's 1.0% confirms the `0756` epilogue work is banked and
  small in prefill.
- `sparse_mla` 13.1% — attention at 484K, the third-largest cost.

### The prefill is also GPU-saturated

Kernel union over the trace window: **70,542 ms busy of 72,345 ms = 97.5%**, idle
1.8 s. Of that idle, **1.62 s is a single stall** 0.6 s into the run, right after
the first `scatter_rows_kernel` and before the first `fill_rows_kernel` — first-
chunk host preparation, not a steady-state cost. Excluding it the idle is 0.25%.

So a prefill lever pays only by removing GPU work (bytes or flops). Hiding
communication behind compute has nothing to hide behind: the only exposed
collective time is 68 ms of AllGather gaps across 120 occurrences, 0.1% of the
window.

## 3. Boot timeline

| Phase | Offset |
| --- | ---: |
| four ranks launched | +6.2 s |
| cluster ready, memory guards active | **+123.7 s** |

The boot is **about two minutes**, of which the launch is six seconds. The
"largest boot lever" (a per-rank pre-processed weight image) can therefore save
at most about 90 s of engine start-up, and no throughput at all — it is
housekeeping, not a performance item.

## Caveats

- One boot; the prefill point is a single profiled request, so its rate carries
  the profiler's overhead and should not be compared with released references
  beyond order-of-magnitude validity.
- The prefix-cache probe is a separate run (`measure_cache.py`); its numbers are
  in `cache-probe.json` beside this file.
