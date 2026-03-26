"""
MDGT Edge Fingerprint Verification System - Data Models.

SQLAlchemy-style dataclasses representing all database entities.
Immutable by default (frozen=True) with factory methods for updates.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"


class VerificationMode(str, Enum):
    VERIFY = "verify"
    IDENTIFY = "identify"


class VerificationDecision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    UNCERTAIN = "UNCERTAIN"


class DeviceStatus(str, Enum):
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"


# ---------------------------------------------------------------------------
# Embedding value object
# ---------------------------------------------------------------------------

EMBEDDING_DIM = 256


@dataclass(frozen=True)
class Embedding:
    """256-dimensional float32 embedding vector (immutable value object)."""

    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.values) != EMBEDDING_DIM:
            raise ValueError(
                f"Embedding must have {EMBEDDING_DIM} dimensions, "
                f"got {len(self.values)}"
            )

    @classmethod
    def from_list(cls, data: list[float]) -> Embedding:
        """Create an Embedding from a plain list of floats."""
        return cls(values=tuple(data))

    @classmethod
    def from_bytes(cls, raw: bytes) -> Embedding:
        """Deserialise from a packed float32 byte buffer."""
        if len(raw) != EMBEDDING_DIM * 4:
            raise ValueError(
                f"Expected {EMBEDDING_DIM * 4} bytes, got {len(raw)}"
            )
        values = struct.unpack(f"<{EMBEDDING_DIM}f", raw)
        return cls(values=values)

    def to_bytes(self) -> bytes:
        """Serialise to a packed little-endian float32 byte buffer."""
        return struct.pack(f"<{EMBEDDING_DIM}f", *self.values)

    def to_list(self) -> list[float]:
        """Return a plain list copy of the values."""
        return list(self.values)

    def to_dict(self) -> dict[str, Any]:
        return {"values": self.to_list(), "dim": EMBEDDING_DIM}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _utcnow() -> str:
    """ISO-8601 UTC timestamp string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class User:
    """Represents a registered user / employee."""

    id: Optional[int] = None
    employee_id: str = ""
    full_name: str = ""
    department: str = ""
    role: UserRole = UserRole.USER
    is_active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    # -- Serialisation -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "full_name": self.full_name,
            "department": self.department,
            "role": self.role.value,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> User:
        return cls(
            id=data.get("id"),
            employee_id=data.get("employee_id", ""),
            full_name=data.get("full_name", ""),
            department=data.get("department", ""),
            role=UserRole(data["role"]) if "role" in data else UserRole.USER,
            is_active=bool(data.get("is_active", True)),
            created_at=data.get("created_at", _utcnow()),
            updated_at=data.get("updated_at", _utcnow()),
        )

    @classmethod
    def from_row(cls, row: tuple) -> User:
        """Build from a database row (ordered by DDL column order)."""
        return cls(
            id=row[0],
            employee_id=row[1],
            full_name=row[2],
            department=row[3],
            role=UserRole(row[4]),
            is_active=bool(row[5]),
            created_at=row[6],
            updated_at=row[7],
        )

    def with_updates(self, **kwargs: Any) -> User:
        """Return a *new* User with the given fields changed."""
        kwargs.setdefault("updated_at", _utcnow())
        return replace(self, **kwargs)


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Fingerprint:
    """An enrolled fingerprint record (encrypted embeddings stored as BLOBs)."""

    id: Optional[int] = None
    user_id: int = 0
    finger_index: int = 0  # 0-9
    embedding_enc: Optional[bytes] = None
    minutiae_enc: Optional[bytes] = None
    quality_score: float = 0.0
    image_hash: str = ""
    enrolled_at: str = field(default_factory=_utcnow)
    is_active: bool = True

    def __post_init__(self) -> None:
        if not (0 <= self.finger_index <= 9):
            raise ValueError(
                f"finger_index must be 0-9, got {self.finger_index}"
            )
        if not (0.0 <= self.quality_score <= 100.0):
            raise ValueError(
                f"quality_score must be 0-100, got {self.quality_score}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "finger_index": self.finger_index,
            "embedding_enc": self.embedding_enc,
            "minutiae_enc": self.minutiae_enc,
            "quality_score": self.quality_score,
            "image_hash": self.image_hash,
            "enrolled_at": self.enrolled_at,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Fingerprint:
        return cls(
            id=data.get("id"),
            user_id=data.get("user_id", 0),
            finger_index=data.get("finger_index", 0),
            embedding_enc=data.get("embedding_enc"),
            minutiae_enc=data.get("minutiae_enc"),
            quality_score=float(data.get("quality_score", 0.0)),
            image_hash=data.get("image_hash", ""),
            enrolled_at=data.get("enrolled_at", _utcnow()),
            is_active=bool(data.get("is_active", True)),
        )

    @classmethod
    def from_row(cls, row: tuple) -> Fingerprint:
        return cls(
            id=row[0],
            user_id=row[1],
            finger_index=row[2],
            embedding_enc=row[3],
            minutiae_enc=row[4],
            quality_score=float(row[5]),
            image_hash=row[6],
            enrolled_at=row[7],
            is_active=bool(row[8]),
        )

    def with_updates(self, **kwargs: Any) -> Fingerprint:
        return replace(self, **kwargs)

    @staticmethod
    def compute_image_hash(image_bytes: bytes) -> str:
        """SHA-256 hex digest of the raw fingerprint image."""
        return hashlib.sha256(image_bytes).hexdigest()


# ---------------------------------------------------------------------------
# Verification Log
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VerificationLog:
    """Immutable audit record for every verification / identification attempt."""

    id: Optional[int] = None
    matched_user_id: Optional[int] = None
    matched_fp_id: Optional[int] = None
    mode: VerificationMode = VerificationMode.VERIFY
    score: float = 0.0
    decision: VerificationDecision = VerificationDecision.REJECT
    latency_ms: float = 0.0
    device_id: str = ""
    timestamp: str = field(default_factory=_utcnow)
    probe_quality: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "matched_user_id": self.matched_user_id,
            "matched_fp_id": self.matched_fp_id,
            "mode": self.mode.value,
            "score": self.score,
            "decision": self.decision.value,
            "latency_ms": self.latency_ms,
            "device_id": self.device_id,
            "timestamp": self.timestamp,
            "probe_quality": self.probe_quality,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationLog:
        return cls(
            id=data.get("id"),
            matched_user_id=data.get("matched_user_id"),
            matched_fp_id=data.get("matched_fp_id"),
            mode=VerificationMode(data["mode"]) if "mode" in data else VerificationMode.VERIFY,
            score=float(data.get("score", 0.0)),
            decision=VerificationDecision(data["decision"]) if "decision" in data else VerificationDecision.REJECT,
            latency_ms=float(data.get("latency_ms", 0.0)),
            device_id=data.get("device_id", ""),
            timestamp=data.get("timestamp", _utcnow()),
            probe_quality=float(data.get("probe_quality", 0.0)),
        )

    @classmethod
    def from_row(cls, row: tuple) -> VerificationLog:
        return cls(
            id=row[0],
            matched_user_id=row[1],
            matched_fp_id=row[2],
            mode=VerificationMode(row[3]),
            score=float(row[4]),
            decision=VerificationDecision(row[5]),
            latency_ms=float(row[6]),
            device_id=row[7],
            timestamp=row[8],
            probe_quality=float(row[9]),
        )


# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Device:
    """Edge device registry entry."""

    id: str = ""
    name: str = ""
    location: str = ""
    firmware_ver: str = ""
    last_sync: Optional[str] = None
    status: DeviceStatus = DeviceStatus.ACTIVE

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "location": self.location,
            "firmware_ver": self.firmware_ver,
            "last_sync": self.last_sync,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Device:
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            location=data.get("location", ""),
            firmware_ver=data.get("firmware_ver", ""),
            last_sync=data.get("last_sync"),
            status=DeviceStatus(data["status"]) if "status" in data else DeviceStatus.ACTIVE,
        )

    @classmethod
    def from_row(cls, row: tuple) -> Device:
        return cls(
            id=row[0],
            name=row[1],
            location=row[2],
            firmware_ver=row[3],
            last_sync=row[4],
            status=DeviceStatus(row[5]),
        )

    def with_updates(self, **kwargs: Any) -> Device:
        return replace(self, **kwargs)


# ---------------------------------------------------------------------------
# System Config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SystemConfig:
    """Key-value configuration entry (value stored as JSON text)."""

    key: str = ""
    value: str = ""
    updated_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SystemConfig:
        return cls(
            key=data.get("key", ""),
            value=data.get("value", ""),
            updated_at=data.get("updated_at", _utcnow()),
        )

    @classmethod
    def from_row(cls, row: tuple) -> SystemConfig:
        return cls(
            key=row[0],
            value=row[1],
            updated_at=row[2],
        )

    def with_updates(self, **kwargs: Any) -> SystemConfig:
        kwargs.setdefault("updated_at", _utcnow())
        return replace(self, **kwargs)
