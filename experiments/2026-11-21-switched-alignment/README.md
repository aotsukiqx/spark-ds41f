# Upstream alignment with switched-fabric optimization

Status: **plan**; owner directive 2026-11-21 — stay as close to the upstream
repositories as possible, and spend the local optimization budget only on this
site's switched fabric. Nothing here is built, booted or deployed yet; the lock
is untouched.

## Evidence gathered (read-only, 2026-11-20/21)

### The NCCL patch stack is dead weight on a switched site

| patch | acts when | upstream state at 2.32.6 |
| --- | --- | --- |
| `0001` IB CTS nreqs fence | always | **owned upstream** (`0bb8dec4 net_ib: Order CTS nreqs load after the idx check`) |
| `0002` bidirectional switchless rings | `NCCL_SWITCHLESS_BIDIRECTIONAL` set (unset here) | ported only |
| `0003` balanced channels | same env, switchless shapes | dead on 2.32 (tuning moved to `src/tuning/`) |
| `0004` small-ring threads | same env | dead on 2.32 |

On the switched site every patch is either upstream-owned or gated off, so a
**stock `v2.32.6-1` build with zero local patches** is the aligned configuration
and should measure identical. The switchless shapes (ring, triangle) still need
`0002`-`0004` re-expressed before any NCCL promotion covers them.

### Upstream deltas today (fresh watch)

- vLLM LIL `integration/karmic-kraken-beta`: deployed pin `6d66eed3` **is the head**.
- tilelang `b1367a59` → `ac88f5bc` (+2): `4ed9b9e` Layout FFI placeholder-Var
  serialization (matters only when Layouts cross the FFI boundary; ours never
  leave the rank process) and a docs commit — **NO-OP for us**.
- TileKernels v2.1.0 (2026-10-14, upstream quiet since): keeps the deliberate no.
- NCCL `v2.32.6-1`, sparknet `1fd6a1fb`, CUTLASS/CuTe DSL `4.8.1`: all at head.
- Canonical `vllm-project/vllm` main: ~2,700 commits in 5 weeks, **parked** (the
  2026-09-20 rebase cost 14 loader patches and still failed the gates).

### The switched fabric is losing packets in the best-effort class

`roce_traffic_class` is unset in `config/nodes-switched.local.json`, and the
hosts run PFC off on both interfaces (MTU 9000). Cumulative since boot
(~6.3 days), `roce_adp_retrans`/`out_of_sequence` per rail:

| node | rail A | rail B |
| --- | ---: | ---: |
| spark-eb1a | 16,849 / 343,103 | 17,701 / 342,035 |
| spark-141e | 17,383 / 270,745 | 17,676 / 268,476 |
| spark-a89f | 17,975 / 323,914 | 18,563 / 321,911 |
| spark-2fe7 | 18,602 / 367,763 | 19,211 / 365,728 |

Uniform across nodes and rails (not a cable), flat at idle (two samples minutes
apart identical), so it is incast loss in the default class — exactly the
signature `docs/switched-fabric.md` records: an unmarked lossless class protects
nothing, and the external switched-GB10 report measured retransmission-free
174-182 Gb/s with `NCCL_IB_TC=106` against 95→78 Gb/s degrading unmarked.
Prefill chunks at the 16,384 budget all-reduce tens of MB per layer, so this is
the regime where the loss bites.

## Plan

### A. Alignment arms (one window, one variable each, two boots each)

1. **`A1` stock NCCL**: rebuild NCCL `v2.32.6-1` with an empty series for the
   site arm (upstream owns `0001`; the rest is gated off here). Gate: quality
   5/5, decode within the site reference, counter behaviour unchanged. Expected
   verdict: identical; the win is the patch stack, not speed.
2. **`A2` tilelang `b1367a59` → `ac88f5bc`**: unchanged 13-patch series; both new
   commits classified NO-OP. Gate as above; keep the fresh cache namespace rule.
3. Next release folds vLLM `6d66eed3` + CUTLASS 4.8.1 + TileLang (A2's pin) and
   **drops B12X** per `docs/upstreams.md` ("Locks without B12X"); NCCL stays
   `v2.30.7-1` for ring/triangle until `0003`/`0004` are re-expressed.

### B. Switched-fabric optimization (site-only, after or beside A)

1. **`B1` lossless class** — re-scoped after the switch was identified
   (owner, 2026-11-21): the site's switch is a **MikroTik CRS812-8DS-2DQ-2DDQ-RM
   (Marvell 98DX7335, Prestera)**; each Spark reaches it over **one QSFP56**
   (the two HCAs are the two PCIe Gen5 x4 paths behind that one port — the
   DGX Spark user guide's model; all 8 interfaces negotiate 200,000 Mb/s, so
   the official playbook's 100G auto-negotiation trap does not apply). An
   earlier attempt to configure RoCE on the switch broke cluster connectivity
   and was reverted; best-effort is also the official NVIDIA baseline for
   switch clustering (the `multi-sparks-through-switch` playbook configures a
   plain L2 bridge, no PFC). The counters above show the cost of staying
   best-effort is small at our message sizes (bounded by the 1 MiB NCCL buffer
   and 2 MiB one-shot dispatch), so **B1 is a robustness/tail-latency lever,
   not a throughput fix**, and it only counts with a *symmetric* config:

   - switch: RouterOS >= 7.21/7.22 with firmware upgraded after it
     (`lossless-traffic-class`/`lossless-buffers` need the firmware), the
     proven CRS812 recipe from the DGX-Spark deployment notes — `pfc=pfc-tc3`,
     `trust-l3=keep`, DSCP map `roce=tc3, cnp=tc6`, `l2mtu=9500`, and **no
     egress-rate shaping** (the chip's shaper caps at 100G and would halve the
     link); on the QSFP-DD breakout ports, never reset `advertise` or the
     second 200G sub-port drops;
   - hosts: boot-time `dcb app add dev <if> dscp-prio 26:3` +
     `dcb pfc set dev <if> prio-pfc 3:on` on both interfaces of every node;
   - node map: `roce_traffic_class: 106`.

   A half-configured state (switch PFC without host marking, or the reverse)
   reproduces the earlier outage: pause frames land on a priority that carries
   everything and the fabric head-of-line blocks. Acceptance unchanged:
   retrans/oos flat across a 131K and a 500K prefill round, prio-3 counters
   carrying the traffic, prefill/decode unchanged or better.
2. **`B2` `NCCL_BUFFSIZE=2 MiB`**: the one arm of the 2026-11-20 sweep that never
   ran (the sweep aborted). Debug-free, two boots, against the deployed arm's
   control. Note the shaper interaction above does not apply: this arm only
   changes the host-side buffer.
3. **`B3` path asymmetry watch**: the loss is uniform across nodes and both
   PCIe paths, so it is systemic, not hardware; revisit only if marking lands
   and one path stays dirty.

## Blocked on the owner

- The symmetric lossless config for `B1` (RouterOS/firmware version first, then
  the switch-side recipe, then the hosts), or an explicit decision to stay on
  the official best-effort baseline.
- A window for `A1`/`A2`/`B2` (two boots each; ~1 h per arm with the gate).
- The promotion decision for the A3 release.

Nothing above advances `upstreams.lock.json` by itself; each arm is an
experiment under this folder with its own receipts.
