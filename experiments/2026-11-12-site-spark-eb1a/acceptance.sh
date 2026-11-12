#!/usr/bin/env bash
# Acceptance for the spark-eb1a site deployment: engine grid against the 1107 switched
# reference, a 700 Ki admission check, and ten concurrent full-length contexts.
set -uo pipefail
cd "$HOME/nvmodels/spark-ds41f" || exit 1
PROFILE=config/cluster-eb1a.local.json
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$HOME/nvmodels/acceptance-$STAMP"
mkdir -p "$OUT"
mark() { echo "[$(date '+%F %T')] $*"; }

mark "doctor --live"
bin/spark --cluster-config "$PROFILE" doctor --live > "$OUT/doctor-live.txt" 2>&1
mark "doctor exit=$? (see $OUT/doctor-live.txt)"

mark "bench: quality + decode (c1..c16) against the 1107 switched reference"
bin/spark --cluster-config "$PROFILE" bench \
  --compare manifests/benchmarks/2026-11-07-spark-ds41f-1107-switched.json \
  --allow-mismatch \
  --output "$OUT/bench" > "$OUT/bench.txt" 2>&1
mark "bench exit=$?"

mark "admission: four concurrent 700,000-token requests, 2,048 forced output tokens"
bin/spark --cluster-config "$PROFILE" bench --suites admission \
  --admission-tokens 700000 --admission-output-tokens 2048 --admission-force-length \
  --allow-mismatch --output "$OUT/admission" > "$OUT/admission.txt" 2>&1
mark "admission exit=$?"

mark "long context: ten concurrent 700,000-token requests, 256 output tokens each"
python3 experiments/2026-11-12-site-spark-eb1a/probe_long_context.py \
  --requests 10 --tokens 700000 --output-tokens 256 \
  > "$OUT/probe10.json" 2>"$OUT/probe10.err"
mark "probe exit=$?"

mark "done: $OUT"
for f in bench.txt admission.txt probe10.json; do
  echo "== $f"; tail -20 "$OUT/$f" 2>/dev/null
done
