# Site deployment: spark-eb1a, 700 Ki context on the four-node switch

The site runs four DGX Sparks through a 200 GbE switch with the pinned
DeepSeek-V4.1-Flash-1017 weights on every node's local disk, and replaces the
DeepSeek service that served 716,800 tokens with this repository's promoted
recipe at the same request limit. It is a site deployment record, not a
promotion request: the recipe's qualified reference stays
`2026-11-07-spark-ds41f-1107`.

Deployed base commit: `bbfe2618` (published on `origin/main`). Everything here is additive —
the site profile, these probes, and the measurements — so a node synced to a branch carrying
this folder runs the same engine; the profile it starts from is `profile.json`, copied to the
site's ignored `config/cluster-eb1a.local.json`.

## Site

| | |
|---|---|
| Nodes | `spark-eb1a` (head, rank 0), `spark-141e` (rank 3), `spark-a89f` (rank 1), `spark-2fe7` (rank 2) |
| Fabric | one 200 GbE switch, both PCIe paths per port (`rocep1s0f1`, `roceP2p1s0f1`), `/24` per rail (192.168.8.0/24, 192.168.9.0/24), MTU 9000, GID index 3 |
| Control | `enp1s0f1np1` (GLOO, NCCL socket, TP socket); management `enP7s7` (192.168.2.0/24) |
| Host | DGX OS, kernel `7.0.0-1019-nvidia` (stock 4 KiB pages), no memory saver, driver 580.178.04 |
| Weights | `{home}/nvmodels/DeepSeek-V4.1-Flash-1017` on every node (476 GiB, 48 shards), mounted read-only at `/hub`; `HF_HUB_OFFLINE=1` |
| Checkout | `{home}/nvmodels/spark-ds41f`, all nodes detached at one published commit (`bbfe2618`) |
| Image | `spark-ds41f:1107`, built on the head from the lock's pinned sources |

`config/cluster-eb1a.local.json` is the site's arm overlay (git-ignored, present
on every node): it extends `config/cluster.json` at `tp4-switched` and changes
only the site's own facts — the 4 KiB host kernel, the node-local model profile,
the deployment path, and the request limit. `config/site.json` names
`tp4-switched` and `config/nodes-switched.local.json` names the nodes, rails and
`transfer_host` (the CX7 address used for bulk copies).

## The one variable against the recipe

**Request limit 716,800 tokens** (700 Ki) instead of 1,048,576, matching the
limit the site's previous service served. Everything else is the recipe at
`tp4-switched` unchanged: 16 admitted sequences, a 16,384-token batch budget,
a 10.5 GiB KV pool per rank, `--long-prefill-token-threshold 16288`,
`--prefix-cache-retention-interval 8192`, CUDA graphs to 96 rows (16 streams x
6 rows), DSpark with five drafts and adaptive verification (row cost 0.035),
one concurrent prefill, and the TileLang kernel family.

Consequences at the pool's geometry (227,840-byte blocks, 49,483 of them):

| Quantity | At 1,048,576 | At 716,800 |
| --- | ---: | ---: |
| Blocks one request holds | 4,142 | 2,846 (2,800 compressed + 45 window + 1 compressor) |
| Full contexts the pool holds | 11 | 16 (the startup line's 16.02x) |
| All 16 sequences at once, up to | 718,848 tokens | 791,728 tokens |

The engine's startup line is the authority for the pool:
`GPU KV cache size: 11,485,987 tokens, Maximum concurrency for 716,800 tokens per
request: 16.02x`. It reads one below the 2,846-block derivation's 17 because the pool also
carries the chunks of the prompt being filled. So sixteen admitted sequences can all hold
full-length 700 Ki contexts — six more than the ten the site asked for — and one more
context still fits.

The recipe's GLP-steered second served name is unset: its vector lives in a hub
cache the nodes do not hold, and `HF_HUB_OFFLINE=1` forbids fetching it. The
stock `deepseek-v4.1-flash` name serves.

## Commands

The site profile is the arm overlay in this folder, copied to the site's ignored path on
every node; the lane arms extend that path, so the copy comes first:

```sh
install -m 0644 experiments/2026-11-12-site-spark-eb1a/profile.json config/cluster-eb1a.local.json
```

```sh
cd ~/nvmodels/spark-ds41f
bin/spark --cluster-config config/cluster-eb1a.local.json build prepare
bin/spark --cluster-config config/cluster-eb1a.local.json build image --apply
bin/spark --cluster-config config/cluster-eb1a.local.json cluster sync --apply
bin/spark --cluster-config config/cluster-eb1a.local.json cluster start --apply
bin/spark --cluster-config config/cluster-eb1a.local.json doctor --live
```

`cluster sync --apply` copies the image over each worker's `transfer_host`, the
200 GbE rail, and checks the ordered layers and runtime configuration on every
node.

## What the guards cover

`cluster start` arms the recipe's fail-closed guards on every node: 5 GiB
MemAvailable during the 900 s start, then 3 GiB steady, sampled every 2 s.
The site's stock 4 KiB pages lose the ~1.8 GiB per node a 64 KiB kernel with the
memory saver recovers; the external receipt
[2026-10-17-site-tp4-4k-1017](../2026-10-17-site-tp4-4k-1017/README.md) measured
18-21 GiB MemAvailable on such a host at the recipe's 1M sizing, and this site
serves 70% of that context.

## Verification

- `doctor --live` clean apart from warnings whose fixes are host-policy changes
  (64 KiB kernel, memory saver, fan control, NVMe sleep, wireless) the site has
  not taken.
- `bin/spark bench --compare manifests/benchmarks/2026-11-07-spark-ds41f-1107-switched.json`
  for the engine grid, and the concurrency probe below for the site's own
  requirement.

## Measured on the site (2026-11-12)

Image `spark-ds41f:1107`, built on the head in 785 s (lowest MemAvailable 77.6 GiB),
distributed to the three workers in 195 s each over the CX7 rails. Boot 753.5 s
(247 TileLang compile keys, cold JIT cache), API ready, all four steady guards armed.
Zero `hf_hub` / `huggingface.co` / `Downloading` lines in any rank's log; the direct
loader read 150.05 GB from the node-local checkpoint at 4.27 GB/s.

`GPU KV cache size: 11,485,987 tokens, Maximum concurrency for 716,800 tokens per
request: 16.02x`, so the pool holds sixteen full 700 Ki contexts at once.

Engine grid against `manifests/benchmarks/2026-11-07-spark-ds41f-1107-switched.json`
(4 samples a point, no cooling preconditioning; the site has no fan-floor control):

| Point | Site tok/s | Reference | Change | Step ms site / reference |
| --- | ---: | ---: | ---: | --- |
| prose-c1 | 72.9 | 73.3 | -0.6% | 27.73 / 27.41 |
| prose-c2 | 130.0 | 128.4 | +1.2% | 30.22 / 31.07 |
| prose-c4 | 226.4 | 212.8 | +6.4% | 33.42 / 36.55 |
| prose-c8 | 383.2 | 396.1 | -3.3% | 40.52 / 39.00 |
| prose-c16 | 577.6 | 587.0 | -1.6% | 51.49 / 51.57 |
| code-c1 | 93.1 | 95.0 | -2.0% | 30.53 / 29.85 |
| code-c2 | 153.1 | 149.8 | +2.1% | 35.45 / 36.63 |
| code-c4 | 242.5 | 266.9 | -9.1% | 44.22 / 39.66 |
| code-c8 | 440.2 | 490.1 | -10.2% | 47.14 / 42.38 |
| code-c16 | 656.0 | 677.3 | -3.2% | 60.57 / 59.38 |

Every point is inside its 95% interval of the reference (verdict `same`); the quality
gate passed 5/5. The widest intervals are the four-stream and eight-stream code points,
where the site's higher ambient temperature costs the most.

Cold 700 Ki prefill: 112 s a request (about 6,250 tok/s), in line with the reference's
7,460 tok/s at 524K and 6,012 tok/s at 1M.

### Concurrent 700 Ki requests: the balance

`probe_long_context.py --requests N --tokens 700000`, each request a distinct filler
document calibrated to 700,000 tokens by the server's own tokenizer, one `cache_salt` per
stream, forced output length. Step time comes from `vllm:iteration_tokens_total_count`
and `vllm:generation_tokens_total` sampled every second, so it is independent of how many
tokens a step happens to accept.

| Requests | Admitted at once | Step ms | tok/step, all streams | KV peak | Preemptions | Wall |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 86.5 | 16.3 | 5.7% | 0 | 51 s (12,000 tokens) |
| 10 | 10 (sustained 139 s) | 250 | 64.4 | 56.5% | 0 | 84 s (30,000 tokens) |
| 16 | 12 | not sampled | 448 tok/s summed per stream | 66.8% | 0 | 902 s (48,000 tokens) |

Read the rows this way:

- **The pool and the scheduler agree up to about twelve.** Ten requests admit together and
  hold, at a 250 ms step and 56.5% of the pool; at sixteen requested the engine holds
  twelve at once (66.8%) and the remaining six wait.
- **Past twelve, work serializes in waves.** The last six of the sixteen saw first-token
  times of 201, 345, 482, 618, 754 and 888 s: each waited for earlier streams to finish
  rather than preempting them. Nothing was evicted or recomputed.
- **Step cost is the concurrency price, and it is the honest number here.** 86.5 ms at one
  stream, 250 ms at ten: 2.9x the step for 10x the streams, so aggregate decode rises
  about threefold (239-246 tok/s solo to 518 tok/s across the ten-stream overlap window).
- **The tok/s figures above overstate ordinary text.** The probe's prompt and its forced
  output are the same 700 Ki of repetitive filler, which CopyDrafter matches almost
  exactly: acceptance reaches 6-16 tokens a step a stream, where the engine grid's prose
  c16 measures about 2. The engine grid is this record's throughput claim; these runs
  measure admission, step cost and capacity.

A cold pass (fresh salts, one prefill at a time through `--max-parallel-prefills 1`)
admitted and served all ten as well, 0 preemptions, at 112 s of prefill a request and a
1,151 s wall; a repeat with the same salts hits the prefix cache (6.99M of 7.00M queried
prefix tokens) and collapses first tokens to 3.0-27.3 s.

### Parallel prefill lanes: measured, and why they are not adopted

`--max-parallel-prefills` decides how many cold prompts prefill at once. The recipe sets 1,
beside `--prefill-yield short`, and the two are **mutually exclusive by upstream
validation** (vLLM 0545): a second lane beside the yield stops the engine before it starts.

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for SchedulerConfig
  Value error, prefill_yield replaces prefill lanes, compute sharing and the prefill
  schedule interval; set none of them with it
```

So a lane count above one is not a knob beside the recipe; it is the alternative policy.
Arms (`arm-lanes1.json`, `arm-lanes2.json`, `arm-lanes4.json`) hold one lane count each with
`--prefill-yield off`, against the production profile. Each arm differs from `profile.json`
in exactly those two resolved values and nothing else (positional diff of the resolved
`serve_args`: two entries for 2 and 4 lanes, one for the control).

Workload per arm: eight concurrent cold 700 Ki requests (`probe_long_context.py --requests 8
--output-tokens 3000`, a fresh salt prefix an arm), then `probe_short_during_prefill.py` — a
fresh 700 Ki prefill with short chat requests at t+20 s, t+50 s and t+80 s. That second
probe is the mixed-workload question the yield exists for.

| Arm | Lanes / yield | 1st .. 8th first token (s) | Spacing (s) | Short request TTFT (s) | Peak KV | Preemptions |
| --- | --- | --- | --- | --- | --- | --- |
| production | 1 / `short` | 113 .. 1,071 | 137 | 2.97 / 4.62 / 3.52 | 19.2% | 0 |
| control | 1 / `off` | 113 .. 914 | 113 | 7.16 / 9.59 / 12.35 | 52.4% | 0 |
| two lanes | 2 / `off` | engine livelocked | — | — | — | — |
| four lanes | 4 / `off` | not run | — | — | — | — |

Three results, in order of importance:

1. **Two lanes livelock the engine on this workload.** The arm booted with
   `--max-parallel-prefills 2`, took eight 700 Ki requests, and then made no progress at
   all: `num_requests_running` 1 with 7 waiting, `iteration_tokens_total_count`, `prompt_tokens_total`
   and `generation_tokens_total` all still 0 after 19.5 minutes, GPU 0%, the TP worker at
   103% CPU in a run state. Evidence kept in `runs/lanes2-stall/` (counters, container log,
   process table, GPU state). The four-lane arm was not run: two lanes is the feature's
   minimum configuration and it does not serve.
2. **The yield buys the mixed workload, and it costs prefill.** Same one-lane engine, yield
   off instead of `short`: the eight cold prefills run 113 s apart instead of 137, so the
   last first token moves 1,071 s -> 914 s (-15%), while a short request arriving during a
   long prefill waits 7-12 s instead of 3-5 s (2.4-3.5x). That is the trade the recipe
   documents, measured on this site rather than assumed.
3. **Peak KV doubles without the yield** (19% -> 52%) because a yielded prefill shares the
   step with decode rows.

Adoption: none. The recipe's `--max-parallel-prefills 1` with `--prefill-yield short` is the
configuration this site keeps; only that pair is qualified on this build. What would have to
change for lanes to be reconsidered: the lane path serving at all (it does not, above), then
its own qualification.

### One correction to this record

An earlier version of this section proposed parallel lanes as a way to shorten the tail of a
cold sixteen-request burst, estimating the tail as "divided by the lane count". That was
wrong twice: the two policies are mutually exclusive, and lanes share one token budget, so
they cannot divide the *tail* of a fixed amount of prefill work — the tail is set by
total prefill work over budget, and what lanes redistribute is the queue in front of it.

### Deviations from the recipe, with their cost

| Deviation | Why | Cost |
| --- | --- | --- |
| Stock 4 KiB kernel, no memory saver | site host policy | about 1.8 GiB less headroom a node; measured 22 GiB (head) / 24 GiB (workers) available at rest |
| `nvidia-drm fbdev=0` (doctor error) | site's existing modulo options | no text console on an attached display; nothing in the serving path |
| No fan-floor control | not installed | bench runs without cooling preconditioning; a few percent on the four- and eight-stream code points |
| GLP steering unset | vector absent from the nodes' hub caches and `HF_HUB_OFFLINE=1` | one served name instead of two |
| Request limit 716,800 | the site's requirement | covered above |

## Review after deployment (2026-11-12): what is left

Everything the site can change without touching host policy or upstream code was checked
against the recipe, not assumed:

| Check | Evidence | Verdict |
| --- | --- | --- |
| Configuration drift | `bin/spark doctor` prints `configuration OK`; `doctor --live` reports no command, environment or mount difference against the profile | none |
| Kernel features actually on | boot log: `[l2_prefetch] TileLang kernel ready (grid=2 block=128 chunk=4096)` and the per-layer segment map, `Direct loader … 4.27 GB/s`, `Chunked prefill … 16384`, deep-context chunk step-down present in the pinned scheduler | on |
| "Unknown vLLM environment variable" warnings | `VLLM_L2_PREFETCH_KERNELS`/`_GRID` are read by `vllm/models/glm5next/nvidia/l2_prefetch.py` at import, which the DS4.1 prefetcher reuses; vLLM's registry simply does not list locally-read variables | cosmetic |
| Thermal headroom | `bench.json`: `thermal_slowdown_ms` 0 on all four nodes, no throttle reason active, clocks at 2.21/3.00 GHz idle | not a lever |
| Memory headroom | bench minimum `MemAvailable` 22.04 GiB (head), 23.86-23.90 GiB (workers); swap growth 0; guards at 3 GiB | not a lever at 700 Ki |
| Prefill at 700 Ki, uncached Engram text (`--prefill-text novel`) | 6,200.6 tok/s, 109.7 s a request (two repeats, ±0.01%) | on the reference curve |
| NVMe interrupt coalescing | A/B on the live engine, one variable: 6,200.57 (on) vs 6,200.39 tok/s (off), delta 0.00% ±1.2 over two repeats each | no effect at this context |
| Concurrency ceiling | `--max-parallel-prefills 1`: the six requests beyond twelve waited 201, 345, 482, 618, 754, 888 s, about 135 s apart — one cold prefill at a time, 0 preemptions | policy, not a defect |

The prefill point matters: 6,200 tok/s at 700 Ki sits exactly where the reference's own
curve puts it (7,460 at 524K, 6,012 at 1M), so the batch budget is not costing anything
and raising it moves along a curve nobody has measured a better point on.

`scripts/disable-nvme-coalescing` was applied on all four nodes because it is this
repository's documented host state, not because it measured faster here: at 700 Ki the
per-chunk compute outweighs the Engram row reads that made 0.7-1.6% at 32K-131K.

### Levers that remain, and their price

| Lever | Upside | Price | Why it is not taken |
| --- | --- | --- | --- |
| `--max-parallel-prefills` 2..4 | none measured | livelocks the engine at 2 on this build (above) | measured, rejected |
| `--prefill-yield off` | eight cold 700 Ki prefills finish 15% sooner | a short request during a long prefill waits 2.4-3.5x longer | the yield is the property that keeps agent traffic responsive |
| `--max-num-batched-tokens 24,576` | 29 prefill chunks instead of 43 | decode latency beside a long prompt | prefill already on the reference curve; upside ~2-4% at best |
| 64 KiB kernel + memory saver | about 1.8 GiB of headroom a node | host policy, reboot, DKMS signing | only pays at 900K-1M context; 700 Ki leaves 19-22 GiB spare |
| Fan-floor control (DGX DKMS) | matches the reference's bench conditions | host package + reboot | 0 ms thermal slowdown measured, so no throughput to win |
| Upstream kernels (persistent MoE, direct RoCE writes, 128-row vocabulary tile, ...) | 1.3-3.5% a decode step | patch work plus a new qualification | repository-level work, not site configuration |

Operational, not performance: the head holds 229.9 GB of reclaimable images and 433 GB of
build cache (`docker system df`).

### What the screen changed about the record

Two claims in this record were corrected by measurement, and both are kept visible rather
than edited away: parallel lanes as a tail-shortening lever (they are mutually exclusive
with the yield, livelock at two, and cannot divide a fixed prefill budget), and NVMe
interrupt coalescing (0.00% at 700 Ki, where the repository's 0.7-1.6% was measured at
32K-131K). The site record now states the engine grid, the concurrency balance and the
lane rejection as measured facts, and lists what is left with its price.

## Files

- `profile.json`: the site profile as an arm overlay on `config/cluster.json` at
  `tp4-switched` — the one variable (716,800-token requests) plus the site's host, model and
  deployment facts. Copy it to `config/cluster-eb1a.local.json` on every node (the site's
  ignored path), or extend it from an arm.
- `arm-lanes{1,2,4}.json`: the prefill-lane screen, one lane count each with
  `--prefill-yield off`, extending `profile.json`.
- `probe_long_context.py`: N concurrent full-length requests, distinct prompts, forced
  output, streaming TTFT and per-stream decode.
- `probe_short_during_prefill.py`: short chat requests at fixed offsets during one cold
  700 Ki prefill — the mixed-workload latency the yield exists for.
- `acceptance.sh`: the whole verification chain in one detached script.
- `build-pipeline.sh`: prepare, build, distribute.
- `runs/`: every measurement in this record.
  - `bench.txt`, `doctor-live.txt`: the engine grid against the switched reference, and
    `doctor --live`.
  - `probe1-solo.json`, `probe10-3000.json`, `probe16-3000.json`, `probe10-cold.json`,
    `probe10-warm*.json`, `probe10-simultaneous.json`, `steps-10streams.json`: admission,
    step cost and capacity at 700 Ki.
  - `nvme/coalescing-{on,off}.json`: the interrupt-coalescing A/B (700 Ki prefill, both arms).
  - `lane-screen/`: the production and one-lane-off arms of the lane screen, with their
    summaries.
  - `lanes2-stall/`: the two-lane livelock — counters, container log, process table, GPU
    state, memory.
