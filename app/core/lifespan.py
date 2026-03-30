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
      2. Initialize local SQLite database
      3. Initialize SensorService (connect USB sensor or fallback to mock)
      4. Initialize PipelineService (load inference model)
      5. Connect MQTT to orchestrator (if enabled)

    Shutdown sequence (reverse order):
      1. Disconnect MQTT
      2. Shutdown PipelineService
      3. Shutdown SensorService
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
    # Step 2: Initialize local database
    # ------------------------------------------------------------------
    mqtt_client = None
    try:
        from app.database.database import DatabaseManager
        db_path = str(Path(settings.data_dir) / "fingerprint.db")
        db = DatabaseManager(db_path)
        logger.info("Local database ready: %s", db.db_path)
    except Exception as exc:
        logger.warning("Database init failed: %s (continuing without local DB)", exc)

    # ------------------------------------------------------------------
    # Step 3: Initialize fingerprint sensor
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
    # Step 4: Initialize inference pipeline
    # ------------------------------------------------------------------
    pipeline = PipelineService.get_instance()
    await pipeline.initialize()
    logger.info("Inference pipeline ready. Active model: %s", pipeline.active_model)

    # ------------------------------------------------------------------
    # Step 5: Connect MQTT to orchestrator
    # ------------------------------------------------------------------
    if settings.mqtt_enabled:
        try:
            import time
            from app.mqtt.client import get_mqtt_client
            from app.mqtt.handlers import create_message_handler

            mqtt_client = get_mqtt_client()
            handler = create_message_handler(mqtt_client)
            mqtt_client.set_message_handler(handler)

            logger.info(
                "Connecting to MQTT broker %s:%d ...",
                settings.mqtt_broker_host, settings.mqtt_broker_port,
            )
            mqtt_client.connect()
            time.sleep(2)

            if mqtt_client.is_connected:
                logger.info("MQTT connected to orchestrator ✅")
            else:
                logger.warning(
                    "MQTT connection pending (broker: %s:%d)",
                    settings.mqtt_broker_host, settings.mqtt_broker_port,
                )
        except Exception as exc:
            logger.warning("MQTT connection failed: %s (running in standalone mode)", exc)
            mqtt_client = None
    else:
        logger.info("MQTT disabled — running in standalone mode")

    logger.info("=== Worker startup complete - listening for requests ===")

    yield  # --- Application running ---

    # ------------------------------------------------------------------
    # Shutdown (reverse order)
    # ------------------------------------------------------------------
    logger.info("=== Worker shutting down... ===")

    # Disconnect MQTT
    if mqtt_client is not None:
        try:
            mqtt_client.disconnect()
            logger.info("MQTT disconnected.")
        except Exception as exc:
            logger.warning("MQTT disconnect error: %s", exc)

    await pipeline.shutdown()
    await sensor.shutdown()
    logger.info("=== Worker shut down cleanly. ===")

