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
→ `build image --apply` → `build distribute --apply`; two clean boots (cold,
then warm) with the `quality,decode,prefill` gate (`--allow-mismatch
--cool-below 0`) against

## Results (window 2026-11-26, cold boot + warm boot)

| measure | 1122 reference | boot 1 (cold) | boot 2 (warm) |
|---|---:|---:|---:|
| quality | 5/5 | 5/5 | 5/5 |
| temp-0 determinism | — | identical, 0/0, hashes equal to the production stack | — |
| decode c1 step (prose/code) | 27.93 / 30.21 ms | 28.07 / 30.43 | 27.75 / 30.23 |
| decode grid | — | 10/10 same | 10/10 same |
| prefill 131,072 (cooled) | 8,654.7 (a3, same suite) | 8,570.6 ±0.2% | 8,695.4 ±0.3% |
| boot to API | — | **+698.8 s** (fresh namespace) | **+111.8 s** |

The reworked series needed one extra patch beyond the rebase: `0709` bumps
vLLM's `requirements/cuda.txt` floor `tilelang==0.1.15` → `==0.1.16` (the
image build's cross-consumer check rejects `0.1.16+snapshot` against
`==0.1.15`; PEP 440 local versions match `==` only on the same base). vLLM
chain tree moved to `9c20f2003ed2`.

**Verdict: qualified, no regression** — decode parity both boots (c1 within
±0.7%), prefill parity (two-boot mean ≈ 8,633 against a3's 8,654.7),
determinism hashes identical to the production stack (the compiler move
changed no temperature-0 output), quality 5/5. Cold boot 698.8 s against the
882 s of the 2026-11-20 refresh and warm boot 111.8 s against 123 s —
consistent with, not proof of, the parallel JIT helping candidate churn.
Adoptable by owner decision; the lock advance carries cache-key hygiene,
toolchain-versioned keys, group-readable shared caches and the TVM/Z3
solver soundness fixes. Receipts: `runs/b1`, `runs/b2`.
