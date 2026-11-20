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
