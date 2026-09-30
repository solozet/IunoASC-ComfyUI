"""Small independent model and output UIs, served on separate RunPod ports."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import uuid
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from huggingface_hub import HfApi, hf_hub_download
from pydantic import BaseModel, Field

from .core import H3_REPO, MODEL_DIR, OUTPUT_DIR, format_size, model_target, output_target, preset_files, preset_workflow

MODE = os.getenv("PANEL_MODE", "models")
if MODE not in {"models", "outputs"}:
    raise RuntimeError("PANEL_MODE must be models or outputs")

app = FastAPI(title=f"IunoASC {MODE}", docs_url=None, redoc_url=None, openapi_url=None)
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()



class TokenRequest(BaseModel):
    token: str = Field(default="", max_length=4096)


class LoraListRequest(TokenRequest):
    repo: str = Field(min_length=3, max_length=200)


class LoraDownloadRequest(LoraListRequest):
    filename: str = Field(min_length=1, max_length=500)


def _repo_name(repo: str) -> str:
    repo = repo.strip().removeprefix("https://huggingface.co/").strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or ".." in repo:
        raise HTTPException(400, "Укажи HF-репозиторий в формате автор/модель")
    return repo


def _new_job(files: list[tuple[str, str, str]], token: str) -> str:
    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {"state": "running", "done": 0, "total": len(files), "current": "", "error": ""}

    def run() -> None:
        try:
            for repo, source, destination in files:
                with jobs_lock:
                    jobs[job_id]["current"] = source
                target = model_target(destination)
                target.parent.mkdir(parents=True, exist_ok=True)
                if repo == H3_REPO:
                    # local_dir preserves the official model subdirectories.
                    hf_hub_download(repo_id=repo, filename=source, local_dir=MODEL_DIR, token=token or None)
                elif not target.is_file() or target.stat().st_size == 0:
                    # Keep a single copy; moving inside the same filesystem is cheap.
                    staging = MODEL_DIR / ".hf-loras" / repo.replace("/", "_")
                    downloaded = Path(hf_hub_download(repo_id=repo, filename=source, local_dir=staging, token=token or None))
                    shutil.move(downloaded, target)
                with jobs_lock:
                    jobs[job_id]["done"] += 1
            with jobs_lock:
                jobs[job_id]["state"] = "done"
        except Exception:
            # Do not reflect library exception strings: they may include private URLs.
            with jobs_lock:
                jobs[job_id]["state"] = "failed"
                jobs[job_id]["error"] = "Не удалось скачать файл. Проверь HF-токен, доступ к модели и свободное место."

    threading.Thread(target=run, daemon=True).start()
    return job_id


@app.get("/", response_class=HTMLResponse)
def index():
    name = "models.html" if MODE == "models" else "outputs.html"
    return (Path(__file__).parent / "static" / name).read_text(encoding="utf-8")


@app.get("/style.css")
def css():
    return FileResponse(Path(__file__).parent / "static" / "style.css", media_type="text/css")


@app.get("/app.js")
def javascript():
    return FileResponse(Path(__file__).parent / "static" / "app.js", media_type="text/javascript")


@app.get("/api/preset")
def preset_status():
    if MODE != "models":
        raise HTTPException(404)
    return {"files": [{"filename": f, "ready": model_target(f).is_file()} for f in preset_files()]}


@app.get("/api/workflow")
def workflow():
    if MODE != "models":
        raise HTTPException(404)
    import json

    return Response(
        json.dumps(preset_workflow(), ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="iunoasc-h3-i2v.json"'},
    )


@app.post("/api/preset")
def download_preset(request: TokenRequest):
    if MODE != "models":
        raise HTTPException(404)
    return {"id": _new_job([(H3_REPO, f, f) for f in preset_files()], request.token)}


@app.post("/api/loras")
def lora_files(request: LoraListRequest):
    if MODE != "models":
        raise HTTPException(404)
    try:
        files = HfApi(token=request.token or None).list_repo_files(repo_id=_repo_name(request.repo))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Не удалось открыть HF-репозиторий. Проверь адрес и токен.")
    return {"files": [f for f in files if f.lower().endswith(".safetensors")]}


@app.post("/api/loras/download")
def download_lora(request: LoraDownloadRequest):
    if MODE != "models":
        raise HTTPException(404)
    repo = _repo_name(request.repo)
    filename = request.filename
    path = PurePosixPath(filename)
    if path.is_absolute() or ".." in path.parts or not filename.lower().endswith(".safetensors"):
        raise HTTPException(400, "Выбери файл .safetensors из HF-репозитория")
    return {"id": _new_job([(repo, filename, f"loras/{path.name}")], request.token)}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404)
        return dict(job)


@app.get("/api/outputs")
def outputs(path: str = Query(default="")):
    if MODE != "outputs":
        raise HTTPException(404)
    directory = output_target(path)
    if not directory.is_dir():
        raise HTTPException(404)
    result = []
    for item in sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if item.is_symlink():
            continue
        rel = item.relative_to(OUTPUT_DIR).as_posix()
        result.append({"name": item.name, "path": rel, "directory": item.is_dir(), "size": "" if item.is_dir() else format_size(item.stat().st_size)})
    return {"path": path, "files": result}


@app.get("/api/outputs/file")
def output_file(path: str):
    if MODE != "outputs":
        raise HTTPException(404)
    file = output_target(path)
    if not file.is_file() or file.is_symlink():
        raise HTTPException(404)
    return FileResponse(file, filename=file.name, media_type="application/octet-stream")


@app.get("/api/outputs/archive")
def output_archive():
    if MODE != "outputs":
        raise HTTPException(404)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not any(OUTPUT_DIR.iterdir()):
        raise HTTPException(404, "Папка outputs пока пуста")

    # zip writes to stdout; the server streams it without creating a second
    # copy of every video on the Pod's paid container disk.
    # -y stores symlinks instead of following them outside outputs.
    process = subprocess.Popen(["zip", "-0", "-r", "-y", "-", "."], cwd=OUTPUT_DIR, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def stream():
        try:
            assert process.stdout is not None
            while chunk := process.stdout.read(1024 * 1024):
                yield chunk
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait()

    return StreamingResponse(stream(), media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="iunoasc-outputs.zip"'})
