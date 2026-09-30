#!/usr/bin/env bash
set -euo pipefail
case "${IUNO_TORCH_INDEX:-}" in
  cu130)
    export IUNO_ATTENTION="${IUNO_ATTENTION:-ck}"
    export IUNO_H3_DIFFUSION_FILE="${IUNO_H3_DIFFUSION_FILE:-diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors}"
    ;;
  cu128)
    export IUNO_ATTENTION="${IUNO_ATTENTION:-torch}"
    export IUNO_H3_DIFFUSION_FILE="${IUNO_H3_DIFFUSION_FILE:-diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled.safetensors}"
    if [[ "$IUNO_ATTENTION" == ck ]]; then
      echo '[IunoASC] CUDA 12.8 cannot use the optimized comfy-kitchen CUDA backend. Set IUNO_ATTENTION=torch.' >&2
      exit 1
    fi
    ;;
  *) echo "[IunoASC] Unsupported image variant: ${IUNO_TORCH_INDEX:-unset}" >&2; exit 1 ;;
esac
if [[ "$IUNO_ATTENTION" != ck && "$IUNO_ATTENTION" != torch ]]; then
  echo '[IunoASC] IUNO_ATTENTION must be ck or torch.' >&2
  exit 1
fi

# Check the real GPU and host driver before starting the panels or ComfyUI.
# A successful Docker build does not test the RunPod host's CUDA driver.
timeout --signal=TERM --kill-after=5s 90s python /opt/iunoasc/preflight.py
mkdir -p /data/models /data/inputs /data/outputs

# ComfyUI uses port 3000; model and output panels have separate public ports.
cat > /tmp/iunoasc-nginx.conf <<'NGINX'
user www-data;
events { worker_connections 1024; }
http {
  map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
  }
  server {
    listen 3000;
    server_name _;
    client_max_body_size 512m;
    location / {
      proxy_pass http://127.0.0.1:3001;
      proxy_http_version 1.1;
      proxy_set_header Host $host;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection $connection_upgrade;
      proxy_read_timeout 3600s;
      proxy_send_timeout 3600s;
    }
  }
}
NGINX
nginx -c /tmp/iunoasc-nginx.conf -g 'daemon off;' &
gateway_pid=$!

PANEL_MODE=models uvicorn panel.app:app --host 0.0.0.0 --port 8081 --no-access-log &
models_pid=$!
PANEL_MODE=outputs uvicorn panel.app:app --host 0.0.0.0 --port 8083 --no-access-log &
outputs_pid=$!

cleanup() { kill "$gateway_pid" "$models_pid" "$outputs_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

args=(--listen 127.0.0.1 --port 3001 --enable-manager \
      --input-directory /data/inputs --output-directory /data/outputs)
if [[ "${IUNO_ATTENTION:-ck}" == "ck" ]]; then
  args+=(--use-ck-attention)
fi
cd /opt/ComfyUI
python main.py "${args[@]}"
