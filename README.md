# IunoASC ComfyUI

A minimal RunPod ComfyUI container with native MiniMax H3, Manager, a Hugging Face downloader and an output browser. No persistent volume or model files in the image. The first CUDA 13.0 Pod failed with CUDA error 804 before ComfyUI started; its host GPU and driver were not captured. The corrected images still need a real GPU test.

## Interfaces

| URL path on port 3000 | Purpose |
| --- | --- |
| `/` | ComfyUI with native H3 nodes and Manager |
| `/iuno/models/` | IunoASC model download UI, HF repository and token for LoRAs |
| `/iuno/outputs/` | IunoASC outputs UI, individual downloads, streaming ZIP |

The models page also offers an adapted copy of Comfy Org's official native H3 I2V workflow. Its diffusion model and FP16 video VAE names match the active image preset. Upload your own starting image in the workflow. The upstream workflow is MIT licensed; its license is in `workflows/LICENSE`.

Expose **only HTTP port 3000** in RunPod. Nginx serves all three pages under one origin and one HTTP Basic authentication prompt, including ComfyUI WebSockets. ComfyUI and both panels listen only on localhost inside the container. The username is `iunoasc`; set `PANEL_PASSWORD` to a strong value in the RunPod template, preferably as a RunPod secret. RunPod login alone does not protect an exposed Pod URL. Never send an HF token in a URL. The panel uses the submitted token in process memory for its download job; it is not written into the image or configuration. The panel does not persist a secret across Pods.

## Image variants

| Image tag | Base | Attention | Model preset |
| --- | --- | --- | --- |
| `torch2.9.1-cu130-r2` | CUDA 13.0.2, Python 3.12, PyTorch 2.9.1+cu130 | Comfy Kitchen (`--use-ck-attention`) | INT8 ConvRot diffusion model |
| `torch2.9.1-cu128-r2` | CUDA 12.8.1, Python 3.12, PyTorch 2.9.1+cu128 | PyTorch standard backend | FP8 scaled diffusion model |

ComfyUI is pinned to `v0.37.0`. [NVIDIA's CUDA release notes](https://docs.nvidia.com/cuda/archive/13.0.3/cuda-toolkit-release-notes/index.html) state that CUDA 13 requires host driver R580 or newer. CUDA 12.8.1 is paired with R570 and is the practical fallback for hosts without R580; newer host drivers can run the older image. The exact host driver is outside the Docker image. Select a RunPod machine with compatible CUDA/driver in its deployment filters. `cu128` remains **experimental** for native H3 until a 4090 GPU smoke test. [Comfy Org recommends FP8](https://huggingface.co/Comfy-Org/MiniMax-H3) only when INT8 ConvRot cannot run. The image now chooses its attention backend and diffusion model automatically, without separate template variables.

At startup `preflight.py` prints the GPU and host driver, checks the installed PyTorch CUDA wheel and initializes the GPU *before* starting ComfyUI. A Docker build and the CI tests cannot verify the actual RunPod GPU. If preflight fails, do not download weights; use the logged driver version to select a different host or image.

## Preset

Five files from `Comfy-Org/MiniMax-H3`: pruned INT8 ConvRot UNet (FP8 in cu128), NVFP4 AWQ Qwen text encoder, FP16 video VAE, FP32 audio VAE, 8-step Turbo LoRA. The download page puts files under `/data/models/{diffusion_models,text_encoders,vae,loras}` and the ComfyUI `models` directory points there. Models are downloaded only when requested. No other H3 files or style embeddings are needed for the default I2V example.

## Build and use

1. Create a GitHub repository and add these source files.
2. Create a Docker Hub repository `comfyui` and set GitHub Actions secrets `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` (a Docker Hub access token, not your password).
3. Merging a PR to `main` builds and pushes both images automatically; **Build IunoASC ComfyUI** can also be triggered manually. A successful GitHub Action only proves the images built; it does not prove H3 runs on a GPU.
4. Create or edit two private RunPod templates with `Container Image` `<namespace>/comfyui:torch2.9.1-cu130-r2` and `<namespace>/comfyui:torch2.9.1-cu128-r2`, **HTTP port `3000` only**, and `PANEL_PASSWORD`. Remove old `IUNO_ATTENTION` and `IUNO_H3_DIFFUSION_FILE` overrides so the matching defaults built into each image take effect.
5. Use **Container Disk**, sized for the image, ~45 GB of H3 files and outputs. No network volume. Check the storage selection before launch so the template does not create a paid Volume Disk by default.
6. Before downloading weights, check container logs for `[IunoASC] GPU preflight passed` and the ComfyUI ready message. On the Pod, open the port `3000` link and enter `iunoasc` / your `PANEL_PASSWORD` once. Add `/iuno/models/` to fetch weights and download the matching workflow; drag the workflow JSON into ComfyUI at `/`. Add `/iuno/outputs/` to download finished outputs. Verify the archive on your PC before stopping the Pod.

## Limits to validate on GPU

- This build has not been run with a 5090 or 4090; H3 memory, Comfy Kitchen, audio/video decode, and the FP8 cu128 workflow need real Pod tests.
- The page shows progress by file, not per-byte transfer rate. Hugging Face may cache metadata beside files in `/data/models/.cache`.
- If 8081 is restarted mid-download, the in-memory job status is lost. HF library metadata can avoid downloading finished files again when rerun.
- Installing arbitrary custom nodes through Manager may change packages in the running Pod; a fresh Pod restores the base image.
- RunPod stops erase Container Disk; termination also removes the Pod's own volume. Download outputs before either action.
