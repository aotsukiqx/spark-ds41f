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
`manifests/benchmarks/2026-11-27-spark-ds41f-1127-switched.json`; second
clean boot, repeat. Acceptance: prefill 131K >= 8,594.8 (residual recovered;
the persistent kernel may beat 0.5.0 by avoiding the old multi-launch yield
stalls), decode 10/10 same, determinism identical, quality 5/5. Explicit
risk gate: the 150-375 µs overlap-stall the cap was designed to prevent.

## Results

(to be filled)
