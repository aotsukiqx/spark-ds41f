# NCCL 2.32 re-expression of the switchless patches (`0003`/`0004`)

Status: **compile-verified draft, runtime-unqualified**. The two patches the
switchless shapes (ring/triangle) still need on 2.32, re-expressed where 2.32
moved the code. Nothing is booted or measured; the switched site needs none of
this (it runs stock 2.32.6-1 — every patch there is upstream-owned or
switchless-gated).

## What moved in 2.32 and where the intent lands now

| 2.30 patch | 2.30 location | 2.32 re-expression |
| --- | --- | --- |
| `0003` `NCCL_MIN_TRAFFIC_PER_CHANNEL` env + validation | `src/enqueue.cc` `scheduleCollTasksToPlan` (constexpr `MinTrafficPerChannel` inline) | the constant became `static constexpr ncclMinTrafficPerChannel` in `src/include/channel.h`, consumed by **three** sites (`src/channel.cc` cell sizing, `src/enqueue/enqueue.cc` planner traffic floor, `src/tuning/tuning_general.cc` model traffic). The re-expression turns it into an `NCCL_PARAM`-backed function-local static (reads env on first use — safe against link-order static init), validates at the planner entry, and all three sites keep calling the same name |
| `0004` balanced tiny-ring threads (`balanceSwitchlessThreads`: shrink `nt` to 128 before dropping channels, bidirectional mode 2 only) | `src/enqueue.cc` `// Ring/Tree channel tuning` loop | the loop moved to `src/tuning/tuning_general.cc` `ncclTuningGetChannels`'s `Ring/Tree/one-RPN PAT` branch; the helper sits directly above that function, takes `ncclTuningInput_t*`, guards on `comm->nChannels >= 4`, Ring+Simple thresholds and `ncclFuncAllReduce`, then halves `nt` before the upstream channel-drop loop runs |

Patch: [nccl/0001-min-traffic-param-and-balanced-tiny-ring-threads.patch](nccl/0001-min-traffic-param-and-balanced-tiny-ring-threads.patch)
— `git format-patch` from `.work/upstreams/nccl-dry` branch `nccl-2.32-switchless`
(base `ad2d192` = `v2.32.6-1`), applies clean, `git diff --check` clean.

## Compile verification (2026-11-21, spark-eb1a head, no serving impact)

CPU-only standalone build in the `a3-no-b12x-r5` image toolchain, tree cloned
fresh at `v2.32.6-1`, `git am` of `0002` then this patch:

    docker run --rm --entrypoint /bin/bash -v /tmp/nccl-verify:/src:Z -w /src \
      spark-ds41f:a3-no-b12x-r5 -c \
      'make -j8 NVCC_GENCODE="-gencode arch=compute_121,code=sm_121"'

Result: **exit 0, zero errors, `build/lib/libnccl.so.2.32.6` (74 MB debug)**
with the `SWITCHLESS_BIDIRECTIONAL` / `MIN_TRAFFIC_PER_CHANNEL` env strings
embedded. The build caught three real draft defects, all now folded into the
patch above:

1. `ncclParamMinTrafficPerChannel` undeclared in `channel.cc` and the three
   2.32 call sites still used the old constexpr *value* syntax — now declared
   + called as a function everywhere.
2. The tiny-ring helper was placed above the definition point of its input
   type — moved directly above `ncclTuningGetChannels` and retyped to
   `ncclTuningInput_t` (the header struct has `func`, not `op`).
3. `NCCL_FUNC_ALL_REDUCE` does not exist in 2.32 — the enum is
   `ncclFuncAllReduce`.

## What is deliberately NOT re-expressed

- `0003`'s `graph/connect.cc` hunk (mode-2 channel reversal in each four-channel
  group) is **already carried** by the ported `0002-bidirectional-switchless-rings`
  (`balanceSwitchlessRings` in `src/graph/connect.cc` reverses the second half
  of the channels after duplication) — verified by patch inspection, and the
  stacked build above compiles both without conflict.
- The 2.30 TUNING log of per-kind element counts: 2.32's planner prints its own
  partition summary; re-adding ours is optional noise — dropped.

## Qualification required before this replaces 2.30.7 on the switchless shapes

1. Four-node ring and three-node triangle: two boots each on an image built with
   `0002` + this patch, quality 5/5, decode grid + c16/c8 within the 11-07
   intervals, and the latency screens that selected the 2.30 patches originally
   (the `MIN_TRAFFIC_PER_CHANNEL=512` arm and the tiny-ring balance on 128-byte
   ranks).
2. Only then may `config/cluster.json`/the recipe lock move both shapes to one
   NCCL line; until then the recipe keeps `2.30.7-1` + `patches/nccl` (four
   patches) and the site runs stock 2.32.6-1.

## Known risks

- The lazy-static `ncclMinTrafficPerChannel()` changes an ODR-used constexpr
  into a call — three call sites are hot-path planning, not per-kernel; the
  static resolves once. First-use ordering: the planner validation block runs
  before any layout computation, so an invalid env fails closed with
  `ncclInvalidUsage` at plan time.
- 2.32's `ncclClampChannels`/per-call `minCTAs`/`maxCTAs` interact with the
  same loop; the tiny-ring helper only shrinks `nt`, never touches `nc`, so it
  composes with those clamps.
- The standalone build proves compilation for SM121 and env-string linkage,
  **not** runtime behavior: `SWITCHLESS_BIDIRECTIONAL` refuses to engage on
  this site (4 nodes but switch-connected; the patch demands rank/cable order),
  and no allreduce path here exercises the tiny-ring helper.
