# spark-eb1a: current deployed state (2026-11-22)

The single record of what production runs, how to restart it, and how to roll it
back. Since the spark-ds41f-1122 promotion (2026-11-22) this is exactly the
promoted release: the site profile
(`experiments/2026-11-12-site-spark-eb1a/profile.json`) and the recipe
(`config/cluster.json`) name the same image, environment and trees, so a
restart from either reproduces production.

## Running

| | |
|---|---|
| Image | `spark-ds41f:a3-no-b12x-r5`, `sha256:e9a657c09426` |
| Promotion | `manifests/baselines/2026-11-22-spark-ds41f-1122.json` (shape `tp4-switched`) |
| Arm | the site profile itself; `experiments/2026-11-21-a3-retire-b12x/arm-tp4-switched.json` reproduces it |
| Lock | `upstreams.lock.json` (promoted; equals `experiments/2026-11-21-a3-retire-b12x/upstreams.lock.json`) |
| Source trees | vllm `51554e28` (650 patches, head `3d16a70c`), tilelang `c3b54074`, nccl `331c032a` (**stock, zero patches**), tile_kernels `cb2fa41c`, sparknet `8cc28a5c`, **b12x absent** |
| Compiler | `tilelang 0.1.15+snapshot.32a1488d…`; cache namespace `…_32a1488d…` |
| NCCL | 2.32.6-1 **stock**, `NCCL_BUFFSIZE=2 MiB` (recipe-promoted 2026-11-21), `NCCL_MAX_NCHANNELS=8`, `NCCL_PROTO=^LL128` |
| Fabric | lossless since 2026-11-20: hosts mark (`NCCL_IB_TC=106`, renderer-owned) with `spark-ds41f-dcb.service` (dscp-prio 26:3, PFC 3:on) and the CRS812 QoS block; retrans/oos flat under load |
| Shape | `tp4-switched`: 716,800-token requests, TP4, 10.5 GiB KV, 16 sequences |
| Boot | warm ~120 s; cold (empty cache namespace) ~880 s |

## Restart (needs a clean local repo and node HEAD equal to local HEAD)

```sh
bin/spark --cluster-config experiments/2026-11-12-site-spark-eb1a/profile.json cluster start --replace --apply
```

Nodes besides the head need the commit they check out; `cluster sync` moves them
to `origin/main`, while deployments of fork-only commits fetch the fork URL and
detach. Clean `spark-ds41f-pre-*` containers before a restart: repeated
`--replace` cycles otherwise fail with `could not preserve spark-ds41f`.

## Rollback images (all on every node)

| Tag | Digest | Role |
|---|---|---|
| `spark-ds41f:1107` | `sha256:db909cb37e6a` | promoted release |
| `spark-ds41f:1107-tilelang-b1367` | `sha256:80030ea12699` | compiler pin `b1367a59` |
| `spark-ds41f:1107-vllm-6d66-cutlass-4.8.1` | `sha256:ef08fbb2712e` | + vLLM `6d66eed3`, CuTe DSL/CUTLASS 4.8.1 |
| `spark-ds41f:1107-nccl-2.32.6` | `sha256:b40b45b94275` | + NCCL 2.32.6 (one ported patch) |
| `spark-ds41f:1107-nccl-2.32.6-stock` | `sha256:7cf124381112` | + NCCL 2.32.6 stock (A1; immediate rollback) |

Each has its kernel namespace on disk; a rollback is a `cluster start` with that
arm or with an earlier site profile copy.

## Known deviations and caveats

- `doctor --live` reports `nvidia-drm fbdev=N` on all four nodes: pre-existing
  site deviation, identical for `1107` and every candidate; benches pass
  `--allow-mismatch` for it only.
- The earlier "`code-c8` 9-16% slower than the record in every candidate" note
  is superseded: the 2026-11-21 same-session A/B (`experiments/2026-11-21-ab-1107-vs-nccl`)
  measured the deployed stack identical to plain `spark-ds41f:1107`; that lean
  was a fleet/session offset, not a regression.
- This is a **site deployment**, not a repository promotion. `config/cluster.json`,
  the promoted `upstreams.lock.json` and `manifests/` still name
  `spark-ds41f-1107` (only `tp4-switched`'s `NCCL_BUFFSIZE` moved, owner
  2026-11-21), and no release baseline exists for this stack until A3.
- The switchless NCCL patches are not in this image and are not needed here; the
  switched fabric sets no `NCCL_SWITCHLESS_BIDIRECTIONAL`. The recipe keeps
  `2.30.7-1`+4 patches for ring/triangle until `0003`/`0004` are re-expressed
  for 2.32.
- Thermal: spark-141e rides 3-5 °C from its slowdown limit under heavy load;
  sequence benches as decode gate -> >=8 min idle -> prefill, or the run halts.
  Local prefill references: 8,716 / 7,040 tok/s at 131K / 524K.

## Soak (next 24-48 h)

Watch `MemAvailable` floor on the head (never below the 3 GiB guard), GPU
temperature/power maxima, NCCL warnings, TileLang cache growth under
`~/nvmodels/spark-ds41f/cache/spark-ds41f/jit/tilelang/…_32a1488d…`, request
latency/error rate, and — since the lossless fabric — that
`roce_adp_retrans`/`out_of_sequence` stay flat under load (any climb means the
dcb unit, the switch QoS block or a port config regressed; diagnose with the
`spark-eb1a-roce-lossless-check` skill). Record any restart or memguard trip in
this file.
