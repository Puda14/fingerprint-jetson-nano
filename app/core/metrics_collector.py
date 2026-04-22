"""Cross-platform system metrics collector for worker heartbeat.

On Jetson Nano (aarch64), reads GPU load from sysfs and temperature from
thermal zones.  On x86 development hosts, provides safe fallbacks.

NOTE: Must stay compatible with Python 3.6 (Jetson Nano / JetPack 4.6).
"""

import logging
import platform

logger = logging.getLogger(__name__)

_IS_ARM = platform.machine().startswith("aarch64") or platform.machine().startswith("arm")


class SystemMetrics(object):
    """Snapshot of system resource usage."""

    def __init__(self):
        self.cpu_percent = 0.0          # overall CPU usage %
        self.ram_used_mb = 0.0          # RAM used (MB)
        self.ram_total_mb = 0.0         # RAM total (MB)
        self.gpu_percent = 0.0          # GPU utilisation %  (Tegra GR3D)
        self.gpu_memory_used_mb = 0.0   # VRAM used (shared on Jetson)
        self.gpu_memory_total_mb = 0.0  # VRAM total
        self.temperature_c = 0.0        # SoC temperature (°C)


def _read_sysfs(path: str, default: str = "0") -> str:
    """Read a single-value sysfs file, return *default* on any error."""
    try:
        with open(path, "r") as fh:
            return fh.read().strip()
    except (OSError, IOError):
        return default


def collect() -> SystemMetrics:
    """Collect current system metrics.  Safe to call from any platform."""
    m = SystemMetrics()

    # ── CPU ──────────────────────────────────────────────────────────
    try:
        import psutil  # type: ignore
        m.cpu_percent = psutil.cpu_percent(interval=0)
        mem = psutil.virtual_memory()
        m.ram_used_mb = round(mem.used / (1024 * 1024), 1)
        m.ram_total_mb = round(mem.total / (1024 * 1024), 1)
    except ImportError:
        # Fallback: read /proc/meminfo directly
        try:
            for line in open("/proc/meminfo"):
                if line.startswith("MemTotal:"):
                    m.ram_total_mb = round(int(line.split()[1]) / 1024, 1)
                elif line.startswith("MemAvailable:"):
                    avail = round(int(line.split()[1]) / 1024, 1)
                    m.ram_used_mb = round(m.ram_total_mb - avail, 1)
        except (OSError, IOError):
            pass

    # ── GPU (Tegra / Jetson) ─────────────────────────────────────────
    if _IS_ARM:
        # GR3D (GPU) load — value is 0–1000 (divide by 10 for %)
        raw = _read_sysfs("/sys/devices/gpu.0/load", "0")
        try:
            m.gpu_percent = round(int(raw) / 10.0, 1)
        except ValueError:
            pass
        # Jetson shares RAM between CPU and GPU — report same values
        m.gpu_memory_used_mb = m.ram_used_mb
        m.gpu_memory_total_mb = m.ram_total_mb
    else:
        # On x86 dev host, try nvidia-smi via pynvml
        try:
            import pynvml  # type: ignore
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            m.gpu_percent = float(util.gpu)
            m.gpu_memory_used_mb = round(mem_info.used / (1024 * 1024), 1)
            m.gpu_memory_total_mb = round(mem_info.total / (1024 * 1024), 1)
        except Exception:
            pass  # No GPU or pynvml not installed — leave as 0

    # ── Temperature ──────────────────────────────────────────────────
    raw_temp = _read_sysfs("/sys/class/thermal/thermal_zone0/temp", "0")
    try:
        m.temperature_c = round(int(raw_temp) / 1000.0, 1)
    except ValueError:
        pass

    return m
