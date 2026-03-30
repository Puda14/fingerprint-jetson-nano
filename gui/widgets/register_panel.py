"""Registration page: create users and enroll fingerprints."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.api_client import ApiClient, ApiWorkerThread


class RegisterPanelWidget(QWidget):
    """User registration and fingerprint enrollment page."""

    def __init__(self, api_client: ApiClient, parent=None) -> None:
        super().__init__(parent)
        self.client = api_client
        self._worker = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # -- Left: Registration form + Enrollment --
        left = QVBoxLayout()
        left.setSpacing(16)

        title = QLabel("User Registration")
        title.setStyleSheet("color: #58a6ff; font-size: 22px; font-weight: 700;")
        left.addWidget(title)

        # Registration form card
        form_card = self._make_card()
        form_outer = QVBoxLayout(form_card)

        form_title = QLabel("Create New User")
        form_title.setStyleSheet("color: #c9d1d9; font-size: 16px; font-weight: 600;")
        form_outer.addWidget(form_title)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        form_layout.setLabelAlignment(Qt.AlignRight)

        self.inp_employee_id = QLineEdit()
        self.inp_employee_id.setPlaceholderText("e.g. EMP001")
        form_layout.addRow("Employee ID:", self.inp_employee_id)

        self.inp_full_name = QLineEdit()
        self.inp_full_name.setPlaceholderText("e.g. Nguyen Van A")
        form_layout.addRow("Full Name:", self.inp_full_name)

        self.inp_department = QLineEdit()
        self.inp_department.setPlaceholderText("e.g. Engineering")
        form_layout.addRow("Department:", self.inp_department)

        self.cmb_role = QComboBox()
        self.cmb_role.addItems(["employee", "admin", "superadmin"])
        form_layout.addRow("Role:", self.cmb_role)

        form_outer.addLayout(form_layout)

        self.btn_create = QPushButton("➕  Create User")
        self.btn_create.setObjectName("btn_primary")
        self.btn_create.clicked.connect(self._do_create_user)
        form_outer.addWidget(self.btn_create)

        self.lbl_create_status = QLabel("")
        self.lbl_create_status.setWordWrap(True)
        form_outer.addWidget(self.lbl_create_status)

        left.addWidget(form_card)

        # -- Enrollment card --
        enroll_card = self._make_card()
        e_layout = QVBoxLayout(enroll_card)

        e_title = QLabel("Enroll Fingerprint")
        e_title.setStyleSheet("color: #c9d1d9; font-size: 16px; font-weight: 600;")
        e_layout.addWidget(e_title)

        e_desc = QLabel("Select a user and finger to enroll")
        e_desc.setStyleSheet("color: #8b949e; font-size: 12px;")
        e_layout.addWidget(e_desc)

        # User selector for enrollment
        e_layout.addSpacing(4)
        usr_lbl = QLabel("User:")
        usr_lbl.setStyleSheet("color: #c9d1d9; font-weight: 600;")
        e_layout.addWidget(usr_lbl)

        self.cmb_enroll_user = QComboBox()
        e_layout.addWidget(self.cmb_enroll_user)

        # Finger selector
        fng_lbl = QLabel("Finger:")
        fng_lbl.setStyleSheet("color: #c9d1d9; font-weight: 600;")
        e_layout.addWidget(fng_lbl)

        self.cmb_finger = QComboBox()
        fingers = [
            "right_thumb", "right_index", "right_middle", "right_ring", "right_little",
            "left_thumb", "left_index", "left_middle", "left_ring", "left_little",
        ]
        self.cmb_finger.addItems(fingers)
        self.cmb_finger.setCurrentIndex(1)  # right_index default
        e_layout.addWidget(self.cmb_finger)

        e_layout.addSpacing(8)

        self.btn_enroll = QPushButton("🖐  Enroll Finger")
        self.btn_enroll.setObjectName("btn_accent")
        self.btn_enroll.clicked.connect(self._do_enroll)
        e_layout.addWidget(self.btn_enroll)

        # Enrollment result
        self.enroll_result_frame = QFrame()
        self.enroll_result_frame.setStyleSheet(
            "QFrame { background-color: #21262d; border: 1px solid #30363d; "
            "border-radius: 8px; padding: 12px; }"
        )
        er_layout = QVBoxLayout(self.enroll_result_frame)
        self.lbl_enroll_result = QLabel("Ready to enroll")
        self.lbl_enroll_result.setStyleSheet("color: #8b949e; font-size: 14px;")
        self.lbl_enroll_result.setAlignment(Qt.AlignCenter)
        self.lbl_enroll_quality = QLabel("")
        self.lbl_enroll_quality.setAlignment(Qt.AlignCenter)
        self.lbl_enroll_quality.setStyleSheet("color: #8b949e; font-size: 12px;")
        er_layout.addWidget(self.lbl_enroll_result)
        er_layout.addWidget(self.lbl_enroll_quality)
        e_layout.addWidget(self.enroll_result_frame)

        left.addWidget(enroll_card)
        left.addStretch()

        layout.addLayout(left, stretch=1)

        # -- Right: User list table --
        right = QVBoxLayout()
        right.setSpacing(12)

        list_header = QHBoxLayout()
        list_title = QLabel("Enrolled Users")
        list_title.setStyleSheet("color: #58a6ff; font-size: 18px; font-weight: 700;")
        list_header.addWidget(list_title)

        self.btn_refresh = QPushButton("🔄  Refresh")
        self.btn_refresh.clicked.connect(self.refresh_users)
        list_header.addWidget(self.btn_refresh)
        list_header.addStretch()
        right.addLayout(list_header)

        self.table_users = QTableWidget()
        self.table_users.setColumnCount(6)
        self.table_users.setHorizontalHeaderLabels(
            ["Employee ID", "Full Name", "Department", "Role", "Fingers", "User ID"]
        )
        self.table_users.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_users.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_users.setEditTriggers(QTableWidget.NoEditTriggers)
        right.addWidget(self.table_users)

        # Delete user button
        self.btn_delete = QPushButton("🗑  Delete Selected User")
        self.btn_delete.setObjectName("btn_danger")
        self.btn_delete.clicked.connect(self._do_delete_user)
        right.addWidget(self.btn_delete, alignment=Qt.AlignLeft)

        layout.addLayout(right, stretch=2)

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

        # Update table
        self.table_users.setRowCount(len(users))
        for row, u in enumerate(users):
            self.table_users.setItem(
                row, 0, QTableWidgetItem(u.get("employee_id", ""))
            )
            self.table_users.setItem(
                row, 1, QTableWidgetItem(u.get("full_name", ""))
            )
            self.table_users.setItem(
                row, 2, QTableWidgetItem(u.get("department", ""))
            )
            self.table_users.setItem(
                row, 3, QTableWidgetItem(u.get("role", ""))
            )
            fingers = u.get("enrolled_fingers", [])
            self.table_users.setItem(
                row, 4, QTableWidgetItem(str(len(fingers)))
            )
            self.table_users.setItem(
                row, 5, QTableWidgetItem(u.get("id", ""))
            )

        # Update enrollment user dropdown
        self.cmb_enroll_user.clear()
        for u in users:
            display = "{} - {}".format(u.get("employee_id", ""), u.get("full_name", ""))
            self.cmb_enroll_user.addItem(display, u.get("id", ""))

    def _do_create_user(self) -> None:
        emp_id = self.inp_employee_id.text().strip()
        name = self.inp_full_name.text().strip()
        dept = self.inp_department.text().strip()
        role = self.cmb_role.currentText()

        if not emp_id or not name:
            self.lbl_create_status.setText("Employee ID and Full Name are required.")
            self.lbl_create_status.setStyleSheet("color: #f85149;")
            return

        self.btn_create.setEnabled(False)
        self.lbl_create_status.setText("Creating user...")
        self.lbl_create_status.setStyleSheet("color: #d29922;")

        self._worker = ApiWorkerThread(
            self.client.create_user, emp_id, name, dept, role
        )
        self._worker.finished.connect(self._on_user_created)
        self._worker.start()

    def _on_user_created(self, result: dict) -> None:
        self.btn_create.setEnabled(True)
        success = result.get("success", False)

        if success:
            data = result.get("data", {})
            self.lbl_create_status.setText(
                "User created: {} ({})".format(
                    data.get("full_name", ""), data.get("employee_id", "")
                )
            )
            self.lbl_create_status.setStyleSheet("color: #3fb950;")
            # Clear form
            self.inp_employee_id.clear()
            self.inp_full_name.clear()
            self.inp_department.clear()
            # Refresh list
            self.refresh_users()
        else:
            error = result.get("error", "Unknown error")
            self.lbl_create_status.setText("Error: {}".format(error))
            self.lbl_create_status.setStyleSheet("color: #f85149;")

    def _do_enroll(self) -> None:
        idx = self.cmb_enroll_user.currentIndex()
        if idx < 0:
            self.lbl_enroll_result.setText("No user selected")
            self.lbl_enroll_result.setStyleSheet("color: #f85149; font-size: 14px;")
            return

        user_id = self.cmb_enroll_user.currentData()
        finger = self.cmb_finger.currentText()

        self.btn_enroll.setEnabled(False)
        self.lbl_enroll_result.setText("Enrolling... Place finger on sensor")
        self.lbl_enroll_result.setStyleSheet("color: #d29922; font-size: 14px;")
        self.lbl_enroll_quality.setText("")

        self._worker = ApiWorkerThread(
            self.client.enroll_finger, user_id, finger
        )
        self._worker.finished.connect(self._on_enrolled)
        self._worker.start()

    def _on_enrolled(self, result: dict) -> None:
        self.btn_enroll.setEnabled(True)
        success = result.get("success", False)
        data = result.get("data", {})

        if success:
            self.lbl_enroll_result.setText("Enrollment successful!")
            self.lbl_enroll_result.setStyleSheet("color: #3fb950; font-size: 14px; font-weight: 600;")
            quality = data.get("quality_score", 0)
            templates = data.get("template_count", 0)
            self.lbl_enroll_quality.setText(
                "Quality: {:.1f}  |  Templates: {}".format(quality, templates)
            )
            self.lbl_enroll_quality.setStyleSheet("color: #c9d1d9; font-size: 12px;")
            self.enroll_result_frame.setStyleSheet(
                "QFrame { background-color: #0b3d2e; border: 2px solid #3fb950; "
                "border-radius: 8px; padding: 12px; }"
            )
            self.refresh_users()
        else:
            error = result.get("error", data.get("message", "Enrollment failed"))
            self.lbl_enroll_result.setText("Error: {}".format(error))
            self.lbl_enroll_result.setStyleSheet("color: #f85149; font-size: 14px;")
            self.enroll_result_frame.setStyleSheet(
                "QFrame { background-color: #3d0b0b; border: 2px solid #f85149; "
                "border-radius: 8px; padding: 12px; }"
            )

    def _do_delete_user(self) -> None:
        row = self.table_users.currentRow()
        if row < 0:
            return

        user_id_item = self.table_users.item(row, 5)
        name_item = self.table_users.item(row, 1)
        if not user_id_item:
            return

        user_id = user_id_item.text()
        name = name_item.text() if name_item else user_id

        reply = QMessageBox.question(
            self,
            "Delete User",
            "Are you sure you want to delete '{}'?\n"
            "This will remove all enrolled fingerprints.".format(name),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self._worker = ApiWorkerThread(self.client.delete_user, user_id)
        self._worker.finished.connect(self._on_user_deleted)
        self._worker.start()

    def _on_user_deleted(self, result: dict) -> None:
        self.refresh_users()
