# A1: stock NCCL 2.32.6-1 on the switched site

Status: **measurement**; the alignment arm of the owner's upstream-first
directive. One variable: the NCCL patch series (one ported patch -> empty).
Everything else is the deployed site stack
([arm-tp4-switched.json](arm-tp4-switched.json) extends the site profile, so it
carries `NCCL_BUFFSIZE=2 MiB` from the recipe promotion).

## Why

On the switched site all four `patches/nccl` patches are dead weight:

| patch | acts when | state at 2.32.6 |
| --- | --- | --- |
| `0001` IB CTS nreqs fence | always | **owned upstream** (`0bb8dec4`) |
| `0002` bidirectional switchless rings | `NCCL_SWITCHLESS_BIDIRECTIONAL` (unset here) | ported only |
| `0003` balanced channels | same, switchless | dead on 2.32 |
| `0004` small-ring threads | same | dead on 2.32 |

Expected verdict: **identical** to the deployed arm — quality 5/5, decode and
prefill within the B2 reference (8,716 / 7,040 tok/s), retrans/oos flat. The
win is the patch stack (the switched fabric carries no NCCL delta), not speed.

## Method

Window: stop production, `build prepare --lock`, `build check`,
`build image --apply --tag spark-ds41f:1107-nccl-2.32.6-stock`, two boots of the
arm with the gate (`quality,decode` 4 samples, `--allow-mismatch --cool-below
0`), then restore the deployed profile. Acceptance: no point outside the
deployed arm's same-session interval, the smoke's `ncclGetVersion` still 23206,
and the image label `nccl.tree` equals the upstream revision `ad2d192c…`.

## Results (window 2026-11-21)

Image `spark-ds41f:1107-nccl-2.32.6-stock` (`sha256:7cf12438…`) built on the
head in 442 s (MemAvailable floor 113.2 GiB), all smokes passed, distributed
over the fabric links. Live identity verified: `nccl==2.32.6`, label
`nccl.tree=331c032a…` (upstream `ad2d192c`, zero patches).

| measure | deployed arm (1 patch) | A1 boot 1 | A1 boot 2 |
| --- | ---: | ---: | ---: |
| prefill 131,072 | 8,661.1 / 8,716.2 | 8,626.9 ±0.6% | **8,696.9** |
| prefill 524,288 | 6,988.3 / 7,039.9 | 6,980.1 ±1.2% | **7,023.0** |
| `prose-c1` / `code-c1` step | 27.81-27.93 / 30.15-30.52 ms | 27.60 / 30.53 | in band |
| quality | 5/5 | 5/5 | 5/5 |
| retrans / oos | flat | flat | flat |

Boot 2's combined load again tripped the bench's thermal guard
(spark-141e 82 °C); the prefill-only rerun from 65-70 °C completed with the
numbers above. Every value sits inside the deployed arm's own boot-to-boot
spread.

**Verdict: stock NCCL is identical to the patched arm on this site**, as the
patch analysis predicted — the switched fabric carries no NCCL delta worth
keeping. Per the owner's upstream-first directive the site profile moves to
the stock image; the 11-20 arm and image remain the rollback. Receipts:
`results/private/bench/2026-11-21-a1-stock-boot{1,2}/`, `-prefill/`.

Correction during the window: the A1 lock initially shared the 11-20 arm's
`source_manifest`, so `prepare --lock` recorded the empty series against the
patched arm and the deployed profile's doctor refused to restart. The locks
now carry separate manifests (`experiments/2026-11-21-a1-stock-nccl/source.json`).
