# Fan control on spark-eb1a: staged, waiting for the console (2026-11-14)

The site runs without `dgx-spark-fan-control`, so `bin/spark bench` cannot pre-cool
and the release suite halts on the thermal guard: `spark-141e` reaches 82-85 °C,
2-4 °C below the platform's slowdown point (`docs/doctor.md`, `bench.py`'s
`THERMAL_HEADROOM_FLOOR_C = 5.0`). This record stages the installer on all four
nodes and stops at the one step no remote command can do.

## The repository's installer was fixed first

`scripts/install-fan-control` called `sudo ./install.sh`, which does not exist at
dgx-spark-fan-control v0.1.4 (checked against the tag's tree). It now follows the
project's documented flow: packages, a checkout, a DKMS build with DKMS signing
when Secure Boot is on, the CLI, the boot-load entry and the service; it is
re-runnable and reports enrolment by reading `mokutil --test-key`'s output, since
that command exits 0 whether or not the key is enrolled (verified on spark-eb1a:
`... MOK.der is not enrolled`, exit 0).

## What is staged on all four nodes

| Item | State |
| --- | --- |
| packages (`dkms`, `build-essential`, headers for 7.0.0-1019-nvidia, `mokutil`, `openssl`) | installed |
| source | `~/nvmodels/dgx-spark-fan-control`, tag `v0.1.4`, detached |
| signing key | one pair for the fleet, `~/.local/share/dgx-spark-fan-control/keys`, `MOK.der` sha256 `5e843a2f002d9ba2…`, the same on all four |
| DKMS module | built, signed and installed on spark-eb1a only (the first run preceded the gate fix); the other three have not built yet |
| MOK enrolment | **not done** — the only enrolled key is Canonical's master CA |
| pending import | none: the key was not imported, so no node surprises the next boot with a firmware prompt |

`SecureBoot enabled` on all four (`mokutil --sb-state`), so the module is
unloadable until the key is enrolled: `modprobe` answered `Key was rejected by
service` on spark-eb1a.

## The remaining step, per node, with a console attached

```bash
cd ~/nvmodels/spark-ds41f
./scripts/install-fan-control --enroll   # mokutil asks for a one-time password
sudo systemctl reboot                    # at the firmware screen: Enroll MOK -> Continue -> Yes -> password
./scripts/install-fan-control            # builds, signs, installs, loads, enables the service
mokutil --test-key ~/.local/share/dgx-spark-fan-control/keys/MOK.der   # expect "already enrolled"
```

The four reboots take the cluster down: schedule them in one window, spark-141e
first (the hottest node) to prove the chain, then the rest, then
`bin/spark cluster start --apply` and a release suite without `--cool-below 0`.

Verification afterwards: `bin/spark --cluster-config config/cluster-eb1a.local.json
doctor --live | grep -i fan` prints nothing, the bench's cooling precondition
reaches 55 °C, and `--cool-below 0` can be dropped from the release-benchmark
commands.

## Rollback

`sudo systemctl disable --now dgx-fan-control.service` returns to NVIDIA's
factory curve; `sudo dgx-fan-control automatic` clears a manual floor; the module
comes off with `sudo dkms remove -m dgx_ec_fan_control -v v0.1.4 --all`.

## Blocked by the EC firmware on this fleet (2026-11-14)

The console enrollment on spark-eb1a succeeded — the key is enrolled
(`mokutil --list-enrolled` holds `CN=DGX Spark local module signing`,
`89:6c:e7:d8…`, beside Canonical's CA, and nothing is pending) — and the module
loads. Its probe then refuses the device:

```
dgx-ec-fan-control arm-ffa-18: packet service partition=0x8003 properties=0x109 FF-A=1.2
dgx-ec-fan-control arm-ffa-18: packet submit operation=0x1 status=0x5
dgx-ec-fan-control arm-ffa-18: error -EIO: refusing fan-floor cooling device
dgx-ec-fan-control arm-ffa-18: probe with driver dgx-ec-fan-control failed with error -5
```

`dgx-fan-control status` therefore reports `expected one 'dgx_ec_fan_floor'
cooling device, found 0`. The driver is an FF-A client: it matches DMI
(`NVIDIA` / `NVIDIA_DGX_Spark` / `P4242` — all match here), FF-A 1.2, shared
partition `0x8003`, properties `0x109`, then submits operation 1 and expects the
observed answer. This board answers `status=0x5`, outside the contract, so the
driver declines by design rather than writing to an unknown interface.

The board's BIOS is `5.36_0ACUM028` (2026-09-04). Upstream v0.1.4 records its
validation on EC firmware 3.5.8 / SoC 2.155.11 with DGX OS 7.5.0 and kernel
6.17.0-1029, and states that compatibility with later firmware is unqualified.
Only `v0.1.4` exists upstream (checked 2026-11-14), so there is no fixed release
to move to.

## Reverted, and what stays

Every node: pending MOK import revoked (`mokutil --revoke-import`), the
modules-load entry, the unit and the loaded module removed, DKMS module removed
on spark-eb1a. The signing key pair and the source checkout stay for a retry
once upstream supports this EC; the enrolled MOK on spark-eb1a is harmless.

Consequences: the bench keeps `--cool-below 0`, the release suite keeps halting
on the thermal guard (exit 1 with `halted: spark-141e ... 2-4 C headroom`), and
spark-141e's margin does not improve. Reopening needs an upstream driver that
accepts `status=0x5` (or NVIDIA's own fan-floor interface on this BIOS), then the
same enrollment path — the key and the installer are ready.

## Is there an official NVIDIA method? No (surveyed 2026-11-14)

| Candidate | Verdict on spark-eb1a |
| --- | --- |
| BMC / IPMI fan control (`nvfancontrol`, DGX Station style) | none: `ipmitool` exists but `/dev/ipmi0` does not; no NVIDIA fan unit or binary in the image |
| `nvidia-smi` fan control | not exposed: `fan.speed` is `N/A`; only thermals are readable |
| ACPI platform fans (`PNP0C0B:00/01`, `cooling_device0/1`, 0-100) | present and writable, but **inert**: `cur_state=100` was accepted, `hwmon0/fan1_input` stayed 0 and the GPU moved 50 -> 49 °C in 60 s. Not wired to the physical fans |
| EC firmware channel | **official and active**: `fwupdmgr` device `8c948e1d…`, current `0x03000d07` (LVFS release 152272, created 2026-09-28, urgency High; supersedes `0x03000508`/`0x0300050b`) |
| GPU clock/power caps | `nvidia-smi -lgc` is supported by this driver; `power.limit` is `N/A` |

So NVIDIA exposes **no user fan control**: the curve belongs to the EC, and the only
official levers are EC firmware updates (NVIDIA's content) and GPU clock caps.

It also explains the refusal precisely: upstream v0.1.4 was validated on EC
`0x03000508`; this fleet runs `0x03000d07`, whose EC answers the fan-floor
operation with `status=0x5`, so the driver declines. Community work reports the
same shift — the 0.3 EC branch changed the fan behaviour and a different project
drives EC **command 5** rather than operation 1 — which means a correct driver for
this EC would be new work, not a version bump.
