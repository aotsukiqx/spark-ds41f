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

## Results

Filled after the window.
