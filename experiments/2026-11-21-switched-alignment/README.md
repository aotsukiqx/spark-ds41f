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

Correction (verified 2026-11-21): the hosts were never unmarked. The pinned
sparknet renderer decides marking by transport (`SWITCHED_TRAFFIC_CLASS = 106`
for `oneshot-switched`, `sparknet/topology/nodes.py`; the node-map
`roce_traffic_class` field is informational at this revision), and the live
container has carried `NCCL_IB_TC=106` + `SPARKNET_ROCE_TRAFFIC_CLASS=106` all
along. The unconfigured side is the **switch**: without its QoS block the DSCP
26 label is ignored and everything rides the default best-effort queue, which
is where these losses come from. The hosts also ran PFC off and no dscp-prio
map, so the NICs put the marked traffic in the prio-0 queue and would not
honour pauses. Cumulative since boot (~6.3 days), `roce_adp_retrans`/
`out_of_sequence` per PCIe path:

| node | path A | path B |
| --- | ---: | ---: |
| spark-eb1a | 16,849 / 343,103 | 17,701 / 342,035 |
| spark-141e | 17,383 / 270,745 | 17,676 / 268,476 |
| spark-a89f | 17,975 / 323,914 | 18,563 / 321,911 |
| spark-2fe7 | 18,602 / 367,763 | 19,211 / 365,728 |

Uniform across nodes and paths (not a cable), flat at idle, so it is incast
loss in the default class. Prefill chunks at the 16,384 budget all-reduce tens
of MB per layer — the regime where the loss bites as tail stalls.

## B1 host side: applied and verified (2026-11-20 15:0xZ window)

Owner-declared maintenance. Production stopped once (~20 s), then on all four
nodes: `spark-ds41f-dcb.service` (oneshot, enabled, `Before=docker.service`)
applying `dcb app replace dev {enp1s0f1np1,enP2p1s0f1np1} dscp-prio 26:3` and
`dcb pfc set … prio-pfc 3:on`; production restarted (+118.7 s, unchanged image
and env). Verified after a quality+decode gate and two 131K prefills:

- `dcb app` shows `dscp-prio AF31:3` and PFC `3:on` on all 8 interfaces;
- **`tx_prio3_packets` carries the load** (175.2 M packets on the head's two
  interfaces after the run; 0 before the change — all traffic was prio-0),
  `rx_prio3_packets` stays 0 (inbound RoCE arrives untagged; the switch's
  `trust-l3` covers that side), pause-storm counters 0;
- counters still climb under load (`roce_adp_retrans` +12, `out_of_sequence`
  +343 on the head across the ~5-minute load) — **expected**: nothing at the
  switch honours prio 3 yet;
- performance unchanged: `code-c1` 30.14 ms, `prose-c1` 27.72 ms, prefill
  131,072 8,282.9 tok/s (n=2), quality 5/5, memory floor 20.6 GiB
  (`results/private/bench/2026-11-21-b1-host-dcb/`).

Remaining for B1: the switch block (below). Once it lands, the acceptance run
is the same gate + 131K/500K prefills with retrans/oos flat and the switch's
pause counters sane.
## B1 switch side: applied by the owner, acceptance passed (2026-11-20)

CRS812 at RouterOS 7.25.1: QoS profiles `roce` (dscp 26 -> tc 3) and `cnp`
(dscp 48 -> tc 6) show **H (hardware-offloaded)**, and the four RUNNING fabric
ports (`qsfp56-1-1`, `qsfp56-2-1`, `qsfp56-dd-2-1`, `qsfp56-dd-2-5`) carry
`trust-l3=trust pfc=pfc-roce egress-rate-queue3=0`. Cosmetic residue:
inactive breakout sub-ports still show `egress-rate-queue3=200bps` from the
earlier attempt — no link, no traffic; zero them at leisure.

Acceptance load (quality 5/5 + decode gate + 2x131K + 2x524K prefills,
`results/private/bench/2026-11-21-b1-switch-lossless/`):

| measure | before (best-effort) | after (lossless) |
| --- | ---: | ---: |
| `roce_adp_retrans` / `out_of_sequence` over the load | +12 / +343 per ~5 min (head, lighter load) | **+0 / +0 on every node and path** |
| pause frames (rx, per node) | 0 | 12.6k-17.1k (the switch pausing instead of dropping; no storms) |
| prefill 131,072 | 7,890-8,050 site band | **8,519.2 ±0.3%** |
| prefill 524,288 | 6,574-6,662 band | **6,914.2 ±0.8%** |
| `code-c1` / `prose-c1` step | 30.1-31.0 / 27.6-27.7 ms | 30.15 / 27.93 ms (in band) |

Verdict: **B1 adopted.** The earlier "tail-only" estimate was too conservative:
the 16,384-budget prefill all-reduces were paying ~5% in retransmission stalls
at depth, and the lossless class returns it. Thermal note: GPUs peaked 75-81 °C
(6-8 °C headroom on spark-141e/2fe7), no slowdown time recorded.

Consequence for the plan: with the fabric now absorbing incast without loss,
re-open **B2 (`NCCL_BUFFSIZE=2 MiB`)** — larger messages were exactly the
regime the old fabric could not carry cleanly.

## B2 (`NCCL_BUFFSIZE=2 MiB`): measured and adopted (2026-11-21)

Env-only arm on the deployed stack ([arm-b2-buf2m.json](arm-b2-buf2m.json)),
two boots. Boot 1 full load; boot 2's combined load tripped the bench's own
thermal halt (spark-2fe7 GPU 79 °C within 5 °C of the limit — back-to-back
heavy loads with `--cool-below 0` accumulate heat on this fanless-control
site), so boot 2's prefill was rerun alone from a cooled state:

| measure | B1 reference (1 MiB) | B2 boot 1 | B2 boot 2 |
| --- | ---: | ---: | ---: |
| prefill 131,072 | 8,519.2 ±0.3% | 8,661.1 ±0.4% | **8,716.2 ±0.6%** |
| prefill 524,288 | 6,914.2 ±0.8% | 6,988.3 ±2.0% | **7,039.9 ±0.6%** |
| `code-c1` / `prose-c1` step | 30.15 / 27.93 ms | 30.52 / 27.81 ms | 30.23 ms (in band) |
| retrans / oos over the loads | +0/+0 | +0/+0 | +0/+0 |
| quality | 5/5 | 5/5 | 5/5 (prefill-only rerun) |

Both boots agree: prefill **+1.7-2.3% at 131K and +1.1-1.8% at 524K** with
tight intervals, decode unchanged, the fabric stays at zero loss. **Adopted**:
tight intervals, decode unchanged, the fabric stays at zero loss. **Adopted**,
first in the site profile and then (owner, 2026-11-21) **promoted into the
recipe**: `config/cluster.json`'s `tp4-switched.environment.NCCL_BUFFSIZE` is
now `2097152` and the site profile no longer overrides it. The
ring/triangle shapes keep their own values until re-qualified, and
tp5-8-switched inherit the 2 MiB value unmeasured, as they inherited 1 MiB.
Receipts:
`results/private/bench/2026-11-21-b2-buf2m-boot{1,2}/` and `-prefill/`.

Operational note: on this site, leave several minutes between heavy bench loads
or the thermal guard halts the run (it halted boot 2's combined pass; a
prefill-only rerun from 66-67 °C completed with 6 °C of headroom left).

## Plan

### A. Alignment arms (one window, one variable each, two boots each)
A3 preparation note (2026-11-21, read-only): the retire-B12X series
(`experiments/2026-10-26-retire-b12x/vllm/0520-0528`) is **not** part of the
current 641-patch series. Dry-applied in order onto the current prepared tree:
4 apply clean, 4 need 3-way merges, and `0525` (the DSpark drafter's NVFP4 head
switches) hard-conflicts — A3 is a real rebase (renumber to 0700+, resolve
0525, drop `sources.b12x` and its label), not a same-day arm.

**A3 is done** (2026-11-21, `experiments/2026-11-21-a3-retire-b12x`): the
rebase ran, four runtime defects were fixed into the series across five build
rounds, and `spark-ds41f:a3-no-b12x-r5` measures identical to A2 with B12X
absent from the image, lock and labels. The site profile runs it; A2's image
is the rollback.

**The prefix-cache retention sweep is closed as a non-lever** (2026-11-22,
read-only): `--prefix-cache-retention-interval` is consumed only by the
KV-offloading connector scheduler
(`vllm/distributed/kv_transfer/kv_connector/v1/offloading/scheduler.py:229`),
which this recipe never configures; the knob is dead on our serving path. The
67.8% live hit rate on 90-500K prompts is workload shape (unique long
documents against an 11.5M-token pool), so the only real lever for the
felt-slowness tail is client-side: keep per-conversation prefixes stable and
within the pool's capacity, and let the prefix cache do its work.

1. **`A1` stock NCCL** — done and adopted 2026-11-21 (`spark-ds41f:1107-nccl-2.32.6-stock`).
2. **`A2` tilelang `b1367a59` → `ac88f5bc`** — done and adopted 2026-11-21 (`spark-ds41f:1107-tilelang-ac88f5b`).
3. **`A3` retire B12X** — done and adopted 2026-11-21 (`spark-ds41f:a3-no-b12x-r5`).
4. **Next release** folds the adopted site stack into the recipe (owner
   decision; needs ring/triangle qualification); NCCL stays `2.30.7-1` for
   ring/triangle until `0003`/`0004` are re-expressed in 2.32's `src/tuning/`.

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

   - switch (owner reports **7.25.1**, which clears the 7.21/7.22 RoCE
     prerequisite and adds 7.23+'s automatic DSCP mapping; verify
     `/system resource print` and `/system routerboard print` both say 7.25.1):
     `/export file=before-roce` first, then the staged recipe — QoS profiles
     `dscp=26->tc3 (roce)` and `dscp=48->tc6 (cnp)`, the DSCP map, tx-manager
     queue 3 `ecn=yes` and queue 6 strict-priority, a PFC profile
     `traffic-class=3 rx=yes tx=yes`, per port `trust-l3=trust`,
     `pfc=pfc-roce`, `egress-rate-queue3=0`, `l2mtu=9500`; **nothing takes
     effect until `/interface/ethernet/switch set switch1 qos-hw-offloading=yes`,
     and the rollback is the same command with `no`**. Two sources disagree on
     the egress rate: the fabric guide sets `egress-rate-queue3=200G`, the
     CRS812 record shows the 98DX7335 shaper rejects >100G and runs `0`
     (PFC arithmetic uses the PHY rate); use `0`. On the QSFP-DD breakout
     ports never reset `advertise` or the second 200G sub-port drops;
   - hosts: boot-time `dcb app add dev <if> dscp-prio 26:3` +
     `dcb pfc set dev <if> prio-pfc 3:on` on both interfaces of every node;
   - node map `roce_traffic_class: 106` (sparknet marks, and NCCL takes
     `NCCL_IB_TC` from it) plus `NCCL_IB_SL=3` in the shape's environment.

   Safe order: the switch's QoS block is inert until the master command, and
     nothing lands in tc3 until the hosts label — stage the switch, activate,
     confirm the cluster still healthy, then hosts, then the marking in a
     window with the restart.

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
