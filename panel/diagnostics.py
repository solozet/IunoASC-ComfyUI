"""Read-only runtime diagnostics; never initialize CUDA or expose environment secrets."""
from importlib.metadata import version, PackageNotFoundError
import csv
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request

from .core import DATA_DIR


def package(name):
    try: return version(name)
    except PackageNotFoundError: return None


def runtime_status():
    gpus=[]
    try:
        result=subprocess.run(['nvidia-smi','--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,check=True,timeout=5)
        for row in csv.reader(io.StringIO(result.stdout)):
            gpus.append(dict(name=row[0].strip(), driver=row[1].strip(), vram_total_mb=float(row[2]), vram_used_mb=float(row[3]), utilization=float(row[4])))
    except (OSError,subprocess.SubprocessError,ValueError,IndexError): pass
    comfy=False;queue=None
    try:
        with urllib.request.urlopen('http://127.0.0.1:3001/queue',timeout=2) as response:
            data=json.load(response);comfy=True
            queue={'running':len(data.get('queue_running',[])),'pending':len(data.get('queue_pending',[]))}
    except (OSError,ValueError): pass
    root=DATA_DIR
    while not root.exists():root=root.parent
    disk=shutil.disk_usage(root)
    cuda=None
    try:
        import torch
        cuda=torch.version.cuda
    except ImportError: pass
    return {'gpus':gpus,'comfy':{'online':comfy,'queue':queue},'disk':{'total_bytes':disk.total,'used_bytes':disk.used,'free_bytes':disk.free},'versions':{'comfy':os.getenv('IUNO_COMFY_VERSION','unknown'),'manager':package('comfyui_manager'),'kitchen':package('comfy-kitchen'),'torch':package('torch'),'torch_cuda':cuda,'base_cuda':os.getenv('IUNO_CUDA_BASE_VERSION','unknown'),'attention':os.getenv('IUNO_ATTENTION','unknown')}}
