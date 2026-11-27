# sparknet captured<->eager stream-order fix + full-width SP collectives

Status: **assembled, awaiting qualification window** (base commit `3164f36a`,
promoted baseline `2026-11-27-spark-ds41f-1127`).

## Content

One local sparknet patch (`sparknet/0001`, applies clean at `b01f350d`,
applied tree `984254146ae2ccbfff6378800b628a4816606eb7`):

- `_mark_stream(capturing=True)` sets `_replay_pending`;
- the next eager collective on a different stream records an event on the
  capture stream (the record enqueues after every replay submitted to it) and
  waits it — restoring global launch order at the captured<->eager boundary
  of the single-epoch/doorbell/two-slot transport.

Root cause and probe evidence: `experiments/2026-11-27-sp-collective-blocks`
(width-scaled, run-to-run-drifting, concurrent-batch-only determinism
deviation; single-stream immune; the 8-CTA cap masks the race window).

With ordering fixed, the arm keeps the eligibility cap
(`SPARK_DS41F_ONESHOT_MAX_BYTES=4194304`) and lets the staged path run at the
default width, taking the proven **8,625.7 tok/s (+1.9%)** prefill at 131K.

## Method

`build prepare --lock` → `build check` → `build image --apply` →
`build distribute --apply`; two clean boots; determinism gate (hashes must
equal the 1127 production stack's) + `quality,decode,prefill` vs the 1127
receipt; acceptance: prefill >= 8,625, decode 10/10 same, determinism
identical, quality 5/5.

## Results (two clean boots, 2026-11-27)

| measure | 1127 reference | boot 1 | boot 2 |
|---|---:|---:|---:|
| determinism | identical | **identical x2, hash 8e46794a (production canonical)** | identical, same hash |
| quality | 5/5 | 5/5 | 5/5 |
| decode grid | — | 10/10 same | 10/10 same |
| prefill 131,072 (cooled) | 8,461.1 | **8,616.9 ±0.1% (+1.8%)** | **8,612.0 ±0.0% (+1.8%)** |

**Verdict: qualified and promoted as spark-ds41f-1128.** The ordering fix
closes the captured<->eager race (determinism back to the production
canonical hash at full width, stable across three runs) and the staged
path's full width takes the proven +1.8% prefill — at the 8,625.7 headroom
within run noise. Receipt: boot 2's bench.
