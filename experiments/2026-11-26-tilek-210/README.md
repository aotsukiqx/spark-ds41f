# TileKernels 2.1.0 (parity alignment; hot path expected unchanged)

Status: **assembled, awaiting its window slot** (base commit `672788ad6`,
promoted baseline `2026-11-22-spark-ds41f-1122`; qualifies last).

## Hypothesis

`66258df6` (v2.0.0) → `c1cf914a` (v2.1.0, quiet since 2026-10-14). The serving
tree imports tile_kernels zero times — only the kernel-parity benchmarks
(`benchmarks/kernels/benchmark_deepseek_v41_{mhc_cast,mhc_post,moe_prefill_tiles}.py`)
use it — so the value is stopping benchmark drift from upstream, not serving
speed. v2.1.0's rewrites:

- count-clamp reduction as int64 via two int32 lanes (dead for serving:
  `count_clamp` off and not imported);
- `norm_forward` reorganized: `rstd` is `None` unless `with_rstd=True`,
  `mega_moe_sf` documented CUDA-only (benchmark-facing API change);
- FP4 `convert_to_e2m1_bits` rewritten arithmetically — not our weight path
  (UE8M0 + 4-bit deltas go through the in-tree `scale_codes`).

## Patch

`0001` (NaN-pass-through clamp, compare-and-select as `torch.clamp`) is
**not absorbed upstream** (v2.1.0 leaves the `T.min`/`T.max` lines untouched)
and applies at both pins byte-identical; applied tree at c1cf914a:
`8386508bc3dcfc19eabc6cde1eb7016824a1bd6e`.

## Method

Same window protocol; the gate's purpose is to **prove** the hot path is
untouched: decode grid and quality must sit inside the reference intervals,
and the release tests keep their two pre-existing scheduler failures.

## Results

(to be filled; adverse runs kept)
