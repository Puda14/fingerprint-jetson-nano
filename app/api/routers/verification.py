"""Verification and identification endpoints plus WebSocket streaming."""

import asyncio
import base64
import contextlib
import json
import logging
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from app.api.schemas import (
    ApiResponse,
    IdentifyCandidate,
    IdentifyRequest,
    IdentifyResponse,
    VerifyRequest,
    VerifyResponse,
)
from app.core.config import Settings, get_settings
from app.services.pipeline_service import PipelineService, get_pipeline_service
from app.services.sensor_service import SensorService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["verification"])

_STREAM_RESULT_COOLDOWN_SEC = 0.75


def _utc_timestamp():
    return datetime.utcnow().isoformat() + "Z"


def _decode_image_base64(image_base64):
    if not image_base64:
        return None

    try:
        return base64.b64decode(image_base64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid image_base64: {0}".format(exc))


def _coerce_int(value, default, minimum=1, maximum=None):
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default

    if result < minimum:
        result = minimum
    if maximum is not None and result > maximum:
        result = maximum
    return result


def _parse_user_id(user_id):
    try:
        return int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="user_id must be an integer")


def _serialize_verify_result(result):
    return VerifyResponse(
        matched=result.matched,
        score=result.score,
        threshold=result.threshold,
        user_id=str(result.user_id),
        latency_ms=result.latency_ms,
    )


def _serialize_identify_result(results, threshold, latency_ms):
    candidates = [
        IdentifyCandidate(
            user_id=str(result.user_id),
            employee_id=result.employee_id,
            full_name=result.full_name,
            score=result.score,
        )
        for result in results
    ]
    return IdentifyResponse(
        identified=bool(candidates),
        candidates=candidates,
        threshold=threshold,
        latency_ms=latency_ms,
    )


def _ws_message(message_type, payload):
    return {
        "type": message_type,
        "payload": payload,
        "timestamp": _utc_timestamp(),
    }


async def _run_live_verification_session(
    websocket,
    pipeline,
    settings,
    mode,
    user_id=None,
    top_k=5,
    fps=5,
):
    sensor = SensorService.get_instance()
    interval = 1.0 / fps
    last_result_at = 0.0

    while True:
        try:
            capture = await sensor.capture_image()
            if not capture.success:
                await websocket.send_json(
                    _ws_message(
                        "system_alert",
                        {
                            "level": "warning",
                            "message": capture.error or "Fingerprint capture failed",
                        },
                    )
                )
                await asyncio.sleep(interval)
                continue

            preview_payload = {
                "image": base64.b64encode(capture.image_data).decode("ascii"),
                "quality_score": capture.quality_score,
                "has_finger": capture.has_finger,
            }
            await websocket.send_json(_ws_message("capture_preview", preview_payload))

            now = time.monotonic()
            if not capture.has_finger or (now - last_result_at) < _STREAM_RESULT_COOLDOWN_SEC:
                await asyncio.sleep(interval)
                continue

            if mode == "verify":
                if not user_id:
                    await websocket.send_json(
                        _ws_message(
                            "system_alert",
                            {
                                "level": "warning",
                                "message": "user_id is required for verify mode",
                            },
                        )
                    )
                else:
                    verify_result = await pipeline.verify_1to1(
                        user_id=_parse_user_id(user_id),
                        image_bytes=capture.image_data,
                    )
                    await websocket.send_json(
                        _ws_message(
                            "verification_result",
                            _serialize_verify_result(verify_result).dict(),
                        )
                    )
            else:
                started_at = time.perf_counter()
                identify_results = await pipeline.identify_1toN(
                    top_k=top_k,
                    image_bytes=capture.image_data,
                )
                latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
                identify_payload = _serialize_identify_result(
                    identify_results,
                    threshold=settings.identify_threshold,
                    latency_ms=latency_ms,
                )
                await websocket.send_json(
                    _ws_message("identification_result", identify_payload.dict())
                )

            last_result_at = now
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Live verification stream error: %s", exc)
            await websocket.send_json(
                _ws_message(
                    "system_alert",
                    {
                        "level": "error",
                        "message": str(exc),
                    },
                )
            )
            await asyncio.sleep(interval)


@router.post("/verify", response_model=ApiResponse)
async def verify(
    body: VerifyRequest,
    pipeline: PipelineService = Depends(get_pipeline_service),
):
    image_bytes = _decode_image_base64(body.image_base64)
    result = await pipeline.verify_1to1(
        user_id=_parse_user_id(body.user_id),
        image_bytes=image_bytes,
    )
    return ApiResponse(success=True, data=_serialize_verify_result(result))


@router.post("/identify", response_model=ApiResponse)
async def identify(
    body: IdentifyRequest,
    pipeline: PipelineService = Depends(get_pipeline_service),
    settings: Settings = Depends(get_settings),
):
    started_at = time.perf_counter()
    image_bytes = _decode_image_base64(body.image_base64)
    results = await pipeline.identify_1toN(top_k=body.top_k, image_bytes=image_bytes)
    latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
    response = _serialize_identify_result(
        results,
        threshold=settings.identify_threshold,
        latency_ms=latency_ms,
    )
    return ApiResponse(success=True, data=response)


@router.websocket("/ws/verify")
@router.websocket("/ws/verification")
async def ws_verify(websocket: WebSocket):
    """Support both the legacy worker protocol and the teammate demo protocol."""
    await websocket.accept()
    pipeline = PipelineService.get_instance()
    settings = get_settings()
    stream_task = None

    logger.info("WebSocket %s connected", websocket.url.path)

    try:
        while True:
            raw_message = await websocket.receive_text()
            try:
                message = json.loads(raw_message)
            except ValueError:
                await websocket.send_json({"error": "Invalid JSON"})
                continue

            action = str(message.get("action", "")).lower()

            if action == "start":
                if stream_task and not stream_task.done():
                    stream_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await stream_task

                mode = str(message.get("mode", "identify")).lower()
                if mode not in ("verify", "identify"):
                    await websocket.send_json({"error": "mode must be 'verify' or 'identify'"})
                    continue

                user_id = str(message.get("user_id", "")).strip() or None
                if mode == "verify" and not user_id:
                    await websocket.send_json({"error": "user_id required for verify mode"})
                    continue

                fps = _coerce_int(message.get("fps"), default=5, minimum=1, maximum=10)
                top_k = _coerce_int(
                    message.get("top_k"),
                    default=settings.identify_top_k,
                    minimum=1,
                    maximum=50,
                )
                stream_task = asyncio.ensure_future(
                    _run_live_verification_session(
                        websocket,
                        pipeline=pipeline,
                        settings=settings,
                        mode=mode,
                        user_id=user_id,
                        top_k=top_k,
                        fps=fps,
                    )
                )
                await websocket.send_json({"status": "running", "mode": mode, "fps": fps})
                continue

            if action == "stop":
                if stream_task and not stream_task.done():
                    stream_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await stream_task
                stream_task = None
                await websocket.send_json({"status": "stopped"})
                continue

            if action == "verify":
                user_id = str(message.get("user_id", "")).strip()
                if not user_id:
                    await websocket.send_json({"error": "user_id required"})
                    continue

                try:
                    image_bytes = _decode_image_base64(message.get("image_base64"))
                    parsed_user_id = _parse_user_id(user_id)
                except HTTPException as exc:
                    await websocket.send_json({"error": exc.detail})
                    continue

                result = await pipeline.verify_1to1(
                    user_id=parsed_user_id,
                    image_bytes=image_bytes,
                )
                payload = _serialize_verify_result(result).dict()
                await websocket.send_json(dict({"action": "verify"}, **payload))
                continue

            if action == "identify":
                top_k = _coerce_int(
                    message.get("top_k"),
                    default=settings.identify_top_k,
                    minimum=1,
                    maximum=50,
                )
                try:
                    image_bytes = _decode_image_base64(message.get("image_base64"))
                except HTTPException as exc:
                    await websocket.send_json({"error": exc.detail})
                    continue

                started_at = time.perf_counter()
                results = await pipeline.identify_1toN(top_k=top_k, image_bytes=image_bytes)
                latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
                payload = _serialize_identify_result(
                    results,
                    threshold=settings.identify_threshold,
                    latency_ms=latency_ms,
                ).dict()
                await websocket.send_json(dict({"action": "identify"}, **payload))
                continue

            await websocket.send_json({"error": "Unknown action: {0}".format(action)})
    except WebSocketDisconnect:
        logger.info("WebSocket %s disconnected", websocket.url.path)
    except Exception as exc:
        logger.exception("WebSocket %s error: %s", websocket.url.path, exc)
        with contextlib.suppress(Exception):
            await websocket.close(code=1011, reason=str(exc))
    finally:
        if stream_task and not stream_task.done():
            stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stream_task
