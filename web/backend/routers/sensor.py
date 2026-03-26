"""
Sensor endpoints: status, single capture, LED control, live stream via WebSocket.

Uses the real USBSensorDriver (with MockSensorDriver fallback when no hardware).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from web.backend.models.schemas import (
    ApiResponse,
    CaptureResponse,
    LEDRequest,
    SensorStatus,
)
from web.backend.services.sensor_service import SensorService, get_sensor_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sensor", tags=["sensor"])


# ---------------------------------------------------------------------------
# GET /sensor/status
# ---------------------------------------------------------------------------


@router.get("/status", response_model=ApiResponse[SensorStatus])
async def sensor_status(
    sensor: Annotated[SensorService, Depends(get_sensor_service)],
) -> ApiResponse[SensorStatus]:
    info = await sensor.get_info()
    user_count = await sensor.get_user_count()
    compare_level = await sensor.get_compare_level()

    data = SensorStatus(
        connected=sensor.is_connected,
        vendor_id=info.vendor_id if info else None,
        product_id=info.product_id if info else None,
        firmware_version=None,
        serial_number=None,
        resolution_dpi=info.resolution_dpi if info else None,
        user_count=user_count if user_count >= 0 else None,
        compare_level=compare_level if compare_level >= 0 else None,
        is_real_hardware=sensor.is_real_hardware,
    )
    return ApiResponse(success=True, data=data)


# ---------------------------------------------------------------------------
# POST /sensor/capture — single capture
# ---------------------------------------------------------------------------


@router.post("/capture", response_model=ApiResponse[CaptureResponse])
async def capture(
    sensor: Annotated[SensorService, Depends(get_sensor_service)],
) -> ApiResponse[CaptureResponse]:
    result = await sensor.capture_image()

    if not result.success:
        return ApiResponse(
            success=False,
            data=CaptureResponse(
                success=False,
                image_base64="",
                width=0,
                height=0,
                quality_score=0.0,
                message=result.error,
            ),
            error=result.error,
        )

    b64 = base64.b64encode(result.image_data).decode("ascii")
    return ApiResponse(
        success=True,
        data=CaptureResponse(
            success=True,
            image_base64=b64,
            width=result.width,
            height=result.height,
            quality_score=result.quality_score,
            has_finger=result.has_finger,
            message="Capture successful",
        ),
    )


# ---------------------------------------------------------------------------
# POST /sensor/led — LED control
# ---------------------------------------------------------------------------


@router.post("/led", response_model=ApiResponse[dict])
async def led_control(
    body: LEDRequest,
    sensor: Annotated[SensorService, Depends(get_sensor_service)],
) -> ApiResponse[dict]:
    if body.color == "off" or body.color == "0":
        ok = await sensor.led_off()
    else:
        color_map = {"red": 1, "green": 2, "blue": 4, "white": 7}
        color_int = color_map.get(body.color, 0)
        try:
            color_int = int(body.color)
        except ValueError:
            pass
        ok = await sensor.led_on(color_int)

    return ApiResponse(
        success=ok,
        data={"color": body.color, "duration_ms": body.duration_ms},
    )


# ---------------------------------------------------------------------------
# WebSocket /ws/sensor/stream — live fingerprint image stream
# ---------------------------------------------------------------------------


@router.websocket("/stream")
async def ws_sensor_stream(websocket: WebSocket) -> None:
    """
    Stream fingerprint images in real time over WebSocket.

    Client sends JSON:
        {"action": "start", "fps": 10}
        {"action": "stop"}

    Server sends JSON frames:
        {"type": "frame", "image_base64": "...", "width": 192, "height": 192,
         "quality_score": 35.2, "has_finger": true, "timestamp": ...}
    """
    await websocket.accept()
    logger.info("WebSocket /ws/sensor/stream connected")

    sensor = get_sensor_service()
    streaming = False
    target_fps = 10

    async def _stream_loop() -> None:
        nonlocal streaming
        while streaming:
            result = await sensor.capture_image()
            if result.success:
                b64 = base64.b64encode(result.image_data).decode("ascii")
                try:
                    await websocket.send_json(
                        {
                            "type": "frame",
                            "image_base64": b64,
                            "width": result.width,
                            "height": result.height,
                            "quality_score": result.quality_score,
                            "has_finger": result.has_finger,
                            "timestamp": time.time(),
                        }
                    )
                except Exception:
                    streaming = False
                    break
            await asyncio.sleep(1.0 / target_fps)

    stream_task: asyncio.Task | None = None

    try:
        while True:
            raw_msg = await websocket.receive_text()
            try:
                msg = json.loads(raw_msg)
            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON"})
                continue

            action = msg.get("action", "")

            if action == "start":
                target_fps = min(max(msg.get("fps", 10), 1), 30)
                streaming = True
                if stream_task is None or stream_task.done():
                    stream_task = asyncio.create_task(_stream_loop())
                await websocket.send_json({"status": "streaming", "fps": target_fps})

            elif action == "stop":
                streaming = False
                if stream_task and not stream_task.done():
                    stream_task.cancel()
                    try:
                        await stream_task
                    except asyncio.CancelledError:
                        pass
                    stream_task = None
                await websocket.send_json({"status": "stopped"})

            else:
                await websocket.send_json({"error": f"Unknown action: {action}"})

    except WebSocketDisconnect:
        streaming = False
        logger.info("WebSocket /ws/sensor/stream disconnected")
    except Exception as exc:
        streaming = False
        logger.exception("WebSocket /ws/sensor/stream error: %s", exc)
        try:
            await websocket.close(code=1011, reason=str(exc))
        except Exception:
            pass
    finally:
        if stream_task and not stream_task.done():
            stream_task.cancel()
