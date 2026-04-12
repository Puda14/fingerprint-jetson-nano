"""
Manages application lifecycle (startup -> running -> shutdown).

Uses FastAPI on_event hooks instead of asynccontextmanager lifespan
for Python 3.6 compatibility (contextlib.asynccontextmanager requires 3.7+).
"""

from typing import List, Dict, Tuple, Set, Optional, Any, Union, Coroutine, Callable, Generator, Iterable, AsyncIterator, TypeVar, Type, Awaitable, Sequence, Mapping
import logging

from pathlib import Path

from fastapi import FastAPI

from app.core.config import get_settings
from app.services.pipeline_service import PipelineService
from app.services.sensor_service import SensorService

logger = logging.getLogger(__name__)

# Module-level handle so shutdown can reach it
_mqtt_client = None


async def startup(app: FastAPI) -> None:
    """
    FastAPI startup handler (Python 3.6 compatible replacement for lifespan).
    """
    global _mqtt_client

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
    print("[STARTUP] Initializing fingerprint sensor...", flush=True)
    sensor = SensorService.get_instance()
    hardware_connected = await sensor.initialize(
        vid=settings.sensor_vid,
        pid=settings.sensor_pid,
        sdk_path=settings.sensor_sdk_path,
        use_mock=settings.mock_mode,
    )
    if settings.mock_mode:
        logger.info("Mock mode enabled — using sample fingerprint images.")
        print("[STARTUP] Mock mode enabled.", flush=True)
    elif hardware_connected:
        logger.info("USB sensor connected successfully.")
        print("[STARTUP] USB sensor connected OK!", flush=True)
    else:
        logger.warning("USB sensor not found - using Mock sensor.")
        print("[STARTUP] USB sensor NOT found, using Mock fallback.", flush=True)

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

            _mqtt_client = get_mqtt_client()
            handler = create_message_handler(_mqtt_client)
            _mqtt_client.set_message_handler(handler)

            logger.info(
                "Connecting to MQTT broker %s:%d ...",
                settings.mqtt_broker_host, settings.mqtt_broker_port,
            )
            _mqtt_client.connect()
            time.sleep(2)

            if _mqtt_client.is_connected:
                logger.info("MQTT connected to orchestrator")
            else:
                logger.warning(
                    "MQTT connection pending (broker: %s:%d)",
                    settings.mqtt_broker_host, settings.mqtt_broker_port,
                )
        except Exception as exc:
            logger.warning("MQTT connection failed: %s (running in standalone mode)", exc)
            _mqtt_client = None
    else:
        logger.info("MQTT disabled — running in standalone mode")

    logger.info("=== Worker startup complete - listening for requests ===")


async def shutdown(app: FastAPI) -> None:
    """
    FastAPI shutdown handler (Python 3.6 compatible replacement for lifespan).
    """
    global _mqtt_client

    logger.info("=== Worker shutting down... ===")

    if _mqtt_client is not None:
        try:
            _mqtt_client.disconnect()
            logger.info("MQTT disconnected.")
        except Exception as exc:
            logger.warning("MQTT disconnect error: %s", exc)

    pipeline = PipelineService.get_instance()
    await pipeline.shutdown()

    sensor = SensorService.get_instance()
    await sensor.shutdown()

    logger.info("=== Worker shut down cleanly. ===")


# Keep the old name so we can pass it to main.py for compatibility
# But main.py will need to be updated to use on_event instead
async def lifespan(app: FastAPI) -> None:
    pass
