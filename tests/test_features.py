"""Exercise optional LoRA, workspace preservation, playback and portable archives."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient
from panel import app as api, install, presets, session


class FeatureTests(unittest.TestCase):
    def test_disabled_optional_lora_does_not_resolve_or_load_file(self):
        path=Path(__file__).resolve().parent.parent/'custom_nodes/iunoasc_tools/__init__.py'
        folder=types.SimpleNamespace(get_filename_list=lambda kind:[])
        with patch.dict(sys.modules,{'folder_paths':folder}):
            spec=importlib.util.spec_from_file_location('optional_lora',path)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            loader=module.IunoOptionalLora();model=object()
            for name in ['',None,'missing.safetensors']:
                self.assertEqual(loader.apply(model,name,1,False),(model,))
            with self.assertRaises(ValueError):loader.apply(model,'',1,True)

    def test_seed_preserves_edits_and_migrates_old_workflow(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(install,'COMFY_DIR',Path(directory)):
            old=Path(directory)/'user/default/workflows/lightspeed-h3.json';old.parent.mkdir(parents=True);old.write_text('{"user":"edited"}')
            install.seed_workflows();install.seed_workflows()
            target=old.parent/'IunoASC/lightspeed-h3.json'
            self.assertEqual(json.loads(target.read_text()),{'user':'edited'})
            self.assertFalse(old.exists())
            self.assertEqual(len(list(target.parent.glob('*.json'))),3)

    def test_experimental_reuses_four_weights_and_only_changes_vae(self):
        normal=presets.manifest('my-h3');experiment=presets.manifest('experimental-h3')
        common={f['filename'] for f in normal['files']} & {f['filename'] for f in experiment['files']}
        self.assertEqual(len(common),4)
        self.assertEqual(experiment['files'][2]['repo'],'Kijai/MiniMax-H3-experimental')
        w=presets.workflow_for('experimental-h3')
        nodes=[n for d in w['definitions']['subgraphs'] for n in d['nodes']]
        self.assertTrue(any(n['type']=='VAELoader' and 'lynnreal' in n['widgets_values'][0] for n in nodes))

    def test_model_download_annotations_match_selected_weights_and_sources(self):
        for preset_id in ('my-h3', 'experimental-h3'):
            workflow=presets.workflow_for(preset_id)
            expected={Path(f['filename']).name:f for f in presets.manifest(preset_id)['files']}
            nodes=[n for graph in workflow['definitions']['subgraphs'] for n in graph['nodes']]
            count=0
            for node in nodes:
                for model in node.get('properties',{}).get('models',[]):
                    count+=1
                    self.assertEqual(model['name'],node['widgets_values'][0])
                    weight=expected[model['name']]
                    self.assertEqual(model['directory'],Path(weight['filename']).parent.as_posix())
                    self.assertEqual(model['url'],f"https://huggingface.co/{weight['repo']}/resolve/main/{weight['source']}")
            self.assertEqual(count,4)

    def test_playback_range_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);video=root/'test.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=96x64:r=24:d=1','-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True)
            with patch.object(api,'MODE','outputs'),patch.object(api,'output_target',lambda name:root/name):
                client=TestClient(api.app)
                response=client.get('/api/outputs/preview?path=test.mp4',headers={'Range':'bytes=0-99'})
                self.assertEqual(response.status_code,206);self.assertEqual(len(response.content),100)
                self.assertNotIn('attachment',response.headers.get('content-disposition',''))
                data=client.get('/api/outputs/metadata?path=test.mp4').json()
                self.assertEqual((data['width'],data['height'],data['fps'],data['bit_depth']),(96,64,24.0,8))

    def test_recursive_snapshot_omits_external_symlinks_and_tracks_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'outputs';(root/'video').mkdir(parents=True)
            file=root/'video/scene.mp4';file.write_bytes(b'first')
            external=Path(directory)/'private';external.write_bytes(b'private')
            (root/'hidden').symlink_to(external)
            with patch.object(api,'MODE','outputs'),patch.object(api,'OUTPUT_DIR',root):
                client=TestClient(api.app);data=client.get('/api/outputs/snapshot').json()['files']
                self.assertEqual([f['path'] for f in data],['video/scene.mp4'])
                version=data[0]['version'];file.write_bytes(b'second')
                self.assertNotEqual(client.get('/api/outputs/snapshot').json()['files'][0]['version'],version)
                self.assertEqual(client.get('/outputs-sw.js').status_code,200)
                self.assertEqual(client.get('/output-backup.js').status_code,200)
                self.assertEqual(client.get('/zip-native.min.js').status_code,200)

    def test_streamed_session_includes_only_selected_outputs_and_no_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);comfy=root/'comfy';(root/'inputs').mkdir();(root/'outputs').mkdir()
            (root/'inputs/ref.png').write_bytes(b'ref');(root/'outputs/keep.mp4').write_bytes(b'keep');(root/'outputs/omit.mp4').write_bytes(b'omit')
            wf=comfy/'user/default/workflows/IunoASC';wf.mkdir(parents=True);(wf/'test.json').write_text('{}')
            (wf.parent.parent/'comfy.settings.json').write_text('{"theme":"dark"}')
            (wf.parent.parent/'token.json').write_text('secret')
            with patch.object(session,'DATA_DIR',root),patch.object(session,'OUTPUT_DIR',root/'outputs'),patch.object(session,'COMFY_DIR',comfy),patch.object(session,'output_target',lambda name:(root/'outputs'/name).resolve()):
                entries=session.collect_session(['keep.mp4'])
                data=b''.join(session.archive_stream(entries,{'comfy':'0.39.0'}))
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    self.assertEqual(set(archive.namelist()),{'session.json','workflows/IunoASC/test.json','settings/comfy.settings.json','inputs/ref.png','outputs/keep.mp4'})
                    self.assertEqual(archive.read('outputs/keep.mp4'),b'keep')
                (root/'inputs/linked').symlink_to(root/'outputs/omit.mp4')
                self.assertFalse(any('linked' in name for _,name in session.collect_session([])))
