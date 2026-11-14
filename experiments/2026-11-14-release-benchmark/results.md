# Release benchmark result: candidate vs the site's own 1107 (2026-11-14)

Candidate `spark-ds41f:1107-upstream-primitives` (1107 + tilelang `0014`
clamp_symmetric backport + `0015` prefetch API + TileKernels clamp patch), two
boots; reference: plain `spark-ds41f:1107` booted on the same site with the same
dev arm settings, because the repository's records are other fleets.

## Verdicts (candidate → site 1107; repeat = candidate's second boot)

| Metric | Change | ±95% | Repeat | Margin | Verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| grid: decode geometric mean (20 shapes) | -0.38% | 0.13% | +0.14% | 0.39% | **same** |
| c16: decode tok/s, paired | +0.13% | 0.32% | +0.07% | 0.49% | **same** |
| c8: decode tok/s, paired | -0.01% | 0.46% | -0.28% | 0.57% | **same** |
| poisson: output tok/s | -0.01% | 17.34% | +0.04% | 17.38% | **same** |
| stall-3 / stall-11 / stall-15: 131K prefill under decode | -0.06% / +0.18% / +0.22% | ≤1.71% | -1.99% | ≤3.43% | **same** |
| prefill 32K / 131K / 262K / 524K | +0.48% / +0.84% / +1.07% / +0.85% | ≤2.57% | ≤0.41% | ≤2.98% | **same** |
| single-stream c1: decode tok/s, paired | +0.11% | 0.21% | -0.23% | 0.37% | **same** |
| sampled c16 / c8: decode tok/s, paired | +0.15% / -0.80% | ≤1.16% | +0.45% | ≤1.23% | **same** |

Quality: the release suite's model step reads **greedy responses identical
256/256** between the candidate and site 1107, acceptance length 2.318 -> 2.317
(-0.06%), verified per draft +0.16%.

## What this decides

The candidate is **performance-neutral and text-identical** on this site. The
release benchmark therefore does not support promoting it for speed; the
instrument that previously read "same" on the legacy bench now says the same on
the authoritative suites, with the repeat bounding boot-to-boot spread. Its value
stays what the kernel screen showed: two upstream primitives carried onto the
tree (one instruction instead of three `Select`s; the prefetch API available for
the next in-kernel experiment) — to ride the next TileLang pin refresh rather
than stand alone.

## The cross-fleet table, kept as evidence

`receipts/table-cross-fleet-release.txt` compares the same candidate against the
recorded `2026-11-07-spark-ds41f-1107-tp4-switched` suite and reads -6% to -12%
on every prefill size and -4.75% at c16 while the same run's decode grid was
`better` at two of its three points. The record is sp1-sp4; this site is
spark-eb1a. The uniform offset is the fleet, not the change — which is why the
same-site reference above had to be measured.

## Open puzzle

The `release` suite exits 1 on this site for **both** images (candidate and 1107;
`single-stream` and `sampled` exit 0). No step failed (`"failed": []`, every
step's summary `"failed": 0`), and no `FAIL:` line is printed. Not
candidate-specific; recorded for a later look at `bin/spark bench`'s suite exit
path.

## Artifacts

- `receipts/table-release.txt`, `table-single-stream.txt`, `table-sampled.txt`
- On spark-eb1a under `~/nvmodels/spark-ds41f/results/private/suites/`:
  `candidate1107-upstream-primitives-release{,-single-stream,-sampled}/` (two boots each)
  and `site1107-release{,-single-stream,-sampled}/site1107` (the site's first reference)
