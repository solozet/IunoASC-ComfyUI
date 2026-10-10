import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import subprocess
from panel import diagnostics as d


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.proc = self.root / 'proc'; self.cg = self.root / 'cgroup'
        self.proc.mkdir(); self.cg.mkdir()
        self.patches = [patch.object(d, 'PROC', self.proc), patch.object(d, 'CGROUP', self.cg), patch.object(d, 'HWMON', self.root / 'hwmon'), patch.object(d, 'POWERCAP', self.root / 'powercap'), patch.object(d, '_previous', {})]
        for p in self.patches: p.start()
        (self.proc / 'meminfo').write_text('MemTotal: 8388608 kB\nMemAvailable: 4194304 kB\nSwapTotal: 1048576 kB\nSwapFree: 524288 kB\n')

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def test_cgroup_quota_cpu_and_memory_not_whole_host(self):
        (self.cg / 'cpu.max').write_text('200000 100000')
        (self.cg / 'cpu.stat').write_text('usage_usec 1000000')
        (self.cg / 'memory.current').write_text(str(3 * 1024**3))
        (self.cg / 'memory.max').write_text(str(4 * 1024**3))
        (self.cg / 'memory.stat').write_text('file 1000\n')
        (self.cg / 'memory.swap.current').write_text('4096')
        (self.cg / 'memory.swap.max').write_text('8192')
        with patch.object(d.time, 'monotonic', return_value=10), patch.object(d.os, 'sched_getaffinity', return_value=set(range(16))):
            first = d.system_metrics()
        self.assertIsNone(first['cpu']['utilization'])
        (self.cg / 'cpu.stat').write_text('usage_usec 6000000')
        with patch.object(d.time, 'monotonic', return_value=15), patch.object(d.os, 'sched_getaffinity', return_value=set(range(16))):
            second = d.system_metrics()
        self.assertEqual(second['cpu']['utilization'], 50)
        self.assertEqual(second['cpu']['cores'], 2)
        self.assertEqual(second['ram']['total_bytes'], 4 * 1024**3)
        self.assertEqual(second['ram']['used_bytes'], 3 * 1024**3)
        self.assertEqual(second['ram']['scope'], 'container')
        self.assertEqual(second['swap']['used_bytes'], 4096)
        self.assertIsNone(second['cpu']['temperature_c'])
        self.assertIsNone(second['cpu']['power_w'])

    def test_unlimited_memory_is_explicitly_host_scope(self):
        (self.cg / 'cpu.stat').write_text('usage_usec 1000000')
        (self.cg / 'memory.max').write_text('max')
        (self.cg / 'memory.current').write_text('1000')
        value = d.system_metrics()
        self.assertEqual(value['ram']['scope'], 'host')
        self.assertEqual(value['ram']['used_bytes'], 4 * 1024**3)
        self.assertEqual(value['swap']['scope'], 'host')

    def test_optional_gpu_query_cannot_hide_working_gpu(self):
        core = subprocess.CompletedProcess([], 0, 'RTX 5090, 590.48.01, 32768, 16384, 72\n', '')
        with patch.object(d.subprocess, 'run', side_effect=[core, subprocess.CalledProcessError(1, 'nvidia-smi')]):
            gpus = d.gpu_metrics()
        self.assertEqual(gpus[0]['name'], 'RTX 5090')
        self.assertEqual(gpus[0]['utilization'], 72)
        self.assertNotIn('power_w', gpus[0])

    def test_gpu_na_power_is_missing_not_zero(self):
        core = subprocess.CompletedProcess([], 0, 'GPU, 590, 32768, 16384, 72\n', '')
        optional = subprocess.CompletedProcess([], 0, '67, [N/A], 575, 44, 2400\n', '')
        with patch.object(d.subprocess, 'run', side_effect=[core, optional]):
            gpu = d.gpu_metrics()[0]
        self.assertIsNone(gpu['power_w'])
        self.assertEqual(gpu['temperature_c'], 67)

    def test_disk_sensor_cannot_be_reported_as_cpu_temperature(self):
        disk = self.root / 'hwmon/hwmon0'; disk.mkdir(parents=True)
        (disk / 'name').write_text('nvme'); (disk / 'temp1_input').write_text('40000')
        self.assertIsNone(d.cpu_sensors(10)['temperature_c'])
        cpu = self.root / 'hwmon/hwmon1'; cpu.mkdir()
        (cpu / 'name').write_text('coretemp'); (cpu / 'temp1_input').write_text('62000')
        self.assertEqual(d.cpu_sensors(10)['temperature_c'], 62)
