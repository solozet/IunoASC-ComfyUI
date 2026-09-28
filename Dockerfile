ARG CUDA_VERSION=13.0.2
FROM nvidia/cuda:${CUDA_VERSION}-cudnn-runtime-ubuntu24.04

ARG TORCH_INDEX=cu130
ARG COMFY_REF=v0.37.0
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip git curl ca-certificates ffmpeg zip \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
RUN pip install --upgrade pip && \
    pip install torch==2.9.1 torchvision==0.24.1 torchaudio==2.9.1 \
      --index-url https://download.pytorch.org/whl/${TORCH_INDEX}

RUN git clone --depth 1 --branch "${COMFY_REF}" https://github.com/Comfy-Org/ComfyUI.git /opt/ComfyUI
WORKDIR /opt/ComfyUI
RUN printf 'torch==2.9.1\ntorchvision==0.24.1\ntorchaudio==2.9.1\n' > /tmp/torch-constraints.txt && \
    pip install -c /tmp/torch-constraints.txt -r requirements.txt -r manager_requirements.txt && \
    pip install -c /tmp/torch-constraints.txt "fastapi==0.115.12" "uvicorn==0.34.2" && \
    pip check

# ComfyUI's requirements pin comfy-kitchen 0.2.35. On CUDA 12.8 we
# launch with standard attention until a GPU trial confirms the fallback.

COPY panel /opt/iunoasc/panel
COPY start.sh /opt/iunoasc/start.sh
RUN mkdir -p /data/models /data/inputs /data/outputs && \
    rm -rf /opt/ComfyUI/models && ln -s /data/models /opt/ComfyUI/models && \
    chmod +x /opt/iunoasc/start.sh

ENV PYTHONPATH=/opt/iunoasc IUNO_DATA_DIR=/data HF_HOME=/data/.hf-cache
ENV IUNO_H3_DIFFUSION_FILE=diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors
EXPOSE 3000 8081 8083
CMD ["/opt/iunoasc/start.sh"]
