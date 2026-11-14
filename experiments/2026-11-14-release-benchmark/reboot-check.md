# Post-reboot comparison: first attempt was clock-latched (2026-11-14)

Intent: after rebooting the whole fleet for the (abandoned) fan-control enrolment,
re-run the three suites and compare against the site's `site1107` reference.

## The first attempt is void

The `release` suite ran at **513 MHz / 4.8 W** on spark-eb1a: the GB10 clock latch
(`docs/recovery.md`). Its symptoms in that run:

| Step | Normal time | This run |
| --- | ---: | ---: |
| model | ~300 s | 656 s |
| c16 | ~365 s | 395 s (failed) |
| c8 | ~365 s | 372 s (failed) |
| poisson | ~366 s | 466 s (failed) |
| stall-3/11/15 | ~130 s | 225 / 232 / 297 s |
| prefill | ~420 s | 1,335 s |

`grid`, `c16`, `c8` and `poisson` were reported failed; `bin/spark bench` printed
`spark-eb1a: GPU clock is 513 MHz at 4.75 W while serving`. The other three nodes
were healthy (2,197-2,210 MHz). Warm reboot and `-lgc` do not clear the latch; an
AC power cycle does. spark-eb1a was powered off, unplugged for over a minute and
powered back on; after that, the four nodes idled at 208-312 MHz (normal idle) and
were re-checked under load.

The receipts stay under `results/private/suites/reboot-check-*` on spark-eb1a as
evidence; they must not be compared with anything.

## The re-run

`reboot-check2`, same dev arm and suite definitions, same comparison target
(`results/private/suites/site1107-release/site1107`), started only after the
clocks were verified under load.

## reboot-check2 result (2026-11-14, 08:35-09:38)

Same image, same dev arm, one boot after the AC cycle cleared the latch; four
nodes healthy at 2,197-2,210 MHz on a 10 W idle. Compared with the site's
`site1107` reference (same fleet, same day):

| Metric | site1107 | reboot-check2 | Change | ±95% | Verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| grid: decode geometric mean (20 shapes) | — | — | +0.59% latency | 0.13% | worse |
| c16: output tok/s | 250.370 | 254.327 | +1.58% | 1.42% | better |
| c16: paired decode tok/s | 15.654 | 15.849 | +1.51% | 0.46% | better |
| c8: output tok/s | 198.900 | 202.640 | +1.88% | 1.40% | better |
| c8: paired decode tok/s | 25.083 | 25.307 | +1.75% | 0.35% | better |
| poisson: output tok/s | 180.353 | 180.387 | +0.02% | 17.57% | same |
| stall-3 / 11 / 15: 131K prefill beside decode | 6,314 / 5,948 / 6,401 | 6,345 / 5,951 / 6,421 | ≤+0.5% | ≤1.7% | same |
| prefill 32K / 131K / 262K / 524K | 7,995 / 7,957 / 7,476 / 6,574 | 8,050 / 8,015 / 7,503 / 6,582 | +0.1 to +0.7% | ≤0.6% | same / better |
| model: greedy responses | — | — | 256/256 identical, KL 0, perplexity identical | — | pass |

Reading: no drift from the reboot worth acting on — the closed loops and prefill
are 0.1-1.9% *faster*, the 20-shape grid 0.59% slower, all inside a couple of
percent and mixed in sign. The comparison's own conditions were hotter than the
reference's (spark-141e peaked 85 °C with 1 °C headroom against 87 °C, versus 2 °C
on the reference boot; spark-2fe7 5 °C), so the `halted` exit 1 is again the
thermal guard, not a failed step. Text and distributions are bit-identical across
the reboots, which is the determinism check that mattered.

The label order matters for this tool: `servebench_suite_table.py <run> <candidate>
<reference>`; putting the reference first inverts every verdict.
