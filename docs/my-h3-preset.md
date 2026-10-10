# LightSpeed H3 manifest and installation

[README](../README.md) · [Development](DEVELOPMENT.md)

Source: [MiniMax H3 Ultra Fastest True 4 Steps + HD Sound | 6GB VRAM 16GB RAM [V8 Update] Lightning Speed](https://civitai.com/models/2835250?modelVersionId=3305336) by [RedditUser9811](https://civitai.com/user/RedditUser9811).

## Weight manifest

| File | Directory | Expected bytes |
| --- | --- | ---: |
| minimax_h3_fl2va_pruned_int8_convrot.safetensors | diffusion_models | 20,970,379,616 |
| qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors | text_encoders | 15,687,142,551 |
| minimax_h3_video_vae_int8_convrot.safetensors | vae | 2,811,065,184 |
| minimax_h3_audio_vae_fp32.safetensors | vae | 605,254,808 |
| minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors | loras | 620,285,592 |

Total: **40,694,127,751 bytes**. The first four files come from [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3). Turbo v4 comes from [drbaph/MiniMax-H3-Turbo-Lora-ComfyUI](https://huggingface.co/drbaph/MiniMax-H3-Turbo-Lora-ComfyUI).

The experimental preset replaces only the video VAE with `minimax_h3_lynnreal_light_vae_int8_convrot.safetensors` from [Kijai/MiniMax-H3-experimental](https://huggingface.co/Kijai/MiniMax-H3-experimental): **2,137,493,384 bytes**. The other four files are shared.

## Installation

| Item | Behavior |
| --- | --- |
| Source workflow | `workflows/minimax_h3_my.json` |
| Installed LightSpeed workflow | `/opt/ComfyUI/user/default/workflows/IunoASC/lightspeed-h3.json` |
| Experimental workflow | Same directory, `lightspeed-h3-light-vae.json` |
| Workspace seeding | All three preset workflows are seeded on startup; existing user edits are preserved |
| Spectrum | Revision `dc6e1b335e1cdcd078a649add6464dab9469a587`; existing installations are preserved |
| Restart | ComfyUI through Manager after installing Spectrum |
| Optional LoRA | Bundled IunoASC loader; disabled/zero-strength inputs bypass filename resolution |
| Model annotations | Names and source URLs match the loader selections and preset manifest |

Frame counts use the selected FPS and H3's supported frame-length rounding. Changing FPS does not interpolate existing frames. Sampling defaults are 5 seconds and 5 steps; video defaults are HDR, 10-bit and 24 FPS.
