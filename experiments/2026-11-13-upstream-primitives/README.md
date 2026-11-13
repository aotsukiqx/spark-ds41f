# Upstream primitives: native clamp and in-kernel L2 prefetch

Three screened opportunities from the 2026-11-13 upstream watch
(`skill://spark-ds41f-upstream-watch`), driven as one compiler-refresh candidate
because they share one prerequisite: a TileLang that carries two upstream
commits our pin `2123e412` predates.

## Hypothesis

1. **Native NaN clamp.** TileLang `824c5c42` adds `tl.clamp_symmetric`
   (`min.NaN.xorsign.abs`, FP32/FP16/BF16, SM86+, vectorizable). Our
   `patches/tile_kernels/0001` implements the same `torch.clamp` semantics with
   three `T.Select` per value. Replacing the Selects with the intrinsic is one
   instruction per value in the routed experts' SwiGLU epilogue
   (`moe_swiglu_cast`, 23-30 us/layer, ~3% of a decode step); the clamp is a
   subset of that, so the ceiling is small but the change is free once the
   compiler carries the commit. It also converts a local correctness patch into
   a call on an upstream primitive.
2. **In-kernel L2 prefetch.** TileLang `35850c06` adds
   `prefetch_l1/prefetchu_l1/prefetch_l2` with an optional eviction policy. Our
   decode prefetch (`0044`/`0119`) already issues
   `cp.async.bulk.prefetch.L2` with `createpolicy.fractional.L2::evict_last`
   from a separate CuTe DSL path; the possible gain is structural (emit the
   prefetch from inside the TileLang projection kernels, dropping the separate
   path and its host-side schedule), not a policy change.
3. **TileKernels 2.1.0.** Upstream rewrote the clamp-count reduction in the
   same function our NaN patch touches: int64-safe counts via two int32 halves
   and a four-warp group reduction, using `T.alloc_var(T.int64)`. That needs a
   newer TileLang than our pin, so the pin moves together with TileKernels. At
   our sizes (16,384 tokens x 2,304 hidden ≈ 3.8e7) the int32 counts do not
   overflow: this is correctness hardening, not a performance claim.

## The one variable

The compiler and kernel-source refresh: TileLang gains backports of the two
upstream commits as patches `0014`/`0015` on the pinned tree, TileKernels'
clamp patch calls the intrinsic when present (Select fallback kept so the
series still applies against a tree without it). No scheduler, serving-option
or recipe change.

## Acceptance criteria

- Correctness: the clamp patch is bit-identical to `patches/tile_kernels/0001`
  on finite inputs and keeps NaN propagation (the existing test in that patch's
  series, plus a finite-vector `torch.equal` against the Select form).
- Kernel-level screen: a TileLang microbench of the SwiGLU epilogue shape
  (live tiles, `swiglu_limit` 10) with both clamp forms; report us/iteration.
  Acceptance for the serving claim needs the paired suites on two boots against
  `spark-ds41f-1107`'s recorded reference — that is a window, not this folder.
- Prefetch prototype: one projection kernel emits `prefetch_l2` for its own B
  tiles; screen decode step time before promoting the idea beyond a prototype.

## Risks

- `c99577fd` (TF32 round-to-nearest-even) is **not** backported: our mHC
  FP32 -> 3x exact-TF32 split assumes the current rounding. If the pin moves to
  a revision that includes it, the determinism and quality gates must be re-run
  before anything else is judged.
- TileKernels 2.1.0 requires `num_threads >= 4 * warp_size` at the call site;
  the launch geometry comes from the vLLM integration branch, so it is checked
  in the prepared tree before any image is built.

## What this folder is not

Not a promotion request. The lock is untouched; production stays
`spark-ds41f-1107`. Serving A/B needs a lab window and the owner's call.
