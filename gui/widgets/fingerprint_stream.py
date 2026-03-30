"""Live fingerprint sensor streaming page."""

from __future__ import annotations

import base64
import time
from typing import Optional

import numpy as np
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gui.api_client import StreamThread


class FingerprintStreamWidget(QWidget):
    """Live fingerprint image streaming page with quality metrics."""

    def __init__(self, ws_url: str = "ws://localhost:8000/api/v1/sensor/stream", parent=None) -> None:
        super().__init__(parent)
        self.ws_url = ws_url
        self._stream_thread = None  # type: Optional[StreamThread]
        self._frame_count = 0
        self._fps_timer_start = time.time()
        self._current_fps = 0.0
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # -- Left: Image viewer --
        left = QVBoxLayout()
        left.setSpacing(12)

        title = QLabel("Fingerprint Stream")
        title.setStyleSheet("color: #58a6ff; font-size: 22px; font-weight: 700;")
        left.addWidget(title)

        # Fingerprint image display
        self.image_label = QLabel()
        self.image_label.setObjectName("fingerprint_viewer")
        self.image_label.setFixedSize(320, 320)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet(
            "background-color: #161b22; border: 2px solid #30363d; border-radius: 8px;"
        )
        self.image_label.setText("No stream")
        self.image_label.setStyleSheet(
            "QLabel { background-color: #161b22; border: 2px solid #30363d; "
            "border-radius: 8px; color: #484f58; font-size: 16px; }"
        )
        left.addWidget(self.image_label, alignment=Qt.AlignCenter)

        # Controls row
        controls = QHBoxLayout()
        controls.setSpacing(8)

        self.btn_start = QPushButton("▶  Start Stream")
        self.btn_start.setObjectName("btn_primary")
        self.btn_start.clicked.connect(self._start_stream)

        self.btn_stop = QPushButton("■  Stop")
        self.btn_stop.setObjectName("btn_danger")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_stream)

        self.btn_capture = QPushButton("📷  Capture")
        self.btn_capture.clicked.connect(self._single_capture)

        controls.addWidget(self.btn_start)
        controls.addWidget(self.btn_stop)
        controls.addWidget(self.btn_capture)
        controls.addStretch()
        left.addLayout(controls)

        # FPS selector
        fps_row = QHBoxLayout()
        fps_lbl = QLabel("FPS:")
        fps_lbl.setStyleSheet("color: #8b949e;")
        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(1, 30)
        self.spin_fps.setValue(10)
        self.spin_fps.setFixedWidth(80)
        fps_row.addWidget(fps_lbl)
        fps_row.addWidget(self.spin_fps)
        fps_row.addStretch()
        left.addLayout(fps_row)

        left.addStretch()
        layout.addLayout(left, stretch=2)

        # -- Right: Metrics panel --
        right = QVBoxLayout()
        right.setSpacing(12)

        metrics_title = QLabel("Metrics")
        metrics_title.setStyleSheet("color: #58a6ff; font-size: 18px; font-weight: 700;")
        right.addWidget(metrics_title)

        # Status
        status_card = self._make_card()
        s_layout = QVBoxLayout(status_card)
        s_h = QLabel("STATUS")
        s_h.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 600;")
        self.lbl_status = QLabel("Stopped")
        self.lbl_status.setStyleSheet("color: #d29922; font-size: 16px; font-weight: 700;")
        s_layout.addWidget(s_h)
        s_layout.addWidget(self.lbl_status)
        right.addWidget(status_card)

        # FPS display
        fps_card = self._make_card()
        f_layout = QVBoxLayout(fps_card)
        f_h = QLabel("REAL-TIME FPS")
        f_h.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 600;")
        self.lbl_fps = QLabel("0.0")
        self.lbl_fps.setStyleSheet("color: #f0f6fc; font-size: 28px; font-weight: 700;")
        self.lbl_fps.setAlignment(Qt.AlignCenter)
        f_layout.addWidget(f_h)
        f_layout.addWidget(self.lbl_fps)
        right.addWidget(fps_card)

        # Quality
        qual_card = self._make_card()
        q_layout = QVBoxLayout(qual_card)
        q_h = QLabel("QUALITY SCORE")
        q_h.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 600;")
        self.lbl_quality = QLabel("0.0")
        self.lbl_quality.setStyleSheet("color: #f0f6fc; font-size: 28px; font-weight: 700;")
        self.lbl_quality.setAlignment(Qt.AlignCenter)
        self.bar_quality = QProgressBar()
        self.bar_quality.setRange(0, 100)
        self.bar_quality.setValue(0)
        self.bar_quality.setTextVisible(False)
        self.bar_quality.setFixedHeight(8)
        q_layout.addWidget(q_h)
        q_layout.addWidget(self.lbl_quality)
        q_layout.addWidget(self.bar_quality)
        right.addWidget(qual_card)

        # Finger detection
        finger_card = self._make_card()
        fg_layout = QVBoxLayout(finger_card)
        fg_h = QLabel("FINGER DETECTED")
        fg_h.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 600;")
        self.lbl_finger = QLabel("No")
        self.lbl_finger.setStyleSheet("color: #f85149; font-size: 20px; font-weight: 700;")
        self.lbl_finger.setAlignment(Qt.AlignCenter)
        fg_layout.addWidget(fg_h)
        fg_layout.addWidget(self.lbl_finger)
        right.addWidget(finger_card)

        # Frame count
        count_card = self._make_card()
        c_layout = QVBoxLayout(count_card)
        c_h = QLabel("FRAMES RECEIVED")
        c_h.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 600;")
        self.lbl_frame_count = QLabel("0")
        self.lbl_frame_count.setStyleSheet("color: #f0f6fc; font-size: 20px; font-weight: 700;")
        self.lbl_frame_count.setAlignment(Qt.AlignCenter)
        c_layout.addWidget(c_h)
        c_layout.addWidget(self.lbl_frame_count)
        right.addWidget(count_card)

        right.addStretch()
        layout.addLayout(right, stretch=1)

        # FPS calculation timer
        self._fps_calc_timer = QTimer(self)
        self._fps_calc_timer.timeout.connect(self._calc_fps)

    def _make_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background-color: #161b22; border: 1px solid #30363d; "
            "border-radius: 8px; padding: 12px; }"
        )
        return card

    # -- Stream control ------------------------------------------------------

    def _start_stream(self) -> None:
        if self._stream_thread and self._stream_thread.isRunning():
            return

        fps = self.spin_fps.value()
        self._stream_thread = StreamThread(self.ws_url, fps=fps)
        self._stream_thread.frame_received.connect(self._on_frame)
        self._stream_thread.stream_status.connect(self._on_stream_status)
        self._stream_thread.stream_error.connect(self._on_stream_error)
        self._stream_thread.start()

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.lbl_status.setText("Connecting...")
        self.lbl_status.setStyleSheet("color: #d29922; font-size: 16px; font-weight: 700;")

        self._frame_count = 0
        self._fps_timer_start = time.time()
        self._fps_calc_timer.start(1000)

    def _stop_stream(self) -> None:
        if self._stream_thread:
            self._stream_thread.stop()
            self._stream_thread.wait(3000)
            self._stream_thread = None

        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.lbl_status.setText("Stopped")
        self.lbl_status.setStyleSheet("color: #d29922; font-size: 16px; font-weight: 700;")
        self._fps_calc_timer.stop()
        self.image_label.setStyleSheet(
            "QLabel { background-color: #161b22; border: 2px solid #30363d; "
            "border-radius: 8px; color: #484f58; font-size: 16px; }"
        )

    def _single_capture(self) -> None:
        """Capture a single frame via HTTP (non-streaming)."""
        from gui.api_client import ApiClient
        client = ApiClient()

        from gui.api_client import ApiWorkerThread
        self._capture_worker = ApiWorkerThread(client.capture_image)
        self._capture_worker.finished.connect(self._on_single_capture)
        self._capture_worker.start()

    def _on_single_capture(self, result: dict) -> None:
        data = result.get("data", {})
        if data and data.get("success"):
            frame = {
                "image_base64": data.get("image_base64", ""),
                "width": data.get("width", 192),
                "height": data.get("height", 192),
                "quality_score": data.get("quality_score", 0),
                "has_finger": data.get("has_finger", False),
            }
            self._on_frame(frame)

    # -- Frame handling ------------------------------------------------------

    def _on_frame(self, frame_data: dict) -> None:
        b64 = frame_data.get("image_base64", "")
        width = frame_data.get("width", 192)
        height = frame_data.get("height", 192)
        quality = frame_data.get("quality_score", 0)
        has_finger = frame_data.get("has_finger", False)

        self._frame_count += 1
        self.lbl_frame_count.setText(str(self._frame_count))

        # Decode and display image
        if b64:
            try:
                img_bytes = base64.b64decode(b64)
                img_array = np.frombuffer(img_bytes, dtype=np.uint8)

                if len(img_array) == width * height:
                    # Grayscale
                    img_array = img_array.reshape((height, width))
                    qimg = QImage(
                        img_array.data, width, height, width, QImage.Format_Grayscale8
                    )
                else:
                    # Try as raw RGB
                    img_array = img_array.reshape((height, width, 3))
                    qimg = QImage(
                        img_array.data, width, height, width * 3, QImage.Format_RGB888
                    )

                pixmap = QPixmap.fromImage(qimg)
                scaled = pixmap.scaled(
                    self.image_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.FastTransformation,
                )
                self.image_label.setPixmap(scaled)
                self.image_label.setStyleSheet(
                    "QLabel { background-color: #161b22; border: 2px solid #3fb950; "
                    "border-radius: 8px; }"
                )
            except Exception:
                pass

        # Update quality
        self.lbl_quality.setText("{:.1f}".format(quality))
        self.bar_quality.setValue(int(min(quality, 100)))

        # Finger detection
        if has_finger:
            self.lbl_finger.setText("Yes")
            self.lbl_finger.setStyleSheet(
                "color: #3fb950; font-size: 20px; font-weight: 700;"
            )
        else:
            self.lbl_finger.setText("No")
            self.lbl_finger.setStyleSheet(
                "color: #f85149; font-size: 20px; font-weight: 700;"
            )

    def _on_stream_status(self, status: str) -> None:
        if status in ("connected", "polling"):
            self.lbl_status.setText("Streaming" if status == "connected" else "Polling")
            self.lbl_status.setStyleSheet(
                "color: #3fb950; font-size: 16px; font-weight: 700;"
            )

    def _on_stream_error(self, error: str) -> None:
        self.lbl_status.setText("Error")
        self.lbl_status.setStyleSheet("color: #f85149; font-size: 16px; font-weight: 700;")

    def _calc_fps(self) -> None:
        elapsed = time.time() - self._fps_timer_start
        if elapsed > 0:
            self._current_fps = self._frame_count / elapsed
        self.lbl_fps.setText("{:.1f}".format(self._current_fps))
        # Reset counters every 3 seconds for rolling average
        if elapsed > 3:
            self._frame_count = 0
            self._fps_timer_start = time.time()

    # -- cleanup -------------------------------------------------------------

    def cleanup(self) -> None:
        self._stop_stream()
