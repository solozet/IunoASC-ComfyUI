"""On-demand metadata and thumbnails. Original video is never converted or replaced."""
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading

from .core import DATA_DIR

MEDIA_SUFFIXES={'.mp4','.webm','.mov','.mkv','.avi','.m4v'}
thumbnail_slots=threading.BoundedSemaphore(2)


@lru_cache(maxsize=128)
def probe(path, mtime_ns, size):
    try:
        result=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,check=True,timeout=10)
        data=json.loads(result.stdout);v=data.get('streams',[{}])[0]
        numerator,denominator=v.get('avg_frame_rate','0/1').split('/')
        fps=round(float(numerator)/float(denominator),3) if float(denominator) else None
        pixel=v.get('pix_fmt','')
        bits=int(v.get('bits_per_raw_sample') or 0) or (10 if '10' in pixel else 12 if '12' in pixel else 8 if pixel else None)
        transfer=v.get('color_transfer')
        return {'width':v.get('width'),'height':v.get('height'),'fps':fps,'codec':v.get('codec_name'),'pixel_format':pixel,'bit_depth':bits,'color_transfer':transfer,'color_primaries':v.get('color_primaries'),'hdr':transfer in {'smpte2084','arib-std-b67'},'duration':float(data.get('format',{}).get('duration',0)),'available':bool(v.get('codec_name'))}
    except (OSError,subprocess.SubprocessError,ValueError,IndexError,KeyError):return {'available':False}


def metadata(path):
    stat=path.stat();return probe(str(path),stat.st_mtime_ns,stat.st_size)


def thumbnail(path):
    stat=path.stat()
    key=hashlib.sha256(f'{path}:{stat.st_mtime_ns}:{stat.st_size}'.encode()).hexdigest()
    root=DATA_DIR / '.iuno-thumbnails';root.mkdir(parents=True,exist_ok=True)
    target=root / (key+'.jpg')
    if target.is_file():return target
    with thumbnail_slots:
        if target.is_file():return target
        descriptor,name=tempfile.mkstemp(suffix='.jpg',dir=root);os.close(descriptor)
        temporary=Path(name)
        try:
            subprocess.run(['ffmpeg','-v','error','-nostdin','-threads','1','-i',str(path),'-frames:v','1','-vf','scale=480:-2','-q:v','4','-y',str(temporary)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=20)
            temporary.replace(target)
            # Bound cache growth; stale thumbnails are reproducible.
            files=sorted(root.glob('*.jpg'),key=lambda f:f.stat().st_mtime)
            for old in files[:-200]:old.unlink(missing_ok=True)
            return target
        finally:temporary.unlink(missing_ok=True)
