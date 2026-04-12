"""
Singleton service bridging the real VerificationPipeline, sensor, and database.

Provides async methods for enrollment, 1:1 verification, and 1:N identification
using the actual AI pipeline (preprocessing → minutiae → graph → inference → FAISS).
"""


from typing import List, Dict, Tuple, Set, Optional, Any, Union, Coroutine, Callable, Generator, Iterable, AsyncIterator, TypeVar, Type, Awaitable, Sequence, Mapping
import asyncio
import json
import logging
import threading
import time
from pathlib import Path

import numpy as np

from app.core.config import get_settings
from app.database.crypto import CryptoService
from app.database.database import DatabaseManager
from app.database.models import (
    EMBEDDING_DIM,
    Fingerprint,
    User,
    VerificationDecision,
    VerificationLog,
    VerificationMode,
)
from app.database.repository import (
    FingerprintRepository,
    UserRepository,
    VerificationLogRepository,
)
from app.pipeline.pipeline import VerificationPipeline

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


class EnrollResult:
    def __init__(
        self,
        user_id: int,
        finger: int,
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
        user_id: Optional[int],
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
        user_id: int,
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
    """Bridges VerificationPipeline, sensor, and database in an async interface.

    Uses singleton pattern to ensure resources are initialized only once.
    """

    _instance: Optional["PipelineService"] = None

    def __init__(self) -> None:
        self._settings = get_settings()
        self._pipeline: Optional[VerificationPipeline] = None
        self._active_model: Optional[str] = None
        self._model_loaded: bool = False
        self._start_time: float = time.time()
        self._lock = asyncio.Lock()

        # DB components (initialized in initialize())
        self._db: Optional[DatabaseManager] = None
        self._user_repo: Optional[UserRepository] = None
        self._fp_repo: Optional[FingerprintRepository] = None
        self._log_repo: Optional[VerificationLogRepository] = None
        self._crypto: Optional[CryptoService] = None
        self._sync_lock = threading.Lock()
        self._sync_state_file = Path(self._settings.data_dir) / ".enrollment_sync_state.json"

    # -- singleton access ----------------------------------------------------

    @classmethod
    def get_instance(cls) -> "PipelineService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- lifecycle -----------------------------------------------------------

    async def initialize(self) -> None:
        """Load model, init DB, build FAISS index from saved embeddings."""
        logger.info("Initializing PipelineService...")

        # --- Database ---
        try:
            db_path = str(Path(self._settings.data_dir) / "fingerprint.db")
            self._db = DatabaseManager(db_path)
            self._user_repo = UserRepository(self._db)
            self._fp_repo = FingerprintRepository(self._db)
            self._log_repo = VerificationLogRepository(self._db)
            logger.info("Database repositories ready.")
        except Exception as exc:
            logger.error("Database init failed: %s", exc)

        # --- Crypto ---
        try:
            self._crypto = CryptoService()
        except Exception as exc:
            logger.warning("CryptoService init failed: %s (embeddings won't be encrypted)", exc)

        # --- Pipeline ---
        pipeline_cfg = self._settings.as_pipeline_config()
        self._pipeline = VerificationPipeline(pipeline_cfg)

        # Determine which model loaded
        model_path = self._settings.model_path
        if model_path and Path(model_path).exists():
            self._active_model = Path(model_path).name
            self._model_loaded = True
            logger.info("Model loaded: %s", self._active_model)
        else:
            # Fallback: scan model_dir
            model_dir = Path(self._settings.model_dir)
            if model_dir.exists():
                trt_files = list(model_dir.glob("*.trt")) + list(model_dir.glob("*.engine"))
                onnx_files = list(model_dir.glob("*.onnx"))
                candidates = trt_files or onnx_files
                if candidates:
                    self._active_model = candidates[0].name
                    self._model_loaded = True
                    logger.info("Model loaded (scanned): %s", self._active_model)

        # --- Build FAISS index from DB ---
        await self._rebuild_faiss_index()

        logger.info("PipelineService ready. Active model=%s", self._active_model)

    async def _rebuild_faiss_index(self) -> None:
        """Load all active fingerprint embeddings from DB and build FAISS gallery."""
        if self._fp_repo is None or self._pipeline is None:
            return

        try:
            rows = self._fp_repo.get_active_embeddings()
            if not rows:
                logger.info("No fingerprints in DB — FAISS index is empty.")
                return

            embeddings = []
            ids = []
            for fp_id, user_id, embedding_enc in rows:
                if embedding_enc is None:
                    continue
                try:
                    if self._crypto is not None:
                        vec = self._crypto.decrypt_embedding(embedding_enc)
                    else:
                        import struct
                        vec = list(struct.unpack("<{}f".format(EMBEDDING_DIM), embedding_enc))
                    embeddings.append(vec)
                    ids.append(fp_id)
                except Exception as exc:
                    logger.warning("Failed to decrypt embedding fp_id=%d: %s", fp_id, exc)

            if embeddings:
                emb_array = np.array(embeddings, dtype=np.float32)
                id_array = np.array(ids, dtype=np.int64)
                self._pipeline.build_gallery(emb_array, id_array)
                logger.info("FAISS index built with %d embeddings.", len(embeddings))
            else:
                logger.info("No valid embeddings found — FAISS index is empty.")

        except Exception as exc:
            logger.error("Failed to build FAISS index: %s", exc)

    async def shutdown(self) -> None:
        logger.info("Shutting down PipelineService.")
        self._model_loaded = False
        # Save FAISS index
        if self._pipeline is not None:
            try:
                gallery_path = str(Path(self._settings.data_dir) / "gallery.faiss")
                self._pipeline.save_gallery(gallery_path)
                logger.info("FAISS gallery saved.")
            except Exception as exc:
                logger.warning("Failed to save FAISS gallery: %s", exc)

    # -- properties ----------------------------------------------------------

    @property
    def active_model(self) -> Optional[str]:
        return self._active_model

    @property
    def is_model_loaded(self) -> bool:
        return self._model_loaded

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._start_time

    # -- user management (SQLite) --------------------------------------------

    async def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        if self._user_repo is None:
            raise RuntimeError("Database not initialized")
        user = User(
            employee_id=user_data["employee_id"],
            full_name=user_data["full_name"],
            department=user_data.get("department", ""),
            role=user_data.get("role", "user"),
        )
        loop = asyncio.get_running_loop()
        created = await loop.run_in_executor(None, self._user_repo.create, user)
        return created.to_dict()

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        if self._user_repo is None:
            return None
        loop = asyncio.get_running_loop()
        user = await loop.run_in_executor(None, self._user_repo.get_by_id, user_id)
        return user.to_dict() if user else None

    async def list_users(
        self,
        page: int = 1,
        limit: int = 20,
        search: Optional[str] = None,
        department: Optional[str] = None,
        role: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        if self._user_repo is None:
            return [], 0

        loop = asyncio.get_running_loop()

        if search:
            all_users = await loop.run_in_executor(
                None, self._user_repo.search, search, True
            )
        else:
            all_users = await loop.run_in_executor(
                None, self._user_repo.get_all, True
            )

        # Apply additional filters
        if department:
            all_users = [u for u in all_users if u.department == department]
        if role:
            all_users = [u for u in all_users if u.role == role]

        total = len(all_users)
        start = (page - 1) * limit
        page_users = all_users[start: start + limit]

        # Enrich with fingerprint count
        result = []
        for u in page_users:
            d = u.to_dict()
            if self._fp_repo is not None:
                count = await loop.run_in_executor(
                    None, self._fp_repo.count_by_user, u.id, True
                )
                d["fingerprint_count"] = count
            result.append(d)

        return result, total

    async def update_user(
        self, user_id: int, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        if self._user_repo is None:
            return None
        loop = asyncio.get_running_loop()
        user = await loop.run_in_executor(None, self._user_repo.get_by_id, user_id)
        if user is None:
            return None
        updated = user.with_updates(**{k: v for k, v in updates.items() if v is not None})
        await loop.run_in_executor(None, self._user_repo.update, updated)
        return updated.to_dict()

    async def deactivate_user(self, user_id: int) -> bool:
        if self._user_repo is None:
            return False
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._user_repo.deactivate, user_id)
        # Also deactivate fingerprints and rebuild FAISS
        if self._fp_repo is not None:
            await loop.run_in_executor(None, self._fp_repo.deactivate_by_user, user_id)
        await self._rebuild_faiss_index()
        return True

    # -- enrollment ----------------------------------------------------------

    async def enroll_user(
        self,
        user_id: int,
        finger: int,
        num_samples: int = 3,
        image_bytes: Optional[bytes] = None,
    ) -> EnrollResult:
        """Enroll a fingerprint using sensor capture or provided image bytes.

        Args:
            user_id: Database user ID.
            finger: Finger index (0-9).
            num_samples: Number of samples to capture (only first used for now).
            image_bytes: Optional pre-captured image bytes (for mock/remote use).
        """
        async with self._lock:
            # Validate user exists
            user = None
            if self._user_repo is not None:
                loop = asyncio.get_running_loop()
                user_obj = await loop.run_in_executor(
                    None, self._user_repo.get_by_id, user_id
                )
                if user_obj is None:
                    return EnrollResult(
                        user_id=user_id, finger=finger,
                        quality_score=0.0, template_count=0,
                        success=False, message="User not found",
                    )
                user = user_obj

            # Capture image from sensor or use provided bytes
            if image_bytes is None:
                from app.services.sensor_service import SensorService
                sensor = SensorService.get_instance()
                capture = await sensor.capture_image()
                if not capture.success:
                    return EnrollResult(
                        user_id=user_id, finger=finger,
                        quality_score=0.0, template_count=0,
                        success=False, message="Sensor capture failed: {}".format(capture.error),
                    )
                image_bytes = capture.image_data
                quality = capture.quality_score
            else:
                quality = 50.0  # default quality for pre-captured images

            # Run pipeline to extract embedding
            if self._pipeline is None:
                return EnrollResult(
                    user_id=user_id, finger=finger,
                    quality_score=quality, template_count=0,
                    success=False, message="Pipeline not initialized",
                )

            try:
                embedding, profiling = await self._pipeline.extract_embedding(image_bytes)
            except Exception as exc:
                logger.error("Pipeline inference failed: %s", exc)
                return EnrollResult(
                    user_id=user_id, finger=finger,
                    quality_score=quality, template_count=0,
                    success=False, message="Inference failed: {}".format(exc),
                )

            # Check if embedding is all-zero (no minutiae detected)
            if np.allclose(embedding, 0.0):
                return EnrollResult(
                    user_id=user_id, finger=finger,
                    quality_score=quality, template_count=0,
                    success=False, message="No minutiae detected in image",
                )

            # Encrypt and save to DB
            embedding_list = embedding.tolist()
            image_hash = Fingerprint.compute_image_hash(image_bytes)

            embedding_enc = None
            if self._crypto is not None:
                embedding_enc = self._crypto.encrypt_embedding(embedding_list)
            else:
                import struct
                embedding_enc = struct.pack("<{}f".format(EMBEDDING_DIM), *embedding_list)

            fp_record = Fingerprint(
                user_id=user_id,
                finger_index=finger,
                embedding_enc=embedding_enc,
                quality_score=quality,
                image_hash=image_hash,
            )

            if self._fp_repo is not None:
                loop = asyncio.get_running_loop()
                saved_fp = await loop.run_in_executor(None, self._fp_repo.create, fp_record)
                fp_id = saved_fp.id

                # Add to FAISS index
                self._pipeline.enroll(embedding, fp_id)

                # Get total fingerprint count for this user
                count = await loop.run_in_executor(
                    None, self._fp_repo.count_by_user, user_id, True
                )
            else:
                count = 1

            logger.info(
                "Enrolled fingerprint for user %d, finger %d (quality=%.1f)",
                user_id, finger, quality,
            )

            # --- Upstream: broadcast enrollment to orchestrator via MQTT ---
            try:
                self._publish_enrollment_event(
                    user_obj=user,
                    fp_id=fp_id if self._fp_repo else 0,
                    finger_index=finger,
                    embedding_list=embedding_list,
                    quality_score=quality,
                    image_bytes=image_bytes,
                )
            except Exception as exc:
                logger.warning("Failed to publish enrollment event: %s", exc)

            return EnrollResult(
                user_id=user_id,
                finger=finger,
                quality_score=quality,
                template_count=count,
            )

    # -- verification (1:1) -------------------------------------------------

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Numerically stable cosine similarity for verification."""
        na = float(np.linalg.norm(a))
        nb = float(np.linalg.norm(b))
        if na <= 1e-8 or nb <= 1e-8:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    async def verify_1to1(
        self,
        user_id: int,
        image_bytes: Optional[bytes] = None,
    ) -> VerifyResult:
        """1:1 verification against a specific user's stored embeddings."""
        start = time.perf_counter()
        threshold = self._settings.verify_threshold
        margin = getattr(self._settings, "verify_margin", 0.0)

        # Capture image
        if image_bytes is None:
            from app.services.sensor_service import SensorService
            sensor = SensorService.get_instance()
            capture = await sensor.capture_image()
            if not capture.success:
                elapsed = (time.perf_counter() - start) * 1000
                return VerifyResult(
                    matched=False, score=0.0, threshold=threshold,
                    user_id=user_id, latency_ms=round(elapsed, 2),
                )
            image_bytes = capture.image_data
            probe_quality = capture.quality_score
        else:
            probe_quality = 50.0

        # Extract probe embedding
        if self._pipeline is None:
            elapsed = (time.perf_counter() - start) * 1000
            return VerifyResult(
                matched=False, score=0.0, threshold=threshold,
                user_id=user_id, latency_ms=round(elapsed, 2),
            )

        try:
            probe_emb, _ = await self._pipeline.extract_embedding(image_bytes)
        except Exception as exc:
            logger.error("Verify inference failed: %s", exc)
            elapsed = (time.perf_counter() - start) * 1000
            return VerifyResult(
                matched=False, score=0.0, threshold=threshold,
                user_id=user_id, latency_ms=round(elapsed, 2),
            )

        # Load user's stored embeddings from DB
        if self._fp_repo is None:
            elapsed = (time.perf_counter() - start) * 1000
            return VerifyResult(
                matched=False, score=0.0, threshold=threshold,
                user_id=user_id, latency_ms=round(elapsed, 2),
            )

        loop = asyncio.get_running_loop()
        fps = await loop.run_in_executor(
            None, self._fp_repo.get_by_user_id, user_id, True
        )
        if not fps:
            elapsed = (time.perf_counter() - start) * 1000
            return VerifyResult(
                matched=False, score=0.0, threshold=threshold,
                user_id=user_id, latency_ms=round(elapsed, 2),
            )

        # Compare probe with selected user's embeddings, take best score.
        best_score = 0.0
        matched_fp_id = None
        for fp in fps:
            if fp.embedding_enc is None:
                continue
            try:
                if self._crypto is not None:
                    gallery_vec = self._crypto.decrypt_embedding(fp.embedding_enc)
                else:
                    import struct
                    gallery_vec = list(struct.unpack(
                        "<{}f".format(EMBEDDING_DIM), fp.embedding_enc
                    ))
                gallery_emb = np.array(gallery_vec, dtype=np.float32)
                score = self._cosine_similarity(probe_emb, gallery_emb)
                if score > best_score:
                    best_score = score
                    matched_fp_id = fp.id
            except Exception as exc:
                logger.warning("Failed to compare with fp_id=%s: %s", fp.id, exc)

        # Anti false-positive gate: target score must be better than non-targets
        # by at least verify_margin. This is useful when many users have high
        # baseline similarity due model/domain mismatch.
        best_non_target = -1.0
        try:
            all_active = await loop.run_in_executor(None, self._fp_repo.get_active_embeddings)
            for fp_id, fp_user_id, embedding_enc in all_active:
                if int(fp_user_id) == int(user_id):
                    continue
                if embedding_enc is None:
                    continue
                if self._crypto is not None:
                    other_vec = self._crypto.decrypt_embedding(embedding_enc)
                else:
                    import struct
                    other_vec = list(struct.unpack("<{}f".format(EMBEDDING_DIM), embedding_enc))
                other_emb = np.array(other_vec, dtype=np.float32)
                s = self._cosine_similarity(probe_emb, other_emb)
                if s > best_non_target:
                    best_non_target = s
        except Exception as exc:
            logger.warning("Failed to compute non-target scores: %s", exc)

        matched = best_score >= threshold
        if best_non_target >= 0 and margin > 0:
            matched = matched and (best_score - best_non_target >= margin)
        elapsed = (time.perf_counter() - start) * 1000

        # Log result
        decision = VerificationDecision.ACCEPT if matched else VerificationDecision.REJECT
        if self._log_repo is not None:
            log = VerificationLog(
                matched_user_id=user_id if matched else None,
                matched_fp_id=matched_fp_id if matched else None,
                mode=VerificationMode.VERIFY.value,
                score=best_score,
                decision=decision.value,
                latency_ms=round(elapsed, 2),
                device_id=self._settings.device_id,
                probe_quality=probe_quality,
            )
            await loop.run_in_executor(None, self._log_repo.create, log)

        logger.info(
            "Verify 1:1: user=%d score=%.4f threshold=%.4f non_target=%.4f margin=%.4f matched=%s (%.1fms)",
            user_id, best_score, threshold, best_non_target, margin, matched, elapsed,
        )

        return VerifyResult(
            matched=matched,
            score=best_score,
            threshold=threshold,
            user_id=user_id,
            latency_ms=round(elapsed, 2),
        )

    # -- identification (1:N) -----------------------------------------------

    async def identify_1toN(
        self,
        top_k: Optional[int] = None,
        image_bytes: Optional[bytes] = None,
    ) -> List[IdentifyResult]:
        """1:N identification — search FAISS gallery for the best match."""
        top_k = top_k or self._settings.identify_top_k
        threshold = self._settings.identify_threshold
        start = time.perf_counter()

        # Capture image
        if image_bytes is None:
            from app.services.sensor_service import SensorService
            sensor = SensorService.get_instance()
            capture = await sensor.capture_image()
            if not capture.success:
                return []
            image_bytes = capture.image_data
            probe_quality = capture.quality_score
        else:
            probe_quality = 50.0

        if self._pipeline is None:
            return []

        # Run identify through pipeline's FAISS search
        try:
            matches = await self._pipeline.identify(
                image_bytes, top_k=top_k, threshold=threshold
            )
        except Exception as exc:
            logger.error("Identify inference failed: %s", exc)
            return []

        elapsed = (time.perf_counter() - start) * 1000

        # Map fp_id → user info from DB
        results: List[IdentifyResult] = []
        if self._fp_repo is not None and self._user_repo is not None:
            loop = asyncio.get_running_loop()
            for fp_id, score in matches:
                fp = await loop.run_in_executor(None, self._fp_repo.get_by_id, fp_id)
                if fp is None:
                    continue
                user = await loop.run_in_executor(
                    None, self._user_repo.get_by_id, fp.user_id
                )
                if user is None:
                    continue
                results.append(IdentifyResult(
                    user_id=user.id,
                    employee_id=user.employee_id,
                    full_name=user.full_name,
                    score=score,
                ))

        # Log best match
        if self._log_repo is not None:
            best = results[0] if results else None
            decision = VerificationDecision.ACCEPT if best else VerificationDecision.REJECT
            loop = asyncio.get_running_loop()
            log = VerificationLog(
                matched_user_id=best.user_id if best else None,
                mode=VerificationMode.IDENTIFY.value,
                score=best.score if best else 0.0,
                decision=decision.value,
                latency_ms=round(elapsed, 2),
                device_id=self._settings.device_id,
                probe_quality=probe_quality,
            )
            await loop.run_in_executor(None, self._log_repo.create, log)

        logger.info(
            "Identify 1:N: %d matches above %.2f (%.1fms)",
            len(results), threshold, elapsed,
        )
        return results

    # -- profiling -----------------------------------------------------------

    async def get_profiling(self) -> Dict[str, Any]:
        user_count = 0
        fp_count = 0
        log_count = 0
        if self._user_repo is not None:
            loop = asyncio.get_running_loop()
            user_count = await loop.run_in_executor(None, self._user_repo.count, True)
        if self._fp_repo is not None:
            loop = asyncio.get_running_loop()
            fp_count = await loop.run_in_executor(None, self._fp_repo.count, True)
        if self._log_repo is not None:
            loop = asyncio.get_running_loop()
            log_count = await loop.run_in_executor(None, self._log_repo.count)

        pipeline_profiling = {}
        if self._pipeline is not None:
            pipeline_profiling = self._pipeline.get_profiling()

        return {
            "active_model": self._active_model,
            "model_loaded": self._model_loaded,
            "uptime_seconds": self.uptime_seconds,
            "total_users": user_count,
            "total_fingerprints": fp_count,
            "total_logs": log_count,
            "pipeline_stages": pipeline_profiling,
        }

    # -- log / stats access --------------------------------------------------

    async def get_logs(
        self,
        page: int = 1,
        limit: int = 50,
        user_id: Optional[int] = None,
        action: Optional[str] = None,
        decision: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        if self._log_repo is None:
            return [], 0

        loop = asyncio.get_running_loop()
        if user_id is not None:
            logs = await loop.run_in_executor(
                None, self._log_repo.get_by_user, user_id, limit * page
            )
        else:
            logs = await loop.run_in_executor(
                None, self._log_repo.get_recent, limit * page
            )

        # Apply filters
        log_dicts = [l.to_dict() for l in logs]
        if action:
            log_dicts = [l for l in log_dicts if l.get("mode") == action]
        if decision:
            log_dicts = [l for l in log_dicts if l.get("decision") == decision]

        total = len(log_dicts)
        start_idx = (page - 1) * limit
        return log_dicts[start_idx: start_idx + limit], total

    async def get_stats(self) -> Dict[str, Any]:
        info = await self.get_profiling()
        return {
            "enrolled_users": info["total_users"],
            "enrolled_fingerprints": info["total_fingerprints"],
            "total_logs": info["total_logs"],
            "active_model": info["active_model"],
            "model_loaded": info["model_loaded"],
            "uptime_seconds": info["uptime_seconds"],
        }


    # -- upstream MQTT publish -----------------------------------------------

    def _load_sync_state(self) -> Dict[str, Any]:
        if not self._sync_state_file.exists():
            return {"synced_fp_ids": [], "pending_events": []}
        try:
            data = json.loads(self._sync_state_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"synced_fp_ids": [], "pending_events": []}
            data.setdefault("synced_fp_ids", [])
            data.setdefault("pending_events", [])
            return data
        except Exception as exc:
            logger.warning("Failed to read enrollment sync state: %s", exc)
            return {"synced_fp_ids": [], "pending_events": []}

    def _save_sync_state(self, state: Dict[str, Any]) -> None:
        try:
            self._sync_state_file.parent.mkdir(parents=True, exist_ok=True)
            self._sync_state_file.write_text(
                json.dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to save enrollment sync state: %s", exc)

    @staticmethod
    def _payload_fp_id(payload: Dict[str, Any]) -> Optional[int]:
        try:
            fp = payload.get("fingerprint", {})
            fp_id = fp.get("fp_id")
            return int(fp_id) if fp_id is not None else None
        except Exception:
            return None

    def _mark_fp_synced(self, fp_id: int) -> None:
        with self._sync_lock:
            state = self._load_sync_state()
            synced = {int(x) for x in state.get("synced_fp_ids", [])}
            synced.add(int(fp_id))
            # Remove pending event for this fp_id if present
            pending = []
            for ev in state.get("pending_events", []):
                if self._payload_fp_id(ev) != int(fp_id):
                    pending.append(ev)
            state["synced_fp_ids"] = sorted(synced)
            state["pending_events"] = pending
            self._save_sync_state(state)

    def _queue_pending_event(self, payload: Dict[str, Any]) -> None:
        fp_id = self._payload_fp_id(payload)
        with self._sync_lock:
            state = self._load_sync_state()
            pending = state.get("pending_events", [])

            # De-duplicate by fingerprint id
            replaced = False
            if fp_id is not None:
                for i, ev in enumerate(pending):
                    if self._payload_fp_id(ev) == fp_id:
                        pending[i] = payload
                        replaced = True
                        break
            if not replaced:
                pending.append(payload)

            state["pending_events"] = pending
            self._save_sync_state(state)

    def _get_mqtt_client_if_connected(self):
        try:
            from app.mqtt.client import get_mqtt_client

            mqtt_client = get_mqtt_client()
        except Exception:
            return None
        if not mqtt_client.is_connected:
            return None
        return mqtt_client

    def _build_enrollment_payload(
        self,
        user_obj: Any,
        fp_id: int,
        finger_index: int,
        embedding_list: List[float],
        quality_score: float,
        image_bytes: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        import base64

        user_dict = user_obj.to_dict() if hasattr(user_obj, "to_dict") else {}
        payload = {
            "event": "enrollment",
            "worker_id": self._settings.device_id,
            "user": {
                "id": user_dict.get("id"),
                "employee_id": user_dict.get("employee_id", ""),
                "full_name": user_dict.get("full_name", ""),
                "department": user_dict.get("department", ""),
                "role": user_dict.get("role", "user"),
            },
            "fingerprint": {
                "fp_id": fp_id,
                "finger_index": finger_index,
                "embedding": embedding_list,
                "quality_score": quality_score,
            },
            "model": {
                "name": self._active_model or "local",
                "embedding_dim": len(embedding_list),
            },
        }
        if image_bytes:
            payload["fingerprint"]["image_base64"] = base64.b64encode(image_bytes).decode(
                "ascii"
            )
            payload["fingerprint"]["image_width"] = int(self._settings.image_width)
            payload["fingerprint"]["image_height"] = int(self._settings.image_height)
        return payload

    def sync_offline_enrollments(self) -> int:
        """Queue unsynced local enrollments and flush them if MQTT is connected.

        Returns:
            Number of enrollment events published in this run.
        """
        if self._fp_repo is None or self._user_repo is None:
            return 0

        # Step 1: discover local unsynced fingerprints and queue them.
        with self._sync_lock:
            state = self._load_sync_state()
            synced = {int(x) for x in state.get("synced_fp_ids", [])}
            pending = state.get("pending_events", [])
            pending_ids = {
                self._payload_fp_id(ev)
                for ev in pending
                if self._payload_fp_id(ev) is not None
            }

            for fp_id, user_id, embedding_enc in self._fp_repo.get_active_embeddings():
                if fp_id in synced or fp_id in pending_ids:
                    continue

                fp_obj = self._fp_repo.get_by_id(fp_id)
                user_obj = self._user_repo.get_by_id(user_id)
                if fp_obj is None or user_obj is None or embedding_enc is None:
                    continue

                try:
                    if self._crypto is not None:
                        embedding_list = self._crypto.decrypt_embedding(embedding_enc)
                    else:
                        import struct

                        embedding_list = list(
                            struct.unpack("<{}f".format(EMBEDDING_DIM), embedding_enc)
                        )
                except Exception as exc:
                    logger.warning("Skip sync fp_id=%d: decode embedding failed (%s)", fp_id, exc)
                    continue

                payload = self._build_enrollment_payload(
                    user_obj=user_obj,
                    fp_id=fp_id,
                    finger_index=fp_obj.finger_index,
                    embedding_list=embedding_list,
                    quality_score=fp_obj.quality_score,
                    image_bytes=None,
                )
                pending.append(payload)

            state["pending_events"] = pending
            self._save_sync_state(state)

        # Step 2: flush pending queue if online.
        mqtt_client = self._get_mqtt_client_if_connected()
        if mqtt_client is None:
            return 0

        sent = 0
        with self._sync_lock:
            state = self._load_sync_state()
            pending = state.get("pending_events", [])
            still_pending: List[Dict[str, Any]] = []
            synced = {int(x) for x in state.get("synced_fp_ids", [])}

            for payload in pending:
                topic = "worker/{}/enrolled".format(self._settings.device_id)
                ok = mqtt_client.publish(topic, json.dumps(payload), qos=1)
                if ok:
                    fp_id = self._payload_fp_id(payload)
                    if fp_id is not None:
                        synced.add(fp_id)
                    sent += 1
                else:
                    still_pending.append(payload)

            state["synced_fp_ids"] = sorted(synced)
            state["pending_events"] = still_pending
            self._save_sync_state(state)

        if sent > 0:
            logger.info("Synced %d offline enrollment event(s) to orchestrator.", sent)
        return sent

    def _publish_enrollment_event(
        self,
        user_obj: Any,
        fp_id: int,
        finger_index: int,
        embedding_list: List[float],
        quality_score: float,
        image_bytes: Optional[bytes] = None,
    ) -> None:
        """Publish a new enrollment event to orchestrator via MQTT.

        Topic: worker/{device_id}/enrolled
        The orchestrator is responsible for broadcasting this to other workers.
        """
        payload = self._build_enrollment_payload(
            user_obj=user_obj,
            fp_id=fp_id,
            finger_index=finger_index,
            embedding_list=embedding_list,
            quality_score=quality_score,
            image_bytes=image_bytes,
        )

        mqtt_client = self._get_mqtt_client_if_connected()
        user_dict = user_obj.to_dict() if hasattr(user_obj, "to_dict") else {}
        if mqtt_client is None:
            self._queue_pending_event(payload)
            logger.info(
                "MQTT offline; queued enrollment event for later sync (fp_id=%d)", fp_id
            )
            return

        topic = "worker/{}/enrolled".format(self._settings.device_id)
        ok = mqtt_client.publish(topic, json.dumps(payload), qos=1)
        if ok:
            self._mark_fp_synced(fp_id)
            logger.info(
                "📤 Enrollment event published for user %s (fp_id=%d)",
                user_dict.get("full_name", "?"),
                fp_id,
            )
        else:
            self._queue_pending_event(payload)
            logger.warning(
                "Enrollment publish failed; queued for retry (fp_id=%d)", fp_id
            )

    # -- downstream: receive sync from orchestrator --------------------------

    async def sync_remote_enrollment(self, data: Dict[str, Any]) -> bool:
        """Handle a sync payload from orchestrator (another worker enrolled).

        Writes user + fingerprint to local SQLite and adds embedding to FAISS.
        Does NOT re-run inference — the embedding is received pre-computed.

        Args:
            data: dict with keys 'user' and 'fingerprint', matching the
                  upstream enrollment event payload format.

        Returns:
            True if sync succeeded, False otherwise.
        """
        user_data = data.get("user", {})
        fp_data = data.get("fingerprint", {})

        remote_user_id = user_data.get("id")
        employee_id = user_data.get("employee_id", "")
        full_name = user_data.get("full_name", "")
        department = user_data.get("department", "")
        role = user_data.get("role", "user")

        embedding_list = fp_data.get("embedding", [])
        finger_index = fp_data.get("finger_index", 0)
        quality_score = fp_data.get("quality_score", 0.0)

        if not embedding_list or not employee_id:
            logger.warning("Sync payload missing embedding or employee_id, skipping.")
            return False

        loop = asyncio.get_running_loop()

        try:
            # --- Upsert user ---
            if self._user_repo is not None:
                existing = await loop.run_in_executor(
                    None, self._user_repo.get_by_employee_id, employee_id
                )
                if existing is None:
                    user = User(
                        employee_id=employee_id,
                        full_name=full_name,
                        department=department,
                        role=role,
                    )
                    existing = await loop.run_in_executor(
                        None, self._user_repo.create, user
                    )
                    logger.info("Sync: created local user '%s' (id=%d)",
                                full_name, existing.id)
                local_user_id = existing.id
            else:
                logger.warning("Sync: no user repo, cannot persist.")
                return False

            # --- Encrypt and save fingerprint ---
            embedding_enc = None
            if self._crypto is not None:
                embedding_enc = self._crypto.encrypt_embedding(embedding_list)
            else:
                import struct
                embedding_enc = struct.pack(
                    "<{}f".format(EMBEDDING_DIM), *embedding_list
                )

            fp_record = Fingerprint(
                user_id=local_user_id,
                finger_index=finger_index,
                embedding_enc=embedding_enc,
                quality_score=quality_score,
                image_hash="synced",
            )

            if self._fp_repo is not None:
                saved = await loop.run_in_executor(
                    None, self._fp_repo.create, fp_record
                )
                fp_id = saved.id

                # --- Add to FAISS immediately ---
                emb_array = np.array(embedding_list, dtype=np.float32)
                if self._pipeline is not None:
                    self._pipeline.enroll(emb_array, fp_id)

                logger.info(
                    "Sync: enrolled fp_id=%d for user '%s' (finger=%d)",
                    fp_id, full_name, finger_index,
                )
                return True
            else:
                logger.warning("Sync: no fingerprint repo, cannot persist.")
                return False

        except Exception as exc:
            logger.error("Sync enrollment failed: %s", exc)
            return False


# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------


async def get_pipeline_service() -> "PipelineService":
    return PipelineService.get_instance()
