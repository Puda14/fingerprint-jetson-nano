"""
Abstract Sensor Driver Interface + USB and Mock implementations.

Abstracts vendor-specific fingerprint sensor SDKs behind a unified interface.
Moved from mdgt_edge/sensor/base.py to app/drivers/ to remove dependency
on mdgt_edge package.
"""

from typing import List, Dict, Tuple, Set, Optional, Any, Union, Coroutine, Callable, Generator, Iterable, AsyncIterator, TypeVar, Type, Awaitable, Sequence, Mapping
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum
import threading


class LEDColor(IntEnum):
    """LED color codes."""
    OFF = 0
    RED = 1
    GREEN = 2
    BLUE = 4
    WHITE = 7


@dataclass(frozen=True)
class SensorInfo:
    """Sensor hardware information."""
    vendor_id: int
    product_id: int
    name: str
    resolution_dpi: int
    image_width: int
    image_height: int
    firmware_version: str = ""
    serial_number: str = ""


@dataclass(frozen=True)
class CaptureResult:
    """Result of fingerprint image capture."""
    success: bool
    image_data: bytes = field(default=b"")
    width: int = 192
    height: int = 192
    quality_score: float = 0.0
    has_finger: bool = False
    error: str = ""


class SensorDriver(ABC):
    """Abstract fingerprint sensor driver.

    All vendor-specific implementations must implement this interface.
    """

    @abstractmethod
    def open(self) -> bool:
        """Open connection to sensor device.

        Returns:
            True if device opened successfully.
        """

    @abstractmethod
    def close(self) -> None:
        """Close connection to sensor device."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if sensor is connected and ready."""

    @abstractmethod
    def capture_image(self) -> CaptureResult:
        """Capture a single fingerprint image."""

    @abstractmethod
    def check_finger(self) -> bool:
        """Check if a finger is currently on the sensor."""

    @abstractmethod
    def get_info(self) -> SensorInfo:
        """Get sensor hardware information."""

    @abstractmethod
    def led_on(self, color: int) -> bool:
        """Turn on sensor LED."""

    @abstractmethod
    def led_off(self) -> bool:
        """Turn off sensor LED."""

    @abstractmethod
    def beep(self, duration_ms: int = 100) -> bool:
        """Emit beep sound."""


class USBSensorDriver(SensorDriver):
    """Thread-safe USB fingerprint sensor driver.

    Communicates with the hardware sensor (VID:0x0483, PID:0x5720)
    via the custom SDK FingerprintReader on Jetson Nano.
    All public methods are protected by a threading.Lock.
    """

    def __init__(
        self,
        vid: int = 0x0483,
        pid: int = 0x5720,
        sdk_path: Optional[str] = None,
    ):
        self._vid = vid
        self._pid = pid
        self._sdk_path = sdk_path or "/home/binhan1/SDK-Fingerprint-sensor"
        self._reader = None
        self._connected = False
        self._lock = threading.Lock()

    def open(self) -> bool:
        with self._lock:
            try:
                import sys
                if self._sdk_path and self._sdk_path not in sys.path:
                    sys.path.insert(0, self._sdk_path)
                from fingerprint import FingerprintReader
                self._reader = FingerprintReader()
                result = self._reader.open()
                self._connected = bool(result)
                return self._connected
            except ImportError as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to import SDK from {self._sdk_path}: {e}")
                return False
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Sensor open() crashed! Hardware permission or USB error?: {e}")
                return False

    def close(self) -> None:
        with self._lock:
            if self._reader:
                try:
                    self._reader.close()
                except Exception:
                    pass
                self._reader = None
                self._connected = False

    def is_connected(self) -> bool:
        return self._connected and self._reader is not None

    def capture_image(self) -> CaptureResult:
        with self._lock:
            if not self.is_connected():
                return CaptureResult(success=False, error="Sensor not connected")
            try:
                image = self._reader.capture_image()
                if image is None:
                    return CaptureResult(success=False, error="Capture returned None")
                quality = _calculate_quality(image)
                return CaptureResult(
                    success=True,
                    image_data=image,
                    width=192,
                    height=192,
                    quality_score=quality,
                    has_finger=quality > 10.0,
                )
            except Exception as e:
                return CaptureResult(success=False, error=str(e))

    def check_finger(self) -> bool:
        with self._lock:
            if not self.is_connected():
                return False
            try:
                return self._reader.check_finger()
            except Exception:
                return False

    def get_info(self) -> SensorInfo:
        return SensorInfo(
            vendor_id=self._vid,
            product_id=self._pid,
            name="USB Fingerprint Reader",
            resolution_dpi=500,
            image_width=192,
            image_height=192,
        )

    def led_on(self, color: int) -> bool:
        with self._lock:
            if not self.is_connected():
                return False
            try:
                return self._reader.led_on(color)
            except Exception:
                return False

    def led_off(self) -> bool:
        with self._lock:
            if not self.is_connected():
                return False
            try:
                return self._reader.led_off()
            except Exception:
                return False

    def beep(self, duration_ms: int = 100) -> bool:
        with self._lock:
            if not self.is_connected():
                return False
            try:
                return self._reader.beep(duration_ms)
            except Exception:
                return False

    # -- Hardware matching (device-side firmware) --------------------------

    def add_user(self, user_id: Optional[int] = None) -> Tuple[bool, int]:
        with self._lock:
            if not self.is_connected():
                return False, 0
            try:
                return self._reader.add_user(user_id)
            except Exception:
                return False, 0

    def match_fingerprint(self, timeout_sec: float = 5.0) -> Tuple[bool, int]:
        with self._lock:
            if not self.is_connected():
                return False, 0
            try:
                return self._reader.match_fingerprint(timeout_sec)
            except Exception:
                return False, 0

    def delete_user(self, user_id: int) -> bool:
        with self._lock:
            if not self.is_connected():
                return False
            try:
                return self._reader.delete_user(user_id)
            except Exception:
                return False

    def delete_all(self) -> bool:
        with self._lock:
            if not self.is_connected():
                return False
            try:
                return self._reader.delete_all()
            except Exception:
                return False

    def get_user_count(self) -> int:
        with self._lock:
            if not self.is_connected():
                return -1
            try:
                return self._reader.get_user_count()
            except Exception:
                return -1

    def get_compare_level(self) -> int:
        with self._lock:
            if not self.is_connected():
                return -1
            try:
                return self._reader.get_compare_level()
            except Exception:
                return -1


class MockSensorDriver(SensorDriver):
    """Mock sensor that loads real sample images from data/sample/.

    On init, scans ``data/sample/*.tif`` and caches them.  Each
    ``capture_image()`` call returns the next sample in round-robin.
    Falls back to random noise if no sample files are found.
    """

    def __init__(self, sample_dir: Optional[str] = None) -> None:
        self._connected = False
        self._finger_present = False
        self._sample_images: List[bytes] = []
        self._sample_index: int = 0
        self._sample_dir = sample_dir or "data/sample"

    def _load_samples(self) -> None:
        """Scan sample_dir for .tif/.bmp/.png images and cache as bytes."""
        import os
        import glob

        patterns = ["*.tif", "*.bmp", "*.png", "*.jpg"]
        files: List[str] = []
        for pat in patterns:
            files.extend(sorted(glob.glob(os.path.join(self._sample_dir, pat))))

        self._sample_images = []
        for f in files:
            try:
                with open(f, "rb") as fh:
                    self._sample_images.append(fh.read())
            except Exception:
                pass

    def open(self) -> bool:
        self._connected = True
        self._load_samples()
        return True

    def close(self) -> None:
        self._connected = False
        self._sample_images.clear()

    def is_connected(self) -> bool:
        return self._connected

    def capture_image(self) -> CaptureResult:
        if not self._connected:
            return CaptureResult(success=False, error="Not connected")

        if self._sample_images:
            # Round-robin through sample images
            image_data = self._sample_images[self._sample_index % len(self._sample_images)]
            self._sample_index += 1
            return CaptureResult(
                success=True,
                image_data=image_data,
                width=192,
                height=192,
                quality_score=65.0,
                has_finger=True,
            )

        # Fallback: random noise (no sample files found)
        import numpy as np
        image = np.random.randint(50, 200, (192, 192), dtype=np.uint8)
        return CaptureResult(
            success=True,
            image_data=image.tobytes(),
            width=192,
            height=192,
            quality_score=35.0,
            has_finger=self._finger_present,
        )

    def check_finger(self) -> bool:
        if self._sample_images:
            return True
        return self._finger_present

    def get_info(self) -> SensorInfo:
        return SensorInfo(
            vendor_id=0x0000,
            product_id=0x0000,
            name="Mock Sensor (sample images: {})".format(len(self._sample_images)),
            resolution_dpi=500,
            image_width=192,
            image_height=192,
        )

    def led_on(self, color: int) -> bool:
        return True

    def led_off(self) -> bool:
        return True

    def beep(self, duration_ms: int = 100) -> bool:
        return True

    def set_finger_present(self, present: bool) -> None:
        """Test helper: simulate finger on/off sensor."""
        self._finger_present = present


def _calculate_quality(image: bytes) -> float:
    """Calculate image quality score (standard deviation of pixel values)."""
    if not image or len(image) < 1000:
        return 0.0
    avg = sum(image) / len(image)
    variance = sum((x - avg) ** 2 for x in image) / len(image)
    return variance ** 0.5
