import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from panel import presets

class PresetTests(unittest.TestCase):
    def test_workflow_and_downloads_match(self):
        preset = presets.manifest('my-h3')
        workflow = presets.workflow_for('my-h3')
        names = {Path(f['filename']).name for f in preset['files']}
        for node in workflow['nodes']:
            if node['type'] in {'UNETLoader', 'VAELoader', 'CLIPLoader'}:
                self.assertIn(node['widgets_values'][0], names)
        self.assertEqual(sum(f['size_bytes'] for f in preset['files']), 40073842159)
        self.assertEqual(len(preset['files']), 4)
        self.assertEqual(preset['optional_files'], [])
        self.assertEqual([p['name'] for p in preset['custom_nodes']], ['Spectrum MiniMax H3'])
        native_names={f['filename'] for f in presets.manifest('native-h3')['files']}
        self.assertEqual([f['filename'] for f in preset['files'] if f['filename'] not in native_names],
                         ['vae/minimax_h3_video_vae_int8_convrot.safetensors'])
        self.assertTrue(all(n['mode']==4 for n in workflow['nodes'] if n['type']=='LoadImage'))

    def test_wrong_size_is_not_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            def target(filename): return Path(directory)/Path(filename).name
            with patch.object(presets, 'model_target', target):
                item=presets.public_manifest('my-h3')
                self.assertFalse(any(f['ready'] for f in item['files']))
                target(item['files'][0]['filename']).write_bytes(b'partial')
                self.assertFalse(presets.public_manifest('my-h3')['files'][0]['ready'])

    def test_cu128_default_preserves_existing_model(self):
        with patch.dict(os.environ, {'IUNO_H3_DIFFUSION_FILE':'diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled.safetensors'}):
            self.assertIn('fp8_scaled',presets.manifest()['files'][0]['filename'])

if __name__=='__main__': unittest.main()
