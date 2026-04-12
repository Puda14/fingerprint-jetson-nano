"""
System service: health metrics, database backup, configuration management.
"""


from typing import List, Dict, Tuple, Set, Optional, Any, Union, Coroutine, Callable, Generator, Iterable, AsyncIterator, TypeVar, Type, Awaitable, Sequence, Mapping
import asyncio
import logging
import shutil
import socket
import time
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class SystemService:
    """Provides system-level operations: health, backup, config."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._start_time = time.time()
        # Override config in memory (can extend to DB later)
        self._config_overrides: Dict[str, Any] = {}

    # -- health --------------------------------------------------------------

    async def get_health(
        self, sensor_connected: bool = False, active_model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Collect system health metrics."""
        try:
            import psutil

            cpu_percent = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            memory_used_mb = round(mem.used / (1024 * 1024), 1)
            memory_total_mb = round(mem.total / (1024 * 1024), 1)
            disk_used_gb = round(disk.used / (1024 ** 3), 2)
            disk_total_gb = round(disk.total / (1024 ** 3), 2)
        except ImportError:
            cpu_percent = 0.0
            memory_used_mb = 0.0
            memory_total_mb = 0.0
            disk_used_gb = 0.0
            disk_total_gb = 0.0

        cpu_temp = await self._read_cpu_temp()
        gpu_temp = await self._read_gpu_temp()

        return {
            "status": "healthy",
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "cpu_percent": cpu_percent,
            "cpu_temp_c": cpu_temp,
            "gpu_temp_c": gpu_temp,
            "memory_used_mb": memory_used_mb,
            "memory_total_mb": memory_total_mb,
            "disk_used_gb": disk_used_gb,
            "disk_total_gb": disk_total_gb,
            "sensor_connected": sensor_connected,
            "active_model": active_model,
            "device_id": self._settings.device_id,
        }

    # -- temperature helpers (Jetson-specific) -------------------------------

    async def _read_cpu_temp(self) -> Optional[float]:
        """Read CPU temperature on Linux / Jetson Nano."""
        thermal_path = Path("/sys/class/thermal/thermal_zone0/temp")
        if thermal_path.exists():
            try:
                raw = await asyncio.to_thread(thermal_path.read_text)
                return round(int(raw.strip()) / 1000.0, 1)
            except Exception:
                pass
        return None

    async def _read_gpu_temp(self) -> Optional[float]:
        """Read GPU temperature on Jetson (thermal_zone1)."""
        thermal_path = Path("/sys/class/thermal/thermal_zone1/temp")
        if thermal_path.exists():
            try:
                raw = await asyncio.to_thread(thermal_path.read_text)
                return round(int(raw.strip()) / 1000.0, 1)
            except Exception:
                pass
        return None

    # -- backup --------------------------------------------------------------

    async def create_backup(self) -> Dict[str, Any]:
        """Copy database file to a timestamped backup."""
        backup_dir = Path(self._settings.backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{ts}.db"
        backup_path = backup_dir / backup_name

        db_path = Path(self._settings.data_dir) / "fingerprint.db"
        if db_path.exists():
            await asyncio.to_thread(shutil.copy2, str(db_path), str(backup_path))
            size_mb = round(backup_path.stat().st_size / (1024 * 1024), 2)
        else:
            await asyncio.to_thread(backup_path.write_text, "empty-backup")
            size_mb = 0.0

        logger.info("Backup created: %s (%.2f MB)", backup_name, size_mb)
        return {
            "success": True,
            "filename": backup_name,
            "size_mb": size_mb,
            "timestamp": datetime.now(timezone.utc),
            "message": "Backup completed",
        }

    # -- configuration CRUD --------------------------------------------------

    def get_config(self) -> Dict[str, Any]:
        s = self._settings
        base = {
            "device_id": s.device_id,
            "verify_threshold": s.verify_threshold,
            "identify_threshold": s.identify_threshold,
            "identify_top_k": s.identify_top_k,
            "model_dir": s.model_dir,
            "data_dir": s.data_dir,
            "sensor_vid": s.sensor_vid,
            "sensor_pid": s.sensor_pid,
            "debug": s.debug,
        }
        base.update(self._config_overrides)
        return base

    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update configurations allowed to change at runtime."""
        allowed = {"verify_threshold", "identify_threshold", "identify_top_k", "debug"}
        for key, value in updates.items():
            if value is not None and key in allowed:
                self._config_overrides[key] = value
        logger.info("Configuration updated: %s", updates)
        return self.get_config()

    # -- device listing ------------------------------------------------------

    async def list_devices(self) -> List[Dict[str, Any]]:
        hostname = socket.gethostname()
        try:
            ip = socket.gethostbyname(hostname)
        except Exception:
            ip = "127.0.0.1"
        return [
            {
                "device_id": self._settings.device_id,
                "hostname": hostname,
                "ip_address": ip,
                "status": "online",
                "last_seen": datetime.now(timezone.utc),
            }
        ]


# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------

_instance: Optional["SystemService"] = None


async def get_system_service() -> "SystemService":
    global _instance
    if _instance is None:
        _instance = SystemService()
    return _instance
