"""
System endpoints: health, logs, stats, config, backup, devices.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from web.backend.models.schemas import (
    ApiResponse,
    BackupResponse,
    ConfigResponse,
    ConfigUpdateRequest,
    DeviceInfo,
    LogEntry,
    LogListResponse,
    PaginationMeta,
    StatsResponse,
    SystemHealth,
)
from web.backend.services.pipeline_service import PipelineService, get_pipeline_service
from web.backend.services.sensor_service import SensorService, get_sensor_service
from web.backend.services.system_service import SystemService, get_system_service

router = APIRouter(tags=["system"])


# ---------------------------------------------------------------------------
# GET /health — system health
# ---------------------------------------------------------------------------


@router.get("/health", response_model=ApiResponse[SystemHealth])
async def health(
    sys_svc: Annotated[SystemService, Depends(get_system_service)],
    pipeline: Annotated[PipelineService, Depends(get_pipeline_service)],
    sensor: Annotated[SensorService, Depends(get_sensor_service)],
) -> ApiResponse[SystemHealth]:
    data = await sys_svc.get_health(
        sensor_connected=sensor.is_connected,
        active_model=pipeline.active_model,
    )
    return ApiResponse(success=True, data=SystemHealth(**data))


# ---------------------------------------------------------------------------
# GET /logs — verification logs (paginated + filtered)
# ---------------------------------------------------------------------------


@router.get("/logs", response_model=ApiResponse[LogListResponse])
async def logs(
    pipeline: Annotated[PipelineService, Depends(get_pipeline_service)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    user_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    decision: str | None = Query(default=None),
    date_from: str | None = Query(default=None, description="ISO date string"),
    date_to: str | None = Query(default=None, description="ISO date string"),
) -> ApiResponse[LogListResponse]:
    raw_logs, total = await pipeline.get_logs(
        page=page,
        limit=limit,
        user_id=user_id,
        action=action,
        decision=decision,
        date_from=date_from,
        date_to=date_to,
    )
    entries = [
        LogEntry(
            id=l["id"],
            timestamp=datetime.fromtimestamp(l["timestamp"], tz=timezone.utc),
            user_id=l.get("user_id"),
            employee_id=l.get("employee_id"),
            action=l["action"],
            decision=l["decision"],
            score=l.get("score"),
            latency_ms=l.get("latency_ms"),
            details=l.get("details"),
        )
        for l in raw_logs
    ]
    pages = max(1, math.ceil(total / limit))
    return ApiResponse(
        success=True,
        data=LogListResponse(
            logs=entries,
            pagination=PaginationMeta(total=total, page=page, limit=limit, pages=pages),
        ),
    )


# ---------------------------------------------------------------------------
# GET /stats — dashboard statistics
# ---------------------------------------------------------------------------


@router.get("/stats", response_model=ApiResponse[StatsResponse])
async def stats(
    pipeline: Annotated[PipelineService, Depends(get_pipeline_service)],
) -> ApiResponse[StatsResponse]:
    data = await pipeline.get_stats()
    return ApiResponse(success=True, data=StatsResponse(**data))


# ---------------------------------------------------------------------------
# GET /config — current configuration
# ---------------------------------------------------------------------------


@router.get("/config", response_model=ApiResponse[ConfigResponse])
async def get_config(
    sys_svc: Annotated[SystemService, Depends(get_system_service)],
) -> ApiResponse[ConfigResponse]:
    cfg = sys_svc.get_config()
    return ApiResponse(success=True, data=ConfigResponse(**cfg))


# ---------------------------------------------------------------------------
# PUT /config — update configuration
# ---------------------------------------------------------------------------


@router.put("/config", response_model=ApiResponse[ConfigResponse])
async def update_config(
    body: ConfigUpdateRequest,
    sys_svc: Annotated[SystemService, Depends(get_system_service)],
) -> ApiResponse[ConfigResponse]:
    cfg = sys_svc.update_config(body.model_dump(exclude_unset=True))
    return ApiResponse(success=True, data=ConfigResponse(**cfg))


# ---------------------------------------------------------------------------
# POST /backup — trigger database backup
# ---------------------------------------------------------------------------


@router.post("/backup", response_model=ApiResponse[BackupResponse])
async def backup(
    sys_svc: Annotated[SystemService, Depends(get_system_service)],
) -> ApiResponse[BackupResponse]:
    result = await sys_svc.create_backup()
    return ApiResponse(success=True, data=BackupResponse(**result))


# ---------------------------------------------------------------------------
# GET /devices — list registered devices
# ---------------------------------------------------------------------------


@router.get("/devices", response_model=ApiResponse[list[DeviceInfo]])
async def devices(
    sys_svc: Annotated[SystemService, Depends(get_system_service)],
) -> ApiResponse[list[DeviceInfo]]:
    devs = await sys_svc.list_devices()
    return ApiResponse(
        success=True,
        data=[DeviceInfo(**d) for d in devs],
    )
