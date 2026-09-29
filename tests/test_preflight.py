"""Host-policy and failure-path tests; these do NOT simulate a real GPU pass."""
import contextlib
import io
import os
import subprocess
import sys
import types
import unittest
from unittest.mock import Mock, patch

import preflight


class PreflightTests(unittest.TestCase):
    def _run(self, base, variant, driver, torch_cuda, init_error=None, smoke_error=None):
        initialize = Mock(side_effect=init_error)
        torch = types.SimpleNamespace(
            version=types.SimpleNamespace(cuda=torch_cuda), __version__="2.9.1",
            cuda=types.SimpleNamespace(init=initialize, get_device_properties=lambda index:
                types.SimpleNamespace(name="RTX 4090", major=8, minor=9, total_memory=24*2**30)),
        )
        stdout, stderr = io.StringIO(), io.StringIO()
        smi = subprocess.CompletedProcess([], 0, f"NVIDIA GeForce RTX 4090, {driver}\n", "")
        env = {"IUNO_TORCH_INDEX": variant, "IUNO_CUDA_BASE_VERSION": base}
        with patch.dict(os.environ, env, clear=True), \
             patch.dict(sys.modules, {"torch": torch}), \
             patch("preflight.subprocess.run", return_value=smi), \
             patch("preflight.gpu_smoke_test", side_effect=smoke_error) as smoke, \
             patch("preflight.report_libraries"), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = preflight.main()
        return code, stdout.getvalue(), stderr.getvalue(), initialize, smoke

    def test_each_base_accepts_its_driver_boundary(self):
        cases = [
            ("12.8.1", "cu128", "570.124.06", "12.8"),
            ("13.0.2", "cu130", "580.95.05", "13.0"),
            ("13.1.1", "cu130", "590.48.01", "13.0"),
            ("13.2.0", "cu130", "595.45.04", "13.0"),
        ]
        for base, variant, driver, wheel in cases:
            with self.subTest(base=base):
                code, output, error, init, smoke = self._run(base, variant, driver, wheel)
                self.assertEqual(code, 0, error)
                self.assertIn("GPU preflight passed", output)
                self.assertIn(f"base {base}, wheel {variant}", output)
                init.assert_called_once()
                smoke.assert_called_once()
                self.assertEqual(smoke.call_args.args[1], "torch" if variant == "cu128" else "ck")

    def test_older_host_rejected_before_cuda_initialization(self):
        for base, variant, driver, wheel in [
            ("12.8.1", "cu128", "570.124.05", "12.8"),
            ("13.0.2", "cu130", "570.124.06", "13.0"),
            ("13.1.1", "cu130", "580.126.20", "13.0"),
            ("13.2.0", "cu130", "590.48.01", "13.0"),
        ]:
            with self.subTest(base=base):
                code, output, error, init, smoke = self._run(base, variant, driver, wheel)
                self.assertEqual(code, 1)
                self.assertIn("driver policy", error)
                self.assertNotIn("preflight passed", output)
                init.assert_not_called()
                smoke.assert_not_called()

    def test_cuda_804_is_explained(self):
        code, output, error, _, smoke = self._run("13.2.0", "cu130", "595.45.04", "13.0", RuntimeError("Error 804"))
        self.assertEqual(code, 1)
        self.assertIn("forward compatibility", error)
        self.assertNotIn("preflight passed", output)
        smoke.assert_not_called()

    def test_kernel_failure_does_not_report_success(self):
        code, output, error, _, smoke = self._run("13.1.1", "cu130", "590.48.01", "13.0", smoke_error=RuntimeError("no kernel image"))
        self.assertEqual(code, 1)
        self.assertIn("no kernel image", error)
        self.assertNotIn("preflight passed", output)
        smoke.assert_called_once()

    def test_base_version_is_not_mistaken_for_wheel_version(self):
        code, _, error, init, _ = self._run("13.2.0", "cu130", "595.45.04", "13.2")
        self.assertEqual(code, 1)
        self.assertIn("Wrong PyTorch wheel", error)
        init.assert_not_called()

    def test_unknown_pair_and_malformed_driver_fail_clearly(self):
        for base, variant, driver in [("13.2.0", "cu132", "595.45.04"), ("13.1.1", "cu130", "N/A")]:
            code, _, error, init, _ = self._run(base, variant, driver, "13.0")
            self.assertEqual(code, 1)
            self.assertTrue(error)
            init.assert_not_called()

    def test_driver_version_parsing(self):
        self.assertEqual(preflight.driver_version("595.45.04"), (595, 45, 4))
        self.assertEqual(preflight.driver_version("600.1"), (600, 1, 0))
        with self.assertRaises(ValueError):
            preflight.driver_version("N/A")

    def test_loaded_libraries_reports_compat_path(self):
        maps = "7f r-xp 0 0 0 /usr/local/cuda/compat/libcuda.so.595.45.04\n7f r-xp 0 0 0 /usr/lib/libc.so.6\n"
        with patch("preflight.Path.read_text", return_value=maps):
            self.assertEqual(preflight.loaded_cuda_libraries(), ["/usr/local/cuda/compat/libcuda.so.595.45.04"])


if __name__ == "__main__":
    unittest.main()
