# Contribution-back: three PRs to local-inference-lab/vllm

One conceptual patch per PR (docs/upstreams.md, "Contributing back"). The
patches below are the already-qualified local work, packaged for review; the
owner pushes each as one branch of `christopherowen/vllm` against
`local-inference-lab/vllm` `integration/karmic-kraken-beta`. On acceptance:
advance the pinned revision, drop the local patch from the series, rebuild
once, reproduce the baseline (same commit).

## 1. `0227-tokenizer-spellings/` — ready to send

**PR title**: `[DeepSeek V4.1] Control-token spellings in request text stay plain text`

**Body** (starting point):

> The V4.1 tokenizer renders the conversation into one prompt string and
> encodes it with the added vocabulary, so a control-token spelling written in
> a message, a text part, reasoning, a tool result, tool-call arguments or a
> tool definition became the control token itself: request text could close
> the reasoning block, open a turn or a DSML tool-call block.
>
> `apply_chat_template` now replaces each such spelling in request text by a
> sentinel before rendering; the rendered prompt is split at the control
> spellings the template itself wrote, those become their IDs, and the text
> between them is encoded without the added vocabulary, the sentinels
> restored. JSON tool-call arguments are protected in decoded form. The
> renderer always asks for token IDs (as the K3 renderer does), because the
> online chat path re-encoding a text form would re-create the control tokens.
>
> A request without any control spelling in its text takes the previous path
> and encodes the same prompt with the same call (bit-identical IDs). Tests
> cover the spellings in seven request locations, thinking and chat mode,
> truncation, sentinels next to private-use characters, and the unchanged path.

- Patch: `0001-deepseek-v41-control-token-spellings-are-text.patch` (3 files,
  +376/−2; tests included). Applies on `6d66eed3` with one rebase hunk
  (upstream `7f68ef19` added two lines to `tokenizers/deepseek_v41.py`).
- Evidence: in the production series since spark-ds41f-1025; the 11-20
  rebase re-applied it unchanged in content.

## 2. `prefill-yield/` — ready to send

**PR title**: `[Scheduler] Prefill yield: a long prompt's chunk gives its step to short prompts`

**Body** (starting point):

> With aligned prefill chunks a long prompt's whole chunk takes the step's
> budget beside the decode rows, so a request that arrives while it prefills
> waits for its last chunk (~19 s behind a 131K prompt on our four-node
> cluster, ~200 s behind 1M). `--prefill-yield short` lets a step carry
> instead the waiting prompts whose prefill finishes within one chunk and,
> with sink rejection, the first decode step of a prompt that just prefilled.
> The long prompt's chunks keep their boundaries; only the step a chunk runs
> in changes. A long prompt stops yielding after `--prefill-yield-limit-s`
> (10 s) until its next chunk runs. Off by default; with nothing short
> waiting a step schedules exactly as before.

- Patch: `0001-scheduler-prefill-yield.patch` (4 files, +331; a new
  164-line test file on an OPT fixture — model-agnostic).
- Evidence: measured in spark-ds41f-1030's release — a short request's first
  token beside a 131K prefill **3.6-3.7x sooner**; prefill throughput within
  intervals; the trade (yield off = eight cold prefills 13% denser) is a
  deployment choice, off by default.

## 3. `dspark-effective-depth/` — analysis only; needs a qualification round

Upstream ships `num_speculative_tokens_per_batch_size` and
`adaptive_speculative_tokens_window`; our DSpark port assumes one fixed depth
(`num_speculative_steps`): `_sample_sequential` and `_sample_sequential_topk`
compute `num_sample = num_reqs * n_spec` and reshape
`base_logits.view(num_reqs, n_spec, vocab)` with the module maximum, so any
adapted depth below it crashes at engine init (receipt:
`experiments/2026-11-21-draft-depth/runs/failed-starts/`).

Fix shape: thread the step's effective depth into the speculator and use it
for `num_sample`, the `base_logits` reshape and the `sample_idx_mapping` view
(padded buffers stay sized for the maximum). It is a hot-path change in the
fork's speculative code: needs the release tests, two boots and acceptance
measurement before it can be proposed. Not authored yet — the local lever it
unblocks (draft depth by load) is itself judged small against
`adaptive_verification_row_cost`/`dead_rows_tau` tuning, which need no code.
