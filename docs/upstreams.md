# Upstreams and contribution flow

`upstreams.lock.json` is the promoted machine-readable authority. An experimental
cluster profile may select a separate repository-relative lock through
`upstreams_config`; build preparation, doctor and image builds use that lock.
This lets candidates add patches without changing the promoted image identity.
The production chain (revisions and series in `upstreams.lock.json`; the image in
`config/cluster.json`) is:

```text
local-inference-lab/vllm integration/karmic-kraken-beta
        (canonical base vllm-project/vllm, parked)
        + the release's vLLM series (Engram projection TP padding and
          asynchronous rows, multimodal block hashes, DSpark verification
          rules, sequence-parallel prefill, explicit collective policy,
          packed BF16 output head, display carve-out weights, the TileLang
          kernel family for every serving kernel, sparknet collectives,
          the SPARK_DS41F_* variables)
                    \
local-inference-lab/b12x (archived; absent from the lock since
        spark-ds41f-1122, see "Locks without B12X")
                    |
tile-ai/tilelang main (0.1.16)
        + patches (SM120/SM121 block-scaled MMA: MXFP8, FP8 x FP4, MXFP4;
          0003/0007/0011 reworked onto the 0.1.16 parallel-compilation
          rewrite, 0012 re-keyed to the pre-metadata tree)
deepseek-ai/TileKernels main (2.1.0) + the release's tile_kernels series
christopherowen/dgx-spark-networking (sparknet 0.5.0)
                     ---- spark-ds41f:<vLLM base>-<release>
                    /
NVIDIA/nccl v2.32.6-1
        + an empty series (the switched fabric carries no local NCCL
          patches), replacing the base image's nvidia-nccl-cu13 libnccl.so.2

deepseek-ai/DeepSeek-V4.1-Flash-1017 (the recipe's model; unchanged, and TP3
        head padding is in the serving source, so no config overlay is mounted)
```

The official vLLM nightly at `af1c0149` supplies the CUDA/runtime base, including
FlashInfer 0.6.18.post1; only vLLM's two stable CUDA extensions are rebuilt for
SM121 against CUTLASS v4.8.1. Canonical vLLM main is parked while the Local
Inference Lab integration branch is the serving source.


**The spark-eb1a site runs exactly this chain** since the spark-ds41f-1126
promotion (2026-11-26): the root lock is the site stack (vLLM `6d66eed3`,
CUTLASS/CuTe DSL 4.8.1, TileLang `640fdcae` / wheel `0.1.16+snapshot.c74164b9`,
TileKernels `c1cf914a` 2.1.0, sparknet `1fd6a1fb`, **NCCL 2.32.6-1 with an
empty series** — on the switched fabric every local NCCL patch is
upstream-owned or switchless-gated) and the site profile inherits it. Candidate
locks still own their `source_manifest` and patch-series files outright; sharing
either with another arm corrupts build identities. A TileLang pin refresh re-keys
the series' `0012` to the new pre-metadata tree (the wheel-version assert fails
otherwise). Promotion records: `experiments/2026-11-26-spark-ds41f-1126`
(plus the single-variable arms `experiments/2026-11-26-tilelang-0116`,
`experiments/2026-11-26-tilek-210`; the rejected sparknet 0.6.0 arm is
`experiments/2026-11-26-sparknet-060`).

## Source map

| Lock key | Canonical upstream | Contribution fork | Purpose |
|---|---|---|---|
| `vllm` | `local-inference-lab/vllm` (`integration/karmic-kraken-beta`) | `christopherowen/vllm` | serving source; canonical `vllm-project/vllm` main is parked |
| `vllm_base_image` | `docker.io/vllm/vllm-openai` | not applicable | official CUDA/Torch/native-extension foundation |
| `b12x` | `local-inference-lab/b12x` (`integration/karmic-kraken-beta`, archived) | none (archived) | spark-ds41f-1025 and earlier: the checkpoint loader (`--load-format b12x`) and modules vLLM still imports; no B12X kernel runs in serving. Not listed from the release after next |
| `nccl` | `NVIDIA/nccl` (tag `v2.30.7-1`) | not created yet | the base image's NCCL version, rebuilt for SM121 with `patches/nccl` |
| `tilelang` | `tile-ai/tilelang` (`main`) | `christopherowen/tilelang` | the promoted kernel compiler, with `patches/tilelang` for SM120/SM121 |
| `tile_kernels` | `deepseek-ai/TileKernels` (`main`) | not created yet | DeepSeek's TileLang kernels: MoE gate, casts, mHC |
| `sparknet` | `christopherowen/dgx-spark-networking` (`main`) | not applicable | one-shot RoCE collectives for the TileLang family |
| `flashinfer` | `flashinfer-ai/flashinfer` | not created yet | not a promoted build input (the runtime base supplies 0.6.18.post1) |
| `cutlass` | `NVIDIA/cutlass` | not created yet | SM121 stable-extension headers at `v4.7.1` |
| `cutlass_dsl` | NVIDIA packages on PyPI | not applicable | SHA-256-locked ARM64 CuTe DSL wheel set |
| `cuda_toolkit` | NVIDIA's Ubuntu 24.04 SBSA CUDA apt repository | not applicable | optional, listed only by a lock that builds on it: SHA-256-locked CUDA 13.5 toolchain and math-library packages over the base image's CUDA 13.0.2 ([docker/README.md](../docker/README.md#cuda-toolkit)) |
| `model` | `deepseek-ai/DeepSeek-V4.1-Flash` | not applicable | unchanged native model weights and tokenizer |

The URL and full immutable revision in `upstreams.lock.json`, not a directory
name or Docker tag, define identity. The `tracking_ref` says which canonical
branch to inspect for future pulls; it does not float the build.

## Refreshing an upstream

Prepare an isolated tree:

```sh
bin/spark upstream prepare vllm
bin/spark upstream prepare b12x
```

The helper clones the canonical repository as `upstream`, adds Christopher's fork
as `origin` when one exists, checks out the full pinned SHA, initializes pinned
submodules where required, applies recorded upstream commits, and then applies
the local series. Worktrees live under ignored `.work/upstreams/`.

To evaluate a newer upstream, create a branch in that prepared tree, rebase the
small patch series, build a new immutable image tag, and record it as an experiment.
Do not advance `upstreams.lock.json` merely because a newer commit exists.

Shared runtime packages move forward, never back. CuTe DSL is used by vLLM,
quack-kernels, FlashInfer, the cuDNN frontend and B12X (while a lock lists it); the
locked wheel set in
`requirements/cutlass-dsl-aarch64.txt` must satisfy every one of them and must
not be older than the version the vLLM base image installs. When a component
pins an older version, patch the component's pin forward and qualify it rather
than downgrading the others. The image build checks each consumer's declared
requirement and fails on a mismatch.

## Locks without B12X — done since spark-ds41f-1122

The promoted lock (2026-11-22) has no `b12x` entry: its vLLM series carries what
serving still took from B12X (the direct loader, the packed BF16 head's in-tree
TileLang packer, Engram's geometry in `vllm/models/deepseek_v4_1/common/engram_geometry.py`;
the retirement itself is [experiments/2026-11-21-a3-retire-b12x](../experiments/2026-11-21-a3-retire-b12x/README.md)).
`bin/spark build` prepares no B12X project or context for such a lock, builds the
TileLang runtime on `runtime-core` (`TILELANG_BASE_STAGE`), records no B12X labels,
and its image smoke checks that B12X is not installed (the running image reports
`find_spec("b12x") is None`). The recipe loads with `--load-format direct` and an
empty `VLLM_PLUGINS`.

Locks that list `b12x` (spark-ds41f-1107 and earlier) still build exactly as
before; the last such promoted lock is
[`2026-11-07-spark-ds41f-1107`](../manifests/baselines/2026-11-07-spark-ds41f-1107.json).

## Contributing back

Standing policy (owner, 2026-11-22): this deployment absorbs valuable code and
ideas from upstream; it does not currently open PRs. Local work is published on
the fork only (`aotsukiqx/spark-ds41f`). The procedure below applies when a
contribution is actually made.

One conceptual local patch should become one upstream branch and pull request.
Preserve tests and benchmark evidence alongside it. After acceptance:

1. advance the pinned upstream revision to include the merged commit;
2. remove the redundant local patch from `series`;
3. rebuild once and distribute the same digest;
4. reproduce the accepted baseline before promotion.

B12X is archived (the lock pins its last commit), so it gets no contribution fork
and its `contribution_remote` stays `null`. FlashInfer and CUTLASS have no fork yet:
add one only when creating the first contribution, and do not invent a fork URL or use
this deployment repository as their `origin`.

The GLM switchless repository is recorded as a research reference, not an
upstream. Ideas may be reimplemented and measured, but its topology- and
model-specific patches do not enter our patch stack implicitly.

The complete research-reference watchlist, review questions, and adoption gates
are maintained in [inspiration.md](inspiration.md). Entries under `references` in
`upstreams.lock.json` are deliberately excluded from build preparation.
