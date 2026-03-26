"""
Model management endpoints: list, upload, activate, convert, profile, delete.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File

from web.backend.models.schemas import (
    ApiResponse,
    ConvertRequest,
    ModelInfo,
    ModelListResponse,
    ModelUploadResponse,
    ProfileResponse,
)
from web.backend.services.model_service import ModelService, get_model_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/models", tags=["models"])


# ---------------------------------------------------------------------------
# GET /models — list available models
# ---------------------------------------------------------------------------


@router.get("", response_model=ApiResponse[ModelListResponse])
async def list_models(
    svc: Annotated[ModelService, Depends(get_model_service)],
) -> ApiResponse[ModelListResponse]:
    raw = await svc.list_models()
    models = [
        ModelInfo(
            id=m["id"],
            filename=m["filename"],
            format=m["format"],
            size_mb=m["size_mb"],
            is_active=m.get("is_active", False),
            created_at=datetime.fromtimestamp(m["created_at"], tz=timezone.utc)
            if isinstance(m["created_at"], (int, float))
            else m["created_at"],
        )
        for m in raw
    ]
    return ApiResponse(success=True, data=ModelListResponse(models=models))


# ---------------------------------------------------------------------------
# POST /models/upload — upload model file (multipart)
# ---------------------------------------------------------------------------


@router.post("/upload", response_model=ApiResponse[ModelUploadResponse])
async def upload_model(
    svc: Annotated[ModelService, Depends(get_model_service)],
    file: UploadFile = File(...),
) -> ApiResponse[ModelUploadResponse]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    allowed = {".onnx", ".trt", ".engine", ".pt", ".pth"}
    suffix = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format. Allowed: {', '.join(allowed)}",
        )

    content = await file.read()
    info = await svc.upload_model(file.filename, content)
    return ApiResponse(
        success=True,
        data=ModelUploadResponse(
            id=info["id"],
            filename=info["filename"],
            size_mb=info["size_mb"],
        ),
    )


# ---------------------------------------------------------------------------
# POST /models/{model_id}/activate — set as active model
# ---------------------------------------------------------------------------


@router.post("/{model_id}/activate", response_model=ApiResponse[dict])
async def activate_model(
    model_id: str,
    svc: Annotated[ModelService, Depends(get_model_service)],
) -> ApiResponse[dict]:
    ok = await svc.activate_model(model_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Model not found")
    return ApiResponse(success=True, data={"message": f"Model {model_id} activated"})


# ---------------------------------------------------------------------------
# POST /models/{model_id}/convert — ONNX -> TensorRT (background)
# ---------------------------------------------------------------------------


@router.post("/{model_id}/convert", response_model=ApiResponse[dict])
async def convert_model(
    model_id: str,
    body: ConvertRequest,
    svc: Annotated[ModelService, Depends(get_model_service)],
    bg: BackgroundTasks,
) -> ApiResponse[dict]:
    model = await svc.get_model(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")

    async def _do_convert() -> None:
        try:
            await svc.convert_model(
                model_id, precision=body.precision, max_batch_size=body.max_batch_size
            )
            logger.info("Conversion of %s complete", model_id)
        except Exception as exc:
            logger.exception("Conversion of %s failed: %s", model_id, exc)

    bg.add_task(_do_convert)

    return ApiResponse(
        success=True,
        data={
            "message": f"Conversion started for model {model_id}",
            "precision": body.precision,
            "max_batch_size": body.max_batch_size,
        },
    )


# ---------------------------------------------------------------------------
# GET /models/{model_id}/profile — benchmark latency
# ---------------------------------------------------------------------------


@router.get("/{model_id}/profile", response_model=ApiResponse[ProfileResponse])
async def profile_model(
    model_id: str,
    svc: Annotated[ModelService, Depends(get_model_service)],
) -> ApiResponse[ProfileResponse]:
    try:
        data = await svc.profile_model(model_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ApiResponse(success=True, data=ProfileResponse(**data))


# ---------------------------------------------------------------------------
# DELETE /models/{model_id} — remove model file
# ---------------------------------------------------------------------------


@router.delete("/{model_id}", response_model=ApiResponse[dict])
async def delete_model(
    model_id: str,
    svc: Annotated[ModelService, Depends(get_model_service)],
) -> ApiResponse[dict]:
    ok = await svc.delete_model(model_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Model not found")
    return ApiResponse(success=True, data={"message": f"Model {model_id} deleted"})
