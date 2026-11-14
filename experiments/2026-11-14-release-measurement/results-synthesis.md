# What the improvements bought, and what is left (2026-11-14)

Synthesis of one measurement window on the promoted `1107` image. Every number is
from `results-prefill-boot.md` / `results-cache.md` in this folder, measured today
on the production site with production's own recipe (profiler on for the traces).

## 1. The improvements did what scheduling work can do

| Claim the patch series made | Measurement today |
| --- | --- |
| Launch and dependency overhead removed from decode (PDL `0753`/`0755`/`0756`, native-depth graphs, fused epilogues) | decode step is **98.9% GPU-busy at c1 and 99.25% at c8** (idle 0.49 / 0.77 ms) |
| Collectives overlapped rather than exposed | exposed collective idle is **0.1% of a long prefill** and ~1% of decode; the collectives themselves are 20% of prefill as GPU work |
| The routed MoE epilogue replaced (TileKernels' 22 µs walk → `moe_swiglu_cast`) | the fused kernel is **1.0% of prefill** (742 ms of 71 s) and 1.14 ms per c1 decode step; the release recorded −2.17% ±0.15% for exactly this |
| Sequence-parallel MoE input gathers MXFP8 rows and local routes (`0720`) | no BF16 double-cast appears in the prefill trace; the only BF16 cast kernel is the WO path (`gemm_fp8w_bf16_cast`, 3.2%) |
| Prefix cache serves agent traffic | **99.6%** of a 63K shared prefix served from cache; suffixes do not disturb the prefix; the 256-token block leaves a 242-token tail uncached |
| Boot work (trimmed cold preparation, packed Engram shards) | boot to ready is **124 s**, launch 6 s |
| "First request after a restart is ~0.37 s slower" (TODO) | **does not reproduce**: 0.172 s cold vs 0.159 s warm, 45-token prompt |

Reading: the class of work that removes *idle, launch, host and dependency* time is
exhausted. The GPU is busy 97.5% of a prefill and 98.9–99.25% of a decode step, so
there is almost no idle left to recover — a second decode stream, a persistent MoE
kernel, or more aggressive collective overlap cannot pay, which is what the
lever-by-lever closures in TODO now record.

## 2. What is left is math and bytes, in four places

Long-context prefill (484K tokens, 71.06 s):

| Cost | Share | Why it is hard |
| --- | ---: | --- |
| `indexer_score_kernel` (MXFP4 scoring) | **22.0%** | the indexer evaluates the whole context per chunk; top-k selection is only 1.2% (882 ms), so the bounded radix top-k TODO item is dead — the scoring GEMM's bytes and tiling are the target |
| MoE body (grouped GEMM 18.2% + combine 5.8% + SwiGLU 1.0%) | **25.0%** | expert weight traffic at prefill row counts; MXFP4 already in use |
| `ncclDevKernel_SendRecv` + `AllGather RING` | **20.0%** | sequence-parallel exchange volume; reducing it means fewer/larger collectives or a different partition, not better overlap |
| `sparse_mla_kernel` | **13.1%** | attention at 484K with the sparse layout |

Decode, for comparison (from `experiments/2026-11-13-upstream-primitives/profile-results.md`):
MoE grouped GEMM 23.1 ms of 43.4 ms at c1, L2 prefetch 12.2 ms, `gemm_mxfp8` 6.1 ms,
one-shot all-reduce 4.2 ms. Decode's remaining costs are the same families, so a
change to any of them must be judged on both phases.

## 3. The judgement

The previous rounds bought their stated gains and, more importantly, the whole
regime where those gains were cheap: idle-filling, launch elimination, overlap and
small-kernel fusion are done, and the release is now limited by four kernels that
move bytes. Every remaining lever is a kernel-level algorithmic change with a
2–20% addressable share and no guarantee above the site's CI — which is why the
next round should start from the indexer's scoring pass (22%, the single largest),
not from anything in the old TODO list.

## 4. Corrections this window forces on TODO

- "First request after a restart ~0.37 s slower" — closed, not reproducible.
- "Indexer selection at 200K–1M … screen a bounded radix top-k" — the selection is
  1.2% of prefill; retarget to the scoring pass (22%).
- "Sequence-parallel MoE input ~3.9%" — banked by `0720`.
- "Per-rank pre-processed weight image (largest boot lever)" — boot is 124 s total;
  the lever is worth at most ~90 s and no throughput.
- The decode levers 1/2/4/5/7 are closed (see TODO's dated notes).
