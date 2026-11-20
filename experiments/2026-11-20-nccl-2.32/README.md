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

## Measured and deployed (2026-11-20)

Image `spark-ds41f:1107-nccl-2.32.6` (`sha256:b40b45b9…`), smoke passed; the
installed `libnccl.so.2` reports **23206** and its sha256 equals the built
library, `strings` shows the `SWITCHLESS_BIDIRECTIONAL` parameter compiled in,
and vLLM logs `vLLM is using nccl==2.32.6`.

**Release tests** (same 150-file manifest, four shards): **9734 passed, 311
skipped, 0 failed** (897/704/410/805 s). **Boots**: API ready at +119.6 s and
+123.1 s; quality 5/5 on both. Step times, ms:

| point | reference | group A boot 1 | A boot 2 | NCCL boot 1 | NCCL boot 2 | NCCL vs A |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| prose-c1 | 27.48 | 27.61 | 27.39 | 27.51 | 27.70 | +0.4% |
| prose-c2 | 31.07 | 28.29 | 34.12 | 31.85 | 28.64 | −3.1% |
| prose-c4 | 37.76 | 30.45 | 34.80 | 37.14 | 31.21 | +4.7% |
| prose-c8 | 38.33 | 41.38 | 38.54 | 38.42 | 38.76 | −3.4% |
| prose-c16 | 51.42 | 54.08 | 47.06 | 47.44 | 55.00 | +1.3% |
| code-c1 | 29.78 | 30.46 | 30.44 | 30.39 | 30.32 | −0.3% |
| code-c2 | 37.73 | 34.12 | 32.49 | 36.40 | 34.73 | +6.8% |
| code-c4 | 39.95 | 40.34 | 40.44 | 44.28 | 40.47 | +4.9% |
| code-c8 | 42.18 | 46.12 | 47.94 | 47.63 | 50.00 | +3.8% |
| code-c16 | 58.63 | 64.70 | 61.85 | 61.64 | 62.73 | −1.7% |

No point regresses consistently beyond the combined intervals: the largest
consistent gap is `code-c2` at +6.8% against this site's 12–20% concurrency
intervals, and `code-c8` is slow against the 11-07 reference in **every**
candidate of the session (group A +9.3%/+13.7%, NCCL +12.9%/+15.7%), so it is
session/environment drift rather than NCCL. `prose-c4`'s direction remains
inconsistent across boots of every candidate.

**Verdict:** keep NCCL 2.32.6-1 deployed at this site. The switchless patches are
not part of this pin (see above), so this is a switched-fabric deployment only;
promotion for `tp4-ring`/`tp3-triangle` needs `0003`/`0004` re-expressed in the
2.32 tuning code first.

## Environment sweep on the deployed stack (2026-11-20)

Because 2.32 rewrote the p2p channel/LL planning and moved tuning into
`src/tuning/`, the environment chosen for 2.30 may not be optimal. Five
one-variable arms (`sweep/`), each one boot plus the default quality+decode gate,
against the deployed arm's two boots as control. Receipts in
`receipts/sweep/<arm>/`; `NCCL_DEBUG=INFO` was on for the first pass so the
tuner's choice is recorded (`ch16` created Channels 00-15 across both rails).

| arm | variable | outcome |
| --- | --- | --- |
| `qps2` | `NCCL_IB_QPS_PER_CONNECTION=2` | mixed, largest gaps −6.5% (`prose-c8`) and +6.9% (`prose-c16`); no direction |
| `ch16` | `NCCL_MAX_NCHANNELS=16` | first sample −14.0% `code-c4`, −7.5% `code-c8`; **did not reproduce** |
| `ar1` | `NCCL_IB_ADAPTIVE_ROUTING=1` | mixed; −5% on code points but +14.7% `prose-c8`, +12.8% `prose-c16` |
| `proto` | `NCCL_PROTO=LL,LL128,Simple` | **invalid**: only the quality suite completed (see incidents); the site disables LL128 by design |
| `buf2m` | `NCCL_BUFFSIZE=2 MiB` | not run (sweep aborted) |

`ch16` was chased with two more boots with `DEBUG=INFO` (`ch16-r1/r2`) and then
two boots of a debug-free arm that changes only the channel count
(`ch16c-r1/r2`). Quality 5/5 everywhere. Against control (`ctl N1/N2`):

| point | ctl | r1 | r2 | clean 1 | clean 2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| prose-c2 | 31.85 / 28.64 | 28.71 | 28.82 | 28.21 | 28.38 |
| code-c2 | 36.40 / 34.73 | 33.36 | 33.63 | 32.75 | 37.60 |
| code-c8 | 47.63 / 50.00 | 43.37 | 48.71 | 44.88 | 50.85 |
| code-c4 | 44.28 / 40.47 | 40.14 | 40.59 | 44.64 | 41.31 |
| code-c16 | 61.64 / 62.73 | 53.65 | 61.54 | 63.87 | 63.07 |
| prose-c8 | 38.42 / 38.76 | 35.65 | 39.29 | 38.78 | 40.87 |

Only `prose-c2` is below both control boots in all four ch16 samples
(28.2-28.8 against 28.64-31.85), and the control's own spread there is 11%, so
the apparent −6% is inside it. `code-c16` (+2.0%) and `prose-c8` (+3.2%) are
consistently slightly slower in the clean pair. **No robust gain: the deployed
`NCCL_MAX_NCHANNELS=8` stays.**

## Incidents during the sweep

1. **A client-side network drop aborted the sweep.** The script used `set -e`
   with `bench | tail`, so `tail`'s status hid the failed benchmark, the loop
   stopped after `proto`, and the automatic restore never ran: the `proto`
   environment (LL128 allowed) served for about ten minutes with no traffic
   (API 200, no restarts, no NCCL errors). Restored manually afterwards.
2. **Preserved-container collisions.** Repeated `--replace` cycles leave
   `spark-ds41f-pre-<epoch>` containers; after enough switches a later start
   failed with `could not preserve spark-ds41f` on all four nodes, rolled back,
   and left a 16-channel environment live for ~9 minutes. Fixed with
   `cluster stop --apply`, `docker rm` of every `spark-ds41f-pre-*`, and an
   explicit start of the deployed arm.

Both incidents changed *which environment served*, not the integrity of any
completed benchmark: every receipt in `receipts/sweep/` carries its full suites,
`finished_utc` and thermal block, and the ones taken before the drop (qps2,
ch16, ar1) are unaffected. `proto`'s incomplete receipt is kept as evidence.

Rules for the next sweep: trap the restore, never pipe a benchmark through
`tail` when its exit status matters, verify `NCCL_MAX_NCHANNELS`/`NCCL_DEBUG`
and `GET /v1/models` after every start, prune `spark-ds41f-pre-*` before each
round, and never let two sweep jobs touch the cluster at once.
