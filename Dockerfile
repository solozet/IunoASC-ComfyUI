ARG CUDA_VERSION=13.0.2
FROM nvidia/cuda:${CUDA_VERSION}-cudnn-runtime-ubuntu24.04

ARG CUDA_VERSION
ARG TORCH_INDEX=cu130
ARG COMFY_REF=v0.38.0
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
ENV IUNO_TORCH_INDEX=${TORCH_INDEX} IUNO_CUDA_BASE_VERSION=${CUDA_VERSION}

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip git curl ca-certificates ffmpeg zip nginx openssl \
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
    pip check && \
    python -c 'import os, torch, torchvision, torchaudio, comfy_kitchen; from importlib.metadata import version; expected={"cu130":"13.0","cu128":"12.8"}[os.environ["IUNO_TORCH_INDEX"]]; assert torch.version.cuda == expected, (torch.version.cuda, expected); print("Base CUDA", os.environ["IUNO_CUDA_BASE_VERSION"], "PyTorch wheel CUDA", torch.version.cuda); print("torch", torch.__version__, "vision", torchvision.__version__, "audio", torchaudio.__version__); print("ComfyUI Manager", version("comfyui_manager"), "Comfy Kitchen", version("comfy-kitchen"))'

# ComfyUI's requirements pin comfy-kitchen 0.2.36. On CUDA 12.8 we
# launch with standard attention until a GPU trial confirms the fallback.

COPY panel /opt/iunoasc/panel
COPY workflows /opt/iunoasc/workflows
COPY start.sh /opt/iunoasc/start.sh
COPY preflight.py /opt/iunoasc/preflight.py
COPY tests/test_gateway.py /tmp/test_gateway.py
RUN python /tmp/test_gateway.py && rm /tmp/test_gateway.py
RUN mkdir -p /data/models/diffusion_models /data/models/text_encoders \
             /data/models/vae /data/models/loras /data/models/embeddings \
             /data/inputs /data/outputs && \
    rm -rf /opt/ComfyUI/models && ln -s /data/models /opt/ComfyUI/models && \
    chmod +x /opt/iunoasc/start.sh

ENV PYTHONPATH=/opt/iunoasc IUNO_DATA_DIR=/data HF_HOME=/data/.hf-cache
EXPOSE 3000 8081 8083
CMD ["/opt/iunoasc/start.sh"]
