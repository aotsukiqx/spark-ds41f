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
`build check`, `build image --apply`, `build distribute --apply`; two clean
boots (containers removed first — `--replace` reuses an existing stopped
container by that name and must not be trusted for an image change) with the
gate (`quality,decode`, `--allow-mismatch --cool-below 0`) and a cooled 131K
prefill (524K referenced from the same-day stack runs — spark-141e's thermal
ceiling).

## Results (window 2026-11-21; five build rounds, r1-r4 preserved as evidence)

Four runtime defects surfaced one per boot and were fixed into the series
(receipts under `runs/failed-starts/`):

| round | defect | fix (folded into the series) |
| --- | --- | --- |
| r1 (tree 98aadb51) | `NameError: build_geometry` — engram.py lacked the in-tree geometry import | 0701 imports `common.engram_geometry` |
| r2 (tree 49a952a6) | `'str' object has no attribute 'layer_ids'` — the reworked `ParallelEngramEmbedding` kept an October `plan` parameter the call site no longer passes | 0701 signature is `(caps, geometry, table_memory)` |
| r3 (tree 329650ee) | the r2 rebase dropped the r1 import fix | re-added; exports now grep-verified before build |
| r4 (tree 51554e28) | `ImportError: get_b12x_packed_bf16_vocab_projection` — packed_bf16.py kept the removed B12X accessor in three fallback branches | the packed head is TileLang-only (`is_supported`, `pack`, `packed_weight`); zero `get_b12x_packed` references remain |

**r5 (`spark-ds41f:a3-no-b12x-r5`, vLLM tree `51554e28`, sha recorded in the
profile) booted clean on the first try** and measures:

| measure | A2 reference | A3 boot 1 | A3 boot 2 |
| --- | ---: | ---: | ---: |
| quality | 5/5 | 5/5 | 5/5 |
| `prose-c1` / `code-c1` step | 27.71-27.97 / 30.22-30.62 ms | 28.00 / 30.80 | 27.79 / 30.30 |
| prefill 131,072 | 8,653-8,716 | **8,654.7** (cooled) | — |
| retrans / oos | flat | flat | flat |
| B12X in container | installed (unused loader modules) | **not installed** | **not installed** |

**Verdict: identical within the same-day spread, with B12X gone from the image,
the lock and the labels. Adopted**: the site profile runs
`spark-ds41f:a3-no-b12x-r5` on the A3 lock (648 active vLLM patches; 0707/0708
TODO- placeholders); A2's image remains the rollback. The next release folds
this into the recipe per docs/upstreams.md "Locks without B12X". Receipts:
`results/private/bench/2026-11-21-a3-r5-*`, `runs/failed-starts/`.
