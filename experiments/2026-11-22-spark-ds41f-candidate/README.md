# Release candidate: fold the A3 site stack into the recipe

Status: **assembled; qualification and the promotion commit are the owner's
call**. Nothing here touches `config/cluster.json`, `upstreams.lock.json`,
`patches/` or `manifests/`.

## What the candidate is

The adopted spark-eb1a stack (`spark-ds41f:a3-no-b12x-r5`, qualified on
`tp4-switched` in `experiments/2026-11-21-a3-retire-b12x`) expressed as a
recipe-shaped lock the promoted `bin/spark build` can reproduce:

| component | pin | series |
| --- | --- | --- |
| vLLM | LIL `6d66eed3` + 648 active patches (641 production + reworked 0700-0706; 0707/0708 TODO-) | `vllm/series` (references the existing per-experiment patch files) |
| TileLang | `ac88f5bc`, wheel `0.1.15+snapshot.32a1488d`, `0012` re-keyed | `tilelang/series` (13 patches, byte copies of the A2 refresh) |
| TileKernels | `2.0.0` + one patch | `patches/tile_kernels/series` (unchanged) |
| sparknet | `1fd6a1fb` (0.5.0) | none |
| CUTLASS / CuTe DSL | `v4.8.1` / 4.8.1 | wheels |
| **NCCL** | **`2.30.7-1` + the four local patches** (`patches/nccl/series`) — the switchless shapes keep their patches; the switched site keeps running stock 2.32.6-1 separately | `patches/nccl/series` |
| **B12X** | **absent from the lock** (docs/upstreams.md, "Locks without B12X") | — |

The source manifest seeds from the A3 build; `build prepare --lock` on a node
records the recipe tree identities (the vLLM tree will be `51554e28` plus the
NCCL 2.30.7 delta — NCCL is rebuilt separately, so the vLLM tree is unchanged
from the site's A3).

## Qualification matrix (before any promotion commit)

| shape | arm | reference | suites |
| --- | --- | --- | --- |
| `tp4-ring` | [arm-tp4-ring.json](arm-tp4-ring.json) | `manifests/suites/2026-11-07-spark-ds41f-1107-tp4` | release, single-stream, sampled (docs/release-benchmark.md) |
| `tp3-triangle` | [arm-tp3-triangle.json](arm-tp3-triangle.json) | `manifests/suites/2026-11-07-spark-ds41f-1107-tp3` | release, single-stream, sampled |
| `tp4-switched` | already qualified 2026-11-21 | `experiments/2026-11-21-a3-retire-b12x` | two boots, gate + prefill |

Gate: quality 5/5, model behaviour (greedy identity, teacher-forced KL)
within the 1107-vs-1030 precedent, decode grid and c16/c8 within intervals,
prefill within intervals. Release tests: the 150-file manifest (the retire
series' own tests are in 0706's scope; B12X's preparation tests skip without
it).

## The promotion commit (one commit, owner-accepted)

1. `upstreams.lock.json` ← this candidate's lock, with `patch_series` paths
   moved to `patches/vllm/series` and `patches/tilelang/series` (the patch
   files move from their experiment dirs into `patches/`, per the repo layout).
2. `config/cluster.json`: `container.image` → the promoted tag;
   `expected_labels` drop `b12x.tree`, take the recorded trees;
   `upstreams_config` stays default; `models` unchanged.
3. `docs/current-state.md` and `docs/upstreams.md`: production moves past
   spark-ds41f-1107; the "Locks without B12X" section collapses to "done".
4. `manifests/baselines/<new>.json` + the shape `benchmark_reference` entries:
   the immutable evidence of the qualification runs.
5. `experiments/2026-11-21-site-state` then reduces to pointing at the
   promoted release (the site may keep running its arm until the owner
   restarts it from the recipe).

## Known deltas the qualification must watch

- **NCCL on the switchless shapes stays at 2.30.7** while the switched site
  runs 2.32.6 — the shapes diverge until `0003`/`0004` are re-expressed in
  2.32's `src/tuning/` (`experiments/2026-11-20-nccl-2.32`).
- The retire series renamed the V4.1 cache layout and attention ops
  (`DeepseekV41B12x*` → `DeepseekV41*`); anything outside the series that
  spelled the old names (external tooling, dashboards) needs the rename —
  the release tests cover the in-tree consumers.
- TileLang's kernel-cache namespace moves to `32a1488d` on every rank: first
  boots are cold (~880 s) and need fresh per-rank cache directories.
