# What spark-ds41f-1107 actually costs: one measurement window

Owner, 2026-11-14: a full measurement of the promoted release, to judge what the
recent improvements bought and what is left.

Released builds are not re-measured (owner, 2026-10-29), so this window measures
the promoted `1107` image only, on the production site, in one boot with the
torch profiler enabled (`experiments/2026-11-13-upstream-primitives/profile-resolved.json`,
identical to production otherwise). Earlier releases contribute their recorded
baselines; this window supplies the attribution those numbers cannot.

## Results

| File | What it establishes |
| --- | --- |
| `results-prefill-boot.md` | cold start does not reproduce; a 484K prefill is 22% indexer scoring, 25% MoE, 20% collectives, 13% sparse MLA; prefill is 97.5% GPU-busy; the boot is 124 s |
| `results-cache.md` | a 63K shared prefix is 99.6% cached after the first request, suffixes do not disturb it, the 256-token block leaves a 242-token tail uncached, and the pool-pressure result |

## Instruments

| File | Use |
| --- | --- |
| `measure_prefill.py` | cold first request, warm repeat, one long prefill, all streamed so TTFT is real |
| `measure_cache.py` | reuse, shared-prefix and pool-pressure phases of the prefix cache |
| `family_time.py` | kernel time by name from a torch-profiler trace |
| `boot_timeline.py` | phase costs from a `cluster start --apply` log |

Trace: `~/nvmodels/spark-ds41f/cache/profiles/d1107/dp0_pp0_tp0_dcp0_ep0_rank0.1794613919667201851.pt.trace.json.gz`
on spark-eb1a (26.5 MB, the 484K prefill).
