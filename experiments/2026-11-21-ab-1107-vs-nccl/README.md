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

Pairing: compare the two runs' `bench.json` point by point with
`--compare <control>/bench.json`. Both arms carry warm kernel namespaces
(`35f15411` and `e808dbdd`), so boot cost is not part of the result.

## Results

Filled after the window.
