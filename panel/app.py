"""Small independent model and output UIs, served on separate RunPod ports."""

from __future__ import annotations

import os
import mimetypes
import time
import io
import shutil
import subprocess
import threading
import uuid
from pathlib import Path, PurePosixPath

from fastapi import Request, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from huggingface_hub import HfApi, hf_hub_download
from pydantic import BaseModel, Field
from huggingface_hub.utils import tqdm
from .diagnostics import runtime_status
from .media import metadata, thumbnail, MEDIA_SUFFIXES
from .session import collect_session, archive_stream

from .core import H3_REPO, MODEL_DIR, OUTPUT_DIR, format_size, model_target, output_target
from .presets import manifest, public_manifest, workflow_for, PRESET_IDS
from .install import install_preset
from .hf_source import parse_hf_source, weight_filename, WEIGHT_DIRECTORIES, WEIGHT_SUFFIXES

MODE = os.getenv("PANEL_MODE", "models")
if MODE not in {"models", "outputs", "control"}:
    raise RuntimeError("PANEL_MODE must be models, outputs or control")

app = FastAPI(title=f"IunoASC {MODE}", docs_url=None, redoc_url=None, openapi_url=None)
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()
download_lock = threading.Lock()
sessions: dict[str, tuple] = {}



class TokenRequest(BaseModel):
    token: str = Field(default="", max_length=4096)


class PresetRequest(TokenRequest):
    preset: str = "native-h3"
    include_optional: bool = False


class LoraListRequest(TokenRequest):
    repo: str = Field(min_length=3, max_length=1000)


class LoraDownloadRequest(LoraListRequest):
    filename: str = Field(min_length=1, max_length=500)


class WeightDownloadRequest(LoraListRequest):
    filename: str = Field(default='', max_length=500)
    directory: str = 'loras'


def _source(value: str):
    try:
        return parse_hf_source(value)
    except ValueError as error:
        raise HTTPException(400, {'code': str(error)}) from None


def _new_job(files: list[tuple], token: str, sizes: dict[str, int] | None = None, preset_id: str | None = None) -> str:
    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {"state": "running", "done": 0, "total": len(files) + bool(preset_id), "current": "", "error": "", "restart_required": False}

    class DownloadProgress(tqdm):
        def __init__(self, *args, **kwargs):
            kwargs["disable"] = False
            kwargs["file"] = io.StringIO()
            super().__init__(*args, **kwargs)
        def display(self, *args, **kwargs): pass
        def update(self, n=1):
            result=super().update(n)
            elapsed=max(time.monotonic()-started, .001)
            with jobs_lock:
                jobs[job_id].update(downloaded_bytes=int(self.n),file_total_bytes=int(self.total or 0),speed_bytes_sec=int(max(0,self.n-self.initial)/elapsed),progress_available=True)
            return result

    started=time.monotonic()

    def run() -> None:
        nonlocal started
        installing = False
        try:
            for file in files:
                repo, source, destination = file[:3]
                revision = file[3] if len(file) > 3 else 'main'
                with jobs_lock:
                    jobs[job_id].update(current=source,downloaded_bytes=0,file_total_bytes=(sizes or {}).get(destination,0),speed_bytes_sec=0,progress_available=False,attempt=1)
                started=time.monotonic()
                target = model_target(destination)
                target.parent.mkdir(parents=True, exist_ok=True)
                expected = (sizes or {}).get(destination)
                repair = target.is_file() and expected is not None and target.stat().st_size != expected
                def download(**kwargs):
                    for attempt in range(1,4):
                        with jobs_lock: jobs[job_id]["attempt"]=attempt
                        try:
                            return hf_hub_download(**kwargs,tqdm_class=DownloadProgress)
                        except Exception:
                            if attempt==3:raise
                            time.sleep(attempt)
                if repo == H3_REPO and source == destination and revision == 'main':
                    # local_dir preserves the official model subdirectories.
                    download(repo_id=repo, filename=source, local_dir=MODEL_DIR, token=token or None, force_download=repair)
                elif repair or not target.is_file() or target.stat().st_size == 0:
                    # Keep a single copy; moving inside the same filesystem is cheap.
                    staging = MODEL_DIR / ".hf-downloads" / repo.replace("/", "_")
                    downloaded = Path(download(repo_id=repo, filename=source, revision=revision, local_dir=staging, token=token or None, force_download=repair))
                    shutil.move(downloaded, target)
                if expected is not None and target.stat().st_size != expected:
                    raise ValueError("Downloaded file has unexpected size")
                with jobs_lock:
                    jobs[job_id]["done"] += 1
            if preset_id:
                installing = True
                def progress(message):
                    with jobs_lock:
                        jobs[job_id]['current'] = message
                restart_required = install_preset(preset_id, progress)
                with jobs_lock:
                    jobs[job_id]['restart_required'] = restart_required
                    jobs[job_id]['done'] += 1
            with jobs_lock:
                jobs[job_id]["state"] = "done"
        except Exception:
            # Do not reflect library exception strings: they may include private URLs.
            with jobs_lock:
                jobs[job_id]["state"] = "failed"
                jobs[job_id]['error_code'] = 'install_failed' if installing else 'download_failed'

    def serial_run():
        with jobs_lock: jobs[job_id]["state"]="queued"
        with download_lock:
            with jobs_lock: jobs[job_id]["state"]="running"
            run()
    threading.Thread(target=serial_run, daemon=True).start()
    return job_id


@app.get("/", response_class=HTMLResponse)
def index():
    name = MODE + ".html"
    return (Path(__file__).parent / "static" / name).read_text(encoding="utf-8")


@app.get("/style.css")
def css():
    return FileResponse(Path(__file__).parent / "static" / "style.css", media_type="text/css")


@app.get("/app.js")
def javascript():
    return FileResponse(Path(__file__).parent / "static" / "app.js", media_type="text/javascript")


@app.get('/i18n.json')
def translations():
    return FileResponse(Path(__file__).parent / 'static' / 'i18n.json', media_type='application/json')


@app.get('/output-backup.js')
@app.get('/outputs-sw.js')
@app.get('/zip-native.min.js')
def backup_asset(request: Request):
    if MODE != 'outputs': raise HTTPException(404)
    name=request.url.path.rsplit('/',1)[-1]
    return FileResponse(Path(__file__).parent/'static'/name,media_type='text/javascript',headers={'Cache-Control':'no-cache'})


def checked_preset(preset: str):
    try:
        return manifest(preset)
    except ValueError:
        raise HTTPException(404, {'code': 'preset_not_found'})


@app.get("/api/presets")
def all_presets():
    if MODE != "models":
        raise HTTPException(404)
    return {"presets": [public_manifest(name) for name in PRESET_IDS]}


@app.get("/api/preset")
def preset_status(preset: str = "native-h3"):
    if MODE != "models":
        raise HTTPException(404)
    checked_preset(preset)
    return public_manifest(preset)


@app.get("/api/workflow")
def workflow(preset: str = "native-h3"):
    if MODE != "models":
        raise HTTPException(404)
    checked_preset(preset)
    import json
    return Response(json.dumps(workflow_for(preset), ensure_ascii=False),
                    media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="iunoasc-{preset}.json"'})


@app.post("/api/preset")
def download_preset(request: PresetRequest):
    if MODE != "models":
        raise HTTPException(404)
    item = checked_preset(request.preset)
    files = item['files'] + (item['optional_files'] if request.include_optional else [])
    if not public_manifest(request.preset)['enough_space']:
        raise HTTPException(409, {'code':'insufficient_space'})
    missing = [f for f in files if not model_target(f['filename']).is_file()
               or model_target(f['filename']).stat().st_size != f['size_bytes']]
    return {"id": _new_job([(f['repo'], f['source'], f['filename']) for f in missing], request.token, {f['filename']: f['size_bytes'] for f in missing}, request.preset)}


@app.post("/api/loras")
def lora_files(request: LoraListRequest):
    result = weight_files(request)
    result['files'] = [f for f in result['files'] if f.lower().endswith('.safetensors')]
    return result


@app.post('/api/weights')
def weight_files(request: LoraListRequest):
    if MODE != "models":
        raise HTTPException(404)
    try:
        source = _source(request.repo)
        files = HfApi(token=request.token or None).list_repo_files(repo_id=source.repo, revision=source.revision)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, {'code': 'hf_open_failed'})
    candidates = [f for f in files if PurePosixPath(f).suffix.lower() in WEIGHT_SUFFIXES]
    if source.filename and source.filename not in candidates:
        raise HTTPException(400, {'code': 'invalid_weight_file'})
    return {'files': candidates, 'selected': source.filename, 'repo': source.repo, 'revision': source.revision}


@app.post("/api/loras/download")
def download_lora(request: LoraDownloadRequest):
    if not request.filename.lower().endswith('.safetensors'):
        raise HTTPException(400, {'code': 'invalid_weight_file'})
    return download_weight(WeightDownloadRequest(**request.model_dump(), directory='loras'))


@app.post('/api/weights/download')
def download_weight(request: WeightDownloadRequest):
    if MODE != "models":
        raise HTTPException(404)
    source = _source(request.repo)
    if request.directory not in WEIGHT_DIRECTORIES:
        raise HTTPException(400, {'code': 'invalid_weight_directory'})
    try:
        filename = weight_filename(request.filename or source.filename or '')
    except ValueError as error:
        raise HTTPException(400, {'code': str(error)}) from None
    destination = f'{request.directory}/{PurePosixPath(filename).name}'
    return {'id': _new_job([(source.repo, filename, destination, source.revision)], request.token)}


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
        result.append({"name": item.name, "path": rel, "directory": item.is_dir(), "size": "" if item.is_dir() else format_size(item.stat().st_size), 'size_bytes': None if item.is_dir() else item.stat().st_size, 'video':item.suffix.lower() in MEDIA_SUFFIXES, 'version':f'{item.stat().st_size}:{item.stat().st_mtime_ns}'})
    return {"path": path, "files": result}


@app.get('/api/outputs/snapshot')
def output_snapshot():
    if MODE != 'outputs': raise HTTPException(404)
    root=OUTPUT_DIR.resolve();files=[]
    if root.is_dir():
        for file in sorted(root.rglob('*')):
            try:
                if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(root):continue
                stat=file.stat()
            except OSError:continue
            files.append({'path':file.relative_to(root).as_posix(),'name':file.name,'size_bytes':stat.st_size,'version':f'{stat.st_size}:{stat.st_mtime_ns}'})
            if len(files)>10000:raise HTTPException(413,{'code':'snapshotTooLarge'})
    return {'files':files}


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
        raise HTTPException(404, {'code': 'folder_empty'})

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


@app.get('/api/status')
def control_status():
    if MODE != 'control':raise HTTPException(404)
    return runtime_status()


def checked_video(path):
    if MODE != 'outputs':raise HTTPException(404)
    try:file=output_target(path)
    except ValueError:raise HTTPException(400, {'code':'invalid_output_selection'}) from None
    if not file.is_file() or file.suffix.lower() not in MEDIA_SUFFIXES:raise HTTPException(404)
    return file


@app.get('/api/outputs/preview')
def output_preview(path: str):
    file=checked_video(path)
    return FileResponse(file, media_type=mimetypes.guess_type(file.name)[0] or 'video/mp4')


@app.get('/api/outputs/metadata')
def output_metadata(path: str):
    return metadata(checked_video(path))


@app.get('/api/outputs/thumbnail')
def output_thumbnail(path: str):
    file=checked_video(path)
    try:return FileResponse(thumbnail(file),media_type='image/jpeg')
    except (OSError,subprocess.SubprocessError):raise HTTPException(415,{'code':'previewUnavailable'}) from None


class SessionRequest(BaseModel):
    outputs: list[str] = Field(default_factory=list, max_length=1000)
    include_inputs: bool = True


@app.post('/api/session')
def export_session(request: SessionRequest):
    if MODE not in {'outputs','control'}:raise HTTPException(404)
    try:entries=collect_session(request.outputs,request.include_inputs)
    except ValueError:raise HTTPException(400,{'code':'invalid_output_selection'}) from None
    ident=uuid.uuid4().hex
    with jobs_lock:
        for old in list(sessions):
            if sessions[old][0]<time.monotonic()-600: sessions.pop(old)
        if len(sessions)>=20:raise HTTPException(429)
        sessions[ident]=(time.monotonic(),entries,runtime_status()['versions'])
    return {'id':ident}


@app.get('/api/session/{ident}')
def download_session(ident: str):
    if MODE not in {'outputs','control'}:raise HTTPException(404)
    with jobs_lock:item=sessions.pop(ident,None)
    if item is None or item[0]<time.monotonic()-600:raise HTTPException(404)
    return StreamingResponse(archive_stream(item[1],item[2]),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="iunoasc-session.zip"'})
