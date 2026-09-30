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

| Short tag (alias) | Versioned tag | NVIDIA base CUDA | PyTorch wheel | Attention / model | Host driver policy |
| --- | --- | --- | --- | --- | --- |
| `cu130` | `comfy0.38.0-cu130` | 13.0.2 | 2.9.1+cu130 (CUDA 13.0) | Comfy Kitchen / INT8 ConvRot | >= 580.95.05 |
| `cu128` | `comfy0.38.0-cu128` | 12.8.1 | 2.9.1+cu128 (CUDA 12.8) | Standard / FP8 scaled | >= 570.124.06 |
| `cu131` | `comfy0.38.0-cu131` | 13.1.1 | 2.9.1+cu130 (CUDA 13.0) | Comfy Kitchen / INT8 ConvRot | >= 590.48.01 |
| `cu132` | `comfy0.38.0-cu132` | 13.2.0 | 2.9.1+cu130 (CUDA 13.0) | Comfy Kitchen / INT8 ConvRot | >= 595.45.04 |

All tags are under `solozeet/comfyui`. For quick switching, use `solozeet/comfyui:cu130` and change only the suffix to `cu128`, `cu131` or `cu132`. The short aliases follow future releases; `comfy0.38.0-cu130` (and its sibling tags) selects this ComfyUI release. Existing `r2` and `r3` tags are not overwritten. All four variants still need an end-to-end H3 test on a real GPU.

**In our short and versioned tags, cu131/cu132 identify the NVIDIA base, not the PyTorch wheel. The last two rows remain experimental base-image variants, not native PyTorch cu131/cu132 builds.** [Official PyTorch 2.9.1 packages](https://pytorch.org/get-started/previous-versions/#v291) are available for cu126/cu128/cu130, not cu131/cu132. PyTorch's CUDA version in both new images remains **13.0**. Its wheel installs its own CUDA dependencies, so a newer base does not upgrade every library used for computation. The tests compare base environments while preserving the existing torch/torchvision/torchaudio stack. Newer PyTorch cu132 releases exist; upgrading PyTorch is a separate change. ComfyUI 0.38.0 removed its core torchaudio dependency; this image retains torchaudio 2.9.1 alongside the matching PyTorch for existing custom-node compatibility.

The driver floors above are this project's conservative policy, using the paired Linux drivers from NVIDIA's release notes for [12.8.1](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-toolkit-release-notes/index.html), [13.0.2](https://docs.nvidia.com/cuda/archive/13.0.2/cuda-toolkit-release-notes/index.html), [13.1.1](https://docs.nvidia.com/cuda/archive/13.1.1/cuda-toolkit-release-notes/index.html), and [13.2.0](https://docs.nvidia.com/cuda/archive/13.2.0/cuda-toolkit-release-notes/index.html). They are **not universal NVIDIA minimums**: CUDA 13.x minor-version compatibility permits some applications on R580, with restrictions. These images deliberately avoid depending on that for newer bases. A newer base does not repair error 804 or install a host driver.

In RunPod **Additional filters → CUDA Versions**, select the base's minor version and newer versions (13.1+ for base13.1.1, 13.2+ for base13.2.0), then confirm the exact driver in startup logs. This does not test or repair the host's container runtime. The NVIDIA entrypoint may reject an incompatible host before our script runs; retain RunPod system logs in that case. Do not disable NVIDIA's compatibility checks.

ComfyUI is pinned to `v0.38.0`, with Comfy Kitchen `0.2.36`. [Comfy Org recommends FP8](https://huggingface.co/Comfy-Org/MiniMax-H3) only when INT8 ConvRot cannot run. Each image chooses its attention backend and diffusion model automatically. Do not set `IUNO_TORCH_INDEX` or `IUNO_CUDA_BASE_VERSION` in RunPod; they describe the actual built image.

At startup `preflight.py` prints the base CUDA, PyTorch CUDA, GPU, driver, SM architecture and VRAM. It verifies the wheel, initializes CUDA, performs tiny FP16 matrix multiplication and standard attention, and (for CK images) forces a Comfy Kitchen CUDA quantization operation with a result check. It logs actual loaded CUDA library paths, including `libcuda`, to help diagnose unwanted compatibility libraries. The startup check has a 90-second timeout. These smoke tests do not validate all H3 kernels, model memory requirements, or video/audio generation.

**Preflight failure exits the container; it does not stop the paid RunPod allocation.** Save the logs and stop/terminate a failing Pod yourself instead of waiting through restart loops. The script does not install host drivers, automatically change images, or download models. CI tests mock the GPU and verify failure handling only; a Docker build runs CPU import checks and cannot prove GPU compatibility.

## ComfyUI 0.38.0 and Manager

This release is useful for H3: it fixes VAE tile-crossing seams ([#16436](https://github.com/Comfy-Org/ComfyUI/pull/16436)) and a fused `rms_rope` crash when `qk_norm_scale` is offloaded to CPU ([#16485](https://github.com/Comfy-Org/ComfyUI/pull/16485)). It also adds MiniMax-H3 Fun-Controlnet-Union 2.0 support; the default I2V preset still downloads only its original five files. See the [release notes](https://github.com/Comfy-Org/ComfyUI/releases/tag/v0.38.0). These application changes do not repair host CUDA error 804.

**ComfyUI Manager is installed and enabled.** The Dockerfile installs upstream `manager_requirements.txt` (`comfyui_manager==4.2.2` for v0.38.0), and `start.sh` passes `--enable-manager`. Build logs print the installed Manager version. Access it from ComfyUI after the server starts; it does not use a separate exposed port. No extra Manager installation or startup argument is needed.

## Preset

Five files from `Comfy-Org/MiniMax-H3`: pruned INT8 ConvRot UNet (FP8 in cu128), NVFP4 AWQ Qwen text encoder, FP16 video VAE, FP32 audio VAE, 8-step Turbo LoRA. The download page puts files under `/data/models/{diffusion_models,text_encoders,vae,loras}` and the ComfyUI `models` directory points there. Models are downloaded only when requested. No other H3 files or style embeddings are needed for the default I2V example.

## Build and use

1. Create a GitHub repository and add these source files.
2. Create a Docker Hub repository `comfyui` and set GitHub Actions secrets `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` (a Docker Hub access token, not your password).
3. Merging a PR to `main` builds and pushes all four images automatically; **Build IunoASC ComfyUI** can also be triggered manually. A successful GitHub Action only proves the images built; it does not prove H3 runs on a GPU.
4. Create a private RunPod template for each variant you want to test, with `Container Image` `solozeet/comfyui:<tag from the table>`, **HTTP port `3000` only**, and `PANEL_PASSWORD`. Remove old `IUNO_ATTENTION` and `IUNO_H3_DIFFUSION_FILE` overrides so the matching defaults built into each image take effect.
5. Use **Container Disk**, sized for the image, ~45 GB of H3 files and outputs. No network volume. Check the storage selection before launch so the template does not create a paid Volume Disk by default.
6. Before downloading weights, check container logs for `[IunoASC] GPU preflight passed` and the ComfyUI ready message. On the Pod, open the port `3000` link and enter `iunoasc` / your `PANEL_PASSWORD` once. Add `/iuno/models/` to fetch weights and download the matching workflow; drag the workflow JSON into ComfyUI at `/`. Add `/iuno/outputs/` to download finished outputs. Verify the archive on your PC before stopping the Pod.

## Limits to validate on GPU

- These builds have not been run with a 5090, 4090, L40 or L40S; H3 memory, Comfy Kitchen, audio/video decode, and the FP8 cu128 workflow need real Pod tests.
- The page shows progress by file, not per-byte transfer rate. Hugging Face may cache metadata beside files in `/data/models/.cache`.
- If 8081 is restarted mid-download, the in-memory job status is lost. HF library metadata can avoid downloading finished files again when rerun.
- Installing arbitrary custom nodes through Manager may change packages in the running Pod; a fresh Pod restores the base image.
- RunPod stops erase Container Disk; termination also removes the Pod's own volume. Download outputs before either action.
