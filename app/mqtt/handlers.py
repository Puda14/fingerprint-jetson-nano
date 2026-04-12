"""
MQTT message handlers — dispatches incoming messages to appropriate services.

Handles:
- task/{worker_id}/model/update → download and convert models
- task/{worker_id}/embed → extract embedding from image URL
- task/{worker_id}/register → capture + enroll via local sensor
- task/{worker_id}/verify → capture + verify/identify via local sensor
- task/{worker_id}/message → log message from orchestrator
"""


from typing import List, Dict, Tuple, Set, Optional, Any, Union, Coroutine, Callable, Generator, Iterable, AsyncIterator, TypeVar, Type, Awaitable, Sequence, Mapping
import json
import logging
import threading

import paho.mqtt.client as mqtt

from app.mqtt.payloads import (
    ModelStatusPayload,
    ModelUpdatePayload,
    RegisterTaskPayload,
    TaskPayload,
    VerifyTaskPayload,
)

logger = logging.getLogger(__name__)


def create_message_handler(mqtt_client_ref: Any) -> Any:
    """Create the on_message callback bound to the MQTT client reference."""

    def on_message(client: mqtt.Client, message: mqtt.MQTTMessage) -> None:
        topic = message.topic
        parts = topic.split("/")

        try:
            if len(parts) >= 3 and parts[0] == "task":
                data = json.loads(message.payload.decode())

                # ── task/{worker_id}/model/update ────────────────────────
                if len(parts) >= 4 and parts[2] == "model" and parts[3] == "update":
                    payload = ModelUpdatePayload(**data)
                    logger.info(
                        "📥 MODEL UPDATE: type=%s, name=%s, ver=%s",
                        payload.model_type, payload.model_name, payload.version,
                    )
                    thread = threading.Thread(
                        target=_handle_model_update,
                        args=(mqtt_client_ref, payload),
                        daemon=True,
                    )
                    thread.start()
                    return

                task_type = parts[2]

                # ── task/{worker_id}/embed ────────────────────────────────
                if task_type == "embed":
                    payload = TaskPayload(**data)
                    logger.info(
                        "📥 EMBED task: id=%s, image_url=%s",
                        payload.task_id,
                        payload.image_url[:60] if payload.image_url else "",
                    )
                    mqtt_client_ref.current_task_id = payload.task_id
                    thread = threading.Thread(
                        target=_handle_embed_task,
                        args=(mqtt_client_ref, data),
                        daemon=True,
                    )
                    thread.start()

                # ── task/{worker_id}/register ─────────────────────────────
                elif task_type == "register":
                    payload = RegisterTaskPayload(**data)
                    logger.info(
                        "📥 REGISTER task: id=%s, user=%s, finger=%s",
                        payload.task_id, payload.full_name, payload.finger_type,
                    )
                    mqtt_client_ref.current_task_id = payload.task_id
                    thread = threading.Thread(
                        target=_handle_register_task,
                        args=(mqtt_client_ref, data),
                        daemon=True,
                    )
                    thread.start()

                # ── task/{worker_id}/verify ────────────────────────────────
                elif task_type == "verify":
                    payload = VerifyTaskPayload(**data)
                    logger.info(
                        "📥 VERIFY task: id=%s, mode=%s, user=%s",
                        payload.task_id, payload.mode, payload.user_id,
                    )
                    mqtt_client_ref.current_task_id = payload.task_id
                    thread = threading.Thread(
                        target=_handle_verify_task,
                        args=(mqtt_client_ref, data),
                        daemon=True,
                    )
                    thread.start()

                # ── task/{worker_id}/match ─────────────────────────────────
                elif task_type == "match":
                    logger.info("📥 MATCH task: %s", data.get("task_id", ""))

                # ── task/{worker_id}/sync ──────────────────────────────────
                elif task_type == "sync":
                    user_name = data.get("user", {}).get("full_name", "?")
                    source = data.get("worker_id", "?")
                    logger.info(
                        "📥 SYNC task: user=%s from worker=%s",
                        user_name, source,
                    )
                    thread = threading.Thread(
                        target=_handle_sync_task,
                        args=(mqtt_client_ref, data),
                        daemon=True,
                    )
                    thread.start()

                # ── task/{worker_id}/message ──────────────────────────────
                elif task_type == "message":
                    content = data.get("content", "")
                    sender = data.get("sender", "orchestrator")
                    logger.info("📩 MESSAGE from %s: %s", sender, content)

                else:
                    logger.warning("Unknown task type: %s", task_type)
            else:
                logger.warning("Unknown topic: %s", topic)

        except Exception as exc:
            logger.error("Error processing message '%s': %s", topic, exc)

    return on_message


# ---------------------------------------------------------------------------
# Task handlers (run in background threads)
# ---------------------------------------------------------------------------


def _handle_embed_task(mqtt_client_ref: Any, task_data: dict) -> None:
    """Process embed task: download image → inference → publish embedding."""
    try:
        from app.services.task_service import TaskService
        task_svc = TaskService(mqtt_client_ref)
        task_svc.process_embed(task_data)
    except Exception as exc:
        logger.error("Embed task failed: %s", exc)
        _publish_error(mqtt_client_ref, task_data.get("task_id", ""), str(exc))
    finally:
        mqtt_client_ref.current_task_id = None


def _handle_register_task(mqtt_client_ref: Any, task_data: dict) -> None:
    """Process register task: capture sensor → pipeline → enroll → publish."""
    try:
        from app.services.task_service import TaskService
        task_svc = TaskService(mqtt_client_ref)
        task_svc.process_register(task_data)
    except Exception as exc:
        logger.error("Register task failed: %s", exc)
        _publish_error(mqtt_client_ref, task_data.get("task_id", ""), str(exc))
    finally:
        mqtt_client_ref.current_task_id = None


def _handle_verify_task(mqtt_client_ref: Any, task_data: dict) -> None:
    """Process verify task: capture sensor → pipeline → verify → publish."""
    try:
        from app.services.task_service import TaskService
        task_svc = TaskService(mqtt_client_ref)
        task_svc.process_verify(task_data)
    except Exception as exc:
        logger.error("Verify task failed: %s", exc)
        _publish_error(mqtt_client_ref, task_data.get("task_id", ""), str(exc))
    finally:
        mqtt_client_ref.current_task_id = None


def _handle_sync_task(mqtt_client_ref: Any, task_data: dict) -> None:
    """Process sync task: store remote enrollment locally (SQLite + FAISS)."""
    try:
        from app.services.task_service import TaskService
        task_svc = TaskService(mqtt_client_ref)
        task_svc.process_sync(task_data)
    except Exception as exc:
        logger.error("Sync task failed: %s", exc)


def _handle_model_update(mqtt_client_ref: Any, payload: ModelUpdatePayload) -> None:
    """Download model from orchestrator and optionally convert to TensorRT."""
    import os
    from app.services.model_service import get_model_service_sync

    worker_id = mqtt_client_ref.worker_id
    model_service = get_model_service_sync()

    task_id = "model_{}".format(payload.model_name)
    mqtt_client_ref.current_task_id = task_id

    try:
        # Publish: downloading
        _publish_model_status(mqtt_client_ref, worker_id, payload, "downloading")

        success, error = model_service.download_model(
            model_type=payload.model_type,
            model_name=payload.model_name,
            version=payload.version,
            download_url=payload.download_url,
        )

        if not success:
            _publish_model_status(mqtt_client_ref, worker_id, payload, "failed", error)
            return

        # Auto-convert ONNX → TensorRT if applicable
        if payload.model_name.endswith(".onnx"):
            model_dir = model_service.model_dir
            onnx_path = os.path.join(model_dir, payload.model_type, payload.model_name)
            trt_path = onnx_path.replace(".onnx", ".trt")

            if not os.path.exists(trt_path):
                try:
                    _publish_model_status(
                        mqtt_client_ref, worker_id, payload, "converting",
                    )
                    logger.info("Auto-converting %s → TensorRT...", payload.model_name)
                    from app.services.inference_service import convert_onnx_to_trt
                    converted = convert_onnx_to_trt(onnx_path, trt_path)
                    if converted:
                        logger.info("✅ TensorRT conversion complete: %s", trt_path)
                    else:
                        logger.warning("⚠️ TensorRT conversion failed, will use ONNX Runtime")
                except ImportError:
                    logger.info("TensorRT converter not available, using ONNX Runtime")
                except Exception as exc:
                    logger.warning("⚠️ TensorRT conversion error: %s", exc)

        # Publish: ready
        _publish_model_status(mqtt_client_ref, worker_id, payload, "ready")

    finally:
        mqtt_client_ref.current_task_id = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _publish_model_status(
    mqtt_client_ref: Any,
    worker_id: str,
    payload: ModelUpdatePayload,
    status: str,
    error: str = None,
) -> None:
    """Publish model download/convert status to orchestrator."""
    status_payload = ModelStatusPayload(
        worker_id=worker_id,
        model_type=payload.model_type,
        model_name=payload.model_name,
        version=payload.version,
        status=status,
        error=error,
    )
    topic = "worker/{}/model/status".format(worker_id)
    mqtt_client_ref.publish(topic, json.dumps(status_payload.__dict__), qos=1)
    logger.info("📤 Model status: %s/%s → %s", payload.model_type, payload.model_name, status)


def _publish_error(mqtt_client_ref: Any, task_id: str, error: str) -> None:
    """Publish a task failure result."""
    if not task_id:
        return
    result = {
        "task_id": task_id,
        "worker_id": mqtt_client_ref.worker_id,
        "status": "failed",
        "error": error,
    }
    mqtt_client_ref.publish_result(task_id, json.dumps(result))
