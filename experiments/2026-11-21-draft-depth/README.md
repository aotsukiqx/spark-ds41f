# Draft depth by load and acceptance

Status: **measurement**; config-only arms on the deployed stack.

Step time is GPU-bound (98.9% busy at c1, 99.25% at c8), so the remaining
throughput gain is tokens per verified row. Live agent traffic accepts **1.89 of
3.40** verified drafts per step against **3.1** on the bench, and acceptance
decays with draft position (0.72, 0.55, 0.48, 0.46, 0.42), while every extra
verified row costs step time (more routed-expert rows). The recipe always sends
five drafts.

Two built-in vLLM knobs change the depth without code:

- `num_speculative_tokens_per_batch_size`: `(range_start, range_end, tokens)` with
  inclusive batch-size ranges (`arm-sched`: 5 at one stream, 4 at 2-4, 3 at 5-8,
  2 at 9-16).
- `adaptive_speculative_tokens_window` (+ `_initial`): averages the accepted
  length over the last N verify steps, with `num_speculative_tokens` as the upper
  bound (`arm-adapt8`: window 8, initial 5).

## Screen

Each arm boots once at the site shape and runs the default quality+decode gate;
the deployed arm's two boots are the control. Deciders are **tokens/s and
accepted/verified per point**, not step ms: a depth change is only good if the
shorter step pays for the drafts it drops. Adopt only if c8/c16 tokens/s improves
consistently across boots with c1 unchanged and quality 5/5.

## First attempt (05:55Z): rejected by validation

`num_speculative_tokens_per_batch_size` ranges are **one-based and inclusive**;
`[0,1]` aborts engine init with `ValueError: Batch-size range (0, 1) must be
positive` (complete failed-start logs under `runs/failed-starts/`, ignored by
`*.log`). The arm now uses `[[1,1,5],[2,4,4],[5,8,3],[9,16,2]]`.

## Result: the config-only route is blocked by a constant in the DSpark port

Second attempt (`05:59Z`, corrected one-based ranges) fails at engine init with

```
File ".../vllm/v1/worker/gpu/spec_decode/dspark/speculator.py", line 457
base_logits = base_logits.view(num_reqs, n_spec, vocab_size)
RuntimeError: shape '[16, 5, 32320]' is invalid for input of size 2068480
```

`2068480 = 16 * 4 * 32320`: the draft-logits tensor carries the **effective**
depth (4 for that batch), while the speculator still reshapes with
`n_spec = self.num_speculative_steps` (line 430), the module maximum 5.
`num_sample = num_reqs * n_spec` and the `sample_idx_mapping` slice use the same
constant. The adaptive-window arm would take the same path for any step whose
adapted depth is below the maximum.

So `num_speculative_tokens_per_batch_size` and
`adaptive_speculative_tokens_window` are advertised by the upstream engine but
our DSpark port assumes one fixed depth. Both failed starts are preserved:
`runs/failed-starts/20261120T055509Z-spark-ds41f` (the (0,1) range) and
`20261120T060134Z-spark-ds41f` (this reshape).

**What it would take:** thread the per-step effective depth from the schedule /
adaptive controller into the speculator and use it for `num_sample`, the
`base_logits` reshape and the `sample_idx_mapping` view (the padded buffers stay
sized for the maximum). That is a real change in the fork's speculative path,
not a knob: it needs the release tests, two boots and acceptance measurement, and
is only worth doing if accepted-length data says a smaller depth pays at high
concurrency.

Until then the recipe keeps five drafts at every batch size. `arm-adapt8` is not
run: it shares the failing reshape.

## Review (2026-11-21): the idea is mature upstream and already present locally

`num_speculative_tokens_per_batch_size` and `adaptive_speculative_tokens_window`
exist in **upstream** `vllm/config/speculative.py` at our base commit
(`6d66eed3`, lines 486/493) — they are not a gap someone forgot to try.

Our DSpark port makes the same tradeoff at a different layer
(`spec_decode/adaptive_verification.py`): a per-step cost model
(`1 + row_cost * effective_rows`), survival-based dead-row pruning
(`dead_rows_tau`), per-slot `assign_draft_budget`, and the copy drafter's cap
doubling. So the engine already decides *how much verification work a step may
spend*; changing the proposer's draft depth would duplicate that decision one
layer earlier.

Consequence: threading the effective depth into `dspark/speculator.py` is a
**compatibility fix**, not an optimization by itself, and its expected marginal
gain is small against the risk (hot path, CUDA-graph shapes, acceptance). If the
economics are to be revisited, tune the parameters that already control it —
`adaptive_verification_row_cost` (0.035) and `dead_rows_tau` (0.2), plus the
copy-drafter cap — as a config-only sweep with paired suites. That is the
non-duplicative version of this lever.
