# spark-eb1a: current deployed state (2026-11-21)

The single record of what production runs, how to restart it, and how to roll it
back. The site profile (`experiments/2026-11-12-site-spark-eb1a/profile.json`)
now names this stack, so a restart from the profile reproduces it instead of
reverting to `spark-ds41f-1107`.

## Running

| | |
|---|---|
| Image | `spark-ds41f:1107-nccl-2.32.6`, `sha256:b40b45b94275` |
| Arm | `experiments/2026-11-20-nccl-2.32/arm-tp4-switched.json` (extends the site profile) |
| Lock | `experiments/2026-11-20-nccl-2.32/upstreams.lock.json` |
| Source trees | vllm `e5a1f99d`, tilelang `fa23bcc8`, nccl `fd7f2d68`, tile_kernels `cb2fa41c`, sparknet `8cc28a5c`, b12x `04e0ee95` |
| Compiler | `tilelang 0.1.15+snapshot.e808dbdd…`; cache namespace `…_e808dbdd…` |
| NCCL | 2.32.6 (`ncclGetVersion` 23206), `NCCL_MAX_NCHANNELS=8`, `NCCL_PROTO=^LL128`, `NCCL_DEBUG=WARN` |
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
| `spark-ds41f:1107-nccl-2.32.6` | `sha256:b40b45b94275` | current |

Each has its kernel namespace on disk; a rollback is a `cluster start` with that
arm or with an earlier site profile copy.

## Known deviations and caveats

- `doctor --live` reports `nvidia-drm fbdev=N` on all four nodes: pre-existing
  site deviation, identical for `1107` and every candidate.
- `code-c8` is 9-16% slower than the 11-07 recorded reference in **every**
  candidate of this session (group A and NCCL alike): session/environment drift,
  not a candidate regression.
- This is a **site deployment**, not a repository promotion. `config/cluster.json`,
  the promoted `upstreams.lock.json` and `manifests/` still name
  `spark-ds41f-1107`, and no release baseline exists for this stack.
- The switchless NCCL patches are not in this image; the fork serves only the
  switched fabric, where `NCCL_SWITCHLESS_BIDIRECTIONAL` is unset.

## Soak (next 24-48 h)

Watch `MemAvailable` floor on the head (never below the 3 GiB guard), GPU
temperature/power maxima, NCCL warnings, TileLang cache growth under
`~/nvmodels/spark-ds41f/cache/spark-ds41f/jit/tilelang/…_e808dbdd…`, and
request latency/error rate. Record any restart or memguard trip in this file.
