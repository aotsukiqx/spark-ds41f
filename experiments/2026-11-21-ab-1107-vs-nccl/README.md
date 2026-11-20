# A/B: deployed site stack vs the previous production (`spark-ds41f:1107`)

Status: **measurement in progress**; site window, not a repository promotion.

## Why

The owner reports the live service feels slower than the previous version. The
deployed stack (`spark-ds41f:1107-nccl-2.32.6`: vLLM `6d66eed3` + CuTe DSL/CUTLASS
4.8.1, TileLang `b1367a59`, NCCL 2.32.6-1) was accepted on "neutral within this
site's intervals" against the recorded `2026-11-07-spark-ds41f-1107-switched`
reference, a record measured on another fleet (sp1-sp4). Every candidate this
session leans slower on the code points:

| point | reference | b1367 B1/B2 | Group A B1/B2 | C3 (live) |
| --- | ---: | ---: | ---: | ---: |
| code-c1 | 29.78 | 30.12 / 30.18 | 30.46 / 30.44 | 30.99 |
| code-c8 | 42.18 | 43.03 / 48.57 | 46.12 / 47.94 | 43.64 |
| code-c16 | 58.63 | 61.02 / 57.15 | 64.70 / 61.85 | 65.41 |

No same-session plain-`1107` control exists: the 11-20 attempt aborted when
external traffic overlapped the control boot. This window supplies that control.

## What changed since `1107` (code review, 2026-11-21)

| component | 1107 | deployed | hot-path delta |
| --- | --- | --- | --- |
| vLLM | `19f2c20e` + 641 patches (`ed1bdb7a`) | `6d66eed3` + 640 patches (`e5a1f99d`) | 13 upstream commits: Anthropic system-message placement, DEBUG probes, GLM-5.3 KDA load/W8A16, docs. **None on the DeepSeek serving path.** Patch `0645` dropped (upstream owns it), `0227` rebased (tokenizer only) |
| CUTLASS/CuTe DSL | 4.7.1 | 4.8.1 | build-time headers/wheels; serving kernels are TileLang |
| TileLang | `2123e412` (`35f15411`) | `b1367a59` (`e808dbdd`) | `71a7c311` loop-vectorize planner rewrite is the one global codegen change |
| NCCL | 2.30.7-1 | 2.32.6-1 | p2p channel planning + tuner move; site env unchanged (`MAX_NCHANNELS=8`, `PROTO=^LL128`, 1 MiB, CUMEM off) |
| recipe | site profile | same | serve args identical: 716,800 tokens, 16 seqs, 16,384 budget, 10.5 GiB KV, 5 drafts, capture 96 |

So the candidates for a real decode regression are the TileLang codegen and
NCCL; both were only ever judged against the cross-fleet record.

## Live read-only snapshot before the window (2026-11-21, since 11-20 06:04)

7 h, 725 finished requests, 0 errors, 0 preemptions. Prompt tokens p50 89,286,
p90/p99 500,000; prefix-cache hit 67.8%; generation 414 tokens/request. ITL p50
39.9 ms / p90 64.9 ms / p99 1.70 s; TTFT p50 2.18 s / p90 61.3 s / p99 543 s;
préfill p50 0.94 s / p90 40.6 s. accepted/draft 1.93. At sample time running 0,
waiting 0, KV 0%. Decode is at reference; the TTFT tail is long-context prefill
queueing behind one prefill lane, not decode.

## Method

One window, two boots, same client and flags:

1. Stop production; boot the **control** `profile-1107.json` (the archived
   `2026-11-12-site-spark-eb1a` profile from `d93021996`: `spark-ds41f:1107`,
   site shape, node-local weights).
2. `bin/spark bench --suites quality,decode --min-samples 4 --max-samples 4`
   (10 points, prose/code c1..c16, 4 samples; reference for warnings only).
3. Boot the deployed stack from `experiments/2026-11-12-site-spark-eb1a/profile.json`;
   repeat the identical bench.
4. Restore the deployed stack, `doctor --live`, remove the hold.

```sh
# window (manual hold, production stopped; the site's fork-only commit is placed
# on the nodes by fetch-and-detach, which is how the site has always deployed)
bin/spark --cluster-config experiments/2026-11-12-site-spark-eb1a/profile.json cluster stop --apply

bin/spark --cluster-config experiments/2026-11-21-ab-1107-vs-nccl/profile-1107.json \
  cluster start --replace --apply
bin/spark bench --suites quality,decode --min-samples 4 --max-samples 4 \
  --output results/private/bench/2026-11-21-ab-1107

bin/spark --cluster-config experiments/2026-11-12-site-spark-eb1a/profile.json \
  cluster start --replace --apply
bin/spark bench --suites quality,decode --min-samples 4 --max-samples 4 \
  --compare results/private/bench/2026-11-21-ab-1107/bench.json \
  --output results/private/bench/2026-11-21-ab-deployed
```

Pairing: compare the two runs' `bench.json` point by point with
`--compare <control>/bench.json`. Both arms carry warm kernel namespaces
(`35f15411` and `e808dbdd`), so boot cost is not part of the result.

## Results

Window 2026-11-20 13:00-13:40Z. Two boots, warm namespaces (API ready +120.8 s
control, +122.8 s deployed; the restore +125.7 s), quality 5/5 on all three,
zero thermal-slowdown time, `MemAvailable` floor 20.7 GiB. The bench needed
`--cool-below 0` (this site has no fan-control DKMS, so 55 °C is unreachable)
and `--allow-mismatch` for the documented `nvidia-drm fbdev=N` deviation; both
arms carry them equally.

### Full gate, 4 samples a point, same client and flags

Step ms (lower is better) and aggregate decode tok/s, control -> deployed:

| point | 1107 step | deployed step | Δ step | 1107 tok/s | deployed tok/s | Δ tok/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| prose-c1 | 27.61 | 27.56 | −0.2% | 72.3 | 72.7 | +0.5% |
| prose-c2 | 30.32 | 28.60 | −5.7% | 129.6 | 134.6 | +3.9% |
| prose-c4 | 37.53 | 33.65 | −10.3% | 208.2 | 225.5 | +8.3% |
| prose-c8 | 39.15 | 40.53 | +3.5% | 391.8 | 381.1 | −2.7% |
| prose-c16 | 48.30 | 48.58 | +0.6% | 613.4 | 610.0 | −0.6% |
| code-c1 | 30.99 | 30.44 | −1.8% | 91.9 | 93.3 | +1.4% |
| code-c2 | 37.07 | 36.26 | −2.2% | 148.0 | 152.1 | +2.7% |
| code-c4 | 38.91 | 38.27 | −1.7% | 270.9 | 274.2 | +1.2% |
| code-c8 | 43.16 | 47.01 | +8.9% | 473.6 | 443.6 | −6.3% |
| code-c16 | 56.95 | 59.33 | +4.2% | 705.3 | 676.5 | −4.1% |

Accepted/verified moves +0.006 to +0.018 on the code points (0.606 -> 0.618 at
code-c1), tokens/step within 0.5%; the deployed arm therefore emits the same
tokens per step. No point passes the repeat-and-interval rule: every concurrent
point's 4-sample interval is ±11-22%.

### Focused re-measure: 16 samples, code c8/c16, plus prefix replay

| point | 1107 | deployed | Δ | verdict |
| --- | ---: | ---: | ---: | --- |
| code-c8 step ms | 42.62 ±7.1% | 44.22 ±6.2% | +3.8% | same (interval crosses 0) |
| code-c8 tok/s | 495.4 ±4.4% | 478.6 ±4.8% | −3.4% | same |
| code-c16 step ms | 52.94 ±5.8% | 52.88 ±5.7% | −0.1% | same |
| code-c16 tok/s | 762.6 ±4.2% | 758.7 ±4.3% | −0.5% | same |
| prefix replay | 0.99 hit, 0.218 s warm | 0.99 hit, 0.216 s warm | — | same as the 11-19 record |

The 4-sample `code-c8` +8.9% shrinks to +3.8% at 16 samples (the same arm read
47.01 and 44.22 within one boot), and `code-c16` resolves to zero. A ~3-4%
`code-c8` residual cannot be excluded, but it is below this site's resolution,
it is absent at c1 and c16, and it is smaller than the prose gains in the same
run.

Both arms read `code-c1` 30.4-31.0 against the cross-fleet record's 29.78
(+2-4% with a ±1.9-3.5% interval), so that offset is the site, not the stack —
the same reading the 11-20 C3 live sample gave.

## Verdict

**The deployed stack is not measurably slower than `spark-ds41f:1107`.** Single
stream is 0.2% (prose) and −1.8% (code) in step time; c16 is identical; the only
candidate signal is ~+3.8% at code-c8 over 16 samples, inside the interval. The
candidate components in the deployed stack agree with this: the 13 upstream vLLM
commits touch no serving path, CUTLASS is build-time only, NCCL's site settings
are unchanged, and the compiler refresh was already judged neutral.

The live service's slow *feel* is the workload, not the step:

- Live prompt tokens p50 89,286, p90/p99 500,000 (725 requests over 7 h);
  prefix-cache hit 67.8%, against 98-99% on the 2026-09-28 agent footprint.
- One prefill lane (`--max-parallel-prefills 1`, `--prefill-yield short`): TTFT
  p50 2.18 s, p90 61.3 s, p99 543 s; request prefill p50 0.94 s, p90 40.6 s.
  The engine is not queueing (`waiting` 0) — a long prompt blocks the batch while
  it prefills.
- Decode is at reference: ITL p50 39.9 ms, p90 64.9 ms; accepted/draft 1.93;
  414 output tokens a request; zero preemptions.

So a user who sends long code or document contexts per turn pays the prefill
lane, and the deployed stack did not change that. The prefill rates themselves
are at the site's 1107 reference (today's llama-benchy run: 8,041 / 7,424 /
6,619 tok/s at 32K / 262K / 500K against 7,995 / 7,476 / 6,574).

If the owner still wants the step back at all costs, a rollback is one command
with warm namespaces; but this window finds no performance reason for it.

## Deviations

- `bin/spark cluster sync --apply` refuses a fork-only commit ("not published on
  origin/main", `deployment.branch` = main). The site's established path was
  used instead: fetch `fork/site/spark-eb1a` and detach on each node (the same
  state the site already ran at 37ab7ea90).
- The bench refuses on the pre-existing `nvidia-drm fbdev=N` deviation; both
  arms used `--allow-mismatch` for it only.
- Cooling: `--cool-below 0`; the site's fan-control DKMS is absent (owner
  decision), so the 55 °C gate cannot be met.
- Production was stopped 13:00-13:40Z; external clients (`192.168.2.10/18`)
  were idle at the start (0 running, 0 waiting) and the service is restored on
  the deployed stack.
