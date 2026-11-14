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
