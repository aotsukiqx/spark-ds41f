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

`build prepare --lock` → `build check` → `build image --apply` → `build
distribute --apply`; clean boots with the determinism gate and the
`quality,decode,prefill` gate vs the 1126 receipt.

## Results

| measure | 1126 reference | boot 1 (env NOT delivered) | boot 2 (capped) | boot 3 (capped) |
|---|---:|---:|---:|---:|
| quality | 5/5 | 5/5 | 5/5 | 5/5 |
| temp-0 determinism | — | identical | identical | — |
| decode grid | — | 10/10 same | 10/10 same | 10/10 same |
| prefill 131,072 (cooled) | 8,594.8 | 8,390.6 ±0.2% (bare 0.6.0 level) | **8,459.7 ±0.1%** | **8,461.1 ±0.4%** |

Boot 1 exposed an arm-wiring failure kept as evidence: `set.shapes.*
.environment` is not a key the renderer merges (candidate.py's own arms set
`environment` at the top level), so the cap never reached the container and
the boot measured bare 0.6.0 again (8,390.6). With the env delivered
(verified in `docker inspect`), the cap recovers a third of the regression
and the two capped boots agree tightly at **-1.6% vs the 1126 receipt**
(8,459.7/8,461.1 vs 8,594.8): the boundary restoration works (large SP
collectives are back on the tuned PyNCCL path), and the residual is
attributable to 0.6.0's changed execution of the <=4 MiB one-shot
collectives themselves.

**Verdict: qualified and promoted as spark-ds41f-1127** on owner direction
(upstream alignment), carrying the recorded -1.6% prefill residual with the
code-level analysis and a proper fix explicitly deferred to a post-window
task. Receipt: boot 3's bench →
`manifests/benchmarks/2026-11-27-spark-ds41f-1127-switched.json`.
Receipts: `runs/b1` (uncapped evidence), `runs/b2`, `runs/b3`.

## Post-window code analysis (2026-11-27, owner-deferred item)

The residual is structural: in 0.6.0 every eager (non-captured) dim-0
all-gather / reduce-scatter whose row fits a slot dispatches to the
multi-stage persistent kernel through `_collective_max_blocks`
(`oneshot/runtime.py`), which caps the grid at
`SPARKNET_ROCE_COLLECTIVE_BLOCKS` — **default 8 CTAs = 2 of 20 GB10 SMs** —
where 0.5.0's `_grid_blocks` spread the same payload over up to 64 CTAs. The
cap is an anti-starvation choice for collectives overlapped with main-stream
GEMM waves on a side stream (the 0.5.0 multi-launch stall, 150-375 µs); in
this serving pipeline the SP prefill collectives are not overlapped that
way, so the preserved SMs sit idle and the collective itself runs ~8x
narrower. That is the -1.6%.

**Queued one-variable experiment**: `SPARKNET_ROCE_COLLECTIVE_BLOCKS=0` (or
32/64) in the switched environment restores full-width collectives under
0.6.0's single persistent kernel — expected to recover the residual and
potentially beat 0.5.0 (the persistent kernel avoids the old multi-launch
yield stalls); the risk to gate is the overlap-stall case the cap protected.
`SPARKNET_ROCE_STAGE_BYTES` (4 MiB stages) is the secondary granularity
knob. The PDL `T.pdl_sync()` addition is a no-op in eager launches (decode
parity confirms).
