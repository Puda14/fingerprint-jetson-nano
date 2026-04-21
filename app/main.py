"""FastAPI entrypoint for the Jetson worker."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import (
    models_router,
    sensor_router,
    system_router,
    users_router,
    verification_router,
)
from app.api.routers.verification import ws_verify
from app.core.config import get_settings
from app.core.lifespan import shutdown, startup

logger = logging.getLogger(__name__)


def _configure_logging(debug=False):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def create_app():
    settings = get_settings()
    _configure_logging(settings.debug)
    logger.info("Worker package source: %s", Path(__file__).resolve())

    app = FastAPI(
        title="Fingerprint Jetson Nano Worker",
        description=(
            "Worker API running on Jetson Nano for enrollment, "
            "1:1 verification, and 1:N fingerprint identification."
        ),
        version="2.1.0",
        docs_url="{0}/docs".format(settings.api_prefix),
        redoc_url="{0}/redoc".format(settings.api_prefix),
        openapi_url="{0}/openapi.json".format(settings.api_prefix),
    )

    @app.on_event("startup")
    async def _startup():
        await startup(app)

    @app.on_event("shutdown")
    async def _shutdown():
        await shutdown(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    prefix = settings.api_prefix
    app.include_router(users_router, prefix=prefix)
    app.include_router(verification_router, prefix=prefix)
    app.include_router(models_router, prefix=prefix)
    app.include_router(system_router, prefix=prefix)
    app.include_router(sensor_router, prefix=prefix)

    # Compatibility routes so the teammate demo can talk directly to the
    # worker without requiring the `/api/v1` prefix.
    app.add_api_websocket_route("/ws/verification", ws_verify, name="ws_verification")
    app.add_api_websocket_route("/ws/verify", ws_verify, name="ws_verify")

    return app


def main():
    """Run the worker API with Uvicorn."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )


app = create_app()


if __name__ == "__main__":
    main()
