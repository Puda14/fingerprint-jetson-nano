"""
FastAPI application entry-point for the MDGT Edge Fingerprint Verification System.

Usage:
    uvicorn web.backend.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from web.backend.config import get_settings
from web.backend.middleware.profiling import ProfilingMiddleware
from web.backend.routers import (
    models_router,
    sensor_router,
    system_router,
    users_router,
    verification_router,
)
from web.backend.services.pipeline_service import PipelineService
from web.backend.services.sensor_service import SensorService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: initialize services on startup, clean up on shutdown."""
    settings = get_settings()
    logger.info("Starting MDGT Edge — device=%s", settings.device_id)

    # Ensure directories exist
    Path(settings.model_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)

    # Initialize sensor (USB hardware or mock fallback)
    sensor = SensorService.get_instance()
    await sensor.initialize(
        vid=settings.sensor_vid,
        pid=settings.sensor_pid,
        sdk_path=settings.sensor_sdk_path,
    )

    # Initialize pipeline (load model, build FAISS index, etc.)
    pipeline = PipelineService.get_instance()
    await pipeline.initialize()

    yield  # ---- application is running ----

    await pipeline.shutdown()
    await sensor.shutdown()
    logger.info("MDGT Edge shut down cleanly.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title="MDGT Edge Fingerprint Verification API",
        description="REST + WebSocket API for fingerprint enrollment, verification, and identification on Jetson Nano.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=f"{settings.api_prefix}/redoc",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        debug=settings.debug,
    )

    # -- CORS ---------------------------------------------------------------
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Profiling middleware ------------------------------------------------
    application.add_middleware(ProfilingMiddleware)

    # -- Routers (REST) -----------------------------------------------------
    application.include_router(users_router, prefix=settings.api_prefix)
    application.include_router(verification_router, prefix=settings.api_prefix)
    application.include_router(models_router, prefix=settings.api_prefix)
    application.include_router(system_router, prefix=settings.api_prefix)
    application.include_router(sensor_router, prefix=settings.api_prefix)

    # -- WebSocket routers (mounted at root; paths already include /ws) -----
    # The verification and sensor routers contain WebSocket endpoints.
    # They are already included above with the api_prefix.

    # -- Global exception handler -------------------------------------------

    @application.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "data": None,
                "error": "Internal server error",
            },
        )

    # -- Static files (frontend build) --------------------------------------
    frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        application.mount(
            "/",
            StaticFiles(directory=str(frontend_dist), html=True),
            name="frontend",
        )

    return application


# ---------------------------------------------------------------------------
# Module-level app instance (used by uvicorn)
# ---------------------------------------------------------------------------

app = create_app()


# ---------------------------------------------------------------------------
# Convenience: run directly with `python -m web.backend.main`
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    _settings = get_settings()
    logging.basicConfig(
        level=logging.DEBUG if _settings.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    uvicorn.run(
        "web.backend.main:app",
        host=_settings.host,
        port=_settings.port,
        reload=_settings.debug,
    )
