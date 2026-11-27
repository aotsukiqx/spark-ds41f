# SPARKNET_ROCE_COLLECTIVE_BLOCKS width knob (full-width SP collectives)

Status: **in window** (base commit `74a0316cb5`, promoted baseline
`2026-11-27-spark-ds41f-1127`).

## Hypothesis

The 2026-11-27 post-window analysis (in
`experiments/2026-11-26-sparknet-060-cap/README.md`) attributed the promoted
stack's -1.6% prefill residual to `_collective_max_blocks`
(`sparknet/oneshot/runtime.py`): every eager dim-0 all-gather /
reduce-scatter with a slot-fitting row runs the multi-stage persistent kernel
capped at `SPARKNET_ROCE_COLLECTIVE_BLOCKS=8` CTAs (2/20 GB10 SMs), where
0.5.0 spread the same payloads over up to 64 CTAs. The cap guards a
side-stream overlap this pipeline never runs, so the preserved SMs idle.

One variable: the switched environment gains
`SPARKNET_ROCE_COLLECTIVE_BLOCKS=0` (`<=0` restores `self._blocks` = 64).
Same image digest as 1127 — no rebuild, the runtime reads the knob at
dispatch.

## Method

Stop production; boot the arm (`--unqualified-shape`); verify the env reached
the container before measuring; determinism gate + the
`quality,decode,prefill` gate vs
`manifests/benchmarks/2026-11-27-spark-ds41f-1127-switched.json`; the
determinism failure on boot 1 ends the arm before its second boot. Risk
watched: the 150-375 µs overlap-stall the cap was designed to prevent
(decode-adjacent points stayed inside their intervals).

## Results (single boot; the gate verdict ends the arm)

| measure | 1127 reference | boot 1 (COLLECTIVE_BLOCKS=0) |
|---|---:|---:|
| prefill 131,072 (cooled) | 8,461.1 | **8,625.7 ±0.1% (+1.9%, faster)** |
| decode grid | — | 10/10 same |
| quality | 5/5 | 5/5 |
| temp-0 determinism | identical | **failed: 1-2 token / 1-3 logprob diffs in every scenario** |

The mechanism is confirmed exactly as analyzed: full-width collectives
(64 CTAs) recover the whole -1.6% residual and land +0.4% above the 1126
level (8,625.7 vs 8,594.8) — the persistent kernel beats 0.5.0's
multi-launch layout once it is not starved at 8 CTAs. But the wider grid
changes the kernel's floating-point reduction order, and the
temperature-0 outputs move (1-2 tokens of 192 in every scenario; hashes
differ from the production stack). That fails the determinism gate by
construction: any width other than 8 changes the order the same way.

**Verdict: not adopted; the headroom is proven and claimed differently.**
Production stays on 1127. The +1.9% prefill at 131K is real and repeatable
(±0.1%), and taking it needs an order-preserving widening of the multi-stage
kernel's reduction (a deterministic reduction tree independent of the CTA
count) — an upstream sparknet change, and a natural contribution-back
candidate alongside the deferred code analysis. Receipts: `runs/b1`
(including the determinism failure record).

## Post-experiment code study (2026-11-27)

Three corrections to the arm's premise, from reading the 0.6.0 kernel stack
(`_reducescatter_tilelang.py`, `_device.py`, `runtime.py`) and the upstream
evidence tree:

- The reduction is **already order-preserving at any width**: each 16-byte
  pack is reduced by a single thread over sources in fixed rank order with
  FP32 accumulation (`roce_reduce_pack_bf16`) — the grid only chooses which
  thread handles which pack. "Widening changes the reduction order" was
  wrong.
- The 64-CTA wide grid is upstream's own measured design for the one-shot
  data phase (`sparknet/evidence/2026-10-20-wide-read/`: 8→64 blocks,
  reduce 35.6→12.3 µs at 480 KiB per rank beside the model's L2 prefetch);
  `SPARKNET_ROCE_COLLECTIVE_BLOCKS=8` is only the staged SP path's overlap
  guard introduced by 0.6.0's `ca59c957`.
- The determinism failure is therefore **not** an inherent property of
  width: the gate JSON's repeat scenario (`again`) differs from itself
  across runs and the diff count tracks batch composition (1 vs 2) — a
  timing/batch-dependent deviation exposed by the wider staged grid, i.e. a
  defect worth root-causing, not a trade-off to design around.

Queued localization probe (owner approval pending): boot the width-0 arm and
(1) classify deterministic-vs-batch-dependent with fixed prompts under
alternating batch compositions, (2) bisect by collective type via selective
`SPARK_DS41F_ONESHOT_MAX_BYTES` caps, (3) sweep `SPARKNET_ROCE_STAGE_BYTES`
to test the epoch/slot/stage interaction with payload-size changes (the
prime suspect: `seq = epoch + 1 + s` slot selection against per-collective
stage counts that vary with the batch).
