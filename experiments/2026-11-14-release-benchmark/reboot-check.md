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
