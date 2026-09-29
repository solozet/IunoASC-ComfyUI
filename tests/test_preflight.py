"""Check the two RunPod host outcomes that previously caused a paid Pod to fail."""

import contextlib
import io
import os
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

import preflight


class PreflightTests(unittest.TestCase):
    def _run(self, variant, driver, torch_cuda, init_error=None):
        def initialize():
            if init_error:
                raise RuntimeError(init_error)

        torch = types.SimpleNamespace(
            version=types.SimpleNamespace(cuda=torch_cuda),
            __version__="2.9.1",
            cuda=types.SimpleNamespace(init=initialize, get_device_name=lambda index: "RTX 4090"),
        )
        stdout, stderr = io.StringIO(), io.StringIO()
        smi = subprocess.CompletedProcess([], 0, f"NVIDIA GeForce RTX 4090, {driver}\n", "")
        with patch.dict(os.environ, {"IUNO_TORCH_INDEX": variant}), \
             patch.dict(sys.modules, {"torch": torch}), \
             patch("preflight.subprocess.run", return_value=smi), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            return preflight.main(), stdout.getvalue(), stderr.getvalue()

    def test_cuda_13_rejects_older_host_before_torch(self):
        code, output, error = self._run("cu130", "570.124.06", "13.0")
        self.assertEqual(code, 1)
        self.assertIn("R580", error)
        self.assertIn("RTX 4090", output)

    def test_cuda_12_8_initializes_on_older_host(self):
        code, output, error = self._run("cu128", "570.124.06", "12.8")
        self.assertEqual(code, 0, error)
        self.assertIn("GPU preflight passed", output)

    def test_cuda_804_is_explained(self):
        code, _, error = self._run("cu130", "580.126.20", "13.0", "Error 804")
        self.assertEqual(code, 1)
        self.assertIn("804", error)
        self.assertIn("forward compatibility", error)

    def test_wrong_wheel_fails_before_comfyui(self):
        code, _, error = self._run("cu128", "580.126.20", "13.0")
        self.assertEqual(code, 1)
        self.assertIn("Wrong PyTorch wheel", error)


if __name__ == "__main__":
    unittest.main()
