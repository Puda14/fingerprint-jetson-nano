"""User management endpoints: CRUD + finger enrollment."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from dateutil.parser import isoparse

from app.core.config import Settings, get_settings
from app.api.schemas import (
    ApiResponse,
    EnrollRequest,
    EnrollResponse,
    EnrolledFinger,
    FingerEnum,
    PaginationMeta,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)
from app.services.pipeline_service import PipelineService, get_pipeline_service

router = APIRouter(prefix="/users", tags=["users"])


# ---------------------------------------------------------------------------
# POST /users — create new user
# ---------------------------------------------------------------------------


@router.post("", response_model=ApiResponse[UserResponse], status_code=201)
async def create_user(
    body: UserCreate,
    pipeline: Annotated[PipelineService, Depends(get_pipeline_service)],
) -> ApiResponse[UserResponse]:
    user = await pipeline.create_user(body.model_dump())
    return ApiResponse(
        success=True,
        data=_to_user_response(user),
    )


# ---------------------------------------------------------------------------
# GET /users — list users (pagination + search)
# ---------------------------------------------------------------------------


@router.get("", response_model=ApiResponse[UserListResponse])
async def list_users(
    pipeline: Annotated[PipelineService, Depends(get_pipeline_service)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None, description="Search by name or employee_id"),
    department: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
) -> ApiResponse[UserListResponse]:
    users, total = await pipeline.list_users(
        page=page, limit=limit, search=search, department=department, role=role
    )
    pages = max(1, math.ceil(total / limit))
    return ApiResponse(
        success=True,
        data=UserListResponse(
            users=[_to_user_response(u) for u in users],
            pagination=PaginationMeta(total=total, page=page, limit=limit, pages=pages),
        ),
    )


# ---------------------------------------------------------------------------
# GET /users/{user_id} — get user details
# ---------------------------------------------------------------------------


@router.get("/{user_id}", response_model=ApiResponse[UserResponse])
async def get_user(
    user_id: str,
    pipeline: Annotated[PipelineService, Depends(get_pipeline_service)],
) -> ApiResponse[UserResponse]:
    user = await pipeline.get_user(int(user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return ApiResponse(success=True, data=_to_user_response(user))


# ---------------------------------------------------------------------------
# PUT /users/{user_id} — update user
# ---------------------------------------------------------------------------


@router.put("/{user_id}", response_model=ApiResponse[UserResponse])
async def update_user(
    user_id: str,
    body: UserUpdate,
    pipeline: Annotated[PipelineService, Depends(get_pipeline_service)],
) -> ApiResponse[UserResponse]:
    updated = await pipeline.update_user(int(user_id), body.model_dump(exclude_unset=True))
    if updated is None:
        raise HTTPException(status_code=404, detail="User not found")
    return ApiResponse(success=True, data=_to_user_response(updated))


# ---------------------------------------------------------------------------
# DELETE /users/{user_id} — deactivate user
# ---------------------------------------------------------------------------


@router.delete("/{user_id}", response_model=ApiResponse[dict])
async def delete_user(
    user_id: str,
    pipeline: Annotated[PipelineService, Depends(get_pipeline_service)],
) -> ApiResponse[dict]:
    ok = await pipeline.deactivate_user(int(user_id))
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return ApiResponse(success=True, data={"message": "User deactivated and templates removed"})


# ---------------------------------------------------------------------------
# POST /users/{user_id}/enroll-finger — enroll new finger
# ---------------------------------------------------------------------------


# Map finger enum to 0-9 index for DB storage
_FINGER_INDEX_MAP = {
    FingerEnum.RIGHT_THUMB: 0,
    FingerEnum.RIGHT_INDEX: 1,
    FingerEnum.RIGHT_MIDDLE: 2,
    FingerEnum.RIGHT_RING: 3,
    FingerEnum.RIGHT_LITTLE: 4,
    FingerEnum.LEFT_THUMB: 5,
    FingerEnum.LEFT_INDEX: 6,
    FingerEnum.LEFT_MIDDLE: 7,
    FingerEnum.LEFT_RING: 8,
    FingerEnum.LEFT_LITTLE: 9,
}


@router.post("/{user_id}/enroll-finger", response_model=ApiResponse[EnrollResponse])
async def enroll_finger(
    user_id: str,
    body: EnrollRequest,
    pipeline: Annotated[PipelineService, Depends(get_pipeline_service)],
) -> ApiResponse[EnrollResponse]:
    finger_idx = _FINGER_INDEX_MAP.get(body.finger, 1)
    result = await pipeline.enroll_user(
        user_id=int(user_id),
        finger=finger_idx,
        num_samples=body.num_samples,
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    return ApiResponse(
        success=True,
        data=EnrollResponse(
            user_id=str(result.user_id),
            finger=body.finger,
            quality_score=result.quality_score,
            template_count=result.template_count,
        ),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_dt(val) -> datetime:
    """Parse ISO string or pass-through datetime."""
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return isoparse(val)
        except Exception:
            pass
    return datetime.now(tz=timezone.utc)


def _to_user_response(user: dict) -> UserResponse:
    return UserResponse(
        id=str(user["id"]),
        employee_id=user["employee_id"],
        full_name=user["full_name"],
        department=user.get("department", ""),
        role=user.get("role", "user"),
        is_active=user.get("is_active", True),
        fingerprint_count=int(user.get("fingerprint_count", 0) or 0),
        enrolled_fingers=[],
        created_at=_parse_dt(user.get("created_at")),
        updated_at=_parse_dt(user.get("updated_at")),
    )
