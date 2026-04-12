"""
Data models for local fingerprint database.

Ported from jetson-fingerverify-app/mdgt_edge/database/models.py.
Simplified for the worker's local storage needs.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Any, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMBEDDING_DIM = 512


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class VerificationMode(str, Enum):
    VERIFY = "verify"
    IDENTIFY = "identify"


class VerificationDecision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    UNCERTAIN = "UNCERTAIN"


# ---------------------------------------------------------------------------
# Embedding value object
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Embedding:
    """512-dimensional float32 embedding vector (immutable)."""

    values: tuple

    def __post_init__(self):
        if len(self.values) != EMBEDDING_DIM:
            raise ValueError(
                "Embedding must have {} dimensions, got {}".format(
                    EMBEDDING_DIM, len(self.values)
                )
            )

    @classmethod
    def from_list(cls, data):
        # type: (list) -> Embedding
        return cls(values=tuple(data))

    @classmethod
    def from_bytes(cls, raw):
        # type: (bytes) -> Embedding
        if len(raw) != EMBEDDING_DIM * 4:
            raise ValueError(
                "Expected {} bytes, got {}".format(EMBEDDING_DIM * 4, len(raw))
            )
        values = struct.unpack("<{}f".format(EMBEDDING_DIM), raw)
        return cls(values=values)

    def to_bytes(self):
        # type: () -> bytes
        return struct.pack("<{}f".format(EMBEDDING_DIM), *self.values)

    def to_list(self):
        # type: () -> list
        return list(self.values)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _utcnow():
    # type: () -> str
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class User:
    """Registered user / employee."""

    id: Optional[int] = None
    employee_id: str = ""
    full_name: str = ""
    department: str = ""
    role: str = "user"
    is_active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def to_dict(self):
        # type: () -> dict
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "full_name": self.full_name,
            "department": self.department,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row):
        # type: (tuple) -> User
        return cls(
            id=row[0], employee_id=row[1], full_name=row[2],
            department=row[3], role=row[4], is_active=bool(row[5]),
            created_at=row[6], updated_at=row[7],
        )

    def with_updates(self, **kwargs):
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

    def to_dict(self):
        # type: () -> dict
        return {
            "id": self.id,
            "user_id": self.user_id,
            "finger_index": self.finger_index,
            "quality_score": self.quality_score,
            "image_hash": self.image_hash,
            "enrolled_at": self.enrolled_at,
            "is_active": self.is_active,
        }

    @classmethod
    def from_row(cls, row):
        # type: (tuple) -> Fingerprint
        return cls(
            id=row[0], user_id=row[1], finger_index=row[2],
            embedding_enc=row[3], minutiae_enc=row[4],
            quality_score=float(row[5]), image_hash=row[6],
            enrolled_at=row[7], is_active=bool(row[8]),
        )

    @staticmethod
    def compute_image_hash(image_bytes):
        # type: (bytes) -> str
        return hashlib.sha256(image_bytes).hexdigest()


# ---------------------------------------------------------------------------
# Verification Log
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VerificationLog:
    """Audit record for every verification/identification attempt."""

    id: Optional[int] = None
    matched_user_id: Optional[int] = None
    matched_fp_id: Optional[int] = None
    mode: str = "verify"
    score: float = 0.0
    decision: str = "REJECT"
    latency_ms: float = 0.0
    device_id: str = ""
    timestamp: str = field(default_factory=_utcnow)
    probe_quality: float = 0.0

    def to_dict(self):
        # type: () -> dict
        return {
            "id": self.id,
            "matched_user_id": self.matched_user_id,
            "matched_fp_id": self.matched_fp_id,
            "mode": self.mode,
            "score": self.score,
            "decision": self.decision,
            "latency_ms": self.latency_ms,
            "device_id": self.device_id,
            "timestamp": self.timestamp,
            "probe_quality": self.probe_quality,
        }

    @classmethod
    def from_row(cls, row):
        # type: (tuple) -> VerificationLog
        return cls(
            id=row[0], matched_user_id=row[1], matched_fp_id=row[2],
            mode=row[3], score=float(row[4]), decision=row[5],
            latency_ms=float(row[6]), device_id=row[7],
            timestamp=row[8], probe_quality=float(row[9]),
        )
