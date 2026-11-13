# Item 2: direct producer writes into the RoCE send buffer — spec

Written from the running `spark-ds41f:1107` image (2026-11-13), read-only. Nothing
here is implemented; the purpose is to fix the change's shape before a window.

## What happens today

`b12x.comm.roce.AllReduce.all_reduce(inp, out=None)` (installed at
`/opt/spark-ds41f/candidate/b12x/b12x/comm/roce/roce_oneshot.py`, ~line 663)
passes two pointers to one CuTe launcher:

| Argument | Meaning |
| --- | --- |
| `src.data_ptr()` | the producer's BF16 output tensor |
| `dst.data_ptr()` | where the reduced result lands |
| `self._send_base` | **the registered RoCE send region**, per collective |
| `self._recv_base` | the registered receive region |
| `stage_counter`, `tail_counter`, `self._epoch_address` | the protocol's epoch/tail handshake |

The launcher copies `src` into the send region, rings the proxy, waits, and writes
the reduction into `dst`. `all_reduce` also stages through
`self._aligned_scratch(...)` when a pointer is not 16-byte aligned. The head of the
file says it plainly: "one kernel launch that stages the input, rings the proxy
thread, waits for".

Measured on the c8 trace: 101–135 `oneshot_allreduce_kernel` launches a step
totalling 15.43 ms (kernel time), while every device-to-device copy in the step
totals **0.017 ms**. So the copy TODO item 2 wants to remove is the intra-kernel
`src -> send region` stage plus the producer→send dependency, not a fleet of
memcpy launches.

## The change

1. **b12x (fork patch): expose the staged slot.**
   `AllReduce.stage_slot(nbytes: int) -> torch.Tensor` returning a view aliasing
   the registered send region for the next collective of that size, and
   `all_reduce_staged(nbytes, out=None)` that runs the launcher with
   `src == slot` so the stage becomes a no-op (the kernel must skip an
   identity copy, or the two pointers are the same and the copy is free).
2. **vLLM producers write into the slot.** `wo.py`'s WO-B epilogue and `moe.py`'s
   `moe_combine` take an extra output buffer and write their final BF16 there
   instead of into a fresh tensor. The collective then consumes the slot.
3. **Slot capacity and capture stability.** A CUDA graph replays fixed pointers,
   so each captured collective needs its own slot: 116 slots of
   `rows x hidden x 2 B` (24 rows, 4,096 hidden = 196 KB -> ~23 MB registered).
   Registered capacity must be raised past the current
   `SPARKNET_ROCE_ALLREDUCE_MAX_BYTES` and checked against the ring's slot
   geometry at startup, not at first use.
4. **Failure mode.** A missing slot, a size change, or a capture without a slot
   must raise (no fallback), consistent with the 2026-10-14 rule.

## Gates before the lever can be claimed

- **Bits:** reduced outputs identical to today's on the release suite (the copy is
  bit-preserving BF16, so the reduction order does not change).
- **A/B:** 16-stream TP4 shape, two boots each, against
  `2026-11-07-spark-ds41f-1107-switched.json`; the claim is 1.3–1.6% of a decode
  step (TODO item 2), and the site's c16 CI is 8–19%, so the point has to be
  quoted on the geometric mean of the 20-shape grid plus c1, not on c16 alone.
- **Memory:** registered slots add ~23 MB of pinned host memory per rank; confirm
  against the 3 GiB steady guard.
- **Overlap:** confirm the stage removal does not lengthen the collective's
  critical path (the send region is written by the producer instead of the
  launcher, so the producer must finish before the ring starts — the same
  dependency, one hop shorter).

## Why it is not attempted in this window

It touches the pinned b12x runtime and two producer kernels, needs a fork patch,
a new image, and an A/B with two boots. That is a candidate cycle, not an edit.
The measurement above already fixed the design constraint that matters: the win
is per-collective dependency, so the A/B must be run on the concurrency point
where collectives dominate (c16), with the grid as the headline.
