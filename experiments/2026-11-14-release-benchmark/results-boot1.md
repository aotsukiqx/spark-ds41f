# Boot 1 receipts (2026-11-14)

Site: spark-eb1a, shape `tp4-switched`, arm
`experiments/2026-11-13-upstream-primitives/tp4-switched-dev.json`
(candidate image `spark-ds41f:1107-upstream-primitives`).

| Suite | Exit | Step seconds |
| --- | ---: | --- |
| `release` | 1 | model 302, grid 90, c16 369, c8 365, poisson 366, stall-3 130, stall-11 134, stall-15 129, prefill 420 — **2,305 s total** |
| `single-stream` | 0 | — |
| `sampled` | 0 | — |

`release` reported `"failed": []` (no step failed) and every step's own summary
carried `"failed": 0`; there is **no `FAIL:` line and no `report:` line** in the
log. The non-zero exit is therefore not a failed step or a regression verdict;
it is unexplained so far and is recorded here rather than papered over. The
run's `suite.json` is intact, `suite_sha256` matches the recorded reference
(`2c1698722faf…`), and all nine step files (`model`, `grid`, `c16`, `c8`,
`poisson`, `stall-3/11/15`, `prefill`) exist in
`results/private/suites/candidate1107-upstream-primitives-release/candidate1107-upstream-primitives/`.

The run's model step produced `acceptance_length 2.318` on 16 streams with a
stable `outputs_sha256` (`74357295b4bb…`), which boot 2 will be scored against.

Artifacts on spark-eb1a under `~/nvmodels/spark-ds41f/results/private/suites/`:

- `candidate1107-upstream-primitives-release/candidate1107-upstream-primitives/`
- `candidate1107-upstream-primitives-release-single-stream/candidate1107-upstream-primitives/`
- `candidate1107-upstream-primitives-release-sampled/candidate1107-upstream-primitives/`
