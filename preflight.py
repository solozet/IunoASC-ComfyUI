"""Check the real host and execute tiny GPU operations before starting services.

The unit tests mock hardware. Only this script running on a GPU tests CUDA;
it still does not validate a full H3 generation or the model's memory needs.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys

# Conservative native-driver policy for the new experimental bases. NVIDIA's
# broader CUDA 13.x minor compatibility floor is R580; these two experiments
# deliberately require the driver paired with their base to avoid relying on it.
# https://docs.nvidia.com/cuda/archive/13.1.1/cuda-toolkit-release-notes/index.html
# https://docs.nvidia.com/cuda/archive/13.2.0/cuda-toolkit-release-notes/index.html
PROFILES = {
    ("13.0.2", "cu130"): (580, 95, 5),
    ("12.8.1", "cu128"): (570, 124, 6),
    ("13.1.1", "cu130"): (590, 48, 1),
    ("13.2.0", "cu130"): (595, 45, 4),
}
TORCH_CUDA = {"cu130": "13.0", "cu128": "12.8"}


def driver_version(version: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", version):
        raise ValueError(f"Unexpected NVIDIA driver version: {version!r}")
    parts = [int(part) for part in version.split(".")]
    return tuple((parts + [0])[:3])


def loaded_cuda_libraries() -> list[str]:
    """Read actual mappings, not an assumed library search path. No env dump."""
    try:
        lines = Path("/proc/self/maps").read_text().splitlines()
    except OSError:
        return []
    return sorted({line.split()[-1] for line in lines
                   if re.search(r"/(?:libcuda|libcudart|libcublas|libcudnn)[^/ ]*\.so", line)})


def report_libraries() -> None:
    for path in loaded_cuda_libraries():
        print(f"[IunoASC] Loaded CUDA library: {path}", flush=True)


def gpu_smoke_test(torch, attention: str) -> None:
    """Exercise allocation, kernels, cuBLAS and attention on the first GPU."""
    with torch.inference_mode():
        x = torch.ones((32, 128), device="cuda:0", dtype=torch.float16)
        y = x @ x.T
        torch.cuda.synchronize()
        if not torch.all(y == 128).item():
            raise RuntimeError("GPU matmul returned an incorrect result")
        q = torch.ones((1, 2, 32, 64), device="cuda:0", dtype=torch.float16)
        result = torch.nn.functional.scaled_dot_product_attention(q, q, q)
        torch.cuda.synchronize()
        if not torch.allclose(result, q, rtol=0.001, atol=0.001):
            raise RuntimeError("GPU attention returned an incorrect result")
        print("[IunoASC] PyTorch GPU matmul and SDPA smoke tests passed.", flush=True)
        if attention == "ck":
            import comfy_kitchen as ck

            backends = ck.list_backends()
            cuda_backend = backends.get("cuda", {})
            if not cuda_backend.get("available") or cuda_backend.get("disabled"):
                raise RuntimeError(f"Comfy Kitchen CUDA backend unavailable: {cuda_backend}")
            # Explicit backend selection prevents a silent eager fallback.
            with ck.use_backend("cuda"):
                quantized = ck.quantize_per_tensor_fp8(
                    x, torch.ones((1,), device="cuda:0", dtype=torch.float32)
                )
            torch.cuda.synchronize()
            if not torch.all(quantized.float() == 1).item():
                raise RuntimeError("Comfy Kitchen CUDA quantization returned an incorrect result")
            print("[IunoASC] Comfy Kitchen CUDA quantization smoke test passed.", flush=True)


def main() -> int:
    variant = os.environ.get("IUNO_TORCH_INDEX", "")
    base = os.environ.get("IUNO_CUDA_BASE_VERSION", "")
    profile = PROFILES.get((base, variant))
    attention = os.environ.get("IUNO_ATTENTION", "torch" if variant == "cu128" else "ck")
    if profile is None or attention not in {"torch", "ck"}:
        print(f"[IunoASC] Unsupported configuration: base={base!r}, wheel={variant!r}, attention={attention!r}", file=sys.stderr)
        return 1
    print(f"[IunoASC] Base CUDA {base}; PyTorch wheel {variant}; attention {attention}.", flush=True)
    print("[IunoASC] Preflight does not install host drivers or stop RunPod billing.", flush=True)
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
            check=True, capture_output=True, text=True, timeout=15,
        )
        devices = [line.rsplit(",", 1) for line in result.stdout.splitlines() if line.strip()]
        if not devices or any(len(device) != 2 for device in devices):
            raise ValueError("nvidia-smi did not return a GPU and driver version")
        for name, driver in devices:
            name, driver = name.strip(), driver.strip()
            print(f"[IunoASC] GPU: {name}; host NVIDIA driver: {driver}", flush=True)
            if driver_version(driver) < profile:
                required = ".".join(map(str, profile))
                print(
                    f"[IunoASC] This image's conservative driver policy requires >= {required} "
                    f"(R{profile[0]}+) for base CUDA {base}. Found {driver}. "
                    "Choose a matching RunPod host or an older base image. "
                    "This is an image policy, not NVIDIA's universal minimum for all CUDA 13.x applications.",
                    file=sys.stderr,
                )
                return 1
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"[IunoASC] NVIDIA GPU unavailable: {exc}", file=sys.stderr)
        return 1

    try:
        import torch

        expected_cuda = TORCH_CUDA[variant]
        if torch.version.cuda != expected_cuda:
            raise RuntimeError(f"Wrong PyTorch wheel: CUDA {torch.version.cuda!r}, expected {expected_cuda}")
        torch.cuda.init()
        props = torch.cuda.get_device_properties(0)
        print(
            f"[IunoASC] PyTorch {torch.__version__}; CUDA {torch.version.cuda}; "
            f"device {props.name}; SM {props.major}.{props.minor}; VRAM {props.total_memory / 2**30:.1f} GiB",
            flush=True,
        )
        gpu_smoke_test(torch, attention)
    except Exception as exc:
        print(f"[IunoASC] GPU preflight failed: {exc}", file=sys.stderr)
        if "804" in str(exc):
            print("[IunoASC] CUDA error 804: forward compatibility unsupported for the host/GPU/library combination. Check the loaded libcuda path and host driver; changing only the base CUDA version is not a guaranteed fix.", file=sys.stderr)
        report_libraries()
        return 1
    report_libraries()
    print(f"[IunoASC] GPU preflight passed (base {base}, wheel {variant}). H3 generation remains untested.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
