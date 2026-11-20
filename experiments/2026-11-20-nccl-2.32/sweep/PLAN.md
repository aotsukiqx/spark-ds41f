# NCCL 2.32 knob sweep on the switched site

2.32 rewrote the p2p channel/LL planning and moved tuning into `src/tuning/`
(commits `b7203029`, `7c635f01`, `41363f47`), so the environment chosen for
2.30 may no longer be optimal. Each arm changes exactly one NCCL variable on the
deployed `spark-ds41f:1107-nccl-2.32.6` stack, boots once, and runs the default
quality+decode gate; the two boots already recorded for the deployed arm
(`receipts/serving/`) are the control. `NCCL_DEBUG=INFO` with `INIT,GRAPH` is on
for every arm so the selected algorithm/protocol/channel count is recorded.

Shapes of the arms (all extend `arm-tp4-switched.json`): `qps2`
(`NCCL_IB_QPS_PER_CONNECTION=2`), `ch16` (`NCCL_MAX_NCHANNELS=16`), `ar1`
(`NCCL_IB_ADAPTIVE_ROUTING=1`), `proto` (`NCCL_PROTO=LL,LL128,Simple`, i.e. allow
LL128 again), `buf2m` (`NCCL_BUFFSIZE=2 MiB`).

An arm earns a follow-up candidate only if it beats the control's better boot on
the collective-heavy points (c8/c16) beyond the combined interval; anything
inside is noise, and the current environment stays.
