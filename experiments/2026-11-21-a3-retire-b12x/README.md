# A3: retire B12X from the serving image

Status: **measurement pending** (source preparation complete). The final
alignment arm: the site stack with **no B12X in the lock, the image or the
labels** — the packed BF16 head packs with in-tree TileLang (`0700`), Engram's
token map/geometry/caps live in vLLM (`0701`), MXFP4-CSF leaves the package and
the `b12x` load format goes (`0702`/`0703`), the V4.1 cache layout is named
(`0704`), and B12X's own tests skip without it (`0706`).

## Series

The 11-20 production series (641) plus reworked retire patches, renumbered:

| patch | content | state |
| --- | --- | --- |
| 0700 | packed BF16 head packs with TileLang `vocab_pack` | 3 rejects resolved (vocab test import, packed_bf16 docstring, logits_processor B12X packed projection) |
| 0701 | Engram token map/geometry/caps in `common/engram_geometry.py` | rejects resolved; `get_b12x_preparation_units` stays as a `()` stub |
| 0702/0703 | MXFP4-CSF out of the DS4.1 package; `b12x` load format removed | clean |
| 0704 | `DeepseekV41B12x*` → `DeepseekV41*` renames, `b12x_dsv41` → `dsv41` | rejects resolved across attention/ced/model_state/tilelang-attention/tests |
| 0705 | NVFP4 head switches | **already gone at base** (the 1107 series removed them); only the packed-head comment reword remains |
| 0706 | B12X's own preparation tests skip without B12X | clean |
| 0707/0708 | direct_io/engram pre-build; TP TileLang vision tower | **TODO- placeholders: content already at base via the 1107 series (rc17 0581/0582)** |

`REBASE-NOTES.md` in `vllm/` carries the per-patch detail. Verification: nine
commits on `a3-retire` in order; a pristine worktree of the vLLM base
`ab513d36d` accepts the exported series and its tree equals the branch HEAD
(`b91839515c7a`); all 43 touched files pass `ast.parse`.

## Method (window)

Stop production; on the head `build prepare --lock` (the lock has no
`sources.b12x`; the image's smoke must confirm B12X is not installed),
`build check`, `build image --apply --tag spark-ds41f:a3-no-b12x`, `build
distribute --apply`; two boots with the gate (`quality,decode`, `--allow-mismatch
--cool-below 0`) and a cooled 131K prefill (524K referenced from the same-day
stack runs — spark-141e's thermal ceiling). Expected: identical to the adopted
A2 stack (c1 ~27.7/30.2 ms, prefill 131K in the 8,627-8,716 spread), plus the
image-level proof that nothing imports B12X.

## Results

Filled after the window.
