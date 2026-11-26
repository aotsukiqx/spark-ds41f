# spark-ds41f-1126: TileLang 0.1.16 + TileKernels 2.1.0

Status: **in promotion window** (base commit `dbd39d1d3`, promoted baseline
`2026-11-22-spark-ds41f-1122`).

## Content

Both advances were qualified alone in the 2026-11-26 maintenance window
(`experiments/2026-11-26-tilelang-0116`, `experiments/2026-11-26-tilek-210`),
each with two clean boots, the determinism gate (hashes equal to the
production stack) and the `quality,decode,prefill` gate at parity against the
1122 reference. This arm qualifies their combination and produces the
promotion's benchmark receipt:

- TileLang `ac88f5bc` → `640fdcae` (0.1.16): 0003/0007/0011 reworked onto the
  parallel-compilation rewrite, 0012 re-keyed (wheel
  `0.1.16+snapshot.c74164b9…`, fresh cache namespace), 0709 bumps vLLM's
  `requirements/cuda.txt` floor to `==0.1.16`. Cold boot 698.8 s against 882 s
  on the 11-20 refresh.
- TileKernels `66258df6` (2.0.0) → `c1cf914a` (2.1.0): serving imports it
  zero times; hot path proven untouched; 0001 carries forward byte-identical.
- sparknet stays `1fd6a1fb` (0.5.0); the 0.6.0 advance (with the capacity
  caps that restore the tuned NCCL fallback) is the next release's own step.

## Method

`build prepare --lock` → `build check` → `build image --apply` →
`build distribute --apply`; stop production; two clean boots with the
determinism gate and the `quality,decode,prefill` gate vs
`manifests/benchmarks/2026-11-22-spark-ds41f-1122-switched.json`; the better
boot's bench becomes `manifests/benchmarks/2026-11-26-spark-ds41f-1126-switched.json`.

## Results

(to be filled)
