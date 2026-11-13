# Item 2 — TileKernels 2.1.0 pin migration: findings

Driven to a decision with evidence from the prepared trees (2026-11-13).

## What 2.1.0 changes that could touch us

`git compare 66258df6...c1cf914a`: 16 files, +352/-382, concentrated in the
clamp-count reduction of `swiglu_forward_cuda.py` (int64-safe counts via two
int32 halves, `T.alloc_var(T.int64)`, `num_threads >= 4 * warp_size`) and in
training-side kernels (norm/swiglu backward, Ascend variants).

## Our call site, checked in the tree

`patches/vllm/0029` `_swiglu_kernel` calls
`get_swiglu_forward_and_per_token_cast_kernel_cuda(..., count_clamp=False, ...)`
with `num_threads = 1024` inside the builder:

- `count_clamp=False` — **the entire count-reduction 2.1.0 rewrote is dead
  code on our serving path**;
- `num_threads = 1024` = 32 warps — 2.1.0's `>= 4 * warp_size` assert passes
  with 8x margin;
- our experiment patch (and the promoted 0001) applies cleanly on 2.1.0
  (`git apply --check` rc=0 on the prepared tree).

`T.alloc_var(T.int64)` and the int64 shifts need a TileLang newer than our
pin — but only on the dead path; the pin constraint is real only if the pins
move together.

## Decision

**No promotion value on its own.** The material 2.1.0 rewrite never executes
for us, the assert is satisfied, and the one delta that does reach us is
`counts_shared` growing from `num_warps * 4` to `num_warps * 8` int32
(+512 B shared memory at 32 warps) on a path we compile either way.

Fold the move into the next TileLang refresh (it must carry the int64 support
for the *upstream* tests to pass), rebase this experiment's series — already
verified to apply — and re-run the standard gates. Recorded here so the next
candidate does not re-derive it.
