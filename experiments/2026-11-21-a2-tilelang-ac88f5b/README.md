# A2: TileLang pin `b1367a59` → `ac88f5bc`

Status: **measurement**; the second alignment arm. One variable: the TileLang
pin (+2 upstream commits, both classified NO-OP for us — `4ed9b9e` keeps
placeholder Var bindings alive across FFI serialization, which only matters
when Layout objects cross a process boundary, and `ac88f5bc` is documentation).
The 13-patch SM120/SM121 series is byte-identical.

## Why

The owner's upstream-first directive: keep tracked upstreams at their heads
when the local delta is unaffected. The pin refresh was already judged neutral
at `b1367a59` (2026-11-19, two boots); `ac88f5bc` is two commits further.

## Method

Window: stop production; on the head `build prepare --lock` (fills the snapshot
version and the tilelang tree into the arm), `build check`,
`build image --apply --tag spark-ds41f:1107-tilelang-ac88f5b`, `build
distribute --apply`; two boots with the gate (`quality,decode` 4 samples,
`--allow-mismatch --cool-below 0`) and a cooled prefill pass (131K/524K);
restore the site profile. Expected verdict: identical to the site stack
(prefill 8,716 / 7,040 tok/s references, c1 steps 27.8/30.2-30.5 ms, quality
5/5, retrans/oos flat). A fresh TileLang cache namespace appears on first boot
(cold boot budget ~880 s; the second boot reuses it).

## Results (window 2026-11-21)

Image `spark-ds41f:1107-tilelang-ac88f5b` (`sha256:39263b11…`) built in 508 s
after re-keying `0012` to the new pre-metadata tree `32a1488d` (the wheel
reports `0.1.15+snapshot.32a1488d…`, tree `c3b54074`). Cold boot +886.2 s
(fresh namespace), warm boot +118.7 s. The site's thermal guard aborted every
524K prefill attempt this window (spark-141e rides 3-5 °C from its limit after
the decode gate), so 524K is referenced from A1's same-day numbers on the same
stack; 131K was measured after a long cooldown:

| measure | site references (same day) | A2 boot 1 | A2 boot 2 |
| --- | ---: | ---: | ---: |
| quality | 5/5 | 5/5 | 5/5 |
| `prose-c1` / `code-c1` step | 27.60-27.93 / 30.15-30.53 ms | 27.97 / 30.62 | 27.71 / 30.22 |
| prefill 131,072 | 8,627-8,716 | (thermal abort) | **8,653.0** after cooldown |
| prefill 524,288 | 6,980-7,040 (A1, same stack) | not measurable this window | — |
| retrans / oos | flat | flat | flat |

**Verdict: identical within the same-day spread** — the two upstream commits
are NO-OP for our paths, as classified. **Adopted**: the site profile now runs
`spark-ds41f:1107-tilelang-ac88f5b` (vLLM `6d66eed3`, CUTLASS 4.8.1, TileLang
`ac88f5bc`, stock NCCL `2.32.6-1`, 2 MiB buffer); the A1 image remains the
rollback. Receipts: `results/private/bench/2026-11-21-a2-ac88f5b-*`.
