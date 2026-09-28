"""Model manifest and filesystem helpers shared by the two web panels."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

DATA_DIR = Path(os.getenv("IUNO_DATA_DIR", "/data"))
MODEL_DIR = DATA_DIR / "models"
OUTPUT_DIR = DATA_DIR / "outputs"

H3_REPO = "Comfy-Org/MiniMax-H3"
H3_FILES = (
    "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
    "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    "vae/minimax_h3_video_vae_fp16.safetensors",
    "vae/minimax_h3_audio_vae_fp32.safetensors",
    "loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
)


def preset_files() -> tuple[str, ...]:
    diffusion = os.getenv("IUNO_H3_DIFFUSION_FILE", H3_FILES[0])
    if diffusion not in {
        H3_FILES[0],
        "diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled.safetensors",
    }:
        raise ValueError("Unsupported H3 diffusion model")
    return (diffusion, *H3_FILES[1:])


def model_target(filename: str) -> Path:
    rel = PurePosixPath(filename)
    if rel.is_absolute() or ".." in rel.parts or len(rel.parts) < 2:
        raise ValueError("Invalid model path")
    if rel.parts[0] not in {"diffusion_models", "text_encoders", "vae", "loras", "embeddings"}:
        raise ValueError("Unsupported model directory")
    target = (MODEL_DIR / Path(*rel.parts)).resolve()
    if not target.is_relative_to(MODEL_DIR.resolve()):
        raise ValueError("Invalid model path")
    return target


def output_target(filename: str) -> Path:
    root = OUTPUT_DIR.resolve()
    target = (root / filename).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Invalid output path")
    return target


def format_size(size: int) -> str:
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if size < 1024 or unit == "ТБ":
            return f"{size:.1f} {unit}" if unit != "Б" else f"{size} Б"
        size /= 1024
    raise AssertionError
