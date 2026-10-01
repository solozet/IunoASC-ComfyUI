# MY.json preset — prepared, no image rebuild

The user supplied MY.json on 2026-10-01 after removing unused branches. This supersedes the provisional UltraFast v8 adaptation. The shipped workflow is an exact copy of the supplied JSON; no model, prompt, resolution, scheduler, bypass, link or Spectrum setting is changed.

## Selected weights

Actual loader widgets are authoritative. Embedded UNET metadata still names REF2VA and video VAE metadata still names FP16; neither is selected. The preset downloads these four files from Comfy-Org/MiniMax-H3:

| Directory / filename | Bytes | Decimal GB |
| --- | ---: | ---: |
| diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors | 20,970,379,616 | 20.9704 |
| text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors | 15,687,142,551 | 15.6871 |
| vae/minimax_h3_video_vae_int8_convrot.safetensors | 2,811,065,184 | 2.8111 |
| vae/minimax_h3_audio_vae_fp32.safetensors | 605,254,808 | 0.6053 |

Total: **40,073,842,159 bytes = 40.07 GB = 37.32 GiB**. With the default cu130 native preset already downloaded, only INT8 video VAE is additional: **2.81 GB**. Both presets together occupy **47,237,843,655 bytes = 47.24 GB** in weights. cu128 native preset uses a different FP8 diffusion model and does not share that diffusion file.

The graph contains no LoRA loader, TAE preview or RTX upscale. All six LoadImage nodes are bypassed. SpectrumApplyMiniMaxH3 is active; its record identifies xmarre/ComfyUI-Spectrum-MiniMax-H3 at dc6e1b335e1cdcd078a649add6464dab9469a587. No other custom node package is present, including within the subgraph. The install button downloads missing weights, installs the pinned Spectrum snapshot into /opt/ComfyUI/custom_nodes and saves lightspeed-h3.json to /opt/ComfyUI/user/default/workflows. It also triggers the workflow download in the browser. An existing Spectrum installation is preserved. ComfyUI must be restarted through Manager to load newly installed nodes; the installer does not interrupt a running generation or restart the Pod. Its recorded source snapshot is approximately 214 KB excluding git history, and its requirements list is empty. This is not a measured installed footprint.

The user reports successful local use with 16 GB RAM, 12 GB VRAM and a 90 GB pagefile. That is evidence for their local configuration, not a verified minimum or a cloud speed measurement. Disk weight size is not simultaneous RAM/VRAM usage. No Linux/GPU generation was run for this change.

The second card is titled LightSpeed H3 and hides its weight list behind a closed details section. Existing native preset and classic Manager draft settings are retained. No Docker build, main update, image tag change or Pod modification was performed.

Sources for sizes (HF metadata checked 2026-09-30, file listings checked 2026-10-01):
- https://huggingface.co/Comfy-Org/MiniMax-H3/tree/main/diffusion_models
- https://huggingface.co/Comfy-Org/MiniMax-H3/tree/main/text_encoders
- https://huggingface.co/Comfy-Org/MiniMax-H3/tree/main/vae
- https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3

Validation: 15 unit tests (one nginx integration skipped locally); JavaScript syntax; real Git fetch of the pinned Spectrum revision into a temporary Comfy directory; exported JSON equality with MY.json; repeat installation preserves the existing node version; failed fetch leaves no partial installation. No full GPU runtime test or image build.
