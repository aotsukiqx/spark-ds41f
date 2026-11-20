# Group B: NCCL `v2.30.7-1` → `v2.32.6-1`

Status: **assembled; build and gates next**. Base commit `c6ab775e` (the deployed
vLLM/CUTLASS group).

## Scope

| | before (deployed) | candidate |
|---|---|---|
| nccl | `v2.30.7-1` (`73cf1122`) | `v2.32.6-1` (`ad2d192c`, 2026-11-09) |
| series | 4 patches | 1 patch (ported) |
| everything else | vLLM `6d66eed3`, CuTe DSL 4.8.1, CUTLASS 4.8.1, TileLang `b1367a59`, TileKernels 2.0.0, sparknet `1fd6a1fb` | unchanged |

The release delta is **1029 commits over two minors** (`v2.31.2-1` 2026-08-11,
`v2.32.3-1`, `v2.32.6-1`), not a narrow fix set: p2p channel/chunk planning was
extracted and reused, the tuner moved into `src/tuning/`, GIN/RMA plugin APIs
bumped (v15/v17 with compatibility layers), GPUNetIO v5.0.0-rc1 landed, and the
crypt/TLS paths changed.

## What happens to our four patches

- **`0001` IB CTS nreqs ordering — dropped, upstream owns it.** 2.32 contains
  `0bb8dec4 net_ib: Order CTS nreqs load after the idx check`, the same change.
- **`0002` bidirectional switchless rings — ported.** It applied onto the new
  `src/graph/connect.cc` with only an offset (the `NCCL_PARAM` block and the
  `ncclBuildRings` call site are still there); the regenerated patch applies
  with `git apply --check` and through `git am`. This is the only patch carried.
- **`0003` balanced channel allocation — dropped.** Two of its three hunks
  targeted `scheduleCollTasksToPlan` in `src/enqueue.cc`; 2.32 rewrote channel
  planning (`b7203029`, `7c635f01`, `41363f47`) and moved the file to
  `src/enqueue/enqueue.cc`. The concept survives but the code does not.
- **`0004` adaptive small-ring threads — dropped.** Its target was the
  `// Ring/Tree channel tuning` loop in `enqueue.cc`, which 2.32 removed; tuning
  now lives in `src/tuning/` cost models. Re-expressing it is a redesign, not a
  rebase.

Both dropped patches only act when `NCCL_SWITCHLESS_BIDIRECTIONAL` is set (modes
1/2 on three- or four-node switchless rings). This site runs the switched
fabric and does not set it (the site profile and `tp4-switched` environment carry
only `NCCL_BUFFSIZE`, `NCCL_CUMEM_ENABLE`, `NCCL_MAX_NCHANNELS`), so the
candidate's behaviour at this site is unaffected by their absence. **This pin
must not be promoted for the switchless shapes** until `0003`/`0004` are
re-expressed in the new tuning code and re-measured.

## Verification plan

1. Build `spark-ds41f:1107-nccl-2.32.6` (NCCL rebuilt for SM121 with the ported
   patch) and smoke it; the image must still report the same vLLM/TileLang trees,
   with `local.spark-ds41f.nccl.tree = fd7f2d68`.
2. Release tests: the vLLM tree is unchanged from the deployed group, so the
   same 150-file gate manifest applies; rerun it in the new image, split across
   the four nodes.
3. Two site boots (quality gate + decode grid) against the recorded `1107`
   reference, and a direct comparison with the deployed group's two boots to
   isolate NCCL.
4. Rollback stays the vLLM/CUTLASS group's image (all namespaces intact) or the
   site profile (`1107`).
