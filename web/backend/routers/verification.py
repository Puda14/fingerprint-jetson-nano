"""
Verification and identification endpoints + WebSocket for real-time streaming.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from web.backend.config import Settings, get_settings
from web.backend.models.schemas import (
    ApiResponse,
    IdentifyCandidate,
    IdentifyRequest,
    IdentifyResponse,
    VerifyRequest,
    VerifyResponse,
)
from web.backend.services.pipeline_service import PipelineService, get_pipeline_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["verification"])


# ---------------------------------------------------------------------------
# POST /verify — 1:1 verification
# ---------------------------------------------------------------------------


@router.post("/verify", response_model=ApiResponse[VerifyResponse])
async def verify(
    body: VerifyRequest,
    pipeline: Annotated[PipelineService, Depends(get_pipeline_service)],
) -> ApiResponse[VerifyResponse]:
    result = await pipeline.verify_1to1(user_id=body.user_id)
    return ApiResponse(
        success=True,
        data=VerifyResponse(
            matched=result.matched,
            score=result.score,
            threshold=result.threshold,
            user_id=result.user_id,
            latency_ms=result.latency_ms,
        ),
    )


# ---------------------------------------------------------------------------
# POST /identify — 1:N identification
# ---------------------------------------------------------------------------


@router.post("/identify", response_model=ApiResponse[IdentifyResponse])
async def identify(
    body: IdentifyRequest,
    pipeline: Annotated[PipelineService, Depends(get_pipeline_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApiResponse[IdentifyResponse]:
    start = time.perf_counter()
    results = await pipeline.identify_1toN(top_k=body.top_k)
    latency = round((time.perf_counter() - start) * 1000, 2)

    candidates = [
        IdentifyCandidate(
            user_id=r.user_id,
            employee_id=r.employee_id,
            full_name=r.full_name,
            score=r.score,
        )
        for r in results
    ]
    return ApiResponse(
        success=True,
        data=IdentifyResponse(
            identified=len(candidates) > 0,
            candidates=candidates,
            threshold=settings.identify_threshold,
            latency_ms=latency,
        ),
    )


# ---------------------------------------------------------------------------
# WebSocket /ws/verify — real-time verification stream
# ---------------------------------------------------------------------------


@router.websocket("/ws/verify")
async def ws_verify(websocket: WebSocket) -> None:
    """
    Real-time 1:1 verification over WebSocket.

    Client sends JSON messages:
        {"action": "verify", "user_id": "<id>"}
        {"action": "identify", "top_k": 5}
        {"action": "stop"}

    Server responds with JSON results continuously until stopped.
    """
    await websocket.accept()
    pipeline = PipelineService.get_instance()
    running = True
    logger.info("WebSocket /ws/verify connected")

    try:
        while running:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON"})
                continue

            action = msg.get("action", "")

            if action == "stop":
                await websocket.send_json({"status": "stopped"})
                running = False

            elif action == "verify":
                user_id = msg.get("user_id")
                if not user_id:
                    await websocket.send_json({"error": "user_id required"})
                    continue
                result = await pipeline.verify_1to1(user_id=user_id)
                await websocket.send_json(
                    {
                        "action": "verify",
                        "matched": result.matched,
                        "score": result.score,
                        "threshold": result.threshold,
                        "user_id": result.user_id,
                        "latency_ms": result.latency_ms,
                    }
                )

            elif action == "identify":
                top_k = msg.get("top_k", 5)
                results = await pipeline.identify_1toN(top_k=top_k)
                candidates = [
                    {
                        "user_id": r.user_id,
                        "employee_id": r.employee_id,
                        "full_name": r.full_name,
                        "score": r.score,
                    }
                    for r in results
                ]
                await websocket.send_json(
                    {
                        "action": "identify",
                        "identified": len(candidates) > 0,
                        "candidates": candidates,
                    }
                )

            else:
                await websocket.send_json({"error": f"Unknown action: {action}"})

    except WebSocketDisconnect:
        logger.info("WebSocket /ws/verify disconnected")
    except Exception as exc:
        logger.exception("WebSocket /ws/verify error: %s", exc)
        try:
            await websocket.close(code=1011, reason=str(exc))
        except Exception:
            pass
