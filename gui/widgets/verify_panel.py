"""Verification page: 1:1 verify and 1:N identify."""


import base64

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.api_client import ApiClient, ApiWorkerThread, StreamThread


class VerifyPanelWidget(QWidget):
    """Verification page with 1:1 verify and 1:N identify sub-panels."""

    def __init__(self, api_client: ApiClient, parent=None) -> None:
        super().__init__(parent)
        self.client = api_client
        self.ws_stream_url = self.client.base_url.replace("http://", "ws://").replace(
            "https://", "wss://"
        ) + "/sensor/stream"
        self._worker = None
        self._users_cache = []  # type: list
        self._stream_thread = None
        self._latest_frame_b64 = ""
        self._latest_has_finger = False
        self._latest_quality = 0.0
        self._build_ui()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(0)
        root_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("Verification")
        title.setStyleSheet("color: #58a6ff; font-size: 22px; font-weight: 700;")
        layout.addWidget(title)

        stream_box = QFrame()
        stream_box.setStyleSheet(
            "QFrame { background-color: #0f141a; border: 1px solid #30363d; border-radius: 8px; }"
        )
        stream_layout = QVBoxLayout(stream_box)
        stream_layout.setContentsMargins(12, 12, 12, 12)
        stream_layout.setSpacing(8)

        stream_title = QLabel("Live Stream (Shared for 1:1 and 1:N)")
        stream_title.setStyleSheet("color: #c9d1d9; font-size: 13px; font-weight: 700;")
        stream_layout.addWidget(stream_title)

        self.lbl_stream_image = QLabel("No stream")
        self.lbl_stream_image.setFixedSize(220, 220)
        self.lbl_stream_image.setAlignment(Qt.AlignCenter)
        self.lbl_stream_image.setStyleSheet(
            "QLabel { background-color: #161b22; border: 2px solid #30363d; border-radius: 8px; color: #8b949e; }"
        )
        stream_layout.addWidget(self.lbl_stream_image, alignment=Qt.AlignCenter)

        stream_controls = QHBoxLayout()
        self.btn_stream_start = QPushButton("Start Stream")
        self.btn_stream_start.clicked.connect(self._start_stream)
        self.btn_stream_stop = QPushButton("Stop")
        self.btn_stream_stop.setEnabled(False)
        self.btn_stream_stop.clicked.connect(self._stop_stream)
        stream_controls.addWidget(self.btn_stream_start)
        stream_controls.addWidget(self.btn_stream_stop)
        stream_controls.addStretch()
        stream_layout.addLayout(stream_controls)

        self.lbl_stream_hint = QLabel("Finger: No | Quality: 0.0")
        self.lbl_stream_hint.setStyleSheet("color: #8b949e; font-size: 12px;")
        stream_layout.addWidget(self.lbl_stream_hint)

        layout.addWidget(stream_box)

        # Two panels side by side
        panels = QHBoxLayout()
        panels.setSpacing(16)

        # -- Left: 1:1 Verify --
        verify_card = self._make_card()
        verify_card.setMinimumWidth(380)
        v_layout = QVBoxLayout(verify_card)

        v_title = QLabel("1:1 Verification")
        v_title.setStyleSheet("color: #58a6ff; font-size: 16px; font-weight: 700;")
        v_layout.addWidget(v_title)

        v_desc = QLabel("Select a user and verify their fingerprint")
        v_desc.setStyleSheet("color: #8b949e; font-size: 12px;")
        v_desc.setWordWrap(True)
        v_layout.addWidget(v_desc)

        v_layout.addSpacing(8)

        # User selector
        user_lbl = QLabel("Select User:")
        user_lbl.setStyleSheet("color: #c9d1d9; font-weight: 600;")
        v_layout.addWidget(user_lbl)

        self.cmb_user = QComboBox()
        self.cmb_user.setMinimumWidth(200)
        v_layout.addWidget(self.cmb_user)

        v_layout.addSpacing(8)

        self.btn_verify = QPushButton("Verify Fingerprint")
        self.btn_verify.setObjectName("btn_accent")
        self.btn_verify.clicked.connect(self._do_verify)
        v_layout.addWidget(self.btn_verify)

        # Result display
        self.verify_result_frame = QFrame()
        self.verify_result_frame.setStyleSheet(
            "QFrame { background-color: #21262d; border: 1px solid #30363d; "
            "border-radius: 8px; padding: 16px; }"
        )
        vr_layout = QVBoxLayout(self.verify_result_frame)

        self.lbl_verify_icon = QLabel("")
        self.lbl_verify_icon.setAlignment(Qt.AlignCenter)
        self.lbl_verify_icon.setStyleSheet("font-size: 48px;")
        vr_layout.addWidget(self.lbl_verify_icon)

        self.lbl_verify_result = QLabel("Awaiting verification...")
        self.lbl_verify_result.setAlignment(Qt.AlignCenter)
        self.lbl_verify_result.setStyleSheet("color: #8b949e; font-size: 16px; font-weight: 600;")
        vr_layout.addWidget(self.lbl_verify_result)

        self.lbl_verify_score = QLabel("")
        self.lbl_verify_score.setAlignment(Qt.AlignCenter)
        self.lbl_verify_score.setStyleSheet("color: #8b949e; font-size: 13px;")
        vr_layout.addWidget(self.lbl_verify_score)

        self.lbl_verify_latency = QLabel("")
        self.lbl_verify_latency.setAlignment(Qt.AlignCenter)
        self.lbl_verify_latency.setStyleSheet("color: #484f58; font-size: 12px;")
        vr_layout.addWidget(self.lbl_verify_latency)

        v_layout.addWidget(self.verify_result_frame)
        v_layout.addStretch()

        panels.addWidget(verify_card)

        # -- Right: 1:N Identify --
        identify_card = self._make_card()
        identify_card.setMinimumWidth(420)
        i_layout = QVBoxLayout(identify_card)

        i_title = QLabel("1:N Identification")
        i_title.setStyleSheet("color: #58a6ff; font-size: 16px; font-weight: 700;")
        i_layout.addWidget(i_title)

        i_desc = QLabel("Identify a fingerprint against all enrolled users")
        i_desc.setStyleSheet("color: #8b949e; font-size: 12px;")
        i_desc.setWordWrap(True)
        i_layout.addWidget(i_desc)

        i_layout.addSpacing(8)

        topk_row = QHBoxLayout()
        topk_lbl = QLabel("Top K:")
        topk_lbl.setStyleSheet("color: #c9d1d9; font-weight: 600;")
        self.spin_topk = QSpinBox()
        self.spin_topk.setRange(1, 50)
        self.spin_topk.setValue(5)
        self.spin_topk.setFixedWidth(80)
        topk_row.addWidget(topk_lbl)
        topk_row.addWidget(self.spin_topk)
        topk_row.addStretch()
        i_layout.addLayout(topk_row)

        i_layout.addSpacing(8)

        self.btn_identify = QPushButton("Identify Fingerprint")
        self.btn_identify.setObjectName("btn_accent")
        self.btn_identify.clicked.connect(self._do_identify)
        i_layout.addWidget(self.btn_identify)

        # Identify result label
        self.lbl_identify_status = QLabel("Awaiting identification...")
        self.lbl_identify_status.setStyleSheet("color: #8b949e; font-size: 14px; font-weight: 600;")
        self.lbl_identify_status.setAlignment(Qt.AlignCenter)
        i_layout.addWidget(self.lbl_identify_status)

        # Candidates table
        self.table_candidates = QTableWidget()
        self.table_candidates.setColumnCount(4)
        self.table_candidates.setHorizontalHeaderLabels(
            ["Employee ID", "Full Name", "Score", "User ID"]
        )
        self.table_candidates.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.table_candidates.setMinimumWidth(500)
        self.table_candidates.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_candidates.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_candidates.setAlternatingRowColors(False)
        i_layout.addWidget(self.table_candidates)

        i_layout.addStretch()
        panels.addWidget(identify_card)

        layout.addLayout(panels)

        # Refresh users button
        self.btn_refresh = QPushButton("Refresh User List")
        self.btn_refresh.clicked.connect(self.refresh_users)
        layout.addWidget(self.btn_refresh, alignment=Qt.AlignLeft)

        scroll.setWidget(container)
        root_layout.addWidget(scroll)

    def _make_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background-color: #161b22; border: 1px solid #30363d; "
            "border-radius: 8px; padding: 16px; }"
        )
        return card

    # -- actions -------------------------------------------------------------

    def refresh_users(self) -> None:
        self._worker = ApiWorkerThread(self.client.list_users)
        self._worker.finished.connect(self._on_users_loaded)
        self._worker.start()

    def _on_users_loaded(self, result: dict) -> None:
        data = result.get("data", {})
        users = data.get("users", [])
        self._users_cache = users
        self.cmb_user.clear()
        for u in users:
            display = "{} - {}".format(u.get("employee_id", ""), u.get("full_name", ""))
            self.cmb_user.addItem(display, u.get("id", ""))

    def _do_verify(self) -> None:
        idx = self.cmb_user.currentIndex()
        if idx < 0:
            self.lbl_verify_result.setText("No user selected")
            return

        user_id = self.cmb_user.currentData()
        if not user_id:
            return

        self.btn_verify.setEnabled(False)
        self.lbl_verify_result.setText("Verifying...")
        self.lbl_verify_icon.setText("...")
        self.lbl_verify_score.setText("")
        self.lbl_verify_latency.setText("")

        if self._latest_frame_b64 and self._latest_has_finger:
            self._worker = ApiWorkerThread(self.client.verify, user_id, self._latest_frame_b64)
        else:
            self._worker = ApiWorkerThread(self.client.verify, user_id)
        self._worker.finished.connect(self._on_verify_result)
        self._worker.start()

    def _start_stream(self) -> None:
        if self._stream_thread and self._stream_thread.isRunning():
            return
        self._stream_thread = StreamThread(self.ws_stream_url, fps=8)
        self._stream_thread.frame_received.connect(self._on_stream_frame)
        self._stream_thread.stream_error.connect(self._on_stream_error)
        self._stream_thread.start()
        self.btn_stream_start.setEnabled(False)
        self.btn_stream_stop.setEnabled(True)

    def _stop_stream(self) -> None:
        if self._stream_thread:
            self._stream_thread.stop()
            self._stream_thread.wait(2500)
            self._stream_thread = None
        self.btn_stream_start.setEnabled(True)
        self.btn_stream_stop.setEnabled(False)

    def _on_stream_error(self, error: str) -> None:
        self.lbl_stream_hint.setText("Stream error: {}".format(error))
        self.lbl_stream_hint.setStyleSheet("color: #f85149; font-size: 12px;")

    def _on_stream_frame(self, frame_data: dict) -> None:
        b64 = frame_data.get("image_base64", "")
        width = frame_data.get("width", 192)
        height = frame_data.get("height", 192)
        quality = float(frame_data.get("quality_score", 0) or 0)
        has_finger = bool(frame_data.get("has_finger", False))

        self._latest_frame_b64 = b64
        self._latest_has_finger = has_finger
        self._latest_quality = quality

        finger_txt = "Yes" if has_finger else "No"
        self.lbl_stream_hint.setText("Finger: {} | Quality: {:.1f}".format(finger_txt, quality))
        self.lbl_stream_hint.setStyleSheet("color: #8b949e; font-size: 12px;")

        if not b64:
            return

        try:
            img_bytes = base64.b64decode(b64)
            img_array = np.frombuffer(img_bytes, dtype=np.uint8)

            if len(img_array) == width * height:
                img_array = img_array.reshape((height, width))
                qimg = QImage(
                    img_array.data, width, height, width, QImage.Format_Grayscale8
                )
            else:
                img_array = img_array.reshape((height, width, 3))
                qimg = QImage(
                    img_array.data, width, height, width * 3, QImage.Format_RGB888
                )

            pixmap = QPixmap.fromImage(qimg)
            scaled = pixmap.scaled(
                self.lbl_stream_image.size(),
                Qt.KeepAspectRatio,
                Qt.FastTransformation,
            )
            self.lbl_stream_image.setPixmap(scaled)
            self.lbl_stream_image.setStyleSheet(
                "QLabel { background-color: #161b22; border: 2px solid #3fb950; border-radius: 8px; }"
            )
        except Exception:
            pass

    def cleanup(self) -> None:
        self._stop_stream()

    def _on_verify_result(self, result: dict) -> None:
        self.btn_verify.setEnabled(True)
        data = result.get("data", {})

        matched = data.get("matched", False)
        score = data.get("score", 0)
        threshold = data.get("threshold", 0.55)
        latency = data.get("latency_ms", 0)

        if matched:
            self.lbl_verify_icon.setText("OK")
            self.lbl_verify_result.setText("MATCH")
            self.lbl_verify_result.setStyleSheet(
                "color: #3fb950; font-size: 20px; font-weight: 700;"
            )
            self.verify_result_frame.setStyleSheet(
                "QFrame { background-color: #0b3d2e; border: 2px solid #3fb950; "
                "border-radius: 8px; padding: 16px; }"
            )
        else:
            self.lbl_verify_icon.setText("X")
            self.lbl_verify_result.setText("NO MATCH")
            self.lbl_verify_result.setStyleSheet(
                "color: #f85149; font-size: 20px; font-weight: 700;"
            )
            self.verify_result_frame.setStyleSheet(
                "QFrame { background-color: #3d0b0b; border: 2px solid #f85149; "
                "border-radius: 8px; padding: 16px; }"
            )

        self.lbl_verify_score.setText(
            "Score: {:.4f}  |  Threshold: {:.2f}".format(score, threshold)
        )
        self.lbl_verify_score.setStyleSheet("color: #c9d1d9; font-size: 13px;")
        self.lbl_verify_latency.setText("Latency: {:.1f} ms".format(latency))

    def _do_identify(self) -> None:
        top_k = self.spin_topk.value()
        self.btn_identify.setEnabled(False)
        self.lbl_identify_status.setText("Identifying...")
        self.table_candidates.setRowCount(0)

        if self._latest_frame_b64 and self._latest_has_finger:
            self._worker = ApiWorkerThread(self.client.identify, top_k, self._latest_frame_b64)
        else:
            self._worker = ApiWorkerThread(self.client.identify, top_k)
        self._worker.finished.connect(self._on_identify_result)
        self._worker.start()

    def _on_identify_result(self, result: dict) -> None:
        self.btn_identify.setEnabled(True)
        data = result.get("data", {})

        identified = data.get("identified", False)
        candidates = data.get("candidates", [])

        if identified and candidates:
            self.lbl_identify_status.setText(
                "Identified: {} candidate(s)".format(len(candidates))
            )
            self.lbl_identify_status.setStyleSheet(
                "color: #3fb950; font-size: 14px; font-weight: 600;"
            )
        else:
            self.lbl_identify_status.setText("No match found")
            self.lbl_identify_status.setStyleSheet(
                "color: #f85149; font-size: 14px; font-weight: 600;"
            )

        self.table_candidates.setRowCount(len(candidates))
        for row, c in enumerate(candidates):
            self.table_candidates.setItem(
                row, 0, QTableWidgetItem(c.get("employee_id", ""))
            )
            self.table_candidates.setItem(
                row, 1, QTableWidgetItem(c.get("full_name", ""))
            )
            score_item = QTableWidgetItem("{:.4f}".format(c.get("score", 0)))
            score_item.setTextAlignment(Qt.AlignCenter)
            self.table_candidates.setItem(row, 2, score_item)
            self.table_candidates.setItem(
                row, 3, QTableWidgetItem(c.get("user_id", ""))
            )
