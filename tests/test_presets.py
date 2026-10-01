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
        nodes = workflow['nodes'] + [n for d in workflow.get('definitions', {}).get('subgraphs', []) for n in d['nodes']]
        for node in nodes:
            if node['type'] in {'UNETLoader', 'VAELoader', 'CLIPLoader', 'LoraLoaderModelOnly'}:
                self.assertIn(node['widgets_values'][0], names)
        self.assertEqual(sum(f['size_bytes'] for f in preset['files']), 40694127751)
        self.assertEqual(len(preset['files']), 5)
        self.assertEqual(preset['optional_files'], [])
        self.assertEqual([p['name'] for p in preset['custom_nodes']], ['Spectrum MiniMax H3'])
        native_names={f['filename'] for f in presets.manifest('native-h3')['files']}
        self.assertEqual([f['filename'] for f in preset['files'] if f['filename'] not in native_names],
                         ['vae/minimax_h3_video_vae_int8_convrot.safetensors', 'loras/minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors'])
        self.assertTrue(all(n['mode']==4 for n in workflow['nodes'] if n['type']=='LoadImage'))

    def test_compact_workflow_boundaries_and_defaults(self):
        workflow = presets.workflow_for('my-h3')
        definition = workflow['definitions']['subgraphs'][0]
        instance = next(n for n in workflow['nodes'] if n['type'] == definition['id'])
        controls = instance['widgets_values_named']
        self.assertEqual((controls['color_space'], controls['bit_depth'], controls['fps']), ('HDR', 10, 24))
        self.assertTrue(controls['turbo_enabled'])
        self.assertFalse(controls['extra_lora_enabled'])
        self.assertEqual(next(n for n in definition['nodes'] if n['type']=='RandomNoise')['widgets_values'][1], 'randomize')
        self.assertTrue(any(n['type']=='MarkdownNote' for n in workflow['nodes']))
        self.assertFalse(any(n['type']=='MarkdownNote' for n in definition['nodes']))
        for graph, objects in [(workflow, False), (definition, True)]:
            nodes = {n['id']:n for n in graph['nodes']}
            links = graph['links']
            seen_targets = set()
            for link in links:
                ident, origin, origin_slot, target, target_slot, kind = ([link[k] for k in ('id','origin_id','origin_slot','target_id','target_slot','type')] if objects else link)
                if origin != -10:
                    self.assertIn(ident, nodes[origin]['outputs'][origin_slot]['links'])
                else:
                    self.assertIn(ident, graph['inputs'][origin_slot]['linkIds'])
                if target != -20:
                    self.assertEqual(nodes[target]['inputs'][target_slot]['link'], ident)
                    self.assertNotIn((target,target_slot),seen_targets)
                    seen_targets.add((target,target_slot))

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
