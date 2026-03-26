"""
Service for managing inference models: scan, upload, delete, convert, profile.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from web.backend.config import get_settings

logger = logging.getLogger(__name__)

# In-memory registry of known models and which one is active
_model_registry: dict[str, dict[str, Any]] = {}
_active_model_id: str | None = None


class ModelService:
    """Manages model files on disk and their lifecycle."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._model_dir = Path(self._settings.model_dir)
        self._model_dir.mkdir(parents=True, exist_ok=True)

    # -- scan / list --------------------------------------------------------

    async def list_models(self) -> list[dict[str, Any]]:
        """Scan the models/ directory and return metadata for each model file."""
        global _active_model_id
        models: list[dict[str, Any]] = []

        if not self._model_dir.exists():
            return models

        extensions = {".onnx", ".trt", ".engine", ".pt", ".pth"}
        for path in sorted(self._model_dir.iterdir()):
            if path.suffix.lower() not in extensions:
                continue
            model_id = _path_to_id(path)
            fmt = path.suffix.lstrip(".").lower()
            if fmt == "engine":
                fmt = "trt"
            if fmt == "pth":
                fmt = "pt"

            info = {
                "id": model_id,
                "filename": path.name,
                "format": fmt,
                "size_mb": round(path.stat().st_size / (1024 * 1024), 2),
                "is_active": model_id == _active_model_id,
                "created_at": path.stat().st_ctime,
            }
            _model_registry[model_id] = info
            models.append(info)

        return models

    # -- upload -------------------------------------------------------------

    async def upload_model(self, filename: str, content: bytes) -> dict[str, Any]:
        dest = self._model_dir / filename
        await asyncio.to_thread(dest.write_bytes, content)

        model_id = _path_to_id(dest)
        info = {
            "id": model_id,
            "filename": filename,
            "size_mb": round(len(content) / (1024 * 1024), 2),
        }
        _model_registry[model_id] = info
        logger.info("Uploaded model %s (%s MB)", filename, info["size_mb"])
        return info

    # -- delete -------------------------------------------------------------

    async def delete_model(self, model_id: str) -> bool:
        global _active_model_id
        info = _model_registry.get(model_id)
        if info is None:
            # Try rescanning
            await self.list_models()
            info = _model_registry.get(model_id)
        if info is None:
            return False

        path = self._model_dir / info["filename"]
        if path.exists():
            await asyncio.to_thread(path.unlink)

        if _active_model_id == model_id:
            _active_model_id = None
        _model_registry.pop(model_id, None)
        logger.info("Deleted model %s", model_id)
        return True

    # -- activate -----------------------------------------------------------

    async def activate_model(self, model_id: str) -> bool:
        global _active_model_id
        if model_id not in _model_registry:
            await self.list_models()
        if model_id not in _model_registry:
            return False
        _active_model_id = model_id
        # Mark all others as inactive
        for mid, info in _model_registry.items():
            info["is_active"] = mid == model_id
        logger.info("Activated model %s", model_id)
        return True

    # -- convert (ONNX -> TensorRT) ----------------------------------------

    async def convert_model(
        self, model_id: str, precision: str = "fp16", max_batch_size: int = 1
    ) -> dict[str, Any]:
        """
        Trigger ONNX to TensorRT conversion.  In production this calls
        trtexec; here we simulate the process.
        """
        info = _model_registry.get(model_id)
        if info is None:
            raise ValueError(f"Model {model_id} not found")
        if info.get("format") != "onnx":
            raise ValueError("Only ONNX models can be converted to TensorRT")

        src = self._model_dir / info["filename"]
        dst_name = src.stem + f"_{precision}.trt"
        dst = self._model_dir / dst_name

        logger.info(
            "Converting %s -> %s (precision=%s, batch=%d)",
            src.name,
            dst_name,
            precision,
            max_batch_size,
        )

        # Simulate conversion (in production: subprocess trtexec ...)
        await asyncio.sleep(2.0)

        # Create a placeholder file
        await asyncio.to_thread(dst.write_bytes, b"TRT_PLACEHOLDER")

        new_id = _path_to_id(dst)
        new_info = {
            "id": new_id,
            "filename": dst_name,
            "format": "trt",
            "size_mb": round(dst.stat().st_size / (1024 * 1024), 2),
            "is_active": False,
            "created_at": dst.stat().st_ctime,
        }
        _model_registry[new_id] = new_info
        return new_info

    # -- profile (benchmark) -----------------------------------------------

    async def profile_model(self, model_id: str, num_runs: int = 100) -> dict[str, Any]:
        info = _model_registry.get(model_id)
        if info is None:
            raise ValueError(f"Model {model_id} not found")

        logger.info("Profiling model %s with %d runs", model_id, num_runs)

        # Simulate benchmarking
        import random

        latencies = [random.uniform(8.0, 25.0) for _ in range(num_runs)]
        latencies.sort()

        return {
            "model_id": model_id,
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2),
            "min_latency_ms": round(latencies[0], 2),
            "max_latency_ms": round(latencies[-1], 2),
            "p95_latency_ms": round(latencies[int(0.95 * num_runs)], 2),
            "throughput_fps": round(1000.0 / (sum(latencies) / len(latencies)), 2),
            "num_runs": num_runs,
        }

    # -- get model by id ----------------------------------------------------

    async def get_model(self, model_id: str) -> dict[str, Any] | None:
        if model_id not in _model_registry:
            await self.list_models()
        return _model_registry.get(model_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _path_to_id(path: Path) -> str:
    """Deterministic short id from filename."""
    return hashlib.md5(path.name.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------

_instance: ModelService | None = None


def get_model_service() -> ModelService:
    global _instance
    if _instance is None:
        _instance = ModelService()
    return _instance
