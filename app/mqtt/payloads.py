"""MQTT payload dataclasses for worker ↔ orchestrator communication."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional


# ── Enums ────────────────────────────────────────────────────────────────────


class TaskType(str, Enum):
    EMBED = "embed"
    MATCH = "match"
    REGISTER = "register"
    VERIFY = "verify"


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkerStatus(str, Enum):
    ONLINE = "online"
    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"


class ModelStatus(str, Enum):
    DOWNLOADING = "downloading"
    CONVERTING = "converting"
    READY = "ready"
    FAILED = "failed"


# ── Orchestrator → Worker payloads ───────────────────────────────────────────


class TaskPayload:
    """Embed task: download image from URL and extract embedding."""

    def __init__(self, **kwargs: Any) -> None:
        self.task_id: str = kwargs.get("task_id", "")
        self.task_type: str = kwargs.get("task_type", "embed")
        self.image_url: str = kwargs.get("image_url", "")
        self.model_name: str = kwargs.get("model_name", "default")
        self.extra: Dict[str, Any] = kwargs.get("extra", {})


class MatchPayload:
    """Match task: compare query vector against candidates."""

    def __init__(self, **kwargs: Any) -> None:
        self.task_id: str = kwargs.get("task_id", "")
        self.task_type: str = kwargs.get("task_type", "match")
        self.query_vector: List[float] = kwargs.get("query_vector", [])
        self.candidate_vectors: List[List[float]] = kwargs.get("candidate_vectors", [])
        self.top_k: int = kwargs.get("top_k", 5)
        self.threshold: float = kwargs.get("threshold", 0.7)


class RegisterTaskPayload:
    """Register task: capture from sensor, enroll user, return embedding."""

    def __init__(self, **kwargs: Any) -> None:
        self.task_id: str = kwargs.get("task_id", "")
        self.task_type: str = kwargs.get("task_type", "register")
        self.user_id: str = kwargs.get("user_id", "")
        self.employee_id: str = kwargs.get("employee_id", "")
        self.full_name: str = kwargs.get("full_name", "")
        self.department: str = kwargs.get("department", "")
        self.finger_type: str = kwargs.get("finger_type", "right_index")
        self.num_samples: int = kwargs.get("num_samples", 3)
        # If image is provided via base64, skip sensor capture
        self.image_base64: str = kwargs.get("image_base64", "")
        self.image_filename: str = kwargs.get("image_filename", "")


class VerifyTaskPayload:
    """Verify task: capture from sensor, verify 1:1 or identify 1:N."""

    def __init__(self, **kwargs: Any) -> None:
        self.task_id: str = kwargs.get("task_id", "")
        self.task_type: str = kwargs.get("task_type", "verify")
        self.user_id: str = kwargs.get("user_id", "")  # for 1:1 verify
        self.mode: str = kwargs.get("mode", "verify")  # "verify" | "identify"
        self.top_k: int = kwargs.get("top_k", 5)
        # If image is provided via base64, skip sensor capture
        self.image_base64: str = kwargs.get("image_base64", "")
        self.image_filename: str = kwargs.get("image_filename", "")


class ModelUpdatePayload:
    """Command to download/update a model on the worker."""

    def __init__(self, **kwargs: Any) -> None:
        self.model_type: str = kwargs.get("model_type", "")       # "embedding", "matching", "pad"
        self.model_name: str = kwargs.get("model_name", "")
        self.version: str = kwargs.get("version", "")
        self.download_url: str = kwargs.get("download_url", "")   # presigned URL
        self.s3_path: str = kwargs.get("s3_path", "")


# ── Worker → Orchestrator payloads ───────────────────────────────────────────


class ModelStatusPayload:
    """Report model download/convert status to orchestrator."""

    def __init__(self, **kwargs: Any) -> None:
        self.worker_id: str = kwargs.get("worker_id", "")
        self.model_type: str = kwargs.get("model_type", "")
        self.model_name: str = kwargs.get("model_name", "")
        self.version: str = kwargs.get("version", "")
        self.status: str = kwargs.get("status", "")
        self.error: Optional[str] = kwargs.get("error", None)


class HeartbeatPayload:
    """Periodic heartbeat sent to orchestrator."""

    def __init__(self, **kwargs: Any) -> None:
        self.worker_id: str = kwargs.get("worker_id", "")
        self.status: str = kwargs.get("status", "idle")
        self.gpu_memory_used_mb: Optional[float] = kwargs.get("gpu_memory_used_mb", None)
        self.gpu_memory_total_mb: Optional[float] = kwargs.get("gpu_memory_total_mb", None)
        self.current_task_id: Optional[str] = kwargs.get("current_task_id", None)
        self.uptime_seconds: Optional[float] = kwargs.get("uptime_seconds", None)
        self.loaded_models: Dict[str, str] = kwargs.get("loaded_models", {})
        self.sensor_connected: bool = kwargs.get("sensor_connected", False)
