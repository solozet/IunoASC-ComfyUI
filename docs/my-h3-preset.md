# LightSpeed H3 preset

The preset is based on the user-edited MY workflow and packaged as a native ComfyUI subgraph. Source: [MiniMax H3 Ultra Fastest True 4 Steps + HD Sound | 6GB VRAM 16GB RAM [V8 Update] Lightning Speed](https://civitai.com/models/2835250?modelVersionId=3305336) by [RedditUser9811](https://civitai.com/user/RedditUser9811).

## Required weights

| File | Directory | Bytes |
| --- | --- | ---: |
| minimax_h3_fl2va_pruned_int8_convrot.safetensors | diffusion_models | 20,970,379,616 |
| qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors | text_encoders | 15,687,142,551 |
| minimax_h3_video_vae_int8_convrot.safetensors | vae | 2,811,065,184 |
| minimax_h3_audio_vae_fp32.safetensors | vae | 605,254,808 |
| minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors | loras | 620,285,592 |

Total: **40,694,127,751 bytes = 40.69 GB**. The first four files are from Comfy-Org/MiniMax-H3. Turbo v4 is from drbaph/MiniMax-H3-Turbo-Lora-ComfyUI. With the cu130 official preset already installed, 3.43 GB is additional; both presets use 47.86 GB. cu128's official preset has a different diffusion model.

## Workflow and installation

| Component | Behavior |
| --- | --- |
| Turbo LoRA | Enabled, strength 1.0; switch bypasses the loader when off |
| Additional LoRA | Disabled; filename selector and independent strength. The initial filename matches the installed Turbo file and creates no additional download. |
| Video | HDR, 10-bit, 24 FPS; FPS also controls frame count |
| Sampling | 5 seconds, 5 steps; Spectrum enabled |
| Resolution | Main-canvas selector, 9:16, 2 MP, multiple 32, live dimensions |
| Noise | Hidden inside the subgraph, randomize |
| Reference images | Six bypassed loaders; supply your own images and enable the needed nodes |
| Resolution reference note | Main canvas |
| Workflow location | /opt/ComfyUI/user/default/workflows/lightspeed-h3.json |
| Custom package | xmarre/ComfyUI-Spectrum-MiniMax-H3 at dc6e1b335e1cdcd078a649add6464dab9469a587 |

Spectrum is the only custom-node package and has no extra pip dependencies at the pinned revision. An existing Spectrum installation is preserved. Restart ComfyUI through Manager after installing nodes. The installer saves the workflow on the Pod and also offers a browser download.

The original graph's stale duplicate prompt edge and dangling audio link were removed when packing. The effective prompt remains empty by default. Frame-count rounding follows the original H3 formula, now using the selected FPS. Changing FPS is not frame interpolation. No TAE preview or RTX upscale is included.

Validation checks loader files against the manifest, both graph boundaries, defaults and install retry behavior. The compact workflow has not been fully validated through a GPU generation in the new container. The user's earlier successful local use (16 GB RAM, 12 GB VRAM, 90 GB pagefile) is not a verified container minimum. LightSpeed retains INT8/Kitchen Attention on every variant; cu128 compatibility remains unverified.
