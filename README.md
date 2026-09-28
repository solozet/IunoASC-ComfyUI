# IunoASC ComfyUI (draft)

A minimal RunPod ComfyUI container with native MiniMax H3, Manager, a Hugging Face downloader and an output browser. No persistent volume or model files in the image. **Both images built in GitHub Actions; a GPU run has not yet been performed.**

## Interfaces

| Port | Purpose |
| --- | --- |
| 3000/http | ComfyUI with native H3 nodes and Manager |
| 8081/http | Original IunoASC model download UI, HF repository and token for LoRAs |
| 8083/http | Original IunoASC outputs UI, individual downloads, streaming ZIP |

All three ports use HTTP Basic authentication from `PANEL_PASSWORD` in the RunPod template. ComfyUI binds only to localhost on 3001 and Nginx proxies it through the password-protected port 3000, including WebSockets. Use `iunoasc` as the username for ComfyUI; the panel pages accept any username with the same password. Set a strong password, preferably by referencing a RunPod secret. Never send an HF token in a URL. The panel uses the submitted token in process memory for its download job; it is not written into the image or configuration. The panel does not persist a secret across Pods.

## Image variants

| Image tag | Base | Attention | Model preset |
| --- | --- | --- | --- |
| `torch2.9.1-cu130` | CUDA 13.0.2, Python 3.12, PyTorch 2.9.1+cu130 | Comfy Kitchen (`--use-ck-attention`) | INT8 ConvRot UNet |
| `torch2.9.1-cu128` | CUDA 12.8.1, Python 3.12, PyTorch 2.9.1+cu128 | PyTorch standard backend | FP8 scaled UNet |

ComfyUI is pinned to `v0.37.0`. `cu130` requires an appropriate host driver. The `cu128` image remains **experimental** for native H3 until a 4090 GPU smoke test. The official workflow defaults to the INT8 UNet; in the `cu128` image, choose the downloaded FP8 UNet in ComfyUI's model dropdown. The official Comfy-Org model card recommends FP8 only if INT8 ConvRot cannot run.

## Preset

Five files from `Comfy-Org/MiniMax-H3`: pruned INT8 ConvRot UNet (FP8 in cu128), NVFP4 AWQ Qwen text encoder, FP16 video VAE, FP32 audio VAE, 8-step Turbo LoRA. The download page puts files under `/data/models/{diffusion_models,text_encoders,vae,loras}` and the ComfyUI `models` directory points there. Models are downloaded only when requested. No other H3 files or style embeddings are needed for the default I2V example.

## Build and use

1. Create a GitHub repository and add these source files.
2. Create a Docker Hub repository `comfyui` and set GitHub Actions secrets `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` (a Docker Hub access token, not your password).
3. Run the **Build IunoASC ComfyUI** workflow manually. Replace `<namespace>` below with your Docker Hub namespace. A successful GitHub Action only proves the images built; it does not prove H3 runs on a GPU. Rebuild after source changes.
4. Create two private RunPod templates with `Container Image` `<namespace>/comfyui:torch2.9.1-cu130` and `<namespace>/comfyui:torch2.9.1-cu128`, HTTP ports `3000,8081,8083`, and `PANEL_PASSWORD`. For the `cu128` template also set `IUNO_ATTENTION=torch` and `IUNO_H3_DIFFUSION_FILE=diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled.safetensors`.
5. Use **Container Disk**, sized for the image, ~45 GB of H3 files and outputs. No network volume. Check the storage selection before launch so the template does not create a paid Volume Disk by default.
6. On the Pod, open `8081` to fetch weights; open `3000` and select the official H3 I2V workflow in the template library; open `8083` to download finished outputs. Verify the archive on your PC before stopping the Pod.

## Limits to validate on GPU

- This build has not been run with a 5090 or 4090; H3 memory, Comfy Kitchen, audio/video decode, and the FP8 cu128 workflow need real Pod tests.
- The page shows progress by file, not per-byte transfer rate. Hugging Face may cache metadata beside files in `/data/models/.cache`.
- If 8081 is restarted mid-download, the in-memory job status is lost. HF library metadata can avoid downloading finished files again when rerun.
- Installing arbitrary custom nodes through Manager may change packages in the running Pod; a fresh Pod restores the base image.
- RunPod stops erase Container Disk; termination also removes the Pod's own volume. Download outputs before either action.
