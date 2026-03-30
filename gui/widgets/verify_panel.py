"""Verification page: 1:1 verify and 1:N identify."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.api_client import ApiClient, ApiWorkerThread


class VerifyPanelWidget(QWidget):
    """Verification page with 1:1 verify and 1:N identify sub-panels."""

    def __init__(self, api_client: ApiClient, parent=None) -> None:
        super().__init__(parent)
        self.client = api_client
        self._worker = None
        self._users_cache = []  # type: list
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("Verification")
        title.setStyleSheet("color: #58a6ff; font-size: 22px; font-weight: 700;")
        layout.addWidget(title)

        # Two panels side by side
        panels = QHBoxLayout()
        panels.setSpacing(16)

        # -- Left: 1:1 Verify --
        verify_card = self._make_card()
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

        self.btn_verify = QPushButton("🔐  Verify Fingerprint")
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

        self.btn_identify = QPushButton("🔍  Identify Fingerprint")
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
        self.table_candidates.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_candidates.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_candidates.setAlternatingRowColors(False)
        i_layout.addWidget(self.table_candidates)

        i_layout.addStretch()
        panels.addWidget(identify_card)

        layout.addLayout(panels)

        # Refresh users button
        self.btn_refresh = QPushButton("🔄  Refresh User List")
        self.btn_refresh.clicked.connect(self.refresh_users)
        layout.addWidget(self.btn_refresh, alignment=Qt.AlignLeft)

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
        self.lbl_verify_icon.setText("⏳")
        self.lbl_verify_score.setText("")
        self.lbl_verify_latency.setText("")

        self._worker = ApiWorkerThread(self.client.verify, user_id)
        self._worker.finished.connect(self._on_verify_result)
        self._worker.start()

    def _on_verify_result(self, result: dict) -> None:
        self.btn_verify.setEnabled(True)
        data = result.get("data", {})

        matched = data.get("matched", False)
        score = data.get("score", 0)
        threshold = data.get("threshold", 0.55)
        latency = data.get("latency_ms", 0)

        if matched:
            self.lbl_verify_icon.setText("✅")
            self.lbl_verify_result.setText("MATCH")
            self.lbl_verify_result.setStyleSheet(
                "color: #3fb950; font-size: 20px; font-weight: 700;"
            )
            self.verify_result_frame.setStyleSheet(
                "QFrame { background-color: #0b3d2e; border: 2px solid #3fb950; "
                "border-radius: 8px; padding: 16px; }"
            )
        else:
            self.lbl_verify_icon.setText("❌")
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
