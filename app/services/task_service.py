"""
Task processing service — handles embed/register/verify tasks from orchestrator.

Bridges MQTT task dispatch to existing PipelineService and SensorService.
Results are published back to orchestrator via MQTT.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from typing import List, Optional, Any, Optional

import requests

logger = logging.getLogger(__name__)

# ── Cached inference engine (singleton) ──────────────────────────────────────
_cached_engine = None
_cached_model_path = None


def _get_cached_engine(onnx_path: str) -> Any:
    """Get or create cached inference engine to avoid PyCUDA context crash."""
    global _cached_engine, _cached_model_path
    if _cached_engine is None or _cached_model_path != onnx_path:
        from app.services.inference_service import create_inference_engine
        _cached_engine = create_inference_engine(onnx_path)
        _cached_engine.load()
        _cached_model_path = onnx_path
        logger.info("Loaded inference engine: %s", onnx_path)
    return _cached_engine


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from a synchronous context (background thread)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=60)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


class TaskService:
    """Handles task processing for MQTT-dispatched work.

    Supports three task types:
    - embed: Download image from URL → run inference → publish embedding
    - register: Capture from sensor → run pipeline → enroll user → publish result
    - verify: Capture from sensor → run pipeline → verify/identify → publish result
    """

    def __init__(self, mqtt_client: Any) -> None:
        self._mqtt_client = mqtt_client

    # ── EMBED task ──────────────────────────────────────────────────────────

    def process_embed(self, task_data: dict) -> None:
        """Process embed task: download image → inference → publish embedding.

        Args:
            task_data: dict with task_id, image_url, model_name
        """
        task_id = task_data.get("task_id", "")
        image_url = task_data.get("image_url", "")
        model_name = task_data.get("model_name", "default")
        extra = task_data.get("extra", {})

        logger.info("Processing EMBED task %s", task_id)
        t0 = time.time()

        try:
            # 1. Download image
            logger.info("Downloading image from URL...")
            image_bytes = self._download_image(image_url)
            logger.info("Downloaded %d bytes", len(image_bytes))

            # 2. Run inference
            from app.services.inference_service import (
                create_inference_engine,
                preprocess_from_bytes,
                normalize_embedding,
            )

            engine = _get_cached_engine(self._find_model(model_name))
            input_data = preprocess_from_bytes(image_bytes)
            raw_output = engine.infer(input_data)
            embedding = normalize_embedding(raw_output)

            elapsed_ms = (time.time() - t0) * 1000

            # 3. Publish result
            result = {
                "task_id": task_id,
                "worker_id": self._mqtt_client.worker_id,
                "status": "completed",
                "result": {
                    "vector": embedding.tolist(),
                    "vector_dim": len(embedding),
                    "model_name": model_name,
                    "processing_time_ms": round(elapsed_ms, 2),
                },
                "processing_time_ms": round(elapsed_ms, 2),
            }
            self._publish_result(task_id, result)
            logger.info(
                "EMBED task %s completed: %dD vector in %.1fms",
                task_id, len(embedding), elapsed_ms,
            )

        except Exception as exc:
            elapsed_ms = (time.time() - t0) * 1000
            logger.error("EMBED task %s failed: %s", task_id, exc)
            self._publish_error(task_id, str(exc), elapsed_ms)

    # ── REGISTER task ───────────────────────────────────────────────────────

    def process_register(self, task_data: dict) -> None:
        """Process register task: capture/decode image → enroll → publish result.

        Args:
            task_data: dict with task_id, user_id, employee_id, full_name,
                       department, finger_type, num_samples, image_base64
        """
        task_id = task_data.get("task_id", "")
        user_id = task_data.get("user_id", "")
        employee_id = task_data.get("employee_id", "")
        full_name = task_data.get("full_name", "")
        department = task_data.get("department", "")
        finger_type = task_data.get("finger_type", "right_index")
        num_samples = task_data.get("num_samples", 3)
        image_base64 = task_data.get("image_base64", "")

        logger.info(
            "Processing REGISTER task %s: user=%s, finger=%s",
            task_id, full_name, finger_type,
        )
        t0 = time.time()

        try:
            from app.services.pipeline_service import PipelineService

            pipeline_svc = PipelineService.get_instance()
            if pipeline_svc is None:
                raise RuntimeError("PipelineService not initialized")

            # Step 1: Get image bytes (from base64 or sensor capture)
            if image_base64:
                image_bytes = base64.b64decode(image_base64)
                logger.info("Using provided image (%d bytes)", len(image_bytes))
            else:
                # Capture from local sensor
                image_bytes = _run_async(self._capture_from_sensor())
                logger.info("Captured from sensor (%d bytes)", len(image_bytes))

            # Step 2: Extract embedding using pipeline
            embedding, profiling = _run_async(
                pipeline_svc._pipeline.extract_embedding(image_bytes)
            )

            elapsed_ms = (time.time() - t0) * 1000

            # Step 3: Enroll locally if pipeline supports it
            # The embedding is sent back to orchestrator for DB storage
            result = {
                "task_id": task_id,
                "worker_id": self._mqtt_client.worker_id,
                "status": "completed",
                "result": {
                    "user_id": user_id,
                    "employee_id": employee_id,
                    "full_name": full_name,
                    "department": department,
                    "finger_type": finger_type,
                    "vector": embedding.tolist(),
                    "vector_dim": len(embedding),
                    "quality_score": profiling.get("quality", 0.0),
                    "num_samples": 1,  # single capture for MQTT tasks
                    "processing_time_ms": round(elapsed_ms, 2),
                },
                "processing_time_ms": round(elapsed_ms, 2),
            }
            self._publish_result(task_id, result)
            logger.info(
                "REGISTER task %s completed: user=%s in %.1fms",
                task_id, full_name, elapsed_ms,
            )

        except Exception as exc:
            elapsed_ms = (time.time() - t0) * 1000
            logger.error("REGISTER task %s failed: %s", task_id, exc)
            self._publish_error(task_id, str(exc), elapsed_ms)

    # ── VERIFY task ─────────────────────────────────────────────────────────

    def process_verify(self, task_data: dict) -> None:
        """Process verify task: capture/decode image → verify/identify → publish.

        Args:
            task_data: dict with task_id, user_id, mode (verify/identify),
                       top_k, image_base64
        """
        task_id = task_data.get("task_id", "")
        user_id = task_data.get("user_id", "")
        mode = task_data.get("mode", "verify")  # "verify" or "identify"
        top_k = task_data.get("top_k", 5)
        image_base64 = task_data.get("image_base64", "")

        logger.info(
            "Processing VERIFY task %s: mode=%s, user=%s",
            task_id, mode, user_id,
        )
        t0 = time.time()

        try:
            from app.services.pipeline_service import PipelineService

            pipeline_svc = PipelineService.get_instance()
            if pipeline_svc is None:
                raise RuntimeError("PipelineService not initialized")

            # Step 1: Get image bytes
            if image_base64:
                image_bytes = base64.b64decode(image_base64)
            else:
                image_bytes = _run_async(self._capture_from_sensor())

            # Step 2: Extract probe embedding
            probe_embedding, profiling = _run_async(
                pipeline_svc._pipeline.extract_embedding(image_bytes)
            )

            elapsed_ms = (time.time() - t0) * 1000

            if mode == "identify":
                # 1:N identification
                result = {
                    "task_id": task_id,
                    "worker_id": self._mqtt_client.worker_id,
                    "status": "completed",
                    "result": {
                        "mode": "identify",
                        "probe_vector": probe_embedding.tolist(),
                        "vector_dim": len(probe_embedding),
                        "quality_score": profiling.get("quality", 0.0),
                        "processing_time_ms": round(elapsed_ms, 2),
                    },
                    "processing_time_ms": round(elapsed_ms, 2),
                }
            else:
                # 1:1 verification — send probe embedding for comparison
                result = {
                    "task_id": task_id,
                    "worker_id": self._mqtt_client.worker_id,
                    "status": "completed",
                    "result": {
                        "mode": "verify",
                        "user_id": user_id,
                        "probe_vector": probe_embedding.tolist(),
                        "vector_dim": len(probe_embedding),
                        "quality_score": profiling.get("quality", 0.0),
                        "processing_time_ms": round(elapsed_ms, 2),
                    },
                    "processing_time_ms": round(elapsed_ms, 2),
                }

            self._publish_result(task_id, result)
            logger.info(
                "VERIFY task %s completed: mode=%s in %.1fms",
                task_id, mode, elapsed_ms,
            )

        except Exception as exc:
            elapsed_ms = (time.time() - t0) * 1000
            logger.error("VERIFY task %s failed: %s", task_id, exc)
            self._publish_error(task_id, str(exc), elapsed_ms)

    # ── SYNC task ──────────────────────────────────────────────────────────

    def process_sync(self, task_data: dict) -> None:
        """Process sync task: receive enrollment data from orchestrator.

        Another worker enrolled a fingerprint; we need to store it locally
        in SQLite and add it to our FAISS index so we can verify/identify
        this user offline.

        Args:
            task_data: dict with 'user' and 'fingerprint' keys matching
                       the upstream enrollment event payload format.
        """
        source_worker = task_data.get("worker_id", "unknown")
        user_name = task_data.get("user", {}).get("full_name", "?")

        logger.info(
            "Processing SYNC from worker %s: user=%s",
            source_worker, user_name,
        )

        # Skip if this enrollment came from ourselves
        from app.core.config import get_settings
        my_id = get_settings().device_id
        if source_worker == my_id:
            logger.debug("Skipping sync from self (worker_id=%s)", my_id)
            return

        try:
            from app.services.pipeline_service import PipelineService

            pipeline_svc = PipelineService.get_instance()
            if pipeline_svc is None:
                raise RuntimeError("PipelineService not initialized")

            success = _run_async(
                pipeline_svc.sync_remote_enrollment(task_data)
            )
            if success:
                logger.info(
                    "SYNC completed: user '%s' added to local DB + FAISS",
                    user_name,
                )
            else:
                logger.warning("SYNC failed for user '%s'", user_name)

        except Exception as exc:
            logger.error("SYNC task failed: %s", exc)

    # ── Helpers ──────────────────────────────────────────────────────────────

    async def _capture_from_sensor(self) -> bytes:
        """Capture a fingerprint image from the local sensor."""
        from app.services.sensor_service import SensorService

        sensor = SensorService.get_instance()
        if sensor is None:
            raise RuntimeError("SensorService not initialized")
        if not sensor.is_connected:
            raise RuntimeError("Sensor not connected")

        capture = await sensor.capture_image()
        if not capture.success:
            raise RuntimeError("Sensor capture failed: {}".format(capture.error))
        return capture.image_data

    def _download_image(self, url: str) -> bytes:
        """Download image from presigned URL."""
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.content

    def _find_model(self, model_name: str) -> str:
        """Find the ONNX model file on disk."""
        from app.services.model_service import get_model_service

        model_svc = get_model_service()

        # Try to get embedding model path by type
        path = model_svc.get_model_path_by_type("embedding")
        if path:
            return path

        # Fallback: search models/ directory
        model_dir = os.path.join(os.getcwd(), "models")
        for model_type in ("embedding", "matching", "pad"):
            type_dir = os.path.join(model_dir, model_type)
            if not os.path.isdir(type_dir):
                continue
            for f in os.listdir(type_dir):
                if f.endswith(".onnx"):
                    return os.path.join(type_dir, f)

        # Check root models/ directory
        if os.path.isdir(model_dir):
            for f in os.listdir(model_dir):
                if f.endswith(".onnx"):
                    return os.path.join(model_dir, f)

        raise FileNotFoundError("No .onnx model found in {}".format(model_dir))

    def _publish_result(self, task_id: str, result: dict) -> None:
        """Publish task result back to orchestrator via MQTT."""
        topic = "result/{}".format(task_id)
        payload = json.dumps(result)
        self._mqtt_client.publish(topic, payload, qos=1)
        logger.info("Published result to %s", topic)

    def _publish_error(self, task_id: str, error: str, elapsed_ms: float = 0) -> None:
        """Publish a task error result."""
        result = {
            "task_id": task_id,
            "worker_id": self._mqtt_client.worker_id,
            "status": "failed",
            "error": error,
            "processing_time_ms": round(elapsed_ms, 2),
        }
        self._publish_result(task_id, result)
