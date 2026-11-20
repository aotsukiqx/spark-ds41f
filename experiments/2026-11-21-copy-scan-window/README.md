# CopyDrafter history scan: bound first, then window

Status: **design + measurement plan**; no code change, nothing deployed.

## Why this is the next lever

The routed MoE, second decode stream, direct RoCE writes and the vocabulary-head
items are closed by measurement (`TODO.md`, `experiments/2026-11-13-upstream-primitives/`).
The copy-draft history scan remains open: at 100K-1M contexts a decode step that
misses the 256-token match walks `[min_match, total_len)` in UVA
(`all_token_ids.gpu`) on `output_copy_stream`, measured at **0.36-0.47 ms/step at
c16** with 1M random tokens and **up to ~2 ms** on repeated 16/32-token
boilerplate (1107 numbers). Against a 102 ms c16 step that is 0.5-2%, and it
contends with DSpark for unified-memory bandwidth.

Those numbers predate the current stack (vLLM `6d66eed3`, CuTe DSL/CUTLASS
4.8.1, NCCL 2.32.6, TileLang `b1367a59`). Re-bound before implementing.

## What the kernel does today

`vllm/v1/worker/gpu/spec_decode/tilelang_copy.py` (`copy_match_kernel`, ported by
`0585`; warp early-exit by `0744`):

- grid `(num_reqs, CHUNKS=32)`, 256 threads (8 warps); each block walks warp tiles
  of 32 ends from the highest priority down, stepping `span = 32 * 256 = 8192`
  tokens, so the 32 blocks tile the whole history in passes of 8192.
- Exact pruning: shortest level first, `need_len` raised to the next unmatched
  level, anchor probes at `need_len` and `need_len // 2`, and a warp stops its
  full-continuation scan when any lane matches the longest level. Remaining work
  visits only ends that can still improve the result.
- `sources[r, c, level]` carries priorities; `copy_alloc` decodes them. No host
  synchronization, fixed grid, CUDA-graph capturable.

## Two designs

**A. Recency + prefix window (approximate).** Add compile-time `recency` and
`prefix` bounds: stage 1 walks ends in `[max(min_match, length - recency), full_last]`
instead of down to `min_match`, and a second bounded pass covers `[min_match, prefix]`
so the system prompt's early repeats stay available. Cost: a few lines in the
warp-tile lower bound plus one bounded stage; window `(0, 0)` reproduces today's
behaviour exactly, so it can ship default-off. Risk: a far non-prefix repeat
(an old tool output) is no longer matched, so acceptance can drop - which is the
quantity to measure, not assume.

**B. Incremental suffix index (exact).** Maintain, per slot, the positions of
16-token suffixes over committed tokens (a small hash table updated only for new
tokens) and let `copy_match` probe exact candidates instead of scanning. Exact by
construction but a much larger change: new device-resident state per slot,
updates tied to the commit path, CUDA-graph-safe buffers, and index maintenance
cost on every accepted token.

Start with A as an experiment because it is small and reversible; fall back to B
only if A's acceptance cost eats the scan saving.

## Measurement plan (one window)

1. Re-bound the lever on the deployed stack: profiled boot
   (`--profiler-config` with `torch_profiler_dir=/cache/profiles/copyscan`),
   one 1M-token prefill, then a c16 decode round; measure `copy_match` /
   `copy_alloc` kernel time and its overlap with the main stream
   (`analyze_trace.py`). Gate: if the scan is under ~0.3 ms/step at c16 on this
   stack, close the lever like the others.
2. Kernel-level screen of A: with the window files bind-mounted (no image build),
   compare scan time and matched levels on 1M random tokens and on repeated
   16/32-token boilerplate for `(recency, prefix)` in `(0,0)`, `(32K,4K)`,
   `(8K,4K)`.
3. Serving screen of the best pair: two boots with paired suites on distinct
   prompts, acceptance (`accepted/verified`, tokens/step) and decode grid against
   the deployed arm's two boots. Acceptance is the deciding number: a 0.4 ms
   saving that costs 0.05 accepted drafts per step is a loss.

## Files this experiment would touch

- `vllm/v1/worker/gpu/spec_decode/tilelang_copy.py` (kernel + wrapper,
  `copy_match_key` for the compile keys) - one vLLM series patch.
- Nothing else: the drafter's call site passes the existing buffers.

## Decision rule

Implement A only if step 1 shows the scan is worth ≥0.3 ms/step at c16 and step 2
shows a window that keeps the matched levels on boilerplate. Otherwise close the
lever in `TODO.md` with the trace as evidence, as was done for the second stream
and the direct RoCE writes.

## Site sizing (why this lever cannot be measured here)

This site caps requests at **716,800 tokens** (`--max-model-len`), and the KV pool
holds 16.02 full contexts. A faithful `c16` trace with 1M-token histories is
therefore impossible at this site: sixteen 1M contexts exceed the pool, and
sixteen 716K contexts (11.4M tokens) sit exactly at the pool limit while their
cold prefill alone costs ~25 minutes at 8.5K tok/s.

Scaling the measured cost with history length, the scan at 716K is about
0.26-0.34 ms/step, i.e. **≤0.3% of a 102 ms c16 step**. That is below every
interval this site resolves (fixed-row ±0.5 ms, concurrency points 10-20%), so
the two-boot repeat rule cannot credit it even if the window keeps acceptance
exactly.

**Verdict: defer (effectively close) the CopyDrafter window at this site.** It
reopens only if a live agent-trace record shows far-history copy scans at high
frequency - the `bin/spark workload` record would show the draft counters - or if
the recipe moves to a longer request limit. Pursue the in-kernel prefetch
emission next instead; it removes GPU work on the critical path rather than
trading acceptance for a sub-0.3% scan.
