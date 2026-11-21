# A3 retire-B12X rebase notes

Base: `ab513d36d` (cu13 requirements: nvidia-cutlass-dsl 4.8.1) on the prepared
tree `.work/build/vllm-6d66eed35b0a-b12x-236ddff04a5f-45ffa671/src/vllm`,
branch `a3-retire`. The nine reworked patches in this directory are
`git format-patch ab513d36d..HEAD` exports of the nine commits.

- 0700: rejects resolved (3): `test_deepseek_v41_tilelang_vocab.py` test import swapped to `tilelang.vocab_pack`; `online/packed_bf16.py` docstring reworded for the in-tree TileLang pack; `logits_processor.py` B12X packed-projection import/init/use removed (TileLang `vocab_pack` replaces it).
- 0701: rejects resolved: `common/engram_geometry.py` lands in vLLM (token map, geometry, caps); `common/engram.py` keeps the `get_b12x_preparation_units` stub returning `()` but holds no b12x imports; engram tests read geometry/caps/token map from vLLM instead of `b12x.sequence.engram`/`b12x.preparation`; `test_deepseek_v4_1_sp_prefill.py` drops the b12x skips 0701 targets (4 → 2; the two kept guards belong to tests added after October).
- 0702: clean.
- 0703: clean.
- 0704: rejects resolved: rename `DeepseekV41B12xMetadata(Builder)` → `DeepseekV41Metadata(Builder)` and `DeepseekV41B12xBackend` → `DeepseekV41Backend` in `attention.py`, `ced.py`, `nvidia/model_state.py`, `tilelang/attention.py`, plus the drifted Builder references in `tests/v1/attention/test_b12x_v41_ced_metadata.py`; `cache_dtype_str="b12x_dsv41"` → `"dsv41"`; `"B12X_DSV41_COMPRESSOR"` → `"DSV41_COMPRESSOR"`. `sparse_mla.py` and the remaining files applied cleanly. (The custom-op renames in the patch predate the base: patch 0611 already removed the `torch.library.custom_op` wrappers.)
- 0705: rejects resolved: the `VLLM_DS41_MARKOV_NVFP4` / `VLLM_DS41_DRAFT_NVFP4_HEAD` entries in `vllm/envs.py` (both TYPE_CHECKING and `environment_variables`) and every read in `nvidia/dspark.py` were already gone at the base — the 1107 series removed the optional NVFP4 draft heads and the Markov head now packs BF16 at 12 bits under TileLang; the only remaining hunk, the `VLLM_DS41_PACKED_BF16_LM_HEAD` comment reword ("packed and projected by TileLang"), is applied.
- 0706: clean.
- 0707: empty (no diff): the direct_io/engram_rows pre-build helpers, `_prebuilt_target`/`prebuild`/`_source_digest`, `/opt/spark-ds41f/native` default root, and `test_prebuilt_native_helpers_resolve_without_compiler` are already at the base via the series' own rc17 patch 0581 (same change, authored four days earlier). Applying this patch needs `git apply --allow-empty`.
- 0708: empty (no diff): the tensor-parallel TileLang vision tower and aligner are already at the base via rc17 patch 0582, since evolved by the row-parallel wo/w2 multi-image work (partials now reduce through `rank_order_sum`/`_reduce_rows` rather than `tensor_model_parallel_all_reduce`, `vl_model.py` wires `is_vit_use_data_parallel` plus the DP-sharded tower runner, and the tests carry a superset of the patch's TP3/TP4 cases). Applying this patch needs `git apply --allow-empty`.

Verification: `git worktree add --detach /tmp/a3-verify ab513d36d` and the nine
patches above applied in order with `git apply --allow-empty` all succeed; the
resulting tree equals the branch's HEAD tree (`b91839515c7a11249ff00ff0d0877bc875fc8d43`).
All 43 touched Python files pass `ast.parse`; no `.rej` files remain. In the
touched tests the `importorskip("b12x"` count drops: `test_deepseek_v4_1_engram.py`
and `test_deepseek_v41_engram_rows.py` to 0, `test_deepseek_v4_1_sp_prefill.py`
4 → 2 (the whole-tree count rises because 0706 adds skips to B12X's own tests,
which is that patch's intent).
