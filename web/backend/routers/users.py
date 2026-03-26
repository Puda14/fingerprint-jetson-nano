"""
User management endpoints: CRUD + finger enrollment.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from web.backend.config import Settings, get_settings
from web.backend.models.schemas import (
    ApiResponse,
    EnrollRequest,
    EnrollResponse,
    EnrolledFinger,
    PaginationMeta,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)
from web.backend.services.pipeline_service import PipelineService, get_pipeline_service

router = APIRouter(prefix="/users", tags=["users"])


# ---------------------------------------------------------------------------
# POST /users — create / enroll user
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
# GET /users — list users (paginated + search + filter)
# ---------------------------------------------------------------------------


@router.get("", response_model=ApiResponse[UserListResponse])
async def list_users(
    pipeline: Annotated[PipelineService, Depends(get_pipeline_service)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="Search by name or employee_id"),
    department: str | None = Query(default=None),
    role: str | None = Query(default=None),
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
# GET /users/{user_id} — user detail
# ---------------------------------------------------------------------------


@router.get("/{user_id}", response_model=ApiResponse[UserResponse])
async def get_user(
    user_id: str,
    pipeline: Annotated[PipelineService, Depends(get_pipeline_service)],
) -> ApiResponse[UserResponse]:
    user = await pipeline.get_user(user_id)
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
    updated = await pipeline.update_user(user_id, body.model_dump(exclude_unset=True))
    if updated is None:
        raise HTTPException(status_code=404, detail="User not found")
    return ApiResponse(success=True, data=_to_user_response(updated))


# ---------------------------------------------------------------------------
# DELETE /users/{user_id} — deactivate + cascade delete templates
# ---------------------------------------------------------------------------


@router.delete("/{user_id}", response_model=ApiResponse[dict])
async def delete_user(
    user_id: str,
    pipeline: Annotated[PipelineService, Depends(get_pipeline_service)],
) -> ApiResponse[dict]:
    ok = await pipeline.deactivate_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return ApiResponse(success=True, data={"message": "User deactivated and templates removed"})


# ---------------------------------------------------------------------------
# POST /users/{user_id}/enroll-finger — enroll a specific finger
# ---------------------------------------------------------------------------


@router.post("/{user_id}/enroll-finger", response_model=ApiResponse[EnrollResponse])
async def enroll_finger(
    user_id: str,
    body: EnrollRequest,
    pipeline: Annotated[PipelineService, Depends(get_pipeline_service)],
) -> ApiResponse[EnrollResponse]:
    result = await pipeline.enroll_user(
        user_id=user_id,
        finger=body.finger.value,
        num_samples=body.num_samples,
    )
    if not result.success:
        raise HTTPException(status_code=404, detail=result.message)

    return ApiResponse(
        success=True,
        data=EnrollResponse(
            user_id=result.user_id,
            finger=body.finger,
            quality_score=result.quality_score,
            template_count=result.template_count,
        ),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_user_response(user: dict) -> UserResponse:
    enrolled = []
    for f in user.get("enrolled_fingers", []):
        enrolled.append(
            EnrolledFinger(
                finger=f["finger"],
                enrolled_at=datetime.fromtimestamp(f["enrolled_at"], tz=timezone.utc),
                quality_score=f["quality_score"],
            )
        )
    return UserResponse(
        id=user["id"],
        employee_id=user["employee_id"],
        full_name=user["full_name"],
        department=user["department"],
        role=user["role"],
        is_active=user["is_active"],
        enrolled_fingers=enrolled,
        created_at=datetime.fromtimestamp(user["created_at"], tz=timezone.utc),
        updated_at=datetime.fromtimestamp(user["updated_at"], tz=timezone.utc),
    )
