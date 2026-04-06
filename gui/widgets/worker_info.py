"""Dashboard page: worker info, system metrics, and stats overview."""


from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


def _card(title: str = "") -> QFrame:
    """Create a styled card frame."""
    frame = QFrame()
    frame.setObjectName("info_card")
    frame.setProperty("class", "card")
    frame.setFrameShape(QFrame.StyledPanel)
    frame.setStyleSheet(
        "QFrame#info_card { background-color: #161b22; border: 1px solid #30363d; "
        "border-radius: 8px; padding: 16px; }"
    )
    return frame


def _stat_widget(value_text: str, label_text: str) -> tuple:
    """Create a value + label stat pair and return (widget, value_label, label_label)."""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)

    val = QLabel(value_text)
    val.setStyleSheet("color: #f0f6fc; font-size: 28px; font-weight: 700;")
    val.setAlignment(Qt.AlignCenter)

    lbl = QLabel(label_text)
    lbl.setStyleSheet(
        "color: #8b949e; font-size: 11px; font-weight: 500; "
        "text-transform: uppercase;"
    )
    lbl.setAlignment(Qt.AlignCenter)

    layout.addWidget(val)
    layout.addWidget(lbl)
    return container, val, lbl


class WorkerInfoWidget(QWidget):
    """Dashboard page showing worker information, system metrics, and stats."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
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

        # -- Title --
        title = QLabel("Dashboard")
        title.setStyleSheet("color: #58a6ff; font-size: 22px; font-weight: 700;")
        layout.addWidget(title)

        # -- Row 1: Device + Model + Sensor info cards --
        row1 = QGridLayout()
        row1.setHorizontalSpacing(12)
        row1.setVerticalSpacing(12)

        # Device card
        dev_card = _card()
        dev_layout = QVBoxLayout(dev_card)
        dev_header = QLabel("DEVICE")
        dev_header.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 600;")
        self.lbl_device_id = QLabel("--")
        self.lbl_device_id.setStyleSheet("color: #f0f6fc; font-size: 18px; font-weight: 700;")
        self.lbl_hostname = QLabel("Hostname: --")
        self.lbl_hostname.setStyleSheet("color: #8b949e; font-size: 12px;")
        self.lbl_ip = QLabel("IP: --")
        self.lbl_ip.setStyleSheet("color: #8b949e; font-size: 12px;")
        dev_layout.addWidget(dev_header)
        dev_layout.addWidget(self.lbl_device_id)
        dev_layout.addWidget(self.lbl_hostname)
        dev_layout.addWidget(self.lbl_ip)
        dev_layout.addStretch()
        dev_card.setMinimumWidth(240)
        row1.addWidget(dev_card, 0, 0)

        # Model card
        model_card = _card()
        model_layout = QVBoxLayout(model_card)
        model_header = QLabel("MODEL")
        model_header.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 600;")
        self.lbl_model = QLabel("--")
        self.lbl_model.setStyleSheet("color: #f0f6fc; font-size: 16px; font-weight: 700;")
        self.lbl_backend = QLabel("Backend: --")
        self.lbl_backend.setStyleSheet("color: #8b949e; font-size: 12px;")
        self.lbl_model_status = QLabel("Status: --")
        self.lbl_model_status.setStyleSheet("color: #8b949e; font-size: 12px;")
        model_layout.addWidget(model_header)
        model_layout.addWidget(self.lbl_model)
        model_layout.addWidget(self.lbl_backend)
        model_layout.addWidget(self.lbl_model_status)
        model_layout.addStretch()
        model_card.setMinimumWidth(240)
        row1.addWidget(model_card, 0, 1)

        # Sensor card
        sensor_card = _card()
        sensor_layout = QVBoxLayout(sensor_card)
        sensor_header = QLabel("SENSOR")
        sensor_header.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 600;")
        self.lbl_sensor_status = QLabel("--")
        self.lbl_sensor_status.setStyleSheet("color: #f0f6fc; font-size: 16px; font-weight: 700;")
        self.lbl_sensor_type = QLabel("Type: --")
        self.lbl_sensor_type.setStyleSheet("color: #8b949e; font-size: 12px;")
        self.lbl_sensor_user_count = QLabel("Users in sensor: --")
        self.lbl_sensor_user_count.setStyleSheet("color: #8b949e; font-size: 12px;")
        sensor_layout.addWidget(sensor_header)
        sensor_layout.addWidget(self.lbl_sensor_status)
        sensor_layout.addWidget(self.lbl_sensor_type)
        sensor_layout.addWidget(self.lbl_sensor_user_count)
        sensor_layout.addStretch()
        sensor_card.setMinimumWidth(240)
        row1.addWidget(sensor_card, 0, 2)

        row1.setColumnStretch(0, 1)
        row1.setColumnStretch(1, 1)
        row1.setColumnStretch(2, 1)

        layout.addLayout(row1)

        # -- Row 2: System metrics --
        row2 = QGridLayout()
        row2.setHorizontalSpacing(12)
        row2.setVerticalSpacing(12)

        # CPU
        cpu_card = _card()
        cpu_layout = QVBoxLayout(cpu_card)
        cpu_h = QLabel("CPU")
        cpu_h.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 600;")
        self.lbl_cpu = QLabel("0%")
        self.lbl_cpu.setStyleSheet("color: #f0f6fc; font-size: 24px; font-weight: 700;")
        self.lbl_cpu.setAlignment(Qt.AlignCenter)
        self.bar_cpu = QProgressBar()
        self.bar_cpu.setRange(0, 100)
        self.bar_cpu.setValue(0)
        self.bar_cpu.setTextVisible(False)
        self.bar_cpu.setFixedHeight(8)
        self.lbl_cpu_temp = QLabel("Temp: --")
        self.lbl_cpu_temp.setStyleSheet("color: #8b949e; font-size: 12px;")
        self.lbl_cpu_temp.setAlignment(Qt.AlignCenter)
        cpu_layout.addWidget(cpu_h)
        cpu_layout.addWidget(self.lbl_cpu, alignment=Qt.AlignCenter)
        cpu_layout.addWidget(self.bar_cpu)
        cpu_layout.addWidget(self.lbl_cpu_temp)
        cpu_layout.addStretch()
        cpu_card.setMinimumWidth(200)
        row2.addWidget(cpu_card, 0, 0)

        # Memory
        mem_card = _card()
        mem_layout = QVBoxLayout(mem_card)
        mem_h = QLabel("MEMORY")
        mem_h.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 600;")
        self.lbl_mem = QLabel("0 / 0 MB")
        self.lbl_mem.setStyleSheet("color: #f0f6fc; font-size: 18px; font-weight: 700;")
        self.lbl_mem.setAlignment(Qt.AlignCenter)
        self.bar_mem = QProgressBar()
        self.bar_mem.setRange(0, 100)
        self.bar_mem.setValue(0)
        self.bar_mem.setTextVisible(False)
        self.bar_mem.setFixedHeight(8)
        mem_layout.addWidget(mem_h)
        mem_layout.addWidget(self.lbl_mem, alignment=Qt.AlignCenter)
        mem_layout.addWidget(self.bar_mem)
        mem_layout.addStretch()
        mem_card.setMinimumWidth(200)
        row2.addWidget(mem_card, 0, 1)

        # Disk
        disk_card = _card()
        disk_layout = QVBoxLayout(disk_card)
        disk_h = QLabel("DISK")
        disk_h.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 600;")
        self.lbl_disk = QLabel("0 / 0 GB")
        self.lbl_disk.setStyleSheet("color: #f0f6fc; font-size: 18px; font-weight: 700;")
        self.lbl_disk.setAlignment(Qt.AlignCenter)
        self.bar_disk = QProgressBar()
        self.bar_disk.setRange(0, 100)
        self.bar_disk.setValue(0)
        self.bar_disk.setTextVisible(False)
        self.bar_disk.setFixedHeight(8)
        disk_layout.addWidget(disk_h)
        disk_layout.addWidget(self.lbl_disk, alignment=Qt.AlignCenter)
        disk_layout.addWidget(self.bar_disk)
        disk_layout.addStretch()
        disk_card.setMinimumWidth(200)
        row2.addWidget(disk_card, 0, 2)

        # Uptime
        up_card = _card()
        up_layout = QVBoxLayout(up_card)
        up_h = QLabel("UPTIME")
        up_h.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 600;")
        self.lbl_uptime = QLabel("--")
        self.lbl_uptime.setStyleSheet("color: #f0f6fc; font-size: 24px; font-weight: 700;")
        self.lbl_uptime.setAlignment(Qt.AlignCenter)
        up_layout.addWidget(up_h)
        up_layout.addWidget(self.lbl_uptime, alignment=Qt.AlignCenter)
        up_layout.addStretch()
        up_card.setMinimumWidth(200)
        row2.addWidget(up_card, 0, 3)

        row2.setColumnStretch(0, 1)
        row2.setColumnStretch(1, 1)
        row2.setColumnStretch(2, 1)
        row2.setColumnStretch(3, 1)

        layout.addLayout(row2)

        # -- Row 3: Stats cards --
        row3 = QGridLayout()
        row3.setHorizontalSpacing(12)
        row3.setVerticalSpacing(12)

        stats_items = [
            ("0", "Enrolled Users"),
            ("0", "Enrolled Fingers"),
            ("0", "Verifications Today"),
            ("0.0 ms", "Avg Latency"),
        ]
        self.stat_values = []
        for val_text, label_text in stats_items:
            card = _card()
            card_layout = QVBoxLayout(card)
            stat_container, val_lbl, _ = _stat_widget(val_text, label_text)
            self.stat_values.append(val_lbl)
            card_layout.addWidget(stat_container)
            card.setMinimumWidth(180)
            row3.addWidget(card, 0, len(self.stat_values) - 1)

        for i in range(4):
            row3.setColumnStretch(i, 1)

        layout.addLayout(row3)
        layout.addStretch()

        scroll.setWidget(container)
        root_layout.addWidget(scroll)
        self._force_transparent_labels()

    def _force_transparent_labels(self) -> None:
        for label in self.findChildren(QLabel):
            label.setAttribute(Qt.WA_TranslucentBackground, True)

    # -- update methods called by MainWindow when health data arrives ---------

    def update_health(self, data: dict) -> None:
        """Update system health metrics from API response."""
        d = data.get("data", data)
        if not d:
            return

        self.lbl_device_id.setText(d.get("device_id", "--"))

        cpu = d.get("cpu_percent", 0)
        self.lbl_cpu.setText("{}%".format(int(cpu)))
        self.bar_cpu.setValue(int(cpu))

        cpu_temp = d.get("cpu_temp_c")
        if cpu_temp is not None:
            self.lbl_cpu_temp.setText("Temp: {}°C".format(cpu_temp))
        else:
            self.lbl_cpu_temp.setText("Temp: N/A")

        mem_used = d.get("memory_used_mb", 0)
        mem_total = d.get("memory_total_mb", 0)
        self.lbl_mem.setText("{:.0f} / {:.0f} MB".format(mem_used, mem_total))
        if mem_total > 0:
            self.bar_mem.setValue(int(mem_used * 100 / mem_total))

        disk_used = d.get("disk_used_gb", 0)
        disk_total = d.get("disk_total_gb", 0)
        self.lbl_disk.setText("{:.1f} / {:.1f} GB".format(disk_used, disk_total))
        if disk_total > 0:
            self.bar_disk.setValue(int(disk_used * 100 / disk_total))

        uptime_s = d.get("uptime_seconds", 0)
        hours = int(uptime_s // 3600)
        mins = int((uptime_s % 3600) // 60)
        self.lbl_uptime.setText("{}h {}m".format(hours, mins))

        model = d.get("active_model")
        self.lbl_model.setText(model if model else "No model")
        self.lbl_model_status.setText(
            "Status: Loaded" if model else "Status: Not loaded"
        )
        if model:
            self.lbl_model_status.setStyleSheet("color: #3fb950; font-size: 12px;")
        else:
            self.lbl_model_status.setStyleSheet("color: #d29922; font-size: 12px;")

        sensor_ok = d.get("sensor_connected", False)
        self.lbl_sensor_status.setText("Connected" if sensor_ok else "Disconnected")
        if sensor_ok:
            self.lbl_sensor_status.setStyleSheet(
                "color: #3fb950; font-size: 16px; font-weight: 700;"
            )
        else:
            self.lbl_sensor_status.setStyleSheet(
                "color: #f85149; font-size: 16px; font-weight: 700;"
            )

    def update_sensor(self, data: dict) -> None:
        """Update sensor-specific details."""
        d = data.get("data", data)
        if not d:
            return
        is_real = d.get("is_real_hardware", False)
        self.lbl_sensor_type.setText(
            "Type: USB Hardware" if is_real else "Type: Mock (simulated)"
        )
        uc = d.get("user_count")
        if uc is not None and uc >= 0:
            self.lbl_sensor_user_count.setText("Users in sensor: {}".format(uc))

    def update_stats(self, data: dict) -> None:
        """Update stats counters."""
        d = data.get("data", data)
        if not d:
            return
        vals = [
            str(d.get("enrolled_users", 0)),
            str(d.get("enrolled_fingers", 0)),
            str(d.get("verifications_today", 0)),
            "{:.1f} ms".format(d.get("avg_latency_ms", 0)),
        ]
        for i, v in enumerate(vals):
            if i < len(self.stat_values):
                self.stat_values[i].setText(v)

    def update_config(self, data: dict) -> None:
        """Update config details."""
        d = data.get("data", data)
        if not d:
            return
        import socket
        self.lbl_hostname.setText("Hostname: {}".format(socket.gethostname()))
        try:
            ip = socket.gethostbyname(socket.gethostname())
            self.lbl_ip.setText("IP: {}".format(ip))
        except Exception:
            self.lbl_ip.setText("IP: 127.0.0.1")
