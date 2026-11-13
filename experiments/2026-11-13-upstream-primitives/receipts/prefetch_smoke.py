"""Smoke: the backported prefetch intrinsics compile and run on SM121."""
import os
os.environ.setdefault("TILELANG_PRINT_ON_COMPILATION", "0")
import torch
import tilelang
from tilelang import language as T
from tilelang.cuda.language import prefetch as pf

print("prefetch module:", pf.__file__)
print("exports:", [n for n in dir(pf) if "prefetch" in n])

N, B = 1 << 20, 256

@T.prim_func
def pf_kernel(A: T.Tensor((N,), dtype="float32"), B_: T.Tensor((N,), dtype="float32")):
    with T.Kernel(T.ceildiv(N, B), threads=B) as bx:
        s = T.alloc_shared((B,), "float32")
        T.prefetch_l2(A[bx * B], "evict_last")
        T.copy(A[bx * B], s)
        for i in T.Parallel(B):
            s[i] = s[i] * 2.0
        T.copy(s, B_[bx * B])

a = torch.arange(N, dtype=torch.float32, device="cuda") * 0.001
b = torch.empty_like(a)
k = tilelang.compile(pf_kernel, out_idx=[1])
b = k(a)
torch.cuda.synchronize()
ok = torch.allclose(b, a * 2)
print("prefetch_l2 kernel ran, result ok:", bool(ok))
assert ok
print("OK prefetch-smoke")
