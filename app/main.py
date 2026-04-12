"""
Entry point for Fingerprint Jetson Nano Worker.

Creates FastAPI app and registers all routers.
Contains only application factory logic — no business logic here.
"""


from typing import List, Dict, Tuple, Set, Optional, Any, Union, Coroutine, Callable, Generator, Iterable, AsyncIterator
import logging
import logging.config

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.lifespan import lifespan
from app.api.routers import (
    users_router,
    verification_router,
    models_router,
    system_router,
    sensor_router,
)

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def _configure_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    # Reduce noise from external libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    settings = get_settings()
    _configure_logging(settings.debug)

    app = FastAPI(
        title="Fingerprint Jetson Nano Worker",
        description=(
            "Worker API running on Jetson Nano — provides endpoints for "
            "enrollment, 1:1 verification, and 1:N fingerprint identification."
        ),
        version="2.0.0",
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=f"{settings.api_prefix}/redoc",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        lifespan=lifespan,
    )

    # -- CORS ---------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Routers ------------------------------------------------------------
    prefix = settings.api_prefix
    app.include_router(users_router, prefix=prefix)
    app.include_router(verification_router, prefix=prefix)
    app.include_router(models_router, prefix=prefix)
    app.include_router(system_router, prefix=prefix)
    app.include_router(sensor_router, prefix=prefix)

    return app


# ---------------------------------------------------------------------------
# Singleton app instance
# ---------------------------------------------------------------------------

app = create_app()
