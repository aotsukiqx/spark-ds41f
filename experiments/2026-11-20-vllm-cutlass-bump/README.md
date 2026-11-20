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

## Measured and deployed (2026-11-20)

Image `spark-ds41f:1107-vllm-6d66-cutlass-4.8.1` (`sha256:ef08fbb2…`), built on the
head in 51 s once the buildx cache was warm, GPU import smoke passed. The
`import vllm` inside the image resolves to `/opt/spark-ds41f/candidate/vllm`
(tree `e5a1f99d`, patch head `ab513d36`), whose `requirements/cuda.txt` pins
`nvidia-cutlass-dsl[cu13]==4.8.1`; the base image's stale site-packages
metadata (`==4.7.1`) does not govern imports.

Three build-time blockers were resolved on the way, each a real defect for any
candidate that moves the CuTe DSL pair:

- the runtime-core consumer check validated the **base image's** vLLM metadata;
  vLLM's check moved to the final stage that reads the candidate's
  `requirements/cuda.txt`, and `nvidia-cutlass-dsl` joined that shared set;
- the runtime-core import check asserted a literal `4.7.1`; it now asserts the
  installed version equals the lock's `CUTLASS_DSL_VERSION` build argument;
- B12X's own metadata pinned 4.7.1; the candidate runs the authoritative
  lil-rebase series (which already drops the obsolete 4.7.1 patch) plus `0013`
  for 4.8.1. `bin/spark build prepare` also gained lockfile-scoped wheel hashes,
  so the promoted 1107 wheel set stays reproducible.

**Release tests** (150 gate files, split 38/38/37/37 across the four nodes,
`scripts/lab.py kernel-local` with the cluster stopped): **9734 passed, 311
skipped, 0 failed**, about 32 minutes wall clock. Receipts in
`receipts/release-tests/<node>/`.

**Boots** (site shape, unchanged): API ready at +122.2 s and +126.9 s with the
warm TileLang namespace; quality 5/5 on both.

| point | reference | Group A boot 1 | boot 2 | Δ1 | Δ2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| prose-c1 | 27.48 | 27.61 | 27.39 | +0.5% | −0.3% |
| prose-c2 | 31.07 | 28.29 | 34.12 | −9.0% | +9.8% |
| prose-c4 | 37.76 | 30.45 | 34.80 | −19.4% | −7.8% |
| prose-c8 | 38.33 | 41.38 | 38.54 | +8.0% | +0.5% |
| prose-c16 | 51.42 | 54.08 | 47.06 | +5.2% | −8.5% |
| code-c1 | 29.78 | 30.46 | 30.44 | +2.3% | +2.2% |
| code-c2 | 37.73 | 34.12 | 32.49 | −9.6% | −13.9% |
| code-c4 | 39.95 | 40.34 | 40.44 | +1.0% | +1.2% |
| code-c8 | 42.18 | 46.12 | 47.94 | +9.3% | +13.7% |
| code-c16 | 58.63 | 64.70 | 61.85 | +10.3% | +5.5% |

No point is outside the reference's combined interval on both boots, so no speed
claim. The vLLM/CUTLASS move is decode-neutral against the three b1367 samples
(mean step difference within ±5% everywhere), which is what a base refresh plus
a header/wheel bump should be. `prose-c2`'s b1367 readings (−8% on three tight
samples) do **not** reproduce here (−9% then +9.8%), so that earlier signal is
noise; `prose-c4` remains the only repeatable direction (faster on every boot of
both candidates) without a passing repeat rule.

**Deployed to the site:** all four nodes serve
`spark-ds41f:1107-vllm-6d66-cutlass-4.8.1` at the unchanged shape, node
checkouts detached at the commit below, `doctor --live` clean except the
pre-existing `nvidia-drm fbdev=N` deviation. Not a repository promotion: the
promoted lock, cluster config and manifests still name `spark-ds41f-1107`.
Rollback options: the b1367 arm (its image and namespace are intact) or the site
profile (`1107`).
