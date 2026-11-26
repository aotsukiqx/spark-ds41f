# TileLang 0.1.16 (parallel JIT, cache-key hygiene, solver fixes)

Status: **assembled, awaiting its window slot** (base commit `672788ad6`, promoted
baseline `2026-11-22-spark-ds41f-1122`; qualifies after the sparknet-060 arm).

## Hypothesis

ac88f5bc → `640fdcae` (the 0.1.16 cut, 24 commits). CUDA-relevant minority:

- `3f01780f` process-based parallel compilation (`tilelang/jit/__init__.py`
  +254/-44) — cold-boot lever; the 11-20 refresh measured 882 s cold / 123 s
  warm on a fresh namespace;
- `423b4d81` CUDA/Ascend toolchain versions in kernel cache keys;
- `a3a4f9ce` group-readable shared cache entries;
- `b4c67597` + `439e5cec` TVM/Z3 bumps (right-shift, low-bit mask, solver
  soundness);
- `8c5d2d89` wide-integer predicates in vote/sync intrinsics;
- `d33f9eb8` Layout/Fragment own bound placeholder Vars — the rebase-risk
  focus; the series' MMA patches do not touch `layout.cc`.

The rest is ROCm/Ascend/CuTeDSL/CI/tests. The TODO big levers (persistent
FC1→SwiGLU→FC2 MoE, producer-direct RoCE writes, 128-row vocab tile) are not
covered.

## Series rework

Three patches moved onto the parallel-compilation rewrite:

| patch | rework |
| --- | --- |
| 0003 | freeze refusal after the memory-cache lookup, beside upstream's new `supports_disk_cache` early-out (which returns `(key, None)`) |
| 0007 | cache-disabled wrapper bypass, re-anchored in the rewritten `jit/__init__.py` |
| 0011 | explicit preparation retained while caching is disabled |
| 0012 | re-keyed: `0.1.16+snapshot.c74164b94cbbc6ab8c83067852019c955092826d` (pre-metadata tree after 0011) |

Verification: the 13-patch series applies at `640fdcae` with plain
`git apply` (no 3way) in a pristine worktree; final tree
`85daad439e0e6e8182a09c3d9ed685bc2cac1d42`; the four touched python files
pass `ast.parse`. A fresh kernel-cache namespace appears on every rank
(wheel identity changes); 1107/1122 namespaces stay untouched.

## Method

Same window protocol as sparknet-060: `build prepare --lock` → `build check`
→ `build image --apply` → `build distribute --apply`; two clean boots with the
`quality,decode` gate (`--allow-mismatch --cool-below 0`) against
`manifests/benchmarks/2026-11-22-spark-ds41f-1122-switched.json`, a cooled
131K prefill, cold and warm boot timing recorded.

## Results

(to be filled; adverse runs kept)
