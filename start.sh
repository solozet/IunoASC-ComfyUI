#!/usr/bin/env bash
set -euo pipefail
: "${PANEL_PASSWORD:?Set PANEL_PASSWORD in your RunPod template before starting the Pod}"
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

# Only port 3000 is public. The panels and ComfyUI stay on loopback behind one
# browser origin and one authentication prompt.
printf 'iunoasc:%s\n' "$(printf '%s\n' "$PANEL_PASSWORD" | openssl passwd -apr1 -stdin)" > /tmp/iunoasc.htpasswd
chmod 600 /tmp/iunoasc.htpasswd
cat > /tmp/iunoasc-nginx.conf <<'NGINX'
events { worker_connections 1024; }
http {
  map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
  }
  server {
    listen 3000;
    server_name _;
    auth_basic "IunoASC ComfyUI";
    auth_basic_user_file /tmp/iunoasc.htpasswd;
    client_max_body_size 512m;
    location = /iuno/models { return 308 /iuno/models/; }
    location = /iuno/outputs { return 308 /iuno/outputs/; }
    location ^~ /iuno/models/ {
      proxy_pass http://127.0.0.1:8081/;
      proxy_set_header Host $host;
    }
    location ^~ /iuno/outputs/ {
      proxy_pass http://127.0.0.1:8083/;
      proxy_set_header Host $host;
      proxy_buffering off;
      proxy_read_timeout 3600s;
    }
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

PANEL_MODE=models uvicorn panel.app:app --host 127.0.0.1 --port 8081 --no-access-log &
models_pid=$!
PANEL_MODE=outputs uvicorn panel.app:app --host 127.0.0.1 --port 8083 --no-access-log &
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
