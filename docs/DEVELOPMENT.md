# Development and validation

[README](../README.md)

## Build and publish

| Step | Action |
| --- | --- |
| Docker Hub | Create the `comfyui` repository |
| GitHub secrets | Configure `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` |
| Publish | Push to `main` to build and publish all four variants |
| Manual build | Run **Build IunoASC ComfyUI** in GitHub Actions |
| Documentation changes | Add `[skip ci]` to the commit message to avoid rebuilding images |

Workflow: [build.yml](../.github/workflows/build.yml). Both short tags and ComfyUI-release tags are mutable; record the published digest for reproducible deployments.

## Runtime components

| Component | Details |
| --- | --- |
| Web panels | FastAPI / Uvicorn |
| Public gateway | nginx |
| Weight transport | Hugging Face Hub |
| Classic Manager | `--enable-manager --enable-manager-legacy-ui` |
| Bundled workflow tools | `custom_nodes/iunoasc_tools`; optional LoRA loader, resolution tools and workflow-open link |
| Spectrum installation | [ComfyUI-Spectrum-MiniMax-H3](https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3), revision `dc6e1b335e1cdcd078a649add6464dab9469a587` |
| Existing Spectrum checkout | Preserved instead of overwritten |
| Browser ZIP | Locally bundled zip.js 2.23.0; [BSD license](../panel/static/zip-native.LICENSE) |

The pinned Spectrum snapshot and the bundled helper package require no extra pip dependencies. The optional LoRA loader returns the input model without resolving a filename when disabled or at zero strength.

## Driver policy

Startup thresholds use drivers paired with each NVIDIA base release as a conservative project policy, rather than NVIDIA's universal compatibility minimum.

| NVIDIA base | Project threshold | Release notes |
| --- | --- | --- |
| CUDA 12.8.1 | 570.124.06 | [NVIDIA](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-toolkit-release-notes/index.html) |
| CUDA 13.0.2 | 580.95.05 | [NVIDIA](https://docs.nvidia.com/cuda/archive/13.0.2/cuda-toolkit-release-notes/index.html) |
| CUDA 13.1.1 | 590.48.01 | [NVIDIA](https://docs.nvidia.com/cuda/archive/13.1.1/cuda-toolkit-release-notes/index.html) |
| CUDA 13.2.0 | 595.45.04 | [NVIDIA](https://docs.nvidia.com/cuda/archive/13.2.0/cuda-toolkit-release-notes/index.html) |

PyTorch 2.9.1 uses official cu128 or cu130 wheels; the cu131/cu132 images change the NVIDIA base while retaining the cu130 wheel. See [PyTorch packages](https://pytorch.org/get-started/previous-versions/#v291).

RunPod's CUDA host filter is a scheduling aid. Preflight checks the actual driver and GPU, CUDA initialization, FP16 matrix multiplication, standard attention and Kitchen CUDA quantization where enabled. It has a 90-second timeout. It does not stop RunPod billing.

## Validation

Resource-monitoring and browser-backup release: [`8e28c23`](https://github.com/solozet/IunoASC-ComfyUI/commit/8e28c23c6a2379dd2f1417a37975eebf1ca6112c). [Successful build and CI run](https://github.com/solozet/IunoASC-ComfyUI/actions/runs/38093212256).

| Check | Covered behavior |
| --- | --- |
| Python tests | Preset manifests, disabled empty LoRA, preserved workspace, byte ranges, video metadata, session ZIP, HF progress/retries/routing and preflight errors |
| Resource telemetry | Container CPU quotas and memory limits, host fallbacks, unavailable sensors and GPU optional-query handling |
| Frontend tests | Six languages, three pages, cross-port links, video playback, selection preservation and docked download progress |
| Browser backup tests | Complete copies, truncated/changing-file rejection, storage quota handling, offline shell and valid ZIP64 export without network access |
| Docker build checks | CPU imports, all four public ports, preset/workflow APIs and output file/ZIP routes |
| Spectrum install checks | Pinned snapshot and repeat installation in a temporary directory |

These checks do not run a full GPU generation. Earlier cu130 CUDA/Kitchen startup passed on an RTX 4090; this belongs to an earlier image, not the current release's GPU validation. Full generation, peak memory and the experimental Light VAE's speed/quality/HDR still require a GPU run.

## Hugging Face downloader

Supported extensions: `.safetensors`, `.gguf`, `.ckpt`, `.bin`, `.pt`, `.pth`. The destination type is explicit; the downloader does not infer architecture or loader compatibility.

Files are flattened to their basename. Existing non-empty files are reused by the general downloader; preset files additionally check exact manifest sizes. Downloads run serially and retry transient failures up to three attempts. Preset installation requires the remaining download size plus at least 1 GiB free working space. Job progress is held in memory; after a panel restart, repeating installation reuses completed files.

## Media and browser storage

Original playback supports HTTP byte ranges. Thumbnails are generated from the first frame and cached. Video metadata comes from ffprobe. Server-side output/session ZIPs stream without a second archive on Pod disk.

Browser output backup uses Cache Storage and only promotes a copy after validating its complete byte count and unchanged remote version. The service worker caches the UI shell, not API responses. ZIP64 export uses the local zip.js bundle; offline export does not contact the Pod or a CDN.

| Browser behavior | Reference |
| --- | --- |
| Storage quotas, origin isolation and eviction | [MDN](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria) |
| Native save-file API | [MDN](https://developer.mozilla.org/en-US/docs/Web/API/Window/showSaveFilePicker) |

## Workflow metadata

Effective loader selections and weight manifests define the preset downloads. LightSpeed download annotations match the selected FL2VA diffusion model and INT8 video VAE. The experimental workflow points its Light VAE annotation to Kijai/MiniMax-H3-experimental. See [LightSpeed manifest and installation details](my-h3-preset.md).
