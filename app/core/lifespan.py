"""
Manages application lifecycle (startup -> running -> shutdown).

Separated from main.py for readability and easier testing.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI

from app.core.config import get_settings
from app.services.pipeline_service import PipelineService
from app.services.sensor_service import SensorService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Manages FastAPI application lifecycle.

    Startup sequence:
      1. Create necessary directories
      2. Initialize SensorService (connect USB sensor or fallback to mock)
      3. Initialize PipelineService (load inference model)

    Shutdown sequence (reverse order):
      1. Shutdown PipelineService
      2. Shutdown SensorService
    """
    settings = get_settings()
    logger.info("=== Fingerprint Jetson Nano Worker starting up ===")
    logger.info("Device ID: %s", settings.device_id)
    logger.info("Inference backend: %s", settings.backend)
    logger.info("Model path: %s", settings.model_path)

    # ------------------------------------------------------------------
    # Step 1: Create necessary directories
    # ------------------------------------------------------------------
    Path(settings.model_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.backup_dir).mkdir(parents=True, exist_ok=True)
    logger.info("Data directories are ready.")

    # ------------------------------------------------------------------
    # Step 2: Initialize fingerprint sensor
    # ------------------------------------------------------------------
    sensor = SensorService.get_instance()
    hardware_connected = await sensor.initialize(
        vid=settings.sensor_vid,
        pid=settings.sensor_pid,
        sdk_path=settings.sensor_sdk_path,
    )
    if hardware_connected:
        logger.info("USB sensor connected successfully.")
    else:
        logger.warning("USB sensor not found - using Mock sensor.")

    # ------------------------------------------------------------------
    # Step 3: Initialize inference pipeline
    # ------------------------------------------------------------------
    pipeline = PipelineService.get_instance()
    await pipeline.initialize()
    logger.info("Inference pipeline ready. Active model: %s", pipeline.active_model)

    logger.info("=== Worker startup complete - listening for requests ===")

    yield  # --- Application running ---

    # ------------------------------------------------------------------
    # Shutdown (reverse order)
    # ------------------------------------------------------------------
    logger.info("=== Worker shutting down... ===")
    await pipeline.shutdown()
    await sensor.shutdown()
    logger.info("=== Worker shut down cleanly. ===")
