"""Install only the preset's fixed, reviewed custom-node snapshot."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path

from .presets import manifest, workflow_for

COMFY_DIR = Path(os.getenv('IUNO_COMFY_DIR', '/opt/ComfyUI'))
SPECTRUM_NAME = 'ComfyUI-Spectrum-MiniMax-H3'
SPECTRUM_REPO = 'https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3'
SPECTRUM_REF = 'dc6e1b335e1cdcd078a649add6464dab9469a587'
install_lock = threading.Lock()


def install_preset(preset_id: str, progress) -> bool:
    """Save workflow and install Spectrum; return whether Comfy must restart."""
    item = manifest(preset_id)
    with install_lock:
        if preset_id == 'my-h3':
            progress('install_spectrum')
            root = COMFY_DIR / 'custom_nodes'
            root.mkdir(parents=True, exist_ok=True)
            target = root / SPECTRUM_NAME
            if target.exists():
                # Preserve a version installed or edited by the user/Manager.
                if not (target / '__init__.py').is_file():
                    raise ValueError('Incomplete Spectrum directory')
            else:
                with tempfile.TemporaryDirectory(prefix='.spectrum-', dir=root) as staging:
                    source = Path(staging) / SPECTRUM_NAME
                    def git(*args):
                        subprocess.run(['git', *args], check=True, timeout=120,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
                    git('init', str(source))
                    git('-C', str(source), 'fetch', '--depth', '1', SPECTRUM_REPO, SPECTRUM_REF)
                    git('-C', str(source), 'checkout', '--detach', 'FETCH_HEAD')
                    if not (source / '__init__.py').is_file():
                        raise ValueError('Invalid Spectrum snapshot')
                    # This pinned Spectrum revision has no additional pip dependencies.
                    source.rename(target)
        progress('save_workflow')
        workflow_dir = COMFY_DIR / 'user' / 'default' / 'workflows'
        workflow_dir.mkdir(parents=True, exist_ok=True)
        filename = 'lightspeed-h3.json' if preset_id == 'my-h3' else 'iunoasc-native-h3.json'
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=workflow_dir,
                                         suffix='.json', delete=False) as handle:
            temporary = Path(handle.name)
            try:
                json.dump(workflow_for(preset_id), handle, ensure_ascii=False)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
        try:
            temporary.replace(workflow_dir / filename)
        finally:
            temporary.unlink(missing_ok=True)
    return bool(item['custom_nodes'])
