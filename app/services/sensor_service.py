"""
Sensor Service — singleton managing the fingerprint sensor driver.

Provides async wrappers around USBSensorDriver so FastAPI endpoints
can call sensor operations without blocking the event loop.
Fallbacks to MockSensorDriver if hardware is not detected.
"""


from typing import List, Dict, Tuple, Set, Optional, Any, Union, Coroutine, Callable, Generator, Iterable, AsyncIterator, TypeVar, Type, Awaitable, Sequence, Mapping
import asyncio
import logging
from functools import partial
import time

from app.drivers import (
    USBSensorDriver,
    MockSensorDriver,
    SensorDriver,
    CaptureResult,
    SensorInfo,
)

logger = logging.getLogger(__name__)


class SensorService:
    """Async-friendly singleton wrapping the fingerprint sensor."""

    _instance: Optional["SensorService"] = None

    def __init__(self) -> None:
        self._driver: Optional[SensorDriver] = None

    @classmethod
    def get_instance(cls) -> "SensorService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- lifecycle -----------------------------------------------------------

    async def initialize(
        self,
        vid: int = 0x0483,
        pid: int = 0x5720,
        sdk_path: str = "/home/binhan1/SDK-Fingerprint-sensor",
        use_mock: bool = False,
    ) -> bool:
        """Opens sensor connection. Returns True if real hardware connected."""
        if use_mock:
            self._driver = MockSensorDriver()
            self._driver.open()
            logger.info("SensorService: using MockSensorDriver")
            return True

        driver = USBSensorDriver(vid=vid, pid=pid, sdk_path=sdk_path)
        loop = asyncio.get_event_loop()
        connected = await loop.run_in_executor(None, driver.open)

        if connected:
            self._driver = driver
            logger.info("SensorService: USB sensor connected successfully")
            return True

        # Do not silently fall back to mock mode in production paths.
        # Otherwise the system may keep returning sample images and create
        # dangerous false matches while appearing healthy.
        logger.warning("SensorService: USB sensor not found")
        self._driver = None
        return False

    async def shutdown(self) -> None:
        if self._driver is not None:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._driver.close)
            self._driver = None
            logger.info("SensorService: shut down")

    # -- properties ----------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._driver is not None and self._driver.is_connected()

    @property
    def is_real_hardware(self) -> bool:
        return isinstance(self._driver, USBSensorDriver)

    # -- async wrappers (run blocking SDK calls in thread pool) ----------

    async def capture_image(self) -> CaptureResult:
        if self._driver is None:
            return CaptureResult(success=False, error="Sensor not initialized")
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._driver.capture_image)

    async def capture_when_ready(
        self,
        min_quality: float = 20.0,
        settle_ms: int = 250,
        timeout_sec: float = 5.0,
    ) -> CaptureResult:
        """Wait until a finger is present and return a stable capture.

        This reduces false matches caused by capturing too early or without
        a real finger on the sensor surface.
        """
        if self._driver is None:
            return CaptureResult(success=False, error="Sensor not initialized")

        deadline = time.monotonic() + max(timeout_sec, 0.1)
        saw_finger = False

        while time.monotonic() < deadline:
            finger_present = await self.check_finger()
            if not finger_present:
                await asyncio.sleep(0.08)
                continue

            saw_finger = True
            await asyncio.sleep(max(settle_ms, 0) / 1000.0)
            capture = await self.capture_image()
            if (
                capture.success
                and capture.has_finger
                and capture.quality_score >= min_quality
            ):
                return capture
            await asyncio.sleep(0.08)

        if saw_finger:
            return CaptureResult(
                success=False,
                error="Finger detected but capture quality is too low",
            )
        return CaptureResult(success=False, error="No finger detected on sensor")

    async def check_finger(self) -> bool:
        if self._driver is None:
            return False
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._driver.check_finger)

    async def get_info(self) -> Optional[SensorInfo]:
        if self._driver is None:
            return None
        return self._driver.get_info()

    async def led_on(self, color: int) -> bool:
        if self._driver is None:
            return False
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._driver.led_on, color))

    async def led_off(self) -> bool:
        if self._driver is None:
            return False
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._driver.led_off)

    async def beep(self, duration_ms: int = 100) -> bool:
        if self._driver is None:
            return False
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, partial(self._driver.beep, duration_ms)
        )

    # -- hardware matching (USB sensor only) ---------------------------------

    async def add_user(self, user_id: Optional[int] = None) -> Tuple[bool, int]:
        if not isinstance(self._driver, USBSensorDriver):
            return False, 0
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, partial(self._driver.add_user, user_id)
        )

    async def match_fingerprint(
        self, timeout_sec: float = 5.0
    ) -> Tuple[bool, int]:
        if not isinstance(self._driver, USBSensorDriver):
            return False, 0
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, partial(self._driver.match_fingerprint, timeout_sec)
        )

    async def delete_user(self, user_id: int) -> bool:
        if not isinstance(self._driver, USBSensorDriver):
            return False
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, partial(self._driver.delete_user, user_id)
        )

    async def delete_all(self) -> bool:
        if not isinstance(self._driver, USBSensorDriver):
            return False
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._driver.delete_all)

    async def get_user_count(self) -> int:
        if not isinstance(self._driver, USBSensorDriver):
            return -1
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._driver.get_user_count)

    async def get_compare_level(self) -> int:
        if not isinstance(self._driver, USBSensorDriver):
            return -1
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._driver.get_compare_level)


async def get_sensor_service() -> "SensorService":
    return SensorService.get_instance()
