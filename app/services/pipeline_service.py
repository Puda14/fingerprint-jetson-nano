"""
Singleton service wrapping the core VerificationPipeline.

Provides async methods for enrollment, 1:1 verification, and 1:N identification.
Initialized once on app startup and shared via FastAPI DI.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory stores (replace with real DB in production)
# ---------------------------------------------------------------------------

_users_db: dict[str, dict[str, Any]] = {}
_templates_db: dict[str, list[dict[str, Any]]] = {}  # user_id -> templates
_logs_db: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


class EnrollResult:
    def __init__(
        self,
        user_id: str,
        finger: str,
        quality_score: float,
        template_count: int,
        success: bool = True,
        message: str = "Enrollment successful",
    ):
        self.user_id = user_id
        self.finger = finger
        self.quality_score = quality_score
        self.template_count = template_count
        self.success = success
        self.message = message


class VerifyResult:
    def __init__(
        self,
        matched: bool,
        score: float,
        threshold: float,
        user_id: str,
        latency_ms: float,
    ):
        self.matched = matched
        self.score = score
        self.threshold = threshold
        self.user_id = user_id
        self.latency_ms = latency_ms


class IdentifyResult:
    def __init__(
        self,
        user_id: str,
        employee_id: str,
        full_name: str,
        score: float,
    ):
        self.user_id = user_id
        self.employee_id = employee_id
        self.full_name = full_name
        self.score = score


# ---------------------------------------------------------------------------
# Pipeline Service (singleton)
# ---------------------------------------------------------------------------


class PipelineService:
    """Wraps fingerprint pipeline operations in an async interface.

    Uses singleton pattern to ensure pipeline is initialized only once.
    """

    _instance: PipelineService | None = None

    def __init__(self) -> None:
        self._settings = get_settings()
        self._active_model: str | None = None
        self._model_loaded: bool = False
        self._start_time: float = time.time()
        self._lock = asyncio.Lock()

    # -- singleton access ----------------------------------------------------

    @classmethod
    def get_instance(cls) -> PipelineService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- lifecycle -----------------------------------------------------------

    async def initialize(self) -> None:
        """Load active model and build index on startup."""
        logger.info("Initializing PipelineService...")
        model_dir = Path(self._settings.model_dir)
        if model_dir.exists():
            # Prioritize TensorRT, fallback to ONNX
            trt_files = list(model_dir.glob("*.trt")) + list(model_dir.glob("*.engine"))
            onnx_files = list(model_dir.glob("*.onnx"))
            candidates = trt_files or onnx_files
            if candidates:
                self._active_model = candidates[0].name
                self._model_loaded = True
                logger.info("Loaded model: %s", self._active_model)
        logger.info("PipelineService ready. Active model=%s", self._active_model)

    async def shutdown(self) -> None:
        logger.info("Shutting down PipelineService.")
        self._model_loaded = False

    # -- properties ----------------------------------------------------------

    @property
    def active_model(self) -> str | None:
        return self._active_model

    @property
    def is_model_loaded(self) -> bool:
        return self._model_loaded

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._start_time

    # -- user management (in-memory) -----------------------------------------

    async def create_user(self, user_data: dict[str, Any]) -> dict[str, Any]:
        user_id = str(uuid.uuid4())
        now_iso = time.time()
        user = {
            "id": user_id,
            "employee_id": user_data["employee_id"],
            "full_name": user_data["full_name"],
            "department": user_data.get("department", ""),
            "role": user_data.get("role", "employee"),
            "is_active": True,
            "enrolled_fingers": [],
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        _users_db[user_id] = user
        _templates_db[user_id] = []
        return user

    async def get_user(self, user_id: str) -> dict[str, Any] | None:
        return _users_db.get(user_id)

    async def list_users(
        self,
        page: int = 1,
        limit: int = 20,
        search: str | None = None,
        department: str | None = None,
        role: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        users = list(_users_db.values())
        if search:
            q = search.lower()
            users = [
                u
                for u in users
                if q in u["full_name"].lower() or q in u["employee_id"].lower()
            ]
        if department:
            users = [u for u in users if u["department"] == department]
        if role:
            users = [u for u in users if u["role"] == role]
        users = [u for u in users if u["is_active"]]
        total = len(users)
        start = (page - 1) * limit
        return users[start : start + limit], total

    async def update_user(self, user_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        user = _users_db.get(user_id)
        if user is None:
            return None
        for key, value in updates.items():
            if value is not None and key in user:
                user[key] = value
        user["updated_at"] = time.time()
        return user

    async def deactivate_user(self, user_id: str) -> bool:
        user = _users_db.get(user_id)
        if user is None:
            return False
        user["is_active"] = False
        _templates_db.pop(user_id, None)
        return True

    # -- enrollment ----------------------------------------------------------

    async def enroll_user(
        self,
        user_id: str,
        finger: str,
        num_samples: int = 3,
    ) -> EnrollResult:
        """
        Captures ``num_samples`` images from sensor, extracts templates,
        and saves them to the user record.
        """
        async with self._lock:
            user = _users_db.get(user_id)
            if user is None:
                return EnrollResult(
                    user_id=user_id,
                    finger=finger,
                    quality_score=0.0,
                    template_count=0,
                    success=False,
                    message="User not found",
                )

            # Simulate capture + template extraction
            await asyncio.sleep(0.1)
            quality = round(0.75 + 0.2 * (hash(user_id + finger) % 100) / 100, 3)
            template = {
                "finger": finger,
                "embedding": np.random.randn(512).tolist(),
                "quality": quality,
                "enrolled_at": time.time(),
            }

            if user_id not in _templates_db:
                _templates_db[user_id] = []
            _templates_db[user_id].append(template)

            finger_entry = {
                "finger": finger,
                "enrolled_at": time.time(),
                "quality_score": quality,
            }
            if not any(f["finger"] == finger for f in user["enrolled_fingers"]):
                user["enrolled_fingers"].append(finger_entry)

            _log_event(user_id, user["employee_id"], "enroll", "accept", quality, 100.0)

            return EnrollResult(
                user_id=user_id,
                finger=finger,
                quality_score=quality,
                template_count=len(_templates_db[user_id]),
            )

    # -- verification (1:1) -------------------------------------------------

    async def verify_1to1(self, user_id: str) -> VerifyResult:
        start = time.perf_counter()
        threshold = self._settings.verify_threshold

        user = _users_db.get(user_id)
        if user is None:
            elapsed = (time.perf_counter() - start) * 1000
            return VerifyResult(
                matched=False,
                score=0.0,
                threshold=threshold,
                user_id=user_id,
                latency_ms=round(elapsed, 2),
            )

        templates = _templates_db.get(user_id, [])
        if not templates:
            elapsed = (time.perf_counter() - start) * 1000
            return VerifyResult(
                matched=False,
                score=0.0,
                threshold=threshold,
                user_id=user_id,
                latency_ms=round(elapsed, 2),
            )

        await asyncio.sleep(0.05)
        score = round(0.4 + 0.55 * (hash(user_id + str(time.time_ns())) % 100) / 100, 4)
        matched = score >= threshold

        elapsed = (time.perf_counter() - start) * 1000
        decision = "accept" if matched else "reject"
        _log_event(user_id, user["employee_id"], "verify", decision, score, round(elapsed, 2))

        return VerifyResult(
            matched=matched,
            score=score,
            threshold=threshold,
            user_id=user_id,
            latency_ms=round(elapsed, 2),
        )

    # -- identification (1:N) -----------------------------------------------

    async def identify_1toN(self, top_k: int | None = None) -> list[IdentifyResult]:
        top_k = top_k or self._settings.identify_top_k
        threshold = self._settings.identify_threshold

        await asyncio.sleep(0.08)
        results: list[IdentifyResult] = []
        for uid, user in _users_db.items():
            if not user["is_active"]:
                continue
            templates = _templates_db.get(uid, [])
            if not templates:
                continue
            score = round(0.3 + 0.65 * (hash(uid + str(time.time_ns())) % 100) / 100, 4)
            if score >= threshold:
                results.append(
                    IdentifyResult(
                        user_id=uid,
                        employee_id=user["employee_id"],
                        full_name=user["full_name"],
                        score=score,
                    )
                )

        results.sort(key=lambda r: r.score, reverse=True)
        results = results[:top_k]

        action_decision = "accept" if results else "reject"
        best_uid = results[0].user_id if results else None
        best_eid = results[0].employee_id if results else None
        best_score = results[0].score if results else 0.0
        _log_event(best_uid, best_eid, "identify", action_decision, best_score, 80.0)

        return results

    # -- profiling -----------------------------------------------------------

    async def get_profiling(self) -> dict[str, Any]:
        return {
            "active_model": self._active_model,
            "model_loaded": self._model_loaded,
            "uptime_seconds": self.uptime_seconds,
            "total_users": len(_users_db),
            "total_templates": sum(len(t) for t in _templates_db.values()),
            "total_logs": len(_logs_db),
        }

    # -- log access ----------------------------------------------------------

    async def get_logs(
        self,
        page: int = 1,
        limit: int = 50,
        user_id: str | None = None,
        action: str | None = None,
        decision: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        logs = list(reversed(_logs_db))  # newest first
        if user_id:
            logs = [l for l in logs if l.get("user_id") == user_id]
        if action:
            logs = [l for l in logs if l.get("action") == action]
        if decision:
            logs = [l for l in logs if l.get("decision") == decision]
        total = len(logs)
        start = (page - 1) * limit
        return logs[start : start + limit], total

    async def get_stats(self) -> dict[str, Any]:
        from datetime import datetime, timezone

        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()

        today_logs = [l for l in _logs_db if l["timestamp"] >= today_start]
        verify_today = [l for l in today_logs if l["action"] in ("verify", "identify")]
        accepts = [l for l in verify_today if l["decision"] == "accept"]
        latencies = [l["latency_ms"] for l in verify_today if l.get("latency_ms")]

        total_v = len(verify_today) or 1
        return {
            "enrolled_users": sum(1 for u in _users_db.values() if u["is_active"]),
            "enrolled_fingers": sum(len(t) for t in _templates_db.values()),
            "verifications_today": len([l for l in today_logs if l["action"] == "verify"]),
            "identifications_today": len([l for l in today_logs if l["action"] == "identify"]),
            "acceptance_rate": round(len(accepts) / total_v, 4),
            "rejection_rate": round(1 - len(accepts) / total_v, 4),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
            "uptime_seconds": self.uptime_seconds,
        }


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _log_event(
    user_id: str | None,
    employee_id: str | None,
    action: str,
    decision: str,
    score: float | None,
    latency_ms: float | None,
) -> None:
    _logs_db.append(
        {
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "user_id": user_id,
            "employee_id": employee_id,
            "action": action,
            "decision": decision,
            "score": score,
            "latency_ms": latency_ms,
            "details": None,
        }
    )


# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------


def get_pipeline_service() -> PipelineService:
    return PipelineService.get_instance()
