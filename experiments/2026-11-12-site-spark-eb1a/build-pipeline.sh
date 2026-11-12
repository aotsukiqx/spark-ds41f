#!/usr/bin/env bash
# Build spark-ds41f:1107 from the pinned sources, then copy it to every node.
# Detached: the build compiles vLLM, TileLang, TileKernels, sparknet and NCCL.
set -uo pipefail
cd "$HOME/nvmodels/spark-ds41f" || exit 1
PROFILE=config/cluster-eb1a.local.json
LOG="$HOME/nvmodels/buildlogs/pipeline-$(date -u +%Y%m%dT%H%M%SZ).log"
mkdir -p "$HOME/nvmodels/buildlogs"
mark() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

mark "waiting for any running build prepare to finish"
while pgrep -f "bin/spark.*build prepare" >/dev/null 2>&1; do sleep 30; done

mark "build prepare (reuses verified parts)"
if ! bin/spark --cluster-config "$PROFILE" build prepare >>"$LOG" 2>&1; then
  mark "FAILED: build prepare"; exit 1
fi

mark "build image --apply"
if ! bin/spark --cluster-config "$PROFILE" build image --apply >>"$LOG" 2>&1; then
  mark "FAILED: build image"; exit 1
fi

mark "cluster sync --apply (checkouts, site maps, image copy over the CX7 rails)"
if ! bin/spark --cluster-config "$PROFILE" cluster sync --apply >>"$LOG" 2>&1; then
  mark "FAILED: cluster sync"; exit 1
fi

mark "PIPELINE COMPLETE: image built and distributed; cluster start is a separate decision"
