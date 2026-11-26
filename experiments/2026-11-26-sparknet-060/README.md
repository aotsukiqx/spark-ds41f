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

## Results

(to be filled; adverse runs kept)
