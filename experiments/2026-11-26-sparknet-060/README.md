# sparknet 0.6.0 (PDL-chained one-shot, multi-stage collectives)

Status: **in window** (base commit `672788ad6`, promoted baseline `2026-11-22-spark-ds41f-1122`).

## Hypothesis

sparknet 0.5.0's pin commit `1fd6a1fb` capped `SparknetOneShotAllReduce` at a
single slot (`<= _slot_bytes`) so large sequence-parallel prefill collectives
fell back to PyNCCL, which steals 4-8 of 20 GB10 SMs; and inside captured CUDA
graphs the four one-shot collective kernels were full-dependency barriers
between the PDL-chained producers (WO-B, `moe_combine`, `fused_wqa_wkv`) and
consumers (`mhc_post`, `attention_front`, `gather_columns_into`).

0.6.0 (`b01f350d`, authored against our exact pin, spark-ds41f#982/#989):

- `ca59c957` one persistent multi-stage pipelined kernel for
  `oneshot_allgather`/`reducescatter`/`exchange`/`all_to_all_rows` — 8 CTAs
  (2/20 SMs), ping-pong RDMA slots, 4 MiB stages;
- `e2b41c65` `T.pdl_sync()` as each kernel's first statement + PDL edges, so
  collectives join the decode PDL chain instead of ending it;
- `fb609995` RoCE proxy thread pinned to a fast core within the cpuset.

Expected effect: decode step time at c8+ (collective edge overlap) and prefill
throughput on SP reduce-scatter beyond 205 tokens (no PyNCCL fallback). The
TODO big levers (persistent FC1→SwiGLU→FC2 MoE, producer-direct RoCE writes,
128-row vocab tile) are explicitly **not** covered by this delta.

## Arm

One variable: `sources.sparknet` `1fd6a1fb` (0.5.0) → `b01f350d` (0.6.0).
Everything else is byte-identical to the 1122 site stack (vLLM series 648
active patches, TileLang `ac88f5bc` 13-patch series, TileKernels `66258df6` +
0001, NCCL `v2.32.6-1` empty series). Series files and `source.json` are owned
by this experiment folder outright.

## Method (window 2026-11-26)

`build prepare --lock` → `build check` → `build image --apply` →
`build distribute --apply`; two clean boots (containers removed first;
`--replace` must not be trusted across an image change) with the
`quality,decode` gate (`--allow-mismatch --cool-below 0`) against
`manifests/benchmarks/2026-11-22-spark-ds41f-1122-switched.json`, a cooled
131K prefill, and the temperature-0 determinism gate.

## Results (window 2026-11-26, two clean boots)

| measure | 1122 reference | boot 1 | boot 2 |
|---|---:|---:|---:|
| quality | 5/5 | 5/5 | 5/5 |
| temp-0 determinism | — | identical, 0/0 diffs (6 scenarios) | — |
| decode c1 step (prose/code) | 27.93 / 30.21 ms | 27.87 / 30.18 | 27.27 / 30.03 |
| decode grid | — | 10/10 same | 10/10 same |
| prefill 131,072 (cooled) | 8,654.7 (a3, same suite) | **8,398.7 ±0.2%** | **8,393.0 ±0.5%** |
| boot to API | ~123 s warm | +118.5 s | +109.0 s |

Decode: parity at every point in both boots — the PDL chaining did not move
step time on this workload. Prefill 131K is **-3.0% against a3's cooled
same-suite measurement (8,654.7)** and about -4.5% against the level expected
after the 2026-11-21 `NCCL_BUFFSIZE` 2 MiB alignment (+1.7-2.3% at 131K);
repeatable across two boots at ±0.2-0.5% spread. Mechanism: 0.6.0's
multi-stage one-shot kernel takes over the >256 KiB sequence-parallel
collectives and displaces the PyNCCL path that the 2 MiB buffer tuning had
accelerated.

**Verdict: not adopted** — parity on decode, repeatable prefill regression.
Production stays on the 1122 stack. Recorded follow-up option (own experiment,
one variable): 0.6.0 with `SPARKNET_ROCE_ALLREDUCE_CAPACITY_BYTES` /
`SPARKNET_ROCE_ALLGATHER_MAX_BYTES` capped back to the single-slot size, which
restores the tuned NCCL fallback under 0.6.0's PDL chaining and proxy pinning.
Receipts: `runs/b1`, `runs/b1-prefill`, `runs/b2`. Host note for the owner:
`doctor --live` now errors on all four nodes with `nvidia-drm fbdev is N,
expected Y` — a host-level drift unrelated to this candidate (present with
production 1122 as well); fix needs a service-stopped reboot.
