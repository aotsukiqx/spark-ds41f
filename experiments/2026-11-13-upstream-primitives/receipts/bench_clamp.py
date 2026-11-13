"""Clamp-variant bench for the SwiGLU+cast kernel (experiment 2026-11-13).

Run inside the production image with one of three PYTHONPATHs:
  old: image tilelang + pristine TileKernels 2.0.0   (T.min/T.max clamp)
  mid: image tilelang + patched TileKernels           (Select clamp)
  new: backported tilelang + patched TileKernels      (clamp_symmetric)

Each run times the kernel at the serving geometry (TP4 rank: 384 experts,
576-wide intermediate, swiglu_limit 10, e4m3/32 out, bf16 in) for the row
counts a decode step actually has, dumps its outputs for the cross-variant
bit-exactness check, and probes NaN propagation.
"""
import os
import sys

os.environ.setdefault("TILELANG_PRINT_ON_COMPILATION", "0")

import torch
import tilelang
from tilelang import language as T

from tile_kernels.quant.swiglu_forward_kernel import swiglu_forward_and_per_token_cast_impl

variant = sys.argv[1]
rows_list = [int(a) for a in (sys.argv[2:] or ["96", "512", "4096"])]

print(f"variant={variant} tilelang={tilelang.__file__}")
print(f"clamp_symmetric present: {hasattr(T, 'clamp_symmetric')}")

dev = "cuda"
torch.manual_seed(7)
E, H, LIMIT = 384, 576, 10.0
def make_inputs(real_rows):
    """Deterministic MoE layout: real_rows tokens spread over E experts,
    each expert's block padded to the kernel's token alignment."""
    from tile_kernels.config import get_token_alignment
    A = get_token_alignment()
    base, extra = divmod(real_rows, E)
    counts = [base + (1 if e < extra else 0) for e in range(E)]
    aligned = [(c + A - 1) // A * A for c in counts]
    expanded = sum(aligned)
    psum = torch.tensor([sum(counts[: e + 1]) for e in range(E)], dtype=torch.int32, device=dev)
    mask = torch.zeros(expanded, dtype=torch.bool, device=dev)
    off = 0
    for c, a in zip(counts, aligned):
        mask[off : off + c] = True
        off += a
    assert int(psum[-1]) == real_rows
    x = torch.randn((expanded, 2 * H), dtype=torch.bfloat16, device=dev)
    w = torch.rand((expanded,), dtype=torch.float32, device=dev)
    return x, psum, w


def run_variant(rows, iters=300):
    x, psum, w = make_inputs(rows)
    out, out_sf = swiglu_forward_and_per_token_cast_impl(
        x, "e4m3", 32,
        psum_num_tokens_per_expert=psum,
        topk_weights=w,
        clamp_value=LIMIT,
    )
    torch.cuda.synchronize()
    s, e = torch.cuda.Event(True), torch.cuda.Event(True)
    s.record()
    for _ in range(iters):
        swiglu_forward_and_per_token_cast_impl(
            x, "e4m3", 32,
            psum_num_tokens_per_expert=psum,
            topk_weights=w,
            clamp_value=LIMIT,
        )
    e.record()
    torch.cuda.synchronize()
    us = s.elapsed_time(e) * 1000.0 / iters
    return us, x, psum, w, out, out_sf


results = {}
for rows in rows_list:
    us, *_ = run_variant(rows)
    results[rows] = us
    print(f"rows={rows:5d}  {us:8.2f} us/iter")

# Fixed-seed dump for the cross-variant bit-exactness check.
rows = 512
us, x, psum, w, out, out_sf = run_variant(rows, iters=10)
torch.save({"x": x.cpu(), "psum": psum.cpu(), "w": w.cpu(),
            "out": out.cpu(), "out_sf": out_sf.cpu(),
            "us": {k: v for k, v in results.items()}},
           f"/out/{variant}.pt")

# NaN probe: a NaN gate value must come through the clamp (torch.clamp rule).
x, psum, w = make_inputs(64)
x[0, 0] = float("nan")
out, _ = swiglu_forward_and_per_token_cast_impl(
    x, "e4m3", 32, psum_num_tokens_per_expert=psum, topk_weights=w,
    clamp_value=LIMIT,
)
print(f"nan_probe: row0 has NaN = {bool(torch.isnan(out[0]).any().item())}, "
      f"out[0,:4] = {out[0, :4].tolist()}")
print("OK", variant)
