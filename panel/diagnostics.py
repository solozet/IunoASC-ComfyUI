"""Read-only runtime diagnostics; never initialize CUDA or expose environment secrets."""
from importlib.metadata import version, PackageNotFoundError
import csv
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import threading
import time

from .core import DATA_DIR


def package(name):
    try: return version(name)
    except PackageNotFoundError: return None



PROC = Path('/proc')
CGROUP = Path('/sys/fs/cgroup')
HWMON = Path('/sys/class/hwmon')
POWERCAP = Path('/sys/class/powercap')
STARTED = time.monotonic()
_SAMPLE_LOCK = threading.Lock()
_previous = {}


def read_text(path):
    try: return path.read_text().strip()
    except OSError: return ''


def numeric(value):
    try: return float(value)
    except (ValueError, TypeError): return None


def pairs(path):
    result = {}
    for line in read_text(path).splitlines():
        fields = line.split()
        if len(fields) >= 2 and numeric(fields[1]) is not None:
            result[fields[0].rstrip(':')] = float(fields[1])
    return result


def counter_rate(key, value, now):
    old = _previous.get(key)
    _previous[key] = (now, value)
    if old is None or value is None or old[1] is None or now <= old[0] or value < old[1]: return None
    return (value - old[1]) / (now - old[0])


def cpu_sensors(now):
    temperatures = []; powers = []
    for directory in HWMON.glob('hwmon*'):
        name = read_text(directory / 'name').lower()
        # Do not present GPU, disk or motherboard readings as CPU readings.
        if not any(part in name for part in ('coretemp', 'k10temp', 'zenpower', 'cpu', 'fam15h', 'fam16h')): continue
        for sensor in directory.glob('temp*_input'):
            value = numeric(read_text(sensor))
            if value is not None and 0 < value < 130000: temperatures.append(value / 1000)
        for sensor in directory.glob('power*_input'):
            value = numeric(read_text(sensor))
            if value is not None and value >= 0: powers.append(value / 1e6)
    if not powers:
        for directory in POWERCAP.glob('intel-rapl:*'):
            if not read_text(directory / 'name').startswith('package'): continue
            value = numeric(read_text(directory / 'energy_uj'))
            if value is not None:
                rate = counter_rate(str(directory), value, now)
                if rate is not None: powers.append(rate / 1e6)
    return {'temperature_c': max(temperatures) if temperatures else None,
            'power_w': sum(powers) if powers else None}


def system_metrics():
    with _SAMPLE_LOCK:
        now = time.monotonic()
        mem = pairs(PROC / 'meminfo')
        host_total = mem.get('MemTotal', 0) * 1024
        host_available = mem.get('MemAvailable', mem.get('MemFree', 0)) * 1024
        v2 = (CGROUP / 'cpu.stat').exists()
        cpu_dir = CGROUP if v2 else CGROUP / 'cpu'
        usage = pairs(CGROUP / 'cpu.stat').get('usage_usec') if v2 else numeric(read_text(CGROUP / 'cpuacct/cpuacct.usage'))
        if usage is not None: usage /= 1e6 if v2 else 1e9
        try: cores = len(os.sched_getaffinity(0))
        except (AttributeError, OSError): cores = os.cpu_count() or 1
        quota = read_text(cpu_dir / 'cpu.max').split() if v2 else [read_text(cpu_dir / 'cpu.cfs_quota_us'), read_text(cpu_dir / 'cpu.cfs_period_us')]
        if len(quota) == 2:
            limit, period = map(numeric, quota)
            if limit is not None and period and limit > 0: cores = min(cores, limit / period)
        percent = None; scope = 'container' if usage is not None else 'host'
        if usage is not None:
            rate = counter_rate('cpu', usage, now)
            if rate is not None: percent = min(100, max(0, rate / max(cores, .001) * 100))
        else:
            line = next((x for x in read_text(PROC / 'stat').splitlines() if x.startswith('cpu ')), '')
            fields = [numeric(x) or 0 for x in line.split()[1:9]]
            if len(fields) >= 5:
                total = counter_rate('host_total', sum(fields), now)
                idle = counter_rate('host_idle', fields[3] + fields[4], now)
                if total and idle is not None: percent = min(100, max(0, (1 - idle / total) * 100))
                cores = os.cpu_count() or cores
        memory_dir = CGROUP if v2 else CGROUP / 'memory'
        used = numeric(read_text(memory_dir / ('memory.current' if v2 else 'memory.usage_in_bytes')))
        limit = numeric(read_text(memory_dir / ('memory.max' if v2 else 'memory.limit_in_bytes')))
        bounded = used is not None and limit is not None and 0 < limit <= host_total
        ram_total = limit if bounded else host_total
        ram_used = used if bounded else max(0, host_total - host_available)
        stat = pairs(memory_dir / 'memory.stat')
        cache = stat.get('file', stat.get('cache')) if bounded else mem.get('Cached', 0) * 1024
        swap_used = numeric(read_text(memory_dir / 'memory.swap.current')) if v2 and bounded else None
        swap_total = numeric(read_text(memory_dir / 'memory.swap.max')) if v2 and bounded else None
        # An unbounded container swap limit has no useful quota denominator.
        if swap_used is None or swap_total is None:
            swap_total = mem.get('SwapTotal', 0) * 1024
            swap_used = max(0, swap_total - mem.get('SwapFree', 0) * 1024)
            swap_scope = 'host'
        else: swap_scope = 'container'
        return {'sampled_at': time.time(), 'uptime_seconds': int(now - STARTED),
                'cpu': {'utilization': percent, 'cores': cores, 'scope': scope, **cpu_sensors(now)},
                'ram': {'used_bytes': ram_used, 'total_bytes': ram_total, 'cache_bytes': cache,
                        'scope': 'container' if bounded else 'host'},
                'swap': {'used_bytes': swap_used, 'total_bytes': swap_total, 'scope': swap_scope}}


def gpu_metrics():
    gpus = []
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu', '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True, timeout=3)
        for row in csv.reader(io.StringIO(result.stdout)):
            gpus.append(dict(name=row[0].strip(), driver=row[1].strip(), vram_total_mb=numeric(row[2]), vram_used_mb=numeric(row[3]), utilization=numeric(row[4])))
        try:
            optional = subprocess.run(['nvidia-smi', '--query-gpu=temperature.gpu,power.draw,power.limit,utilization.memory,clocks.sm', '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True, timeout=3)
            for gpu, row in zip(gpus, csv.reader(io.StringIO(optional.stdout))):
                gpu.update(dict(zip(('temperature_c', 'power_w', 'power_limit_w', 'memory_utilization', 'clock_mhz'), map(numeric, row))))
        except (OSError, subprocess.SubprocessError): pass
    except (OSError, subprocess.SubprocessError, ValueError, IndexError): pass
    return gpus


def runtime_status():
    metrics = system_metrics()
    gpus = gpu_metrics()
    comfy=False;queue=None
    try:
        with urllib.request.urlopen('http://127.0.0.1:3001/queue',timeout=2) as response:
            data=json.load(response);comfy=True
            queue={'running':len(data.get('queue_running',[])),'pending':len(data.get('queue_pending',[]))}
    except (OSError,ValueError): pass
    root=DATA_DIR
    while not root.exists():root=root.parent
    disk=shutil.disk_usage(root)
    cuda=None
    try:
        import torch
        cuda=torch.version.cuda
    except ImportError: pass
    return {**metrics, 'gpus':gpus,'comfy':{'online':comfy,'queue':queue},'disk':{'total_bytes':disk.total,'used_bytes':disk.used,'free_bytes':disk.free},'versions':{'comfy':os.getenv('IUNO_COMFY_VERSION','unknown'),'manager':package('comfyui_manager'),'kitchen':package('comfy-kitchen'),'torch':package('torch'),'torch_cuda':cuda,'base_cuda':os.getenv('IUNO_CUDA_BASE_VERSION','unknown'),'attention':os.getenv('IUNO_ATTENTION','unknown')}}
