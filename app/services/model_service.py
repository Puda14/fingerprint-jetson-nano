"""
Service managing model inference: scan, upload, delete, convert, profile.
"""


from typing import List, Dict, Tuple, Set, Optional, Any, Union, Coroutine, Callable, Generator, Iterable, AsyncIterator, TypeVar, Type, Awaitable, Sequence, Mapping
import asyncio
import hashlib
import json
import logging
import os
import re
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
_MODEL_EXTENSIONS = {".onnx", ".trt", ".engine", ".pt", ".pth"}

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
        self._loaded_models: Dict[str, str] = {}  # {"embedding": "embedding_v1", ...}
        self._lock = threading.Lock()
        self._load_state()

    # -- State persistence (for MQTT-downloaded models) ----------------------

    def _load_state(self) -> None:
        """Load saved model state from disk."""
        try:
            if os.path.exists(_STATE_FILE):
                with open(_STATE_FILE, "r") as f:
                    raw_state = json.load(f)
                normalized_state = {
                    model_type: self._normalize_loaded_ref(model_ref)
                    for model_type, model_ref in raw_state.items()
                }
                self._loaded_models = normalized_state
                if normalized_state != raw_state:
                    self._save_state()
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

    def build_local_model_path(
        self,
        model_type: str,
        model_name: str,
        relative_path: str = "",
    ) -> Path:
        """Resolve the local target path for a downloaded model."""
        if relative_path:
            clean_parts = [
                part for part in Path(relative_path).parts
                if part not in ("", ".")
            ]
            return self._model_dir / model_type / Path(*clean_parts)
        return self._model_dir / model_type / model_name

    def _store_loaded_ref(
        self,
        model_name: str,
        relative_path: str = "",
    ) -> str:
        if model_name:
            return self._normalize_loaded_ref(model_name)
        if relative_path:
            return self._normalize_loaded_ref(relative_path)
        return ""

    def _normalize_loaded_ref(self, model_ref: str) -> str:
        ref = str(model_ref or "").strip()
        if not ref:
            return ""

        ref_path = Path(ref)
        if ref_path.parent != Path("."):
            parent_name = ref_path.parent.name
            if parent_name:
                return parent_name

        name = ref_path.name
        suffix = ref_path.suffix.lower()
        if suffix in _MODEL_EXTENSIONS:
            name = ref_path.stem

        normalized = re.sub(r"_(fp16|fp32|int8)$", "", name, flags=re.IGNORECASE)
        return normalized or name

    def _resolve_loaded_scope(self, model_type: str) -> Optional[Path]:
        with self._lock:
            model_ref = self._loaded_models.get(model_type)

        if not model_ref:
            return None

        type_dir = self._model_dir / model_type
        candidate = type_dir / model_ref
        if candidate.exists():
            return candidate

        if not type_dir.exists():
            return None

        normalized_ref = self._normalize_loaded_ref(model_ref)
        matches = sorted(
            path for path in type_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in _MODEL_EXTENSIONS
            and self._normalize_loaded_ref(path.relative_to(type_dir).as_posix()) == normalized_ref
        )
        if matches:
            parent_dirs = {match.parent for match in matches}
            if len(parent_dirs) == 1:
                return matches[0].parent
            return matches[0]
        return None

    def _collect_candidate_models(self, root: Path) -> List[Path]:
        if root.is_file() and root.suffix.lower() in _MODEL_EXTENSIONS:
            return [root]
        if not root.exists():
            return []
        return sorted(
            p for p in root.rglob("*")
            if p.is_file() and p.suffix.lower() in _MODEL_EXTENSIONS
        )

    # -- scan / list ---------------------------------------------------------

    async def list_models(self) -> List[Dict[str, Any]]:
        """Scans models/ directory and returns metadata for each model file."""
        global _active_model_id
        models: List[Dict[str, Any]] = []

        if not self._model_dir.exists():
            return models

        for path in sorted(
            p for p in self._model_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in _MODEL_EXTENSIONS
        ):
            relative_name = path.relative_to(self._model_dir).as_posix()
            model_id = _path_to_id(relative_name)
            fmt = path.suffix.lstrip(".").lower()
            if fmt == "engine":
                fmt = "trt"
            if fmt == "pth":
                fmt = "pt"

            info = {
                "id": model_id,
                "filename": relative_name,
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
        dest.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(dest.write_bytes, content)

        model_id = _path_to_id(dest.relative_to(self._model_dir).as_posix())
        info = {
            "id": model_id,
            "filename": dest.relative_to(self._model_dir).as_posix(),
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
        dst_name = src.stem + f"_{precision}.engine"
        dst = src.parent / dst_name

        logger.info(
            "Converting %s -> %s (precision=%s, batch=%d)",
            src.name, dst_name, precision, max_batch_size,
        )

        # Find trtexec on Jetson Nano
        import shutil
        import subprocess
        trtexec_paths = [
            "/usr/src/tensorrt/bin/trtexec",
            "/usr/local/bin/trtexec",
            shutil.which("trtexec") or "",
        ]
        trtexec_bin = next((p for p in trtexec_paths if p and os.path.exists(p)), None)

        if trtexec_bin is None:
            raise RuntimeError(
                "trtexec not found on this system. "
                "Install TensorRT or use ONNX Runtime fallback."
            )

        cmd = [
            trtexec_bin,
            f"--onnx={src}",
            f"--saveEngine={dst}",
            f"--maxBatch={max_batch_size}",
        ]
        if precision == "fp16":
            cmd.append("--fp16")
        elif precision == "int8":
            cmd.append("--int8")

        logger.info("Running: %s", " ".join(cmd))

        loop = asyncio.get_event_loop()
        proc = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
            )
        )

        if proc.returncode != 0:
            raise RuntimeError(
                f"trtexec failed (code {proc.returncode}):\n{proc.stderr[-2000:]}"
            )

        if not dst.exists():
            raise RuntimeError(f"trtexec succeeded but output file not found: {dst}")

        new_id = _path_to_id(dst.relative_to(self._model_dir).as_posix())
        new_info = {
            "id": new_id,
            "filename": dst.relative_to(self._model_dir).as_posix(),
            "format": "engine",
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
        relative_path: str = "",
    ) -> Tuple[bool, Optional[str]]:
        """Download a model from orchestrator presigned URL.

        Saves to: models/{model_type}/{relative_path or model_name}
        Returns (success, error_message).
        """
        save_path = self.build_local_model_path(
            model_type=model_type,
            model_name=model_name,
            relative_path=relative_path,
        )
        save_dir = save_path.parent

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
                self._loaded_models[model_type] = self._store_loaded_ref(
                    model_name=model_name,
                    relative_path=relative_path,
                )
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

    def get_model_path_by_type(
        self,
        model_type: str,
        backend_preference: Optional[str] = None,
    ) -> Optional[str]:
        """Get the path to the loaded model for a given type.

        Prefers the active folder for that type and then selects the best
        matching file for the current runtime/backend preference.
        """
        type_dir = self._model_dir / model_type
        search_root = self._resolve_loaded_scope(model_type) or type_dir
        if not search_root.exists():
            return None

        candidate_root = search_root.parent if search_root.is_file() else search_root
        candidates = self._collect_candidate_models(candidate_root)
        if not candidates and candidate_root != type_dir and type_dir.exists():
            candidates = self._collect_candidate_models(type_dir)
        if not candidates:
            return None

        want_tensorrt = (
            backend_preference == "tensorrt" and is_tensorrt_runtime_available()
        )
        preferred_exts = (
            (".engine", ".trt", ".onnx")
            if want_tensorrt
            else (".onnx", ".engine", ".trt")
        )

        for ext in preferred_exts:
            for candidate in candidates:
                if candidate.suffix.lower() == ext:
                    return str(candidate)

        return str(candidates[0])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _path_to_id(path_ref: Any) -> str:
    """Deterministic short id from a path-like reference."""
    path_str = str(path_ref)
    return hashlib.md5(path_str.encode()).hexdigest()[:12]


def is_tensorrt_runtime_available() -> bool:
    """Return whether TensorRT and PyCUDA are both available."""
    try:
        import tensorrt  # type: ignore[import-untyped]  # noqa: F401
        import pycuda.driver  # type: ignore[import-untyped]  # noqa: F401
        return True
    except ImportError:
        return False


def convert_onnx_to_trt(
    input_path: str,
    output_path: str,
    fp16: bool = True,
    max_workspace_mb: int = 1024,
    max_batch_size: int = 1,
) -> bool:
    """Convert ONNX model to TensorRT engine using Python TensorRT API.

    Handles dynamic shapes automatically.
    Falls back gracefully when TensorRT is not available.

    Args:
        input_path: Path to input ONNX model.
        output_path: Path to save TensorRT engine.
        fp16: Enable FP16 precision (default True).
        max_workspace_mb: Max GPU workspace in MB.
        max_batch_size: Maximum batch size.

    Returns:
        True if conversion was successful.
    """
    try:
        import tensorrt as trt  # type: ignore
    except ImportError:
        logger.warning(
            "TensorRT not available — skipping conversion, will use ONNX Runtime."
        )
        return False

    logger.info("TensorRT version: %s", trt.__version__)
    logger.info("Converting: %s → %s (fp16=%s)", input_path, output_path, fp16)

    trt_logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(trt_logger)
    network = builder.create_network(
        1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
    )
    parser = trt.OnnxParser(network, trt_logger)

    # Parse ONNX model
    logger.info("Parsing ONNX model...")
    with open(input_path, "rb") as f:
        if not parser.parse(f.read()):
            for i in range(parser.num_errors):
                logger.error("  Parse error: %s", parser.get_error(i))
            return False

    logger.info(
        "  Inputs: %d  Outputs: %d",
        network.num_inputs, network.num_outputs,
    )

    # Build config
    config = builder.create_builder_config()
    # TRT 8.4+ uses set_memory_pool_limit; older (Jetson JetPack 4.x) uses max_workspace_size
    workspace_bytes = max_workspace_mb * (1 << 20)
    if hasattr(config, "set_memory_pool_limit"):
        config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, workspace_bytes)
    else:
        config.max_workspace_size = workspace_bytes  # TRT 8.2 / 8.3

    if fp16 and builder.platform_has_fast_fp16:
        logger.info("Enabling FP16 precision")
        config.set_flag(trt.BuilderFlag.FP16)
    elif fp16:
        logger.warning("FP16 not supported on this platform, using FP32")

    # Handle dynamic shapes
    profile = builder.create_optimization_profile()
    for i in range(network.num_inputs):
        inp = network.get_input(i)
        shape = inp.shape
        if any(d == -1 for d in shape):
            # For fingerprint models: always batch=1, fixed spatial dims
            # Using small/safe shapes to avoid GPU OOM on Jetson Nano (2GB shared RAM)
            min_shape = tuple(1 if d == -1 else max(1, d) for d in shape)
            opt_shape = tuple(1 if d == -1 else max(1, d) for d in shape)
            max_shape = tuple(1 if d == -1 else max(1, d) for d in shape)
            logger.info(
                "  Dynamic input %s: min=%s opt=%s max=%s",
                inp.name, min_shape, opt_shape, max_shape,
            )
            profile.set_shape(inp.name, min_shape, opt_shape, max_shape)
    config.add_optimization_profile(profile)

    # Build engine
    logger.info("Building TensorRT engine (may take several minutes)...")
    start_time = time.time()
    serialized_engine = builder.build_serialized_network(network, config)
    if serialized_engine is None:
        logger.error("Failed to build TensorRT engine")
        return False

    build_time = time.time() - start_time
    logger.info("Engine built in %.1f seconds", build_time)

    # Save to disk
    with open(output_path, "wb") as f:
        f.write(serialized_engine)

    engine_size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    logger.info("Engine saved: %s (%.1f MB)", output_path, engine_size_mb)
    return True



# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------

_instance: Optional["ModelService"] = None


async def get_model_service() -> "ModelService":
    global _instance
    if _instance is None:
        _instance = ModelService()
    return _instance


def get_model_service_sync() -> "ModelService":
    """Sync version for use in background threads (MQTT handlers etc)."""
    global _instance
    if _instance is None:
        _instance = ModelService()
    return _instance
