# sparknet 0.6.0 with the one-shot eligibility cap

Status: **in qualification window** (base commit `312944f6d`, promoted baseline
`2026-11-26-spark-ds41f-1126`).

## Hypothesis

The bare 0.6.0 advance measured a repeatable **-3.0% prefill regression at
131K** (8,393-8,399 vs 8,654.7, `experiments/2026-11-26-sparknet-060`):
0.6.0's multi-stage kernel takes over arbitrarily large payloads whose
per-row pack fits a slot (`world_size * row_bytes <= _slot_bytes` outside
CUDA graph capture — not env-pinnable in sparknet), displacing the PyNCCL
path the 2026-11-21 2 MiB `NCCL_BUFFSIZE` alignment accelerated. Decode was
at parity, so the PDL chaining bought nothing measurable but cost nothing.

This arm keeps 0.6.0 (PDL-chained one-shot kernels, pinned proxy, upstream
alignment) and restores the 0.5.0 eligibility boundary at the vLLM dispatch
level: series patch **0710** adds `SPARK_DS41F_ONESHOT_MAX_BYTES`, and the
arm sets it to 4194304 (the 0.5.0 single-slot boundary given the switched
shape's 4 MiB `SPARKNET_ROCE_ALLGATHER_MAX_BYTES`). Larger payloads fall back
to PyNCCL exactly as 0.5.0 did.

Gate: 131K prefill back at the production level (~8,600+), decode 10/10
same, determinism identical, quality 5/5. A deeper code-level analysis of
the multi-stage kernel's loss against the tuned NCCL path is deferred by the
owner to after the window (recorded in the window summary).

## Method

`build prepare --lock` → `build check` → `build image --apply` →
`build distribute --apply`; two clean boots with the determinism gate and the
`quality,decode,prefill` gate vs
`manifests/benchmarks/2026-11-26-spark-ds41f-1126-switched.json`.

## Results

(to be filled)
