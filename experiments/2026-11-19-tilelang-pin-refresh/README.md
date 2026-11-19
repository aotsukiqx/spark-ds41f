# TileLang pin refresh: `2123e412` → `b1367a59`

Status: **measured on the site; verdict: accept the compiler refresh, no speed claim**. Base commit `65366133`.

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

## Measured (2026-11-19, owner window on spark-eb1a, tp4-switched)

Image `spark-ds41f:1107-tilelang-b1367` (`sha256:80030ea1…`), built on the head
in 538 s under the memory guard, lowest `MemAvailable` 109.0 GiB, GPU import
smoke passed with the wheel at `0.1.15+snapshot.e808dbdd…`.

- **Release tests** (`bundles/release-tests`, 1107's 149-file gate manifest,
  receipts in `receipts/release-tests/`): 9551 passed, 311 skipped, 2 failed.
  Both failures are `test_schedule_concurrent_partial_requests[True/False]`,
  which reproduce **in the promoted 1107 image under the same bundle
  environment** (2 failed, 655 passed, 191 skipped) and pass with the served
  model redirect unset in either image (621 passed, 0 failed). Pre-existing
  deployment behaviour of the vLLM series, deselected in
  `release-tests.json` with the reason; not caused by the compiler.
- **Boots**: first boot API ready at +882 s (empty new namespace, every kernel
  compiled fresh), second boot +123 s (namespace reused). The container's
  `tilelang.__version__` and the cache namespace both read
  `0.1.15+snapshot.e808dbdd…`; 1107's `…_35f15411…` namespace is untouched.
  Boot logs show no `fallback` or `compile failed`; the three `disabled` lines
  are explicit switches (FlashInfer autotune, EAGLE trailing prefix-cache drop,
  scale-out endpoints), and no JIT runs after readiness.
- **Quality**: 5/5 on both boots.
- **Decode grid** against `manifests/benchmarks/2026-11-07-spark-ds41f-1107-switched.json`
  (step ms; delta is candidate/reference):

  | point | reference | boot 1 | boot 2 | Δ boot 1 | Δ boot 2 | same direction |
  | --- | ---: | ---: | ---: | ---: | ---: | --- |
  | prose-c1 | 27.48 | 27.47 | 27.38 | −0.0% | −0.4% | yes |
  | prose-c2 | 31.07 | 28.62 | 28.30 | −7.9% | −8.9% | yes |
  | prose-c4 | 37.76 | 31.03 | 31.66 | −17.8% | −16.2% | yes |
  | prose-c8 | 38.33 | 36.25 | 41.95 | −5.4% | +9.4% | no |
  | prose-c16 | 51.42 | 54.47 | 49.77 | +5.9% | −3.2% | no |
  | code-c1 | 29.78 | 30.12 | 30.18 | +1.2% | +1.3% | yes |
  | code-c2 | 37.73 | 34.59 | 37.59 | −8.3% | −0.4% | yes |
  | code-c4 | 39.95 | 37.63 | 37.98 | −5.8% | −4.9% | yes |
  | code-c8 | 42.18 | 43.03 | 48.57 | +2.0% | +15.1% | yes |
  | code-c16 | 58.63 | 61.02 | 57.15 | +4.1% | −2.5% | no |

  No point is outside the reference's combined 95% interval on both boots. The
  only consistent outside-interval reading is `prose-c4` on boot 1 (−17.8%,
  boot 2's own interval is ±24.7%), so the repeat rule does not pass and no
  speed claim is made. The mixed signs at c8/c16 are this site's boot-to-boot
  noise (the recorded reference has ±3-4% intervals; the default boot samples
  four times).
- **Record values** (the switched reference carries only quality and decode):
  prefill 32768/65536/131072 tokens 8604/8518/8282 tok/s; prefix replay hit rate
  0.99 (warm 0.216 s); admission 4 x 65536 pass, peak KV 9%; sampled acceptance
  0.87 prose-c1, 0.90 prose-c4, 3.09 code-c1, 2.86 code-c4.
- **Resources**: `MemAvailable` floor 20.45 GiB (boot 1) and 22.25 GiB (boot 2),
  no swap growth, no thermal slowdown, GPU max 80 C.

**Verdict:** the compiler identity moved and nothing else did — quality and
decode hold at 1107 within this site's intervals, the kernel-cache namespace is
source-bound and reused, and the two release-test failures are pre-existing.
Carry `b1367a59` into the next release; do not claim a speedup.

## Status log

- 2026-11-19: upstream re-check (`b1367a59`, +4 commits, all non-material);
  candidate folder, lock, arm and re-keyed `0012` assembled; chain verified
  13/13 on the new pin.
- 2026-11-19: owner window (manual hold, production stopped): image built and
  smoke-tested, release-test gate run, two boots measured, production restored
  on `spark-ds41f:1107`, hold removed. Receipts under `receipts/`.

## Out of scope

In-kernel `prefetch_l2` emission (`ITEM3-prefetch-design.md`), host-mapped
buffer annotations (`fd530580`), TileKernels v2.1.0, and the big decode levers
(persistent `FC1 -> SwiGLU -> FC2`, direct producer writes, 128-row vocab head).

## Deployed to the site (2026-11-20)

Owner-directed site deployment, not a repository promotion:

- All four spark-eb1a nodes run `spark-ds41f:1107-tilelang-b1367`; the engine
  shape is unchanged (`tp4-switched`, 716,800-token requests, TP4, 10.5 GiB KV).
- Node checkouts are clean and detached at `a5288eb4` (`site/spark-eb1a`, fork).
- Container `tilelang.__version__` is `0.1.15+snapshot.e808dbdd…`, the kernel
  cache namespace is present and warm, `GET /v1/models` returns 200, and
  `doctor --live` reports only the site's pre-existing `nvidia-drm fbdev=N`
  deviation (no image-label mismatch).
- Boot: API ready at **+120.1 s** with the namespace already populated.
- `config/cluster.json`, `upstreams.lock.json` and `manifests/` still name
  `spark-ds41f-1107`; promotion (config, documentation and a new immutable
  baseline in one commit) and qualification on the other shapes remain the
  owner's call.

Rollback: start `experiments/2026-11-12-site-spark-eb1a/profile.json`, which
names `spark-ds41f:1107` and whose cache namespace is intact — a warm boot of
about two minutes.

## Same-day verification of the deployed candidate (2026-11-20)

The deployed candidate was measured once more on the live service (C3) and the
previous release was booted for a same-day control. The control bench **aborted**:
`code-c8: other traffic overlapped 4 attempts` — the API server logged 122
`POST /v1/` requests in 15 minutes from `192.168.2.10` and `192.168.2.18` while the
cluster was in its control boot. Two consequences: the same-day control has no
decode data (`receipts/serving/bench-p1-aborted/` keeps the aborted run), and
production cannot be benchmarked while external clients use it. The rule that a
released build is not re-measured also applies, so the recorded `1107` reference is
the comparison surface.

| point | reference | C1 (boot 1) | C2 (boot 2) | C3 (live) | Δ C1 | Δ C2 | Δ C3 | candidate spread |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| code-c1 | 29.78 | 30.12 | 30.18 | 30.99 | +1.2% | +1.3% | +4.1% | 2.9% |
| code-c16 | 58.63 | 61.02 | 57.15 | 65.41 | +4.1% | -2.5% | +11.6% | 14.5% |
| code-c2 | 37.73 | 34.59 | 37.59 | 35.10 | -8.3% | -0.4% | -7.0% | 8.7% |
| code-c4 | 39.95 | 37.63 | 37.98 | 41.50 | -5.8% | -4.9% | +3.9% | 10.3% |
| code-c8 | 42.18 | 43.03 | 48.57 | 43.64 | +2.0% | +15.1% | +3.4% | 12.9% |
| prose-c1 | 27.48 | 27.47 | 27.38 | 27.38 | -0.0% | -0.4% | -0.4% | 0.4% |
| prose-c16 | 51.42 | 54.47 | 49.77 | 48.95 | +5.9% | -3.2% | -4.8% | 11.3% |
| prose-c2 | 31.07 | 28.62 | 28.30 | 28.62 | -7.9% | -8.9% | -7.9% | 1.1% |
| prose-c4 | 37.76 | 31.03 | 31.66 | 30.83 | -17.8% | -16.2% | -18.4% | 2.7% |
| prose-c8 | 38.33 | 36.25 | 41.95 | 36.21 | -5.4% | +9.4% | -5.5% | 15.9% |

Verdict, on the repo's rule (a point must agree across repeats **and** exceed the
combined 95% interval):

- **No point passes.** Nothing is outside the reference's own interval on all three
  candidate samples; the reference's concurrency-point intervals are wide
  (`prose-c2` ±16.7% = ±5.19 ms, `prose-c4` ±13.4% = ±4.89 ms), and the candidate's
  own intervals are 1-14%.
- The only repeatable *direction* is `prose-c2` (−7.9/−8.9/−7.9%) and `prose-c4`
  (−17.8/−16.2/−18.4%), with candidate spreads of 1.1% and 2.7% — far tighter than
  the 8-16% spread of the other concurrency points. That makes them plausible
  step-time wins (+8% and +16% tok/s at those points) that this reference cannot
  prove; a proof needs a same-day control on a quiesced service.
- Everything else is noise: `prose-c8`, `prose-c16`, `code-c16` change sign between
  samples, and `code-c8` ranges over 12.9%.
- Quality 5/5 on all three samples; acceptance (`accepted/verified`,
  `tokens/step`) is unchanged, so any step-time gain is not traded for shallower
  speculation.

Operational finding: the site serves real external traffic, so (a) live benchmarking
must not run while clients are connected — the tool aborts rather than report mixed
numbers — and (b) the deployment itself replaces the service for ~2-3 minutes; both
need the owner's coordination with the clients' users.
