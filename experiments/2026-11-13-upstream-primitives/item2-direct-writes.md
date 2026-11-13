# Item 2: direct producer writes into the RoCE send buffer — closed by the runtime's structure

Written from the running `spark-ds41f:1107` image (2026-11-13), read-only. The
first version of this file proposed per-collective slots; reading the installed
runtime and the live capacity settings shows that design does not exist and
cannot be added at acceptable cost. This is the corrected record.

## What the runtime actually does

`b12x.comm.roce.AllReduce` (installed at
`/opt/spark-ds41f/candidate/b12x/b12x/comm/roce/roce_oneshot.py`):

| Fact | Source |
| --- | --- |
| `slot_bytes = align_up(max(max_size, max_gather_bytes), _SLOT_ALIGNMENT)`, then `Layout(world_size, slot_bytes)` — **one send region per peer, sized for the largest message** | lines ~372-375 |
| `all_reduce(inp, out)` hands one CuTe launcher `src`, `dst`, `_send_base`, `_recv_base`, epoch and tail counters; the kernel stages `src` into the send region, rings the proxy, waits | lines ~663-760 |
| Live settings | `SPARKNET_ROCE_ALLREDUCE_CAPACITY_BYTES=2097152`, `SPARKNET_ROCE_ALLGATHER_MAX_BYTES=4194304`, `SPARKNET_ROCE_ALLREDUCE_DISPATCH_MAX_BYTES=2097152` — so one slot is 4 MiB, reused by every collective in the step |
| Measured cost | 101–135 `oneshot_allreduce_kernel` launches a step, 15.43 ms of kernel time at c8 (114 µs each), while **all device copies in the step total 0.017 ms** |

## Why the lever does not pay

1. **The copy being removed is 0.2 µs of bandwidth.** A 196 KB stage at ~1 TB/s,
   116 times a step, is ~23 µs — 0.05% of a decode step. The 114 µs each
   collective costs is ring latency and the single-slot sequencing, not the copy.
2. **The single slot is the binding constraint.** Per-collective slots would need
   116 × 4 MiB = **464 MiB of pinned host memory** per rank, which the GB10's
   unified memory cannot afford beside the 10.5 GiB KV pool and the 3 GiB steady
   guard. Without per-collective slots, producers cannot run ahead of the
   collectives that will consume their output.
3. **What remains is a dependency hop**: the ring could start as soon as the
   producer's last store lands instead of after a stage kernel reads it. Bounded
   by a few microseconds per collective — ~0.2-0.5% of a step at best, below the
   site's c16 CI (8-19%) and below its c1 CI (2-4%).

**Verdict: closed.** Not implemented, not scheduled. Reopening requires either a
runtime that sequences collectives from a pool smaller than one slot per
collective (so a producer can target the slot the *next* collective will read) or
an engine that issues fewer, larger collectives per step, so that per-collective
slots fit in pinned memory. Neither exists today, and TODO item 2's 1.3–1.6% is
not supported by the copy's measured size.

## What would have to be measured first

If a future runtime offers a slot *ring* of, say, eight slots (32 MiB), the
question becomes whether the producer can run eight collectives ahead inside the
captured graph. That is a property of the graph's dependency structure, readable
from the same traces: count the collectives whose predecessor kernel is a
producer and whose consumer follows within N kernels. Until such a ring exists,
there is nothing to A/B.
