"""Stream a portable session archive without a second copy on Pod disk."""
import json
from pathlib import Path
import queue
import threading
import zipfile

from .core import DATA_DIR, OUTPUT_DIR, output_target
from .install import COMFY_DIR


def collect_session(selected_outputs, include_inputs=True):
    entries=[]
    def add_tree(root, prefix):
        if not root.is_dir():return
        for path in sorted(root.rglob('*')):
            if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()):
                entries.append((path,prefix+'/'+path.relative_to(root).as_posix()))
    add_tree(COMFY_DIR/'user/default/workflows','workflows')
    settings=COMFY_DIR/'user/default/comfy.settings.json'
    if settings.is_file() and not settings.is_symlink():entries.append((settings,'settings/comfy.settings.json'))
    if include_inputs:add_tree(DATA_DIR/'inputs','inputs')
    for name in dict.fromkeys(selected_outputs):
        path=output_target(name)
        if not path.is_file() or path.is_symlink():raise ValueError('invalid_output_selection')
        entries.append((path,'outputs/'+path.relative_to(OUTPUT_DIR.resolve()).as_posix()))
    return entries


def archive_stream(entries, versions):
    chunks=queue.Queue(maxsize=8);cancelled=threading.Event()
    class Sink:
        position=0
        def write(self,data):
            if cancelled.is_set():raise BrokenPipeError()
            data=bytes(data);self.position+=len(data)
            for offset in range(0,len(data),1024*1024):
                while not cancelled.is_set():
                    try:chunks.put(data[offset:offset+1024*1024],timeout=.2);break
                    except queue.Full:pass
            if cancelled.is_set():raise BrokenPipeError()
            return len(data)
        def tell(self):return self.position
        def flush(self):pass
    def build():
        try:
            with zipfile.ZipFile(Sink(),'w',compression=zipfile.ZIP_STORED,allowZip64=True) as archive:
                archive.writestr('session.json',json.dumps({'format':'iunoasc-session-v1','versions':versions,'files':[name for _,name in entries]},ensure_ascii=False,indent=2))
                for path,name in entries:archive.write(path,name)
        except Exception as error:
            if not cancelled.is_set():chunks.put(error)
        finally:
            while not cancelled.is_set():
                try:chunks.put(None,timeout=.2);break
                except queue.Full:pass
    threading.Thread(target=build,daemon=True).start()
    try:
        while True:
            chunk=chunks.get()
            if chunk is None:break
            if isinstance(chunk,Exception):raise chunk
            yield chunk
    finally:cancelled.set()
