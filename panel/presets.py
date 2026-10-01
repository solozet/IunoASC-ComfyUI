"""Verified weight manifests; file sizes are bytes from HF metadata (2026-09-30)."""
from __future__ import annotations
import json
import os
from pathlib import Path
from .core import H3_REPO, H3_FILES, MODEL_DIR, model_target, preset_workflow

SIZES = {
 H3_FILES[0]: 20970379616,
 'diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled.safetensors': 20958205608,
 'diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors': 20970379616,
 H3_FILES[1]: 15687142551,
 H3_FILES[2]: 5207808496,
 'vae/minimax_h3_video_vae_int8_convrot.safetensors': 2811065184,
 H3_FILES[3]: 605254808,
 H3_FILES[4]: 1956193000,
 'vae_approx/taeh3.safetensors': 9791388,
 'loras/minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors': 620285592,
}
CUSTOM_NODES = [
 {'name':'Spectrum MiniMax H3','repo':'https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3', 'ref':'dc6e1b335e1cdcd078a649add6464dab9469a587', 'state':'active','note':'Устанавливается вместе с пресетом. Имеющаяся версия сохраняется.'},
]

def weight(filename, repo=H3_REPO, source=None):
 return {'filename':filename,'repo':repo,'source':source or filename,'size_bytes':SIZES[filename]}

def manifest(preset_id='native-h3'):
 if preset_id == 'native-h3':
  diffusion=os.getenv('IUNO_H3_DIFFUSION_FILE',H3_FILES[0])
  files=[weight(f) for f in [diffusion,*H3_FILES[1:]]]
  return {'id':preset_id,'name':'MiniMax H3 · официальный I2V','description':'Основной пресет · video VAE FP16 · Turbo 8 шагов.','files':files,'optional_files':[],'custom_nodes':[], 'note':'Готовый workflow для основной сборки.'}
 if preset_id == 'my-h3':
  files=[weight(H3_FILES[0]),weight(H3_FILES[1]),weight('vae/minimax_h3_video_vae_int8_convrot.safetensors'),weight(H3_FILES[3]),weight('loras/minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors', repo='drbaph/MiniMax-H3-Turbo-Lora-ComfyUI', source='minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors')]
  return {'id':preset_id,'name':'LightSpeed H3','description':'FL2VA INT8 · video VAE INT8 · Spectrum · Turbo LoRA.','files':files,'optional_files':[],'custom_nodes':CUSTOM_NODES,'note':'Компактный workflow + веса + Spectrum. После установки нод перезапусти ComfyUI через Manager. Для cu128 INT8/CK пока не проверен.', 'compatibility':'cu130' if os.getenv('IUNO_TORCH_INDEX','cu130')=='cu130' else 'unverified'}
 raise ValueError('Unknown preset')

def public_manifest(preset_id):
 item=manifest(preset_id)
 for file in item['files']+item['optional_files']:
  path=model_target(file['filename'])
  file['ready']=path.is_file() and path.stat().st_size==file['size_bytes']
 item['size_bytes']=sum(f['size_bytes'] for f in item['files'])
 item['remaining_bytes']=sum(f['size_bytes'] for f in item['files'] if not f['ready'])
 return item

def workflow_for(preset_id):
 if preset_id=='native-h3': return preset_workflow()
 manifest(preset_id)
 return json.loads((Path(__file__).resolve().parent.parent/'workflows/minimax_h3_my.json').read_text())
