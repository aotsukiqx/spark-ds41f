# TileLang pin refresh: `2123e412` → `b1367a59`

Status: **assembled and verified; image build next**. Base commit `65366133`.

## The one variable

The compiler pin; the 1107 patch series is unchanged. TileKernels, recipe,
scheduler, collectives, models and serving options stay at `spark-ds41f-1107`.

| | before (promoted) | after (this candidate) |
|---|---|---|
| tilelang revision | `2123e412` (2026-11-03) | `b1367a59ce10ae4939d26821f4ed8a82457fb004` (2026-11-19) |
| tilelang series | `1107/tilelang` 13 patches | same 13 patches, `0012` re-keyed |
| snapshot identity | `0.1.15+snapshot.35f15411…` | `0.1.15+snapshot.e808dbdd…` |
| carried backports | `0014` clamp, `0015` prefetch | not carried: upstream owns `824c5c42`, `35850c06` |
| tile_kernels | `66258df6` v2.0.0 | **unchanged** (see below) |

**TileKernels 2.1.0 is deliberately left out.** `ITEM2` folded it into "the next
TileLang refresh", but 2.1.0 rewrites `quant/norm_forward_*`, `quant/swiglu_*`
and `torch/cast.py`, and the mHC finalize path still calls TileKernels' cast;
its int64 count rewrite is on a path we do not execute (`count_clamp=False`,
swiglu is a test oracle). It would add serving-path risk for no benefit, so it
stays at v2.0.0 and moves in its own candidate when there is a reason.

Expected serving effect: **zero**. The clamp patch's target kernel is a test
oracle at `1107` (`0181` replaced the serving call with `moe_swiglu_cast`;
`0665` only compares against `_tile_kernels_swiglu`). The candidate is judged as
"compiler identity changed, nothing else moved".

## Deep review of the 39-commit delta (what can actually reach us)

| commit | surface | verdict |
|---|---|---|
| `824c5c42` clamp, `35850c06` prefetch | new builtins + `math.h`/`copy.h` templates, additive | no behavior change; the 1107 refresh already ran both on SM121 |
| `c99577fd` TF32 RNE | `codegen_cuda.cc` cast lowering, **only for an explicit `round="rn"` f32→tf32 cast** | we pass no `round="rn"` anywhere (`rg` over the vllm and tilelang series: 0 hits), so the default `tfloat32_t(float)` rounding mHC relies on is untouched. The 2026-11-13 note that called this a risk was too broad |
| `71a7c311` vector widths | `src/transform/loop_vectorize.cc` planner rewrite (branch/`Select`/`if_then_else` casts, bound-var expansion) | changes codegen globally; correctness rests on the determinism/quality gates, not on reading the diff. The one unmeasured freebie |
| `9009dbc5` multi-source cache | `TILELANG_CACHE_DIR` becomes a path list; corrupt/incomplete entries **raise** instead of recompiling; `_get_cache_root` → `_get_write_cache_root` | our cache patches (`0003`, `0007`, `0011`) reference none of the renamed internals, but the policy change is real: a half-written entry now fails a boot instead of healing it. Fresh per-rank cache directories and the C45 provenance check are mandatory, not optional |
| `20184270`, `54f19ec5` JIT adapters | per-device dynamic-smem attribute, caller-device restore | one visible device per rank process: no-op |
| `3c0bd4cb` NVRTC, `d60ec7a4` CPU `any_of`, ROCm/Ascend/CuTeDSL/docs/CI | not our backends | no-op |
| `b1367a59` version labels | drops `version_provider.py`/`NO_TOOLCHAIN_VERSION`; `VERSION` + `NO_VERSION_LABEL=1` still decide the label | our identity is a literal `VERSION`, so it survives; assert wheel version == lock version and namespace == pre-metadata tree at first use |
| `fd530580` host-mapped annotations | new annotation | usable later for Engram's C2C control; not in this candidate |

## Verified, not inferred

- `1107/tilelang` `0001..0013` (with the regenerated `0012`) applies **13/13**
  on `b1367a59` in a clean worktree; `git diff --check` clean; 40 files;
  final tree `fa23bcc84a7322e41eb339dcac776aeec248d44c`.
- Pre-metadata tree (0001..0011, before `VERSION`) is
  `e808dbdd8093942a3e469054515507bf60d7e52c`, head
  `49b04b84a80a2973262c916b4fdbf1d0b75ce52b`; `VERSION` now carries it and
  `upstreams.lock.json` `sources.tilelang.version` matches.
- Everything else in the candidate folder is a byte copy of the promoted
  series or lock; only `0012` and the lock's tilelang entry changed.

## Steps

1. `bin/spark --cluster-config experiments/2026-11-19-tilelang-pin-refresh/arm-tp4-switched.json build prepare --lock`
   on a node: records patch heads/trees/fingerprints into `source.json`, the
   candidate lock and the arm's `expected_labels`.
2. `build check`, then `build image --apply --tag spark-ds41f:1107-tilelang-b1367`.
   Beyond the standard smoke: wheel version == lock `version`; the cache
   namespace is absent before first use, then equals the pre-metadata tree;
   fresh cache directories per rank; the IKET prepare/freeze check with caching
   disabled passes; no `disabled`/`fallback`/`compile failed` in the boot log
   and no JIT after readiness.
3. Gates and screen on `tp4-switched` (and `tp3-switched` before any promotion):
   determinism, quality 5/5, release tests, fixed-row decode grid plus
   `c1`/`c8`/`c16`, prefill spot points, two boots, against the recorded
   `2026-11-07-spark-ds41f-1107` references.
4. Decision: accept if no point regresses outside CI on both boots; promote
   alone only for a ≥1% repeatable fixed-row change; reject on any gate failure.
   Rollback is restoring `spark-ds41f:1107` through the site profile and closing
   the hold, keeping every receipt.

## Status log

- 2026-11-19: upstream re-check (`b1367a59`, +4 commits, all non-material);
  candidate folder, lock, arm and re-keyed `0012` assembled; chain verified
  13/13 on the new pin. Production still serves `1107`; no window taken yet.

## Out of scope

In-kernel `prefetch_l2` emission (`ITEM3-prefetch-design.md`), host-mapped
buffer annotations (`fd530580`), TileKernels v2.1.0, and the big decode levers
(persistent `FC1 -> SwiGLU -> FC2`, direct producer writes, 128-row vocab head).
