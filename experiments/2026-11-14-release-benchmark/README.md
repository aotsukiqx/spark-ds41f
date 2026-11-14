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
