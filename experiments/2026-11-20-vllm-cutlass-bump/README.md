# Group A pre-judgment: vLLM `6d66eed3` + CuTe DSL / CUTLASS `4.8.1`

Status: **analysis only**, nothing built, lock untouched. Requested 2026-11-20 after
the tilelang pin refresh.

## What "Group A" is

One candidate carrying the matched dependency set:

| component | from | to |
|---|---|---|
| `vllm` | `19f2c20e` (LIL `integration/karmic-kraken-beta`) | `6d66eed35b0a` (2026-10-15, +13) |
| vLLM requirement | `nvidia-cutlass-dsl[cu13]==4.7.1` | `==4.8.1` (one line) |
| `cutlass_dsl` | 4.7.1 wheel set | 4.8.1 wheel set (hashes regenerated) |
| `cutlass` | `v4.7.1` headers | `v4.8.1` headers |

## Method

Fresh shallow clone of `local-inference-lab/vllm` at the new head, then the
promoted series (`experiments/2026-10-26-spark-ds41f-candidate/1107/vllm/series`,
641 patches) applied in order with `git apply --reject` followed by `git add -A`,
so a rejected hunk does not cascade into false failures in later patches. A naive
`git am` run reports six failures; that is cascade noise (four of them retry the
same `tests/tokenizers_/test_deepseek_v41.py` context after the first rejection).

## Result: effectively clean

| measure | value |
|---|---:|
| patches in the promoted series | 641 |
| applied cleanly | 639 |
| patches with rejected hunks | **2** |

1. **`0227-DeepSeek-V4.1-encoding-control-token-spellings-in-re.patch`** — one
   rejected hunk in `vllm/tokenizers/deepseek_v41.py` (naive `git am` reports the
   context at line 76). Upstream `7f68ef19` also edits that file (+2 lines).
2. **`0645-fix-anthropic-keep-mid-conversation-system-messages-.patch`** — seven
   rejected files, because it is *our local copy of upstream `7f68ef19`*:
   `vllm/entrypoints/anthropic/serving.py`, `scale_out/render/serving.py`,
   `tokenizers/deepseek_v3{2,4}.py`, `tokenizers/deepseek_v41.py` and the two
   test files. Upstream now carries the fix **with tests** (137 + 6 changed test
   lines), so the resolution is to delete this patch, not to rebase it.

Everything else — the DeepSeek model, TileLang kernel family, DSpark, Engram,
collective and scheduler patches — applies on the new base untouched.

## The rest of the set

- **Requirement line**: `requirements/cuda.txt:31` is
  `nvidia-cutlass-dsl[cu13]==4.7.1`. Our series edits the same file only at
  lines 19–25 (`tilelang==0.1.12` → `0.1.15`), so a separate hunk on line 31
  does not overlap textually.
- **4.8.1 artifacts exist for this platform**: `nvidia_cutlass_dsl-4.8.1-py3-none-any.whl`
  plus `nvidia-cutlass-dsl-libs-{base,core,cu12,cu13}` `cp312-manylinux_2_28_aarch64`.
  `requirements/cutlass-dsl-aarch64.txt` must be regenerated with their SHA-256s;
  the other consumers accept it (`quack-kernels>=4.7`, `flashinfer>=4.6.2a0`,
  `nccl4py~=4.6`, `cudnn-frontend>=4.6.2`). Only vLLM's exact `==4.7.1` blocks it,
  which the one-line patch lifts.
- **CUTLASS 4.8.1 headers**: no static conflict can be shown; the two stable
  extensions (`_C_stable_libtorch`, `_moe_C_stable_libtorch`) include CUTLASS/CuTe
  headers for SM121 block-scaled MMA, so this is a build-time gate. If the headers
  moved an API, the failure is a compile error in the image build, not a silent
  one.

## Verdict and steps

Feasible with small rework; nothing here looks like a multi-day rebase.

1. Copy the vLLM series to the candidate folder; drop `0645` and note that
   upstream owns the fix.
2. Rebase `0227`'s single hunk onto the new tokenizer file (upstream added two
   lines nearby; read the `.rej` against the new context).
3. Add the `==4.8.1` requirement hunk; regenerate
   `requirements/cutlass-dsl-aarch64.txt`; set the lock's `cutlass` release tag
   and revision to `v4.8.1`.
4. Build (`build prepare --lock`, `check`, `image --apply`), run the release-test
   bundle and two site boots, and judge with the same rule used for the TileLang
   refresh.

Residual risk is concentrated in the CUTLASS 4.8.1 header compile and in vLLM
runtime code that may call a CuTe DSL API changed between 4.7.1 and 4.8.1; both
surface in the build or the boot, not in the patch application.
