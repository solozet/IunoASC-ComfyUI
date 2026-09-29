"""Ensure the downloadable official workflow names match the preset on each image."""

import json
import os
import unittest
from unittest.mock import patch

from panel.core import preset_files, preset_workflow


class WorkflowTests(unittest.TestCase):
    def test_each_image_workflow_uses_only_downloaded_weights(self):
        for diffusion in (
            "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
            "diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled.safetensors",
        ):
            with self.subTest(diffusion=diffusion), patch.dict(os.environ, {"IUNO_H3_DIFFUSION_FILE": diffusion}):
                workflow = preset_workflow()
                serialized = json.dumps(workflow)
                for file in preset_files():
                    self.assertIn(file.split("/")[-1], serialized)
                self.assertNotIn("minimax_h3_video_vae_int8_convrot.safetensors", serialized)
                if "fp8_scaled" in diffusion:
                    self.assertNotIn("minimax_h3_fl2va_pruned_int8_convrot.safetensors", serialized)


if __name__ == "__main__":
    unittest.main()
