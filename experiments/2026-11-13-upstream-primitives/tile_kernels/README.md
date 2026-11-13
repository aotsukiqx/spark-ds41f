# TileKernels series (experiment)

One patch, replacing the promoted `patches/tile_kernels/0001` for this
candidate: the NaN-passing clamp now prefers `tl.clamp_symmetric`
(tile-ai/tilelang `824c5c42`, backported as `tilelang/0014`) and keeps the
compare-and-select form for a compiler without the intrinsic.

- applies clean on v2.0.0 (`66258df6`) and v2.1.0 (`c1cf914a`);
- `count_clamp` stays `False` on our call site (`patches/vllm/0029`,
  `_swiglu_kernel`), so the count paths — the part 2.1.0 rewrote — are dead
  code for us;
- our launch passes `num_threads = 1024` (32 warps), so 2.1.0's
  `num_threads >= 4 * warp_size` assert is satisfied with margin.
