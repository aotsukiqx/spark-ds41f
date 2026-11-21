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

## Results

Filled after the window.
