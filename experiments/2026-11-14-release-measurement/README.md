# What spark-ds41f-1107 actually does: one measurement window

Owner, 2026-11-14: a full measurement of the promoted release to judge what the
recent improvements bought and what is left.

Released builds are not re-measured (owner, 2026-10-29), so this window measures
the promoted `1107` image only, on the production site, in one boot with the
torch profiler enabled (`experiments/2026-11-13-upstream-primitives/profile-resolved.json`,
identical to production otherwise). The value of earlier releases comes from
their recorded baselines and references; this window supplies the attribution
those numbers cannot: where a step's time goes, what a cold start costs, and how
the prefix cache behaves under pressure.

## Measurements

| # | What | Instrument |
| --- | --- | --- |
| 1 | Cold first request after a boot, and the same request warm | `measure_prefill.py` (streaming TTFT) |
| 2 | One long-context prefill (~500K tokens) with the profiler on | `measure_prefill.py --profile` + `analyze_trace.py` |
| 3 | Prefix-cache retention at a 65K prefix, shared prefixes, and under eviction pressure | `measure_cache.py` |
| 4 | Boot phase costs | `boot_timeline.py` on the start log |

Not measured here: another release's absolute numbers (recorded, not re-run), and
decode at the real 700K context (today's decode profile used short prompts; that
caveat is stated in `experiments/2026-11-13-upstream-primitives/profile-results.md`).
