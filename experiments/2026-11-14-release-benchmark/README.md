# Release benchmark for the 1107-upstream-primitives candidate (2026-11-14)

The candidate carries two upstream primitives onto the 1107 tree — the
NaN-propagating symmetric clamp (tilelang `0014`) and the L1/L2 prefetch API
(`0015`) — plus the TileKernels clamp patch. It was screened on the legacy
`bin/spark bench` comparison (`experiments/2026-11-13-upstream-primitives`, two
boots, quality 5/5, every point `same`) and retained without promotion.

This run is the authoritative instrument instead: the servebench `release`,
`single-stream` and `sampled` suites, two boots of the candidate, against the
recorded reference `manifests/suites/2026-11-07-spark-ds41f-1107-tp4-switched`
(`docs/release-benchmark.md`, "3. Release comparison", the by-hand sequence —
the lab testbeds this section names are not this site).

- Candidate arm: `experiments/2026-11-13-upstream-primitives/tp4-switched.json`
- Site: spark-eb1a four-node switched ring, shape `tp4-switched`
- Boots: `<candidate>` then `<candidate>-again`, the second scored on the first's
  `model.json.gz`
- Suites per boot: `release`, `single-stream`, `sampled`
- Run name: `candidate1107-upstream-primitives-release`

## Gotchas hit on this site (2026-11-14)

- **The `release` suite needs dev mode.** It refuses a production arm:
  "suite release times the engine grid, which needs the dev-mode collective RPC
  (VLLM_SERVER_DEV_MODE=1); production does not expose it, so run the suite on a
  development arm". `tp4-switched-dev.json` (this experiment's companion) extends
  the candidate arm and sets it; the reference suites were recorded on dev arms
  too.
- **Never probe `/collective_rpc` with a method the worker does not implement.**
  A single `POST /collective_rpc {"method": "get_world_size"}` raises inside the
  worker, the EngineCore treats it as fatal and exits, and every later request
  gets `EngineDeadError`; the suite then reports every step as failed with 0.0 s.
  It cost one boot to find out. (Worse, the first "failed" suite run was this,
  not a candidate problem.)
- **The site's pre-existing doctor items need the bench flags**: `--allow-mismatch`
  (the `nvidia-drm fbdev=N` ERROR on all four nodes) and `--cool-below 0`
  (no fan-floor control, so the 600 s cooling precondition cannot reach 55 °C).
- `fan curve: … not installed` and the `cpupower` WARNs are the same site
  deviations; they do not block the run.

## Commands used

```
./bin/spark --cluster-config experiments/2026-11-13-upstream-primitives/tp4-switched-dev.json \
  bench --suite release --compare none --allow-mismatch --cool-below 0 \
  --label candidate1107-upstream-primitives --output results/private/suites/candidate1107-upstream-primitives-release/candidate1107-upstream-primitives
# then single-stream and sampled into -single-stream / -sampled companions
# boot 2 repeats with --corpus <boot-1>/model.json.gz and label ...-again
```
