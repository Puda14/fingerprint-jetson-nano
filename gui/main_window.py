"""Minimal main window: sidebar (preview + status + actions) + tabbed content."""

import logging
from typing import Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.api_client import ApiClient, ApiWorkerThread, HealthPollerThread
from gui.widgets.fingerprint_preview import FingerprintPreview

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────


def _dot(color: str) -> str:
    return '<span style="color:{c};">●</span>'.format(c=color)


def _make_action_btn(text: str, icon: str, object_name: str = "") -> QPushButton:
    btn = QPushButton("  {} {}".format(icon, text))
    btn.setCursor(Qt.PointingHandCursor)
    btn.setMinimumHeight(44)
    if object_name:
        btn.setObjectName(object_name)
    btn.setStyleSheet(
        """
        QPushButton {{
            background-color: #1c2733;
            color: #e6edf3;
            border: 1px solid #334152;
            border-radius: 10px;
            padding: 10px 14px;
            font-size: 14px;
            font-weight: 600;
            text-align: left;
        }}
        QPushButton:hover {{
            background-color: #243242;
            border-color: #4d5f74;
        }}
        QPushButton:pressed {{
            background-color: #18212b;
        }}
        """
    )
    return btn


def _separator() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet("background-color: #222e3b;")
    return line


# ── Tab Button ─────────────────────────────────────────────────────────────


def _make_tab_btn(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setCheckable(True)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setMinimumHeight(38)
    btn.setStyleSheet(
        """
        QPushButton {
            background-color: transparent;
            color: #8b949e;
            border: none;
            border-bottom: 2px solid transparent;
            padding: 8px 16px;
            font-size: 13px;
            font-weight: 600;
            border-radius: 0;
        }
        QPushButton:hover {
            color: #f0f6fc;
        }
        QPushButton:checked {
            color: #58a6ff;
            border-bottom: 2px solid #58a6ff;
        }
        """
    )
    return btn


# ═══════════════════════════════════════════════════════════════════════════
# Main Window
# ═══════════════════════════════════════════════════════════════════════════


class MainWindow(QMainWindow):
    """Minimal single-page window: sidebar + tabbed content."""

    def __init__(
        self,
        api_base_url: str = "http://localhost:8000/api/v1",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.api_base_url = api_base_url
        self.client = ApiClient(base_url=api_base_url)
        self._ws_url = api_base_url.replace("http://", "ws://").replace(
            "https://", "wss://"
        ) + "/sensor/stream"

        self._worker = None  # current background thread

        self.setWindowTitle("Fingerprint Worker")
        self.setMinimumSize(960, 640)
        self.resize(1120, 720)

        self._build_ui()
        self._setup_health_poller()
        self._initial_load()

    # ── Build UI ───────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ────────────────────────────────────────────────────────
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(260)
        sidebar.setStyleSheet(
            "QFrame#sidebar { background-color: #101720; "
            "border-right: 1px solid #222e3b; }"
        )
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(16, 16, 16, 16)
        sb.setSpacing(10)

        # Brand
        brand = QLabel("🔐 Fingerprint Worker")
        brand.setStyleSheet("color: #f0f6fc; font-size: 16px; font-weight: 700;")
        sb.addWidget(brand)

        sb.addWidget(_separator())

        # Live preview
        self.preview = FingerprintPreview(ws_url=self._ws_url, size=220)
        sb.addWidget(self.preview, alignment=Qt.AlignCenter)

        sb.addWidget(_separator())

        # Status indicators
        self.lbl_backend = QLabel("{} Backend: Connecting".format(_dot("#d29922")))
        self.lbl_backend.setStyleSheet("color: #c9d1d9; font-size: 12px;")
        sb.addWidget(self.lbl_backend)

        self.lbl_sensor = QLabel("{} Sensor: --".format(_dot("#8b949e")))
        self.lbl_sensor.setStyleSheet("color: #c9d1d9; font-size: 12px;")
        sb.addWidget(self.lbl_sensor)

        self.lbl_model = QLabel("Model: --")
        self.lbl_model.setWordWrap(True)
        self.lbl_model.setStyleSheet("color: #8b949e; font-size: 11px;")
        sb.addWidget(self.lbl_model)

        self.lbl_users_count = QLabel("Users: --  |  Fingers: --")
        self.lbl_users_count.setStyleSheet("color: #8b949e; font-size: 11px;")
        sb.addWidget(self.lbl_users_count)

        sb.addWidget(_separator())
        sb.addSpacing(4)

        # Action buttons
        self.btn_register = _make_action_btn("Register", "➕", "btn_primary")
        self.btn_register.clicked.connect(self._action_register)
        sb.addWidget(self.btn_register)

        self.btn_verify = _make_action_btn("Verify 1:1", "✓")
        self.btn_verify.clicked.connect(self._action_verify)
        sb.addWidget(self.btn_verify)

        self.btn_identify = _make_action_btn("Identify 1:N", "🔍")
        self.btn_identify.clicked.connect(self._action_identify)
        sb.addWidget(self.btn_identify)

        sb.addStretch()
        root.addWidget(sidebar)

        # ── Content Area ───────────────────────────────────────────────────
        content = QWidget()
        content.setStyleSheet("background-color: #0b1118;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        # Tab bar
        tab_bar = QWidget()
        tab_bar.setStyleSheet(
            "background-color: #0d141c; border-bottom: 1px solid #1f2a36;"
        )
        tb_layout = QHBoxLayout(tab_bar)
        tb_layout.setContentsMargins(20, 0, 20, 0)
        tb_layout.setSpacing(0)

        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._tab_buttons = []

        for idx, label in enumerate(["Users", "Register", "Results"]):
            btn = _make_tab_btn(label)
            self._tab_group.addButton(btn, idx)
            self._tab_buttons.append(btn)
            tb_layout.addWidget(btn)

        tb_layout.addStretch()

        # Refresh button in tab bar
        self.btn_refresh = QPushButton("⟳ Refresh")
        self.btn_refresh.setStyleSheet(
            "color: #8b949e; background: transparent; border: none; "
            "font-size: 12px; padding: 8px;"
        )
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.clicked.connect(self._refresh_users)
        tb_layout.addWidget(self.btn_refresh)

        cl.addWidget(tab_bar)

        # Stacked content
        self._stack = QStackedWidget()
        self._build_users_page()
        self._build_register_page()
        self._build_results_page()
        cl.addWidget(self._stack)

        root.addWidget(content)

        # Wire tabs
        self._tab_group.buttonClicked[int].connect(self._switch_tab)
        self._tab_buttons[0].setChecked(True)

    # ── Users Page ─────────────────────────────────────────────────────────

    def _build_users_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        self.table_users = QTableWidget()
        self.table_users.setColumnCount(5)
        self.table_users.setHorizontalHeaderLabels(
            ["Employee ID", "Full Name", "Department", "Fingers", "ID"]
        )
        self.table_users.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_users.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_users.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_users.setAlternatingRowColors(True)
        self.table_users.setStyleSheet(
            "QTableWidget { alternate-background-color: #111820; }"
        )
        layout.addWidget(self.table_users)

        # Bottom row
        bottom = QHBoxLayout()
        self.btn_delete = QPushButton("Delete Selected")
        self.btn_delete.setObjectName("btn_danger")
        self.btn_delete.clicked.connect(self._do_delete_user)
        bottom.addWidget(self.btn_delete)
        bottom.addStretch()

        self.lbl_user_count = QLabel("0 users")
        self.lbl_user_count.setStyleSheet("color: #8b949e; font-size: 12px;")
        bottom.addWidget(self.lbl_user_count)
        layout.addLayout(bottom)

        self._stack.addWidget(page)

    # ── Register Page ──────────────────────────────────────────────────────

    def _build_register_page(self) -> None:
        page = QWidget()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        # Create user card
        card = QFrame()
        card.setProperty("card", True)
        card.setStyleSheet(
            "QFrame { background-color: #141c24; border: 1px solid #2b3642; "
            "border-radius: 14px; padding: 20px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(12)

        title = QLabel("Create New User & Enroll")
        title.setStyleSheet("color: #f0f6fc; font-size: 18px; font-weight: 700;")
        card_layout.addWidget(title)

        desc = QLabel("Enter user information. After creation, place finger on sensor to enroll.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8b949e; font-size: 12px;")
        card_layout.addWidget(desc)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)

        self.inp_employee_id = QLineEdit()
        self.inp_employee_id.setPlaceholderText("e.g. EMP001")
        form.addRow("Employee ID:", self.inp_employee_id)

        self.inp_full_name = QLineEdit()
        self.inp_full_name.setPlaceholderText("e.g. Nguyen Van A")
        form.addRow("Full Name:", self.inp_full_name)

        self.inp_department = QLineEdit()
        self.inp_department.setPlaceholderText("e.g. Engineering")
        form.addRow("Department:", self.inp_department)

        card_layout.addLayout(form)

        self.btn_create = QPushButton("Create User")
        self.btn_create.setObjectName("btn_primary")
        self.btn_create.setMinimumHeight(40)
        self.btn_create.clicked.connect(self._do_create_user)
        card_layout.addWidget(self.btn_create)

        self.lbl_create_status = QLabel("")
        self.lbl_create_status.setWordWrap(True)
        card_layout.addWidget(self.lbl_create_status)

        layout.addWidget(card)

        # Enroll card
        enroll_card = QFrame()
        enroll_card.setProperty("card", True)
        enroll_card.setStyleSheet(
            "QFrame { background-color: #141c24; border: 1px solid #2b3642; "
            "border-radius: 14px; padding: 20px; }"
        )
        ec_layout = QVBoxLayout(enroll_card)
        ec_layout.setSpacing(10)

        e_title = QLabel("Enroll Fingerprint")
        e_title.setStyleSheet("color: #f0f6fc; font-size: 16px; font-weight: 600;")
        ec_layout.addWidget(e_title)

        e_desc = QLabel("Select a user, then place finger on sensor to enroll.")
        e_desc.setWordWrap(True)
        e_desc.setStyleSheet("color: #8b949e; font-size: 12px;")
        ec_layout.addWidget(e_desc)

        self.cmb_enroll_user = QComboBox()
        ec_layout.addWidget(self.cmb_enroll_user)

        self.btn_enroll = QPushButton("Enroll Finger")
        self.btn_enroll.setObjectName("btn_accent")
        self.btn_enroll.setMinimumHeight(38)
        self.btn_enroll.clicked.connect(self._do_enroll)
        ec_layout.addWidget(self.btn_enroll)

        self.lbl_enroll_status = QLabel("")
        self.lbl_enroll_status.setWordWrap(True)
        ec_layout.addWidget(self.lbl_enroll_status)

        layout.addWidget(enroll_card)
        layout.addStretch()

        scroll.setWidget(container)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)
        self._stack.addWidget(page)

    # ── Results Page ───────────────────────────────────────────────────────

    def _build_results_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        self.result_card = QFrame()
        self.result_card.setProperty("card", True)
        self.result_card.setStyleSheet(
            "QFrame { background-color: #141c24; border: 1px solid #2b3642; "
            "border-radius: 14px; padding: 24px; }"
        )
        rc_layout = QVBoxLayout(self.result_card)
        rc_layout.setSpacing(12)

        self.lbl_result_title = QLabel("No action performed yet")
        self.lbl_result_title.setStyleSheet(
            "color: #f0f6fc; font-size: 20px; font-weight: 700;"
        )
        rc_layout.addWidget(self.lbl_result_title)

        self.lbl_result_detail = QLabel("Use the sidebar buttons to Verify or Identify.")
        self.lbl_result_detail.setWordWrap(True)
        self.lbl_result_detail.setStyleSheet("color: #8b949e; font-size: 14px;")
        rc_layout.addWidget(self.lbl_result_detail)

        self.lbl_result_score = QLabel("")
        self.lbl_result_score.setStyleSheet("color: #58a6ff; font-size: 36px; font-weight: 700;")
        self.lbl_result_score.setAlignment(Qt.AlignCenter)
        rc_layout.addWidget(self.lbl_result_score)

        self.lbl_result_extra = QLabel("")
        self.lbl_result_extra.setWordWrap(True)
        self.lbl_result_extra.setStyleSheet("color: #c9d1d9; font-size: 13px;")
        rc_layout.addWidget(self.lbl_result_extra)

        layout.addWidget(self.result_card)
        layout.addStretch()
        self._stack.addWidget(page)

    # ── Tab switching ──────────────────────────────────────────────────────

    def _switch_tab(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        if index == 0:
            self._refresh_users()
        elif index == 1:
            self._refresh_enroll_dropdown()

    # ── Health polling ─────────────────────────────────────────────────────

    def _setup_health_poller(self) -> None:
        self._health_poller = HealthPollerThread(self.client, interval_sec=5.0)
        self._health_poller.health_received.connect(self._on_health)
        self._health_poller.connection_changed.connect(self._on_connection_change)
        self._health_poller.start()

    def _on_health(self, data: dict) -> None:
        if not data.get("success"):
            return
        d = data.get("data", data)

        model = d.get("active_model") or "None"
        self.lbl_model.setText("Model: {}".format(model))

        sensor = d.get("sensor_connected", False)
        if sensor:
            self.lbl_sensor.setText("{} Sensor: Connected".format(_dot("#3fb950")))
        else:
            self.lbl_sensor.setText("{} Sensor: Disconnected".format(_dot("#f85149")))

        users = d.get("total_users", "--")
        fps_count = d.get("total_fingerprints", "--")
        self.lbl_users_count.setText("Users: {}  |  Fingers: {}".format(users, fps_count))

    def _on_connection_change(self, connected: bool) -> None:
        if connected:
            self.lbl_backend.setText("{} Backend: Online".format(_dot("#3fb950")))
        else:
            self.lbl_backend.setText("{} Backend: Offline".format(_dot("#f85149")))

    def _initial_load(self) -> None:
        self._refresh_users()
        self.preview.start_stream()

    # ── Users tab ──────────────────────────────────────────────────────────

    def _refresh_users(self) -> None:
        self._worker = ApiWorkerThread(self.client.list_users)
        self._worker.finished.connect(self._on_users_loaded)
        self._worker.start()

    def _on_users_loaded(self, result: dict) -> None:
        data = result.get("data", {})
        users = data.get("users", [])

        self.table_users.setRowCount(len(users))
        for row, u in enumerate(users):
            self.table_users.setItem(row, 0, QTableWidgetItem(u.get("employee_id", "")))
            self.table_users.setItem(row, 1, QTableWidgetItem(u.get("full_name", "")))
            self.table_users.setItem(row, 2, QTableWidgetItem(u.get("department", "")))
            count = int(u.get("fingerprint_count", 0) or 0)
            self.table_users.setItem(row, 3, QTableWidgetItem(str(count)))
            self.table_users.setItem(row, 4, QTableWidgetItem(str(u.get("id", ""))))

        self.lbl_user_count.setText("{} users".format(len(users)))
        self._users_cache = users
        self._refresh_enroll_dropdown()

    def _refresh_enroll_dropdown(self) -> None:
        self.cmb_enroll_user.clear()
        for u in getattr(self, "_users_cache", []):
            display = "{} - {}".format(u.get("employee_id", ""), u.get("full_name", ""))
            self.cmb_enroll_user.addItem(display, u.get("id", ""))

    # ── Create user ────────────────────────────────────────────────────────

    def _do_create_user(self) -> None:
        emp = self.inp_employee_id.text().strip()
        name = self.inp_full_name.text().strip()
        dept = self.inp_department.text().strip()

        if not emp or not name:
            self.lbl_create_status.setText("Employee ID and Full Name are required.")
            self.lbl_create_status.setStyleSheet("color: #f85149;")
            return

        self.btn_create.setEnabled(False)
        self.lbl_create_status.setText("Creating user...")
        self.lbl_create_status.setStyleSheet("color: #d29922;")

        self._worker = ApiWorkerThread(self.client.create_user, emp, name, dept, "user")
        self._worker.finished.connect(self._on_user_created)
        self._worker.start()

    def _on_user_created(self, result: dict) -> None:
        self.btn_create.setEnabled(True)
        if result.get("success"):
            data = result.get("data", {})
            self.lbl_create_status.setText(
                "✓ Created: {} ({})".format(data.get("full_name", ""), data.get("employee_id", ""))
            )
            self.lbl_create_status.setStyleSheet("color: #3fb950;")
            self.inp_employee_id.clear()
            self.inp_full_name.clear()
            self.inp_department.clear()
            self._refresh_users()
        else:
            error = result.get("error", "Unknown error")
            self.lbl_create_status.setText("✗ {}".format(error))
            self.lbl_create_status.setStyleSheet("color: #f85149;")

    # ── Enroll finger ──────────────────────────────────────────────────────

    def _do_enroll(self) -> None:
        idx = self.cmb_enroll_user.currentIndex()
        if idx < 0:
            self.lbl_enroll_status.setText("No user selected.")
            self.lbl_enroll_status.setStyleSheet("color: #f85149;")
            return

        user_id = self.cmb_enroll_user.currentData()
        self.btn_enroll.setEnabled(False)
        self.lbl_enroll_status.setText("Enrolling... keep finger on sensor")
        self.lbl_enroll_status.setStyleSheet("color: #d29922;")

        self._worker = ApiWorkerThread(self.client.enroll_finger, user_id, "right_index")
        self._worker.finished.connect(self._on_enrolled)
        self._worker.start()

    def _on_enrolled(self, result: dict) -> None:
        self.btn_enroll.setEnabled(True)
        if result.get("success"):
            data = result.get("data", {})
            quality = data.get("quality_score", 0)
            templates = data.get("template_count", 0)
            self.lbl_enroll_status.setText(
                "✓ Enrolled! Quality: {:.0f}  |  Templates: {}".format(quality, templates)
            )
            self.lbl_enroll_status.setStyleSheet("color: #3fb950; font-weight: 600;")
            self._refresh_users()
        else:
            error = result.get("error", result.get("data", {}).get("message", "Failed"))
            self.lbl_enroll_status.setText("✗ {}".format(error))
            self.lbl_enroll_status.setStyleSheet("color: #f85149;")

    # ── Delete user ────────────────────────────────────────────────────────

    def _do_delete_user(self) -> None:
        row = self.table_users.currentRow()
        if row < 0:
            return

        uid_item = self.table_users.item(row, 4)
        name_item = self.table_users.item(row, 1)
        if not uid_item:
            return

        name = name_item.text() if name_item else uid_item.text()
        reply = QMessageBox.question(
            self,
            "Delete User",
            "Delete '{}' and all fingerprints?".format(name),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self._worker = ApiWorkerThread(self.client.delete_user, uid_item.text())
        self._worker.finished.connect(lambda _: self._refresh_users())
        self._worker.start()

    # ── Action: Register ───────────────────────────────────────────────────

    def _action_register(self) -> None:
        """Switch to Register tab."""
        self._tab_buttons[1].setChecked(True)
        self._switch_tab(1)

    # ── Action: Verify 1:1 ─────────────────────────────────────────────────

    def _action_verify(self) -> None:
        """Show a user picker dialog, then run 1:1 verify."""
        if not getattr(self, "_users_cache", []):
            self._show_result("No Users", "Register some users first.", "", "", "warning")
            return

        dialog = _UserPickerDialog(self._users_cache, title="Verify 1:1", parent=self)
        if dialog.exec_() != QDialog.Accepted:
            return

        user_id = dialog.selected_user_id
        user_name = dialog.selected_user_name

        self._show_result(
            "Verifying...",
            "Running 1:1 verify for {}".format(user_name),
            "⏳", "", "default"
        )

        self._worker = ApiWorkerThread(self.client.verify, user_id)
        self._worker.finished.connect(self._on_verify_result)
        self._worker.start()

    def _on_verify_result(self, result: dict) -> None:
        data = result.get("data", {})
        if not result.get("success"):
            self._show_result("Verify Failed", result.get("error", "Unknown error"), "", "", "danger")
            return

        matched = data.get("matched", False)
        score = float(data.get("score", 0))
        threshold = float(data.get("threshold", 0))
        latency = data.get("latency_ms", 0)

        if matched:
            self._show_result(
                "✓ MATCH",
                "Identity verified successfully.",
                "{:.2f}%".format(score * 100),
                "Threshold: {:.2f}%  |  Latency: {:.0f}ms".format(threshold * 100, latency),
                "success",
            )
        else:
            self._show_result(
                "✗ NO MATCH",
                "Fingerprint does not match the selected user.",
                "{:.2f}%".format(score * 100),
                "Threshold: {:.2f}%  |  Latency: {:.0f}ms".format(threshold * 100, latency),
                "danger",
            )

    # ── Action: Identify 1:N ───────────────────────────────────────────────

    def _action_identify(self) -> None:
        """Run 1:N identification against the full gallery."""
        self._show_result("Identifying...", "Searching gallery for matches...", "⏳", "", "default")

        self._worker = ApiWorkerThread(self.client.identify, 5)
        self._worker.finished.connect(self._on_identify_result)
        self._worker.start()

    def _on_identify_result(self, result: dict) -> None:
        data = result.get("data", {})
        if not result.get("success"):
            self._show_result("Identify Failed", result.get("error", "Unknown error"), "", "", "danger")
            return

        matches = data.get("matches", [])
        if not matches:
            self._show_result("No Match Found", "No matching fingerprint in the gallery.", "0", "", "warning")
            return

        top = matches[0]
        score = float(top.get("score", 0))
        emp_id = top.get("employee_id", "")
        name = top.get("full_name", "")

        extras = []
        for i, m in enumerate(matches[:5]):
            extras.append("{}. {} ({}) — {:.1f}%".format(
                i + 1, m.get("full_name", ""), m.get("employee_id", ""),
                float(m.get("score", 0)) * 100
            ))

        self._show_result(
            "🔍 Identified: {} ({})".format(name, emp_id),
            "Top match found in gallery.",
            "{:.2f}%".format(score * 100),
            "\n".join(extras),
            "success",
        )

    # ── Result display helper ──────────────────────────────────────────────

    def _show_result(self, title: str, detail: str, score: str, extra: str, tone: str) -> None:
        """Switch to Results tab and display the action outcome."""
        self._tab_buttons[2].setChecked(True)
        self._stack.setCurrentIndex(2)

        self.lbl_result_title.setText(title)
        self.lbl_result_detail.setText(detail)
        self.lbl_result_score.setText(score)
        self.lbl_result_extra.setText(extra)

        colors = {
            "success": ("#0b3d2e", "#3fb950"),
            "danger": ("#3d0b0b", "#f85149"),
            "warning": ("#2d220f", "#d29922"),
            "default": ("#141c24", "#2b3642"),
        }
        bg, border = colors.get(tone, colors["default"])
        self.result_card.setStyleSheet(
            "QFrame {{ background-color: {bg}; border: 2px solid {b}; "
            "border-radius: 14px; padding: 24px; }}".format(bg=bg, b=border)
        )

        title_color = {
            "success": "#3fb950",
            "danger": "#f85149",
            "warning": "#d29922",
            "default": "#f0f6fc",
        }.get(tone, "#f0f6fc")
        self.lbl_result_title.setStyleSheet(
            "color: {}; font-size: 20px; font-weight: 700;".format(title_color)
        )

    # ── Cleanup ────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        if hasattr(self, "_health_poller"):
            self._health_poller.stop()
            self._health_poller.wait(2000)
        self.preview.cleanup()
        event.accept()


# ═══════════════════════════════════════════════════════════════════════════
# User Picker Dialog (for Verify 1:1)
# ═══════════════════════════════════════════════════════════════════════════


class _UserPickerDialog(QDialog):
    """Minimal dialog to pick a user for 1:1 verification."""

    def __init__(self, users: list, title: str = "Select User", parent=None) -> None:
        super().__init__(parent)
        self.users = users
        self.selected_user_id = None
        self.selected_user_name = ""
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(360)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        lbl = QLabel("Select user to verify against:")
        lbl.setStyleSheet("color: #c9d1d9; font-size: 14px; font-weight: 600;")
        layout.addWidget(lbl)

        self.cmb = QComboBox()
        for u in self.users:
            display = "{} - {}".format(u.get("employee_id", ""), u.get("full_name", ""))
            self.cmb.addItem(display, u.get("id", ""))
        layout.addWidget(self.cmb)

        btns = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)

        btn_ok = QPushButton("Verify")
        btn_ok.setObjectName("btn_primary")
        btn_ok.clicked.connect(self._accept)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

    def _accept(self) -> None:
        idx = self.cmb.currentIndex()
        if idx >= 0:
            self.selected_user_id = self.cmb.currentData()
            self.selected_user_name = self.cmb.currentText()
        self.accept()
