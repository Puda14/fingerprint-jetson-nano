"""Entry point for the PyQt5 GUI: python -m gui"""

from __future__ import annotations

import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> None:
    # Allow overriding via environment variable
    api_url = os.environ.get("WORKER_GUI_API_URL", "http://localhost:8000/api/v1")

    try:
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import Qt
    except ImportError:
        print("ERROR: PyQt5 is required. Install with:")
        print("  pip install PyQt5")
        print("  # or on Jetson Nano:")
        print("  sudo apt-get install python3-pyqt5")
        sys.exit(1)

    from gui.styles import DARK_THEME
    from gui.main_window import MainWindow

    # High-DPI support (for non-Jetson displays)
    try:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        pass  # Older Qt versions

    app = QApplication(sys.argv)
    app.setApplicationName("Fingerprint Worker GUI")
    app.setOrganizationName("MDGT")

    # Apply dark theme
    app.setStyleSheet(DARK_THEME)

    window = MainWindow(api_base_url=api_url)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
