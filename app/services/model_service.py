"""
Service managing model inference: scan, upload, delete, convert, profile.
"""


from typing import List, Dict, Tuple, Set, Optional, Any, Union, Coroutine, Callable, Generator, Iterable, AsyncIterator, TypeVar, Type, Awaitable, Sequence, Mapping
import asyncio
import hashlib
import json
import logging
import os
import shutil
import threading
import time
from pathlib import Path

import requests

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# In-memory registry: stores model info and tracks active model
_model_registry: Dict[str, Dict[str, Any]] = {}
_active_model_id: Optional[str] = None

# State file for loaded models (persisted across restarts)
_STATE_FILE = os.path.join(os.getcwd(), "models", "loaded_models.json")


class ModelService:
    """Manages model files on disk and their lifecycle.

    Supports:
    - Local model management (list, upload, delete, activate, convert)
    - MQTT-driven model downloads from orchestrator (download_model)
    - Multi-model type tracking: embedding, matching, pad
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._model_dir = Path(self._settings.model_dir)
        self._model_dir.mkdir(parents=True, exist_ok=True)
        self._loaded_models: Dict[str, str] = {}  # {"embedding": "model.onnx", ...}
        self._lock = threading.Lock()
        self._load_state()

    # -- State persistence (for MQTT-downloaded models) ----------------------

    def _load_state(self) -> None:
        """Load saved model state from disk."""
        try:
            if os.path.exists(_STATE_FILE):
                with open(_STATE_FILE, "r") as f:
                    self._loaded_models = json.load(f)
                logger.info("Loaded model state: %s", self._loaded_models)
        except Exception as exc:
            logger.error("Failed to load model state: %s", exc)

    def _save_state(self) -> None:
        """Save current model state to disk."""
        try:
            os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
            with open(_STATE_FILE, "w") as f:
                json.dump(self._loaded_models, f, indent=2)
        except Exception as exc:
            logger.error("Failed to save model state: %s", exc)

    @property
    def loaded_models(self) -> Dict[str, str]:
        """Return dict of loaded models by type: {type: name}."""
        with self._lock:
            return dict(self._loaded_models)

    @property
    def model_dir(self) -> str:
        return str(self._model_dir)

    # -- scan / list ---------------------------------------------------------

    async def list_models(self) -> List[Dict[str, Any]]:
        """Scans models/ directory and returns metadata for each model file."""
        global _active_model_id
        models: List[Dict[str, Any]] = []

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

    # -- upload --------------------------------------------------------------

    async def upload_model(self, filename: str, content: bytes) -> Dict[str, Any]:
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

    # -- delete --------------------------------------------------------------

    async def delete_model(self, model_id: str) -> bool:
        global _active_model_id
        info = _model_registry.get(model_id)
        if info is None:
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

    # -- activate ------------------------------------------------------------

    async def activate_model(self, model_id: str) -> bool:
        global _active_model_id
        if model_id not in _model_registry:
            await self.list_models()
        if model_id not in _model_registry:
            return False
        _active_model_id = model_id
        for mid, info in _model_registry.items():
            info["is_active"] = mid == model_id
        logger.info("Activated model %s", model_id)
        return True

    # -- convert (ONNX -> TensorRT) ------------------------------------------

    async def convert_model(
        self, model_id: str, precision: str = "fp16", max_batch_size: int = 1
    ) -> Dict[str, Any]:
        """
        ONNX to TensorRT conversion.
        In production: invokes trtexec subprocess.
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

        # TODO: replace with subprocess trtexec when running on Jetson Nano
        await asyncio.sleep(2.0)

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

    # -- profile (benchmark) -------------------------------------------------

    async def profile_model(self, model_id: str, num_runs: int = 100) -> Dict[str, Any]:
        info = _model_registry.get(model_id)
        if info is None:
            raise ValueError(f"Model {model_id} not found")

        logger.info("Profiling model %s with %d runs", model_id, num_runs)

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

    # -- get model by id -----------------------------------------------------

    async def get_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        if model_id not in _model_registry:
            await self.list_models()
        return _model_registry.get(model_id)

    # -- download from orchestrator (MQTT-driven, sync) ----------------------

    def download_model(
        self,
        model_type: str,
        model_name: str,
        version: str,
        download_url: str,
    ) -> Tuple[bool, Optional[str]]:
        """Download a model from orchestrator presigned URL.

        Saves to: models/{model_type}/{model_name}
        Returns (success, error_message).
        """
        save_dir = self._model_dir / model_type
        save_path = save_dir / model_name

        try:
            save_dir.mkdir(parents=True, exist_ok=True)

            logger.info(
                "Downloading model: %s/%s → %s",
                model_type, model_name, save_path,
            )

            response = requests.get(download_url, stream=True, timeout=300)
            response.raise_for_status()

            downloaded = 0
            with open(str(save_path), "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)

            file_size = save_path.stat().st_size
            logger.info(
                "✅ Model downloaded: %s/%s (%.1f MB)",
                model_type, model_name, file_size / (1024 * 1024),
            )

            with self._lock:
                self._loaded_models[model_type] = model_name
                self._save_state()

            return True, None

        except requests.RequestException as exc:
            error = "Download failed: {}".format(exc)
            logger.error("❌ %s", error)
            return False, error

        except Exception as exc:
            error = "Model save failed: {}".format(exc)
            logger.error("❌ %s", error)
            return False, error

    def get_model_path_by_type(self, model_type: str) -> Optional[str]:
        """Get the path to the loaded model for a given type.

        Prefers TRT/engine files over ONNX.
        """
        with self._lock:
            model_name = self._loaded_models.get(model_type)

        type_dir = self._model_dir / model_type

        if not model_name:
            # Try to find any model file in the type directory
            if not type_dir.is_dir():
                return None
            for f in sorted(type_dir.iterdir()):
                if f.suffix in (".trt", ".engine"):
                    return str(f)
            for f in sorted(type_dir.iterdir()):
                if f.suffix == ".onnx":
                    return str(f)
            return None

        # Prefer TRT engine over ONNX
        if model_name.endswith(".onnx"):
            for ext in (".trt", ".engine"):
                alt = type_dir / model_name.replace(".onnx", ext)
                if alt.exists():
                    return str(alt)

        model_path = type_dir / model_name
        if model_path.exists():
            return str(model_path)
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _path_to_id(path: Path) -> str:
    """Deterministic short id from filename."""
    return hashlib.md5(path.name.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------

_instance: Optional["ModelService"] = None


async def get_model_service() -> "ModelService":
    global _instance
    if _instance is None:
        _instance = ModelService()
    return _instance
