"""Main window with sidebar navigation and page stack."""


import logging
from typing import Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from gui.api_client import ApiClient, ApiWorkerThread, HealthPollerThread
from gui.widgets.fingerprint_stream import FingerprintStreamWidget
from gui.widgets.register_panel import RegisterPanelWidget
from gui.widgets.verify_panel import VerifyPanelWidget
from gui.widgets.worker_info import WorkerInfoWidget

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window with sidebar navigation."""

    def __init__(
        self,
        api_base_url: str = "http://localhost:8000/api/v1",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.api_base_url = api_base_url
        self.client = ApiClient(base_url=api_base_url)

        # Build WebSocket URL from API URL
        ws_base = api_base_url.replace("http://", "ws://").replace("https://", "wss://")
        self.ws_stream_url = "{}/sensor/stream".format(ws_base)

        self.setWindowTitle("Fingerprint Jetson Nano Worker")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

        self._build_ui()
        self._setup_health_poller()
        self._initial_load()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # -- Sidebar --
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(240)
        sidebar.setStyleSheet(
            "QWidget#sidebar { background-color: #161b22; "
            "border-right: 1px solid #30363d; }"
        )
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 20, 14, 20)
        sidebar_layout.setSpacing(8)

        # App title
        app_title = QLabel("FP Worker")
        app_title.setObjectName("app_title")
        app_title.setStyleSheet(
            "color: #58a6ff; font-size: 20px; font-weight: 700; padding: 6px 6px 14px 6px;"
        )
        sidebar_layout.addWidget(app_title)

        # Navigation buttons
        nav_items = ["Dashboard", "Streaming", "Verify", "Register"]

        self.nav_buttons = []
        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)

        for i, label in enumerate(nav_items):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                """
                QPushButton {
                    background-color: transparent;
                    color: #8b949e;
                    border: none;
                    border-radius: 6px;
                    padding: 12px 14px;
                    text-align: left;
                    font-size: 15px;
                    font-weight: 600;
                    min-height: 40px;
                }
                QPushButton:hover {
                    background-color: #21262d;
                    color: #c9d1d9;
                }
                QPushButton:checked {
                    background-color: #1f6feb;
                    color: #ffffff;
                }
                """
            )
            self.btn_group.addButton(btn, i)
            sidebar_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sidebar_layout.addStretch()

        # Version label at bottom
        version_lbl = QLabel("v2.0.0")
        version_lbl.setStyleSheet("color: #484f58; font-size: 11px; padding: 4px;")
        version_lbl.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(version_lbl)

        main_layout.addWidget(sidebar)

        # -- Page stack --
        self.page_stack = QStackedWidget()
        self.page_stack.setStyleSheet("background-color: #0d1117;")

        # Create pages
        self.dashboard_page = WorkerInfoWidget()
        self.stream_page = FingerprintStreamWidget(ws_url=self.ws_stream_url)
        self.verify_page = VerifyPanelWidget(api_client=self.client)
        self.register_page = RegisterPanelWidget(api_client=self.client)

        self.page_stack.addWidget(self.dashboard_page)
        self.page_stack.addWidget(self.stream_page)
        self.page_stack.addWidget(self.verify_page)
        self.page_stack.addWidget(self.register_page)

        main_layout.addWidget(self.page_stack)

        # Connect navigation
        self.btn_group.buttonClicked[int].connect(self._switch_page)
        self.nav_buttons[0].setChecked(True)

        # -- Status bar --
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet(
            "QStatusBar { background-color: #161b22; color: #8b949e; "
            "border-top: 1px solid #30363d; font-size: 13px; padding: 4px 10px; }"
        )
        self.setStatusBar(self.status_bar)

        self.status_connection = QLabel("Connecting...")
        self.status_connection.setStyleSheet("color: #d29922; padding: 0 14px;")
        self.status_model = QLabel("Model: --")
        self.status_model.setStyleSheet("color: #8b949e; padding: 0 14px;")
        self.status_sensor = QLabel("Sensor: --")
        self.status_sensor.setStyleSheet("color: #8b949e; padding: 0 14px;")

        self.status_bar.addWidget(self.status_connection)
        self.status_bar.addWidget(self.status_model)
        self.status_bar.addWidget(self.status_sensor)

    def _switch_page(self, index: int) -> None:
        self.page_stack.setCurrentIndex(index)
        # Refresh data when switching to certain pages
        if index == 2:  # Verify
            self.verify_page.refresh_users()
        elif index == 3:  # Register
            self.register_page.refresh_users()

    # -- Health polling ------------------------------------------------------

    def _setup_health_poller(self) -> None:
        self._health_poller = HealthPollerThread(self.client, interval_sec=5.0)
        self._health_poller.health_received.connect(self._on_health)
        self._health_poller.connection_changed.connect(self._on_connection_change)
        self._health_poller.start()

    def _on_health(self, data: dict) -> None:
        success = data.get("success", False)
        if not success:
            return

        d = data.get("data", data)
        self.dashboard_page.update_health(data)

        # Update status bar
        model = d.get("active_model", None)
        self.status_model.setText(
            "Model: {}".format(model if model else "None")
        )

        sensor = d.get("sensor_connected", False)
        if sensor:
            self.status_sensor.setText("Sensor: Connected")
            self.status_sensor.setStyleSheet("color: #3fb950; padding: 0 12px;")
        else:
            self.status_sensor.setText("Sensor: Disconnected")
            self.status_sensor.setStyleSheet("color: #f85149; padding: 0 12px;")

        # Keep dashboard counters fresh (users/fingers/latency cards).
        self._refresh_dashboard_cards()

    def _refresh_dashboard_cards(self) -> None:
        """Refresh non-health dashboard data periodically."""
        # Prevent spawning overlapping workers if a previous call is still running.
        if hasattr(self, "_stats_worker") and self._stats_worker is not None and self._stats_worker.isRunning():
            return

        self._stats_worker = ApiWorkerThread(self.client.get_stats)
        self._stats_worker.finished.connect(self.dashboard_page.update_stats)
        self._stats_worker.start()

        if hasattr(self, "_sensor_worker") and self._sensor_worker is not None and self._sensor_worker.isRunning():
            return

        self._sensor_worker = ApiWorkerThread(self.client.get_sensor_status)
        self._sensor_worker.finished.connect(self.dashboard_page.update_sensor)
        self._sensor_worker.start()

    def _on_connection_change(self, connected: bool) -> None:
        if connected:
            self.status_connection.setText("Connected")
            self.status_connection.setStyleSheet("color: #3fb950; padding: 0 12px;")
        else:
            self.status_connection.setText("Disconnected")
            self.status_connection.setStyleSheet("color: #f85149; padding: 0 12px;")

    def _initial_load(self) -> None:
        """Load additional data on startup."""
        # Load stats + sensor once immediately; afterwards refreshed in _on_health.
        self._refresh_dashboard_cards()

        # Load config (for hostname/IP)
        self._config_worker = ApiWorkerThread(self.client.get_config)
        self._config_worker.finished.connect(self.dashboard_page.update_config)
        self._config_worker.start()

    # -- cleanup -------------------------------------------------------------

    def closeEvent(self, event) -> None:
        """Clean up threads on window close."""
        if hasattr(self, '_health_poller'):
            self._health_poller.stop()
            self._health_poller.wait(2000)

        self.stream_page.cleanup()
        self.verify_page.cleanup()
        event.accept()
