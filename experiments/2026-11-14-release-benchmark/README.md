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

## The repository's records are other fleets (found 2026-11-14)

The tp4-switched suite record `manifests/suites/2026-11-07-spark-ds41f-1107-tp4-switched`
was captured on **sp1-sp4**, and the legacy comparison record
`manifests/benchmarks/2026-11-07-spark-ds41f-1107-switched.json` on **dgx1-dgx4**
(`metadata.identity.nodes`). This site is spark-eb1a/141e/a89f/2fe7 and has no
recorded suite of its own.

Comparing across fleets produces a uniform offset, not a verdict: the first table
(candidate vs the sp1-sp4 record) read −6% to −12% on *every* prefill size,
−4.75% at c16 and `same` at c8, while the same run's grid was *faster* at its two
small points. A two-intrinsic patch cannot do that; a different four-node set can.

So this window adds the site's own reference: boot 2 used the plain `1107` image
on the same site and arm settings (`1107-dev.json`), and the comparison to make
is candidate vs that same-site run, with the candidate's two boots as its repeat.
The cross-fleet table is kept only as evidence of why it cannot be used.

## The site's reference is now recorded

`reference-1107-site/` holds the plain
`1107` run this window measured on spark-eb1a (suite, grid, c16, c8, poisson,
prefill, stalls, conditions; 248 KB, no model corpus, so its model step stays
"not kept" exactly like the sp1-sp4 record). Future candidates on this site
compare against it with the same table command, which makes the comparison
same-fleet by construction:

```
python3 scripts/servebench_suite_table.py <run> \
  results/private/suites/site1107-release/site1107 \
  <candidate> <candidate>-again
```

It stays under `experiments/` rather than `manifests/suites/`: the site generator
treats everything in `manifests/suites/` as a promoted release's evidence and
rendered this run into `docs/index.html` with an empty date, which the release
tests then rejected. The run itself is unchanged on the node under
`results/private/suites/site1107-release{,-single-stream,-sampled}/`.
