"""Small independent model and output UIs, served on separate RunPod ports."""

from __future__ import annotations

import hmac
import os
import re
import shutil
import subprocess
import threading
import uuid
from pathlib import Path, PurePosixPath

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from huggingface_hub import HfApi, hf_hub_download
from pydantic import BaseModel, Field

from .core import H3_REPO, MODEL_DIR, OUTPUT_DIR, format_size, model_target, output_target, preset_files

MODE = os.getenv("PANEL_MODE", "models")
if MODE not in {"models", "outputs"}:
    raise RuntimeError("PANEL_MODE must be models or outputs")

app = FastAPI(title=f"IunoASC {MODE}", docs_url=None, redoc_url=None, openapi_url=None)
basic = HTTPBasic(auto_error=False)
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


def authenticated(credentials: HTTPBasicCredentials | None = Depends(basic)) -> None:
    expected = os.getenv("PANEL_PASSWORD", "")
    if not expected:
        raise RuntimeError("Set PANEL_PASSWORD before exposing the panel")
    if credentials is None or not hmac.compare_digest(credentials.password, expected):
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": 'Basic realm="IunoASC"'})


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


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(authenticated)])
def index():
    name = "models.html" if MODE == "models" else "outputs.html"
    return (Path(__file__).parent / "static" / name).read_text(encoding="utf-8")


@app.get("/style.css", dependencies=[Depends(authenticated)])
def css():
    return FileResponse(Path(__file__).parent / "static" / "style.css", media_type="text/css")


@app.get("/app.js", dependencies=[Depends(authenticated)])
def javascript():
    return FileResponse(Path(__file__).parent / "static" / "app.js", media_type="text/javascript")


@app.get("/api/preset", dependencies=[Depends(authenticated)])
def preset_status():
    if MODE != "models":
        raise HTTPException(404)
    return {"files": [{"filename": f, "ready": model_target(f).is_file()} for f in preset_files()]}


@app.post("/api/preset", dependencies=[Depends(authenticated)])
def download_preset(request: TokenRequest):
    if MODE != "models":
        raise HTTPException(404)
    return {"id": _new_job([(H3_REPO, f, f) for f in preset_files()], request.token)}


@app.post("/api/loras", dependencies=[Depends(authenticated)])
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


@app.post("/api/loras/download", dependencies=[Depends(authenticated)])
def download_lora(request: LoraDownloadRequest):
    if MODE != "models":
        raise HTTPException(404)
    repo = _repo_name(request.repo)
    filename = request.filename
    path = PurePosixPath(filename)
    if path.is_absolute() or ".." in path.parts or not filename.lower().endswith(".safetensors"):
        raise HTTPException(400, "Выбери файл .safetensors из HF-репозитория")
    return {"id": _new_job([(repo, filename, f"loras/{path.name}")], request.token)}


@app.get("/api/jobs/{job_id}", dependencies=[Depends(authenticated)])
def job_status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404)
        return dict(job)


@app.get("/api/outputs", dependencies=[Depends(authenticated)])
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


@app.get("/api/outputs/file", dependencies=[Depends(authenticated)])
def output_file(path: str):
    if MODE != "outputs":
        raise HTTPException(404)
    file = output_target(path)
    if not file.is_file() or file.is_symlink():
        raise HTTPException(404)
    return FileResponse(file, filename=file.name, media_type="application/octet-stream")


@app.get("/api/outputs/archive", dependencies=[Depends(authenticated)])
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
