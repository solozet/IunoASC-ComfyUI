"""Check the actual RunPod GPU before starting ComfyUI or the web panels."""

from __future__ import annotations

import os
import re
import subprocess
import sys


def driver_major(version: str) -> int:
    match = re.match(r"(\d+)\.", version)
    if not match:
        raise ValueError(f"Unexpected NVIDIA driver version: {version!r}")
    return int(match.group(1))


def main() -> int:
    variant = os.environ["IUNO_TORCH_INDEX"]
    expected_cuda = {"cu130": "13.0", "cu128": "12.8"}[variant]

    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        devices = [line.strip().rsplit(", ", 1) for line in result.stdout.splitlines() if line.strip()]
        if not devices or any(len(device) != 2 for device in devices):
            raise ValueError("nvidia-smi did not return a GPU and driver version")
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as exc:
        print(f"[IunoASC] NVIDIA GPU unavailable: {exc}", file=sys.stderr)
        return 1

    for name, driver in devices:
        print(f"[IunoASC] GPU: {name}; host NVIDIA driver: {driver}", flush=True)
        if variant == "cu130" and driver_major(driver) < 580:
            print(
                "[IunoASC] CUDA 13 needs host driver R580 or newer. "
                "This host cannot run the cu130 image. Choose a RunPod host "
                "with driver R580+ or use the cu128 image (FP8 preset).",
                file=sys.stderr,
            )
            return 1

    try:
        import torch

        if torch.version.cuda != expected_cuda:
            print(
                f"[IunoASC] Wrong PyTorch wheel: CUDA {torch.version.cuda!r}, "
                f"expected {expected_cuda} for {variant}.",
                file=sys.stderr,
            )
            return 1
        torch.cuda.init()
        name = torch.cuda.get_device_name(0)
        print(f"[IunoASC] PyTorch {torch.__version__}; CUDA {torch.version.cuda}; device {name}", flush=True)
    except Exception as exc:
        print(f"[IunoASC] PyTorch cannot initialize CUDA: {exc}", file=sys.stderr)
        print(
            "[IunoASC] Check the host driver and GPU. CUDA error 804 means "
            "forward compatibility is unsupported for this host/GPU combination. "
            "Try cu128 on an older host, or select a host with driver R580+ for cu130.",
            file=sys.stderr,
        )
        return 1

    print(f"[IunoASC] GPU preflight passed ({variant}).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
