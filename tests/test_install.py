"""Verify retry behavior without downloading model weights or running Comfy."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from panel import install, presets


class InstallTests(unittest.TestCase):
    def test_existing_custom_version_preserved_and_workflow_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            node = root / 'custom_nodes' / install.SPECTRUM_NAME
            node.mkdir(parents=True)
            (node / '__init__.py').write_text('user version')
            with patch.object(install, 'COMFY_DIR', root), patch.object(install.subprocess, 'run') as git:
                self.assertTrue(install.install_preset('my-h3', lambda message: None))
                self.assertTrue(install.install_preset('my-h3', lambda message: None))
                git.assert_not_called()
            self.assertEqual((node / '__init__.py').read_text(), 'user version')
            workflow = json.loads((root / 'user/default/workflows/lightspeed-h3.json').read_text())
            self.assertEqual(workflow, presets.workflow_for('my-h3'))

    def test_failed_fetch_leaves_no_partial_install(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(install, 'COMFY_DIR', root), patch.object(install.subprocess, 'run', side_effect=subprocess.TimeoutExpired('git', 120)):
                with self.assertRaises(subprocess.TimeoutExpired):
                    install.install_preset('my-h3', lambda message: None)
            self.assertEqual(list((root / 'custom_nodes').iterdir()), [])
            self.assertFalse((root / 'user/default/workflows/lightspeed-h3.json').exists())
