# Site performance verification: the aligned stack vs its receipts (2026-11-22)

Status: **measured**. Window on live production (no image change, no restart):
the hold covered the whole run. Production runs `spark-ds41f:a3-no-b12x-r5`
(vLLM `6d66eed3`+648, TileLang `ac88f5bc`, stock NCCL `2.32.6-1`,
`NCCL_BUFFSIZE=2 MiB`, lossless fabric, B12X absent).

Purpose: the owner's final ask — complete the local queue, then verify the
performance improvement of the promoted site stack against its recorded
receipts. Reference for decode: the **same-session** `1107` control
(`experiments/2026-11-21-ab-1107-vs-nccl/`), the only valid baseline on this
site (the 11-07 record is another fleet).

## Method

`bin/spark --cluster-config experiments/2026-11-12-site-spark-eb1a/profile.json
bench --suites quality,decode | --suites prefill --min-samples 4 --max-samples 4
--allow-mismatch --cool-below 0` (flags per site convention: `--allow-mismatch`
only for the documented `nvidia-drm fbdev=N` deviation; this site has no
fan-control DKMS). Decode first, 26 min idle before prefill (rule: ≥8 min).

Runs: `results/private/bench/2026-11-22-perf-verify-{decode,prefill,prefill524k*}/`.

## Decode (step ms, lower is better; n=4; concurrent CIs ±11-23%)

| point | 1107 control (11-21) | deployed then (11-21) | **now (a3+b2)** | verdict vs 1107 |
| --- | ---: | ---: | ---: | --- |
| prose-c1 | 27.61 | 27.56 | **27.93 ±2.6%** | same |
| prose-c8 | 39.15 | 40.53 | 39.60 ±19.9% | same |
| prose-c16 | 48.30 | 48.58 | 50.83 ±23.4% | same (interval crosses) |
| code-c1 | 30.99 | 30.44 | **30.21 ±2.2%** | −2.5%, edge of interval |
| code-c8 | 43.16 | 40.53 | 48.92 ±22.4% | noisy point (4-sample) |
| code-c16 | 56.95 | 59.33 | 61.34 ±16.1% | noisy point (4-sample) |

Quality 5/5. The c1 judge points sit at/below the 1107 control; the concurrent
points repeat the known ±11-23% sampling noise (the 11-21 window's 16-sample
re-measure showed c8/c16 intervals cross zero). Accepted/verified 0.643-0.708,
3.0→2.67 tok/step — matches the 11-21 arms. Thermal: GPU ≤69 °C, zero
thermal-slowdown ms, MemAvailable floor 20.7 GiB, swap growth 0.

## Prefill (tok/s, higher is better)

| size | B2 boots (ref) | A1 same-day | A3 boots | **now** | verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| 2,048 | — | — | — | 5,771.7 ±4.7% | recorded |
| 32,768 | — | — | — | 9,024.8 ±0.9% | recorded |
| 65,536 | — | — | — | 8,977.7 ±0.2% | recorded |
| 131,072 | 8,661.1 / 8,716.2 | 8,626.9 / 8,696.9 | 8,654.7 | **8,648.0 ±0.2%** | at reference (−0.2% vs B2 boot mean, inside ±0.6%) |
| 524,288 | 6,988.3 / 7,039.9 | 6,980.1 / 7,023.0 | — | **7,006** (1 sample, guard-aborted at 79 °C) | at reference |

### 524,288

First attempt aborted at spark-141e 82 °C (within 4 °C of the limit) before
any sample — the documented behaviour of this point on this site
(`experiments/2026-11-21-a1-stock-nccl` hit the same wall). The cooled retry
(GPUs ~50 °C at start) recorded **7,006 tok/s** on its first sample before
the guard aborted at spark-141e 79 °C — dead centre of the reference cluster
(cluster mean 7,008). Verdict: **at reference**. Run:
`results/private/bench/2026-11-22-perf-verify-prefill524k-r2/`.

## Lossless fabric receipt (all four nodes)
`roce_adp_retrans` / `out_of_sequence` before == after **the entire window**
(decode + prefill suites + the aborted 524K load): head
`0,16873,0,17731,0,343666,0,342574` unchanged from the morning snapshot; every
worker byte-identical pre/post. Zero increment under load — the B1 lossless
state holds with the promoted B2 buffers.

## Verdict

- **Decode: at reference.** Judge points (c1) at or below the same-session
  1107 control; no regression from any of A1/A2/A3/B2.
- **Prefill: at reference.** 131K within −0.2% of the B2 boot mean; 524K at
  the reference-cluster centre (7,006 vs mean 7,008); the curve peaks where it
  always did (~9.0k at 32-64K).
- **Fabric: zero loss.** The felt-slowness investigation stands: decode and
  prefill are at their receipts; the workload shape (89K-token p50 prompts,
  500K p90+, one prefill lane) owns the TTFT tail, not the stack.
