"""System endpoints: health, logs, stats, config, backup, devices."""


from typing import List, Dict, Tuple, Set, Optional, Any, Union, Coroutine, Callable, Generator, Iterable, AsyncIterator, TypeVar, Type, Awaitable, Sequence, Mapping
import math
from datetime import datetime, timezone

from dateutil.parser import isoparse

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.pydantic_compat import model_dump_compat
from app.api.schemas import (
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
from app.services.pipeline_service import PipelineService, get_pipeline_service
from app.services.sensor_service import SensorService, get_sensor_service
from app.services.system_service import SystemService, get_system_service

router = APIRouter(prefix="/system", tags=["system"])


# ---------------------------------------------------------------------------
# GET /health — system health
# ---------------------------------------------------------------------------


@router.get("/health", response_model=ApiResponse)
async def health(
    sys_svc: SystemService = Depends(get_system_service),
    pipeline: PipelineService = Depends(get_pipeline_service),
    sensor: SensorService = Depends(get_sensor_service),
) -> ApiResponse:
    data = await sys_svc.get_health(
        sensor_connected=sensor.is_connected,
        active_model=pipeline.active_model,
        model_loaded=pipeline.is_model_loaded,
    )
    return ApiResponse(success=True, data=SystemHealth(**data))


# ---------------------------------------------------------------------------
# GET /logs — verification history (pagination + filter)
# ---------------------------------------------------------------------------


@router.get("/logs", response_model=ApiResponse)
async def logs(
    pipeline: PipelineService = Depends(get_pipeline_service),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    user_id: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
    decision: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None, description="ISO date string"),
    date_to: Optional[str] = Query(default=None, description="ISO date string"),
) -> ApiResponse:
    uid = int(user_id) if user_id else None
    raw_logs, total = await pipeline.get_logs(
        page=page,
        limit=limit,
        user_id=uid,
        action=action,
        decision=decision,
        date_from=date_from,
        date_to=date_to,
    )
    entries = []
    for l in raw_logs:
        ts = l.get("timestamp", "")
        if isinstance(ts, str):
            try:
                dt = isoparse(ts)
            except Exception:
                dt = datetime.now(tz=timezone.utc)
        elif isinstance(ts, datetime):
            dt = ts
        else:
            dt = datetime.now(tz=timezone.utc)
        entries.append(
            LogEntry(
                id=str(l.get("id", "")),
                timestamp=dt,
                user_id=str(l.get("matched_user_id", "")) if l.get("matched_user_id") else None,
                employee_id=None,
                action=l.get("mode", "verify"),
                decision=l.get("decision", "REJECT"),
                score=l.get("score"),
                latency_ms=l.get("latency_ms"),
                details=None,
            )
        )
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


@router.get("/stats", response_model=ApiResponse)
async def stats(
    pipeline: PipelineService = Depends(get_pipeline_service),
) -> ApiResponse:
    data = await pipeline.get_stats()
    return ApiResponse(
        success=True,
        data=StatsResponse(
            enrolled_users=data.get("enrolled_users", 0),
            enrolled_fingers=data.get("enrolled_fingerprints", 0),
            verifications_today=0,
            identifications_today=0,
            acceptance_rate=0.0,
            rejection_rate=0.0,
            avg_latency_ms=0.0,
            uptime_seconds=data.get("uptime_seconds", 0.0),
        ),
    )


# ---------------------------------------------------------------------------
# GET /config — view current config
# ---------------------------------------------------------------------------


@router.get("/config", response_model=ApiResponse)
async def get_config(
    sys_svc: SystemService = Depends(get_system_service),
) -> ApiResponse:
    cfg = sys_svc.get_config()
    return ApiResponse(success=True, data=ConfigResponse(**cfg))


# ---------------------------------------------------------------------------
# PUT /config — update config
# ---------------------------------------------------------------------------


@router.put("/config", response_model=ApiResponse)
async def update_config(
    body: ConfigUpdateRequest,
    sys_svc: SystemService = Depends(get_system_service),
) -> ApiResponse:
    cfg = sys_svc.update_config(model_dump_compat(body, exclude_unset=True))
    return ApiResponse(success=True, data=ConfigResponse(**cfg))


# ---------------------------------------------------------------------------
# POST /backup — create database backup
# ---------------------------------------------------------------------------


@router.post("/backup", response_model=ApiResponse)
async def backup(
    sys_svc: SystemService = Depends(get_system_service),
) -> ApiResponse:
    result = await sys_svc.create_backup()
    return ApiResponse(success=True, data=BackupResponse(**result))


# ---------------------------------------------------------------------------
# GET /devices — list registered devices
# ---------------------------------------------------------------------------


@router.get("/devices", response_model=ApiResponse)
async def devices(
    sys_svc: SystemService = Depends(get_system_service),
) -> ApiResponse:
    devs = await sys_svc.list_devices()
    return ApiResponse(
        success=True,
        data=[DeviceInfo(**d) for d in devs],
    )

# ---------------------------------------------------------------------------
# POST /sync — sync data from orchestrator
# ---------------------------------------------------------------------------


@router.post("/sync", response_model=ApiResponse)
async def sync_data(
    payload: Dict[str, Any],
    pipeline: PipelineService = Depends(get_pipeline_service),
) -> ApiResponse:
    """Overwrite local DB and FAISS index with server data payload."""
    try:
        users_count, fps_count = await pipeline.sync_from_server(payload)
        return ApiResponse(
            success=True,
            data={"users_synced": users_count, "fingerprints_synced": fps_count},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
