#!/bin/bash
# Three-variant clamp bench inside the production image (side container).
set -eux
export TILELANG_CACHE_DIR=/tmp/tljit
export TRITON_CACHE_DIR=/tmp/tritonjit
export XDG_CACHE_HOME=/tmp/xdg
python3 -m pip install --quiet --no-deps --target /out/tlnew /out/tilelang-*.whl
grep -c "clamp_symmetric" /src/tk-patched/tile_kernels/quant/swiglu_forward_cuda.py
cd /bench
echo "=== OLD: image tilelang + pristine TileKernels"
PYTHONPATH=/src/tk-orig python3 bench_clamp.py old 2>&1 | grep -v "^INFO"
echo "=== MID: image tilelang + patched TileKernels (Select clamp)"
PYTHONPATH=/src/tk-patched python3 bench_clamp.py mid 2>&1 | grep -v "^INFO"
echo "=== NEW: backported tilelang + patched TileKernels (clamp_symmetric)"
PYTHONPATH=/out/tlnew:/src/tk-patched python3 bench_clamp.py new 2>&1 | grep -v "^INFO"
echo "=== COMPARE"
python3 compare_clamp.py
echo "=== PREFETCH SMOKE (new tilelang only)"
PYTHONPATH=/out/tlnew python3 prefetch_smoke.py 2>&1 | grep -v "^INFO" || echo "prefetch smoke FAILED (non-fatal for clamp verdict)"
