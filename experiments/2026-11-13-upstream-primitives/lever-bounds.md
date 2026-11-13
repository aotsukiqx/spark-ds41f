# Bounding the open decode levers (2026-11-13)

Read-only work: no window, no image, no serving change. Everything below is
either source-level arithmetic or measured on the production container
`spark-ds41f:1107` as it runs.

## Item 7 — RoCE one-shot broadcast for adaptive verification: closed

`adaptive_verification.py` broadcasts one buffer per decode step
(`tp_group.broadcast(self._confidence_buffer, src=0)`, line 278).

| Quantity | Value | Source |
| --- | --- | --- |
| Buffer shape | `(1 + planned_confidences, max_num_reqs, num_speculative_steps)` | source line 136 |
| Live values | `max_num_reqs=16`, `num_speculative_steps=5` | container command line, `--max-num-seqs 16`, `--speculative-config num_speculative_tokens=5` |
| Payload | 80–160 floats = **320–640 bytes** | arithmetic |
| Step time | 21.05 ms (grid geometric mean), 27.7 ms (c1) | `2026-11-07-spark-ds41f-1107` reference |
| Collective cost floor | 4–10 µs (latency-bound, ≤1 KiB over RoCE) | launch + round-trip latency |
| **Share of a step** | **0.014–0.05%** (0.1% even at 20 µs) | arithmetic |

The site's narrowest CI is 2–4% (c1), i.e. 0.5–1 ms. The lever is two orders of
magnitude below what this site can resolve and below any plausible step-time
gain, so a `sparknet` one-shot replacement cannot pay for itself. Closed as a
measured dead end. It reopens only if a trace shows the broadcast stalling the
step loop (which would appear as an idle gap and belongs to item 5's
measurement, not to this one).

## Item 6 — all-reduce skew and proxy core affinity: premise reduced

`lscpu` reports 20 cores in two capacity classes; `/sys/devices/system/cpu/*/cpu_capacity`
on spark-eb1a reads 718/731 for cpus 0–4 and 10–14 and 997–1024 for cpus 5–9
and 15–19. The production container's cpuset is **5-9,15-19** — every thread of
`vllm`, `VLLM::EngineCore` and `VLLM::Worker_TP` inherits it, so no serving
thread can land on a slow core. The hypothesis in TODO ("proxy threads run
without explicit CPU core affinity on GB10's mixed core types") does not hold
for this deployment: it is already confined to the fast clusters, and no code in
the patch series calls `sched_setaffinity`.

What remains is coarse splitting *within* the ten fast cores (engine busy loops,
`sparknet` proxy threads, gloo/NCCL watchdogs, the API server on rank 0 all
share one cpuset). Bounding that needs CPU-side contention under load, and the
site is idle outside a window; production returned 0 running / 0 waiting
requests when this was read. Deferred to a loaded trace, not pruned.

## Item 5 — second stream inside the decode graph: needs a profiled boot

The lever's ceiling is the serial-dependency share of the step, which is
`step_time - GPU busy`. No decode profile of the `1107` stack exists in this
repository: the last torch-profiler captures are `experiments/2026-09-24-*`
(r5 era) and the c16/c8 summaries under `experiments/2026-10-11-c16-profile`
and `2026-10-24-tilelang-completion` are profiler *configs*, not captures. An
old-release number cannot bound a lever whose whole question is how much of the
step is host-and-dependency time after PDL and CUDA-graph work landed.

Exact plan (one candidate-free boot inside a window):

1. Start the promoted `1107` recipe with `--profiler-config` (the c8 harness at
   `experiments/2026-10-11-c16-profile/profile_c8.py` is the working example:
   one profiled round after a warm-up, warm prefix, `code` prompt).
2. Capture at c1 and c8, one round each, all four ranks.
3. Sum kernel durations per rank and divide by the step's wall time: the
   remainder is the latency-bound bucket. Split it by the gap's predecessor
   kernel name to tell "serial dependency" (attention → MoE → combine) from
   "launch/host" (which the second stream cannot fix).
4. Report the c8 bucket as the ceiling for item 5; if it is under ~1%, the
   second stream is not worth implementing, exactly as this file closed item 7.
