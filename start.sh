#!/usr/bin/env bash
set -euo pipefail
: "${PANEL_PASSWORD:?Set PANEL_PASSWORD in your RunPod template before starting the Pod}"
mkdir -p /data/models /data/inputs /data/outputs

PANEL_MODE=models uvicorn panel.app:app --host 0.0.0.0 --port 8081 --no-access-log &
models_pid=$!
PANEL_MODE=outputs uvicorn panel.app:app --host 0.0.0.0 --port 8083 --no-access-log &
outputs_pid=$!

cleanup() { kill "$models_pid" "$outputs_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

args=(--listen 0.0.0.0 --port 3000 --enable-manager \
      --input-directory /data/inputs --output-directory /data/outputs)
if [[ "${IUNO_ATTENTION:-ck}" == "ck" ]]; then
  args+=(--use-ck-attention)
fi
cd /opt/ComfyUI
python main.py "${args[@]}"
