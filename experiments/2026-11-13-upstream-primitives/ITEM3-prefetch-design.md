# Item 3 — in-kernel L2 prefetch: design and screen plan

## Current mechanism (what runs today)

`vllm/models/deepseek_v4_1/l2_prefetch.py` builds per-layer weight segments
(`0044` adds the `tilelang_weight_sf` scale words) and a separate CuTe DSL
kernel issues `cp.async.bulk.prefetch.L2` with
`createpolicy.fractional.L2::evict_last` on a schedule ahead of the decode
kernels (`0119`, `VLLM_L2_PREFETCH_KERNELS=tilelang`).

## What the backport adds

`0015-prefetch-l1-l2-backport.patch` (tile-ai/tilelang `35850c06`) exposes:

- `T.prefetch_l1(addr, is_global)`, `T.prefetchu_l1(addr)`
- `T.prefetch_l2(...)` with an optional eviction-policy argument

as TileLang intrinsics, so a kernel can prefetch its own (or its sibling
projection's) B tiles from inside the kernel instead of a host-scheduled
separate path.

## Why the expected gain is structural, not policy

Our policy is already `evict_last`; a policy change is not on the table. The
candidate mechanism is: emit `T.prefetch_l2` for the *next* K-tiles of B in
the same kernel that consumes them (or for the paired projection's weights in
the WO-A/WO-B pair), removing the separate prefetch stream and its
host-side per-step schedule. Whether that wins depends on overlap, which is
exactly what the screen must measure — the README makes no claim.

## Screen (what has to be measured, in order)

1. **Smoke** (`prefetch_smoke.py`): the intrinsics compile and run on SM121
   with the backported wheel. Gate for everything below.
2. **Kernel-level**: extend `bench_clamp.py`'s harness with one projection
   kernel (WO-B, `5120 x 2048`, block-32 MXFP8) in two forms — B tiles
   prefetched by the existing separate path vs `T.prefetch_l2` emitted in the
   kernel's TMA pipeline — same inputs, CUDA-event timing.
3. **Serving**: only if (2) shows a step-relevant saving: a candidate image
   with the in-kernel emission replacing the host-side schedule for that one
   projection, judged by the paired servebench suites on two boots against
   `spark-ds41f-1107`'s recorded reference. That is a lab window, not this
   folder.

## Anchors to check at apply time

- The prefetch intrinsics live in `tilelang/cuda/language/prefetch.py` after
  the backport; the eviction-policy argument shape must be read from that
  file before writing the kernel-side call (not assumed from the commit
  subject).
- Our decode kernels are emitted from `patches/vllm/0029-*`; the WO-B GEMM
  and the routed-expert FC2 are the two places with a B-operand the kernel
  itself could prefetch.
- PDL ordering: `0520-0525` chains decode kernels with programmatic dependent
  launch; a prefetch issued in-kernel must not be reordered behind the
  consumer's own loads by PDL — check the generated PTX once, by hand.
