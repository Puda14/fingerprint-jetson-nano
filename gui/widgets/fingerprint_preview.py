"""Compact live sensor preview widget for the sidebar.

Auto-starts streaming when shown, auto-stops when hidden.
Displays quality score and finger detection status.
"""

import base64
import time
from typing import Optional

import numpy as np
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QFrame,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from gui.api_client import StreamThread


class FingerprintPreview(QWidget):
    """Compact sensor preview with auto-stream management."""

    # Emitted whenever a frame arrives (for other widgets to use)
    frame_arrived = pyqtSignal(dict)

    def __init__(
        self,
        ws_url: str = "ws://localhost:8000/api/v1/sensor/stream",
        size: int = 220,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.ws_url = ws_url
        self._preview_size = size
        self._stream_thread = None  # type: Optional[StreamThread]
        self._quality = 0.0
        self._has_finger = False
        self._frame_count = 0
        self._fps_start = time.time()
        self._fps_count = 0
        self._current_fps = 0.0
        self._build_ui()

        self._fps_timer = QTimer(self)
        self._fps_timer.timeout.connect(self._calc_fps)

    # -- UI ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Sensor image
        self.image_label = QLabel("No stream")
        self.image_label.setFixedSize(self._preview_size, self._preview_size)
        self.image_label.setAlignment(Qt.AlignCenter)
        self._set_border(False)
        layout.addWidget(self.image_label, alignment=Qt.AlignCenter)

        # Quality bar
        self.bar_quality = QProgressBar()
        self.bar_quality.setRange(0, 100)
        self.bar_quality.setValue(0)
        self.bar_quality.setTextVisible(False)
        self.bar_quality.setFixedHeight(6)
        layout.addWidget(self.bar_quality)

        # Info row
        self.lbl_info = QLabel("Quality: --  |  Finger: --")
        self.lbl_info.setAlignment(Qt.AlignCenter)
        self.lbl_info.setStyleSheet("color: #8b949e; font-size: 11px;")
        layout.addWidget(self.lbl_info)

    def _set_border(self, active: bool) -> None:
        border = "#3fb950" if active else "#2b3642"
        self.image_label.setStyleSheet(
            "QLabel {{ background-color: #0f1620; border: 2px solid {b}; "
            "border-radius: 12px; color: #6b7280; font-size: 12px; }}".format(b=border)
        )

    # -- Stream management ---------------------------------------------------

    def start_stream(self) -> None:
        """Start the WebSocket sensor stream."""
        if self._stream_thread and self._stream_thread.isRunning():
            return

        self._stream_thread = StreamThread(self.ws_url, fps=8)
        self._stream_thread.frame_received.connect(self._on_frame)
        self._stream_thread.start()

        self._frame_count = 0
        self._fps_count = 0
        self._fps_start = time.time()
        self._fps_timer.start(2000)

    def stop_stream(self) -> None:
        """Stop the WebSocket sensor stream."""
        self._fps_timer.stop()
        if self._stream_thread:
            self._stream_thread.stop()
            self._stream_thread.wait(2000)
            self._stream_thread = None
        self._set_border(False)

    def cleanup(self) -> None:
        self.stop_stream()

    # -- Frame handling ------------------------------------------------------

    def _on_frame(self, frame_data: dict) -> None:
        b64 = frame_data.get("image_base64", "")
        width = frame_data.get("width", 192)
        height = frame_data.get("height", 192)
        self._quality = float(frame_data.get("quality_score", 0) or 0)
        self._has_finger = bool(frame_data.get("has_finger", False))

        self._frame_count += 1
        self._fps_count += 1

        # Render image
        if b64:
            try:
                img_bytes = base64.b64decode(b64)
                arr = np.frombuffer(img_bytes, dtype=np.uint8)

                if len(arr) == width * height:
                    arr = arr.reshape((height, width))
                    qimg = QImage(arr.data, width, height, width, QImage.Format_Grayscale8)
                else:
                    arr = arr.reshape((height, width, 3))
                    qimg = QImage(arr.data, width, height, width * 3, QImage.Format_RGB888)

                pixmap = QPixmap.fromImage(qimg)
                scaled = pixmap.scaled(
                    self.image_label.size(), Qt.KeepAspectRatio, Qt.FastTransformation
                )
                self.image_label.setPixmap(scaled)
                self.image_label.setText("")
                self._set_border(True)
            except Exception:
                pass

        # Update info
        q_str = "{:.0f}".format(self._quality)
        f_str = "Yes" if self._has_finger else "No"
        self.lbl_info.setText("Quality: {}  |  Finger: {}".format(q_str, f_str))

        q_color = "#3fb950" if self._quality >= 40 else "#d29922" if self._quality >= 20 else "#f85149"
        self.lbl_info.setStyleSheet("color: {}; font-size: 11px; font-weight: 600;".format(q_color))
        self.bar_quality.setValue(int(min(self._quality, 100)))

        # Forward to other widgets
        self.frame_arrived.emit(frame_data)

    def _calc_fps(self) -> None:
        elapsed = time.time() - self._fps_start
        if elapsed > 0:
            self._current_fps = self._fps_count / elapsed
        self._fps_count = 0
        self._fps_start = time.time()

    # -- Properties ----------------------------------------------------------

    @property
    def quality(self) -> float:
        return self._quality

    @property
    def has_finger(self) -> bool:
        return self._has_finger
