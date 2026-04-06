"""
Pydantic v2 schemas for all API request/response models.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field, ConfigDict, field_validator


# ---------------------------------------------------------------------------
# Generic API response wrapper
# ---------------------------------------------------------------------------

DataT = TypeVar("DataT")
RoleLiteral = Literal["user", "admin", "superadmin"]


class ApiResponse(BaseModel, Generic[DataT]):
    """Standard envelope returned by every endpoint."""

    success: bool = True
    data: DataT | None = None
    error: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class PaginationMeta(BaseModel):
    total: int
    page: int
    limit: int
    pages: int


# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------


class FingerEnum(str, Enum):
    RIGHT_THUMB = "right_thumb"
    RIGHT_INDEX = "right_index"
    RIGHT_MIDDLE = "right_middle"
    RIGHT_RING = "right_ring"
    RIGHT_LITTLE = "right_little"
    LEFT_THUMB = "left_thumb"
    LEFT_INDEX = "left_index"
    LEFT_MIDDLE = "left_middle"
    LEFT_RING = "left_ring"
    LEFT_LITTLE = "left_little"


class UserCreate(BaseModel):
    employee_id: str = Field(..., min_length=1, max_length=50)
    full_name: str = Field(..., min_length=1, max_length=200)
    department: str = Field(default="", max_length=100)
    role: RoleLiteral = Field(default="user")

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, value):
        if value == "employee":
            return "user"
        return value


class UserUpdate(BaseModel):
    full_name: str | None = None
    department: str | None = None
    role: RoleLiteral | None = None

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, value):
        if value == "employee":
            return "user"
        return value


class EnrolledFinger(BaseModel):
    finger: FingerEnum
    enrolled_at: datetime
    quality_score: float


class UserResponse(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    employee_id: str
    full_name: str
    department: str
    role: str
    is_active: bool = True
    fingerprint_count: int = 0
    enrolled_fingers: list[EnrolledFinger] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(from_attributes=True)


class UserListResponse(BaseModel):
    users: list[UserResponse]
    pagination: PaginationMeta


# ---------------------------------------------------------------------------
# Fingerprint / Enrollment schemas
# ---------------------------------------------------------------------------


class FingerprintResponse(BaseModel):
    finger: FingerEnum
    image_base64: str | None = None
    quality_score: float = 0.0
    width: int = 0
    height: int = 0


class EnrollRequest(BaseModel):
    finger: FingerEnum = FingerEnum.RIGHT_INDEX
    num_samples: int = Field(default=3, ge=1, le=10)


class EnrollResponse(BaseModel):
    user_id: str
    finger: FingerEnum
    quality_score: float
    template_count: int
    message: str = "Enrollment successful"


# ---------------------------------------------------------------------------
# Verification / Identification schemas
# ---------------------------------------------------------------------------


class VerifyRequest(BaseModel):
    user_id: str
    image_base64: str | None = None


class VerifyResponse(BaseModel):
    matched: bool
    score: float
    threshold: float
    user_id: str
    latency_ms: float


class IdentifyRequest(BaseModel):
    top_k: int = Field(default=5, ge=1, le=50)
    image_base64: str | None = None


class IdentifyCandidate(BaseModel):
    user_id: str
    employee_id: str
    full_name: str
    score: float


class IdentifyResponse(BaseModel):
    identified: bool
    candidates: list[IdentifyCandidate]
    threshold: float
    latency_ms: float


# ---------------------------------------------------------------------------
# Model management schemas
# ---------------------------------------------------------------------------


class ModelInfo(BaseModel):
    id: str
    filename: str
    format: str  # "onnx", "trt", "pt"
    size_mb: float
    is_active: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ModelListResponse(BaseModel):
    models: list[ModelInfo]


class ModelUploadResponse(BaseModel):
    id: str
    filename: str
    size_mb: float
    message: str = "Model uploaded successfully"


class ConvertRequest(BaseModel):
    precision: str = Field(default="fp16", pattern="^(fp16|fp32|int8)$")
    max_batch_size: int = Field(default=1, ge=1, le=32)


class ProfileResponse(BaseModel):
    model_id: str
    avg_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    p95_latency_ms: float
    throughput_fps: float
    num_runs: int


# ---------------------------------------------------------------------------
# Logging / Stats schemas
# ---------------------------------------------------------------------------


class LogEntry(BaseModel):
    id: str
    timestamp: datetime
    user_id: str | None = None
    employee_id: str | None = None
    action: str  # "verify", "identify", "enroll"
    decision: str  # "accept", "reject", "error"
    score: float | None = None
    latency_ms: float | None = None
    details: str | None = None


class LogListResponse(BaseModel):
    logs: list[LogEntry]
    pagination: PaginationMeta


class StatsResponse(BaseModel):
    enrolled_users: int
    enrolled_fingers: int
    verifications_today: int
    identifications_today: int
    acceptance_rate: float
    rejection_rate: float
    avg_latency_ms: float
    uptime_seconds: float


# ---------------------------------------------------------------------------
# System schemas
# ---------------------------------------------------------------------------


class SystemHealth(BaseModel):
    status: str = "healthy"
    uptime_seconds: float
    cpu_percent: float
    cpu_temp_c: float | None = None
    gpu_temp_c: float | None = None
    memory_used_mb: float
    memory_total_mb: float
    disk_used_gb: float
    disk_total_gb: float
    sensor_connected: bool
    active_model: str | None = None
    device_id: str


class ConfigResponse(BaseModel):
    device_id: str
    verify_threshold: float
    identify_threshold: float
    identify_top_k: int
    model_dir: str
    data_dir: str
    sensor_vid: int
    sensor_pid: int
    debug: bool


class ConfigUpdateRequest(BaseModel):
    verify_threshold: float | None = None
    identify_threshold: float | None = None
    identify_top_k: int | None = None
    debug: bool | None = None


# ---------------------------------------------------------------------------
# Sensor schemas
# ---------------------------------------------------------------------------


class SensorStatus(BaseModel):
    connected: bool
    vendor_id: int | None = None
    product_id: int | None = None
    firmware_version: str | None = None
    serial_number: str | None = None
    resolution_dpi: int | None = None
    user_count: int | None = None
    compare_level: int | None = None
    is_real_hardware: bool = False


class CaptureResponse(BaseModel):
    success: bool
    image_base64: str | None = None
    width: int = 0
    height: int = 0
    quality_score: float = 0.0
    has_finger: bool = False
    message: str = ""


class LEDRequest(BaseModel):
    color: str = "green"
    duration_ms: int = Field(default=1000, ge=0, le=10000)


# ---------------------------------------------------------------------------
# Device schemas
# ---------------------------------------------------------------------------


class DeviceInfo(BaseModel):
    device_id: str
    hostname: str
    ip_address: str | None = None
    status: str = "online"
    last_seen: datetime = Field(default_factory=datetime.utcnow)


class BackupResponse(BaseModel):
    success: bool
    filename: str
    size_mb: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    message: str = "Backup completed"
