"""Dark theme QSS stylesheet for the fingerprint GUI application."""

DARK_THEME = """
/* ========== Global ========== */
QMainWindow, QWidget {
    background-color: #0d1117;
    color: #c9d1d9;
    font-family: "Segoe UI", "Noto Sans", "Liberation Sans", sans-serif;
    font-size: 13px;
}

/* ========== Sidebar ========== */
#sidebar {
    background-color: #161b22;
    border-right: 1px solid #30363d;
    min-width: 200px;
    max-width: 200px;
}

#sidebar QPushButton {
    background-color: transparent;
    color: #8b949e;
    border: none;
    border-radius: 6px;
    padding: 10px 16px;
    text-align: left;
    font-size: 14px;
    font-weight: 500;
}

#sidebar QPushButton:hover {
    background-color: #21262d;
    color: #c9d1d9;
}

#sidebar QPushButton:checked,
#sidebar QPushButton[active="true"] {
    background-color: #1f6feb;
    color: #ffffff;
}

#app_title {
    color: #58a6ff;
    font-size: 16px;
    font-weight: 700;
    padding: 16px;
}

/* ========== Cards ========== */
.card {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 16px;
}

/* ========== Labels ========== */
.section-title {
    color: #58a6ff;
    font-size: 18px;
    font-weight: 700;
    padding-bottom: 8px;
}

.stat-value {
    color: #f0f6fc;
    font-size: 28px;
    font-weight: 700;
}

.stat-label {
    color: #8b949e;
    font-size: 12px;
    font-weight: 500;
    text-transform: uppercase;
}

.success-text {
    color: #3fb950;
    font-weight: 600;
}

.error-text {
    color: #f85149;
    font-weight: 600;
}

.warning-text {
    color: #d29922;
    font-weight: 600;
}

/* ========== Buttons ========== */
QPushButton {
    background-color: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
    min-height: 32px;
}

QPushButton:hover {
    background-color: #30363d;
    border-color: #8b949e;
}

QPushButton:pressed {
    background-color: #1f6feb;
    border-color: #1f6feb;
    color: #ffffff;
}

QPushButton:disabled {
    background-color: #161b22;
    color: #484f58;
    border-color: #21262d;
}

QPushButton#btn_primary {
    background-color: #238636;
    border-color: #238636;
    color: #ffffff;
}

QPushButton#btn_primary:hover {
    background-color: #2ea043;
}

QPushButton#btn_danger {
    background-color: #da3633;
    border-color: #da3633;
    color: #ffffff;
}

QPushButton#btn_danger:hover {
    background-color: #f85149;
}

QPushButton#btn_accent {
    background-color: #1f6feb;
    border-color: #1f6feb;
    color: #ffffff;
}

QPushButton#btn_accent:hover {
    background-color: #388bfd;
}

/* ========== Inputs ========== */
QLineEdit, QSpinBox, QComboBox {
    background-color: #0d1117;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px 12px;
    min-height: 28px;
}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #1f6feb;
}

QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #161b22;
    color: #c9d1d9;
    border: 1px solid #30363d;
    selection-background-color: #1f6feb;
}

/* ========== Tables ========== */
QTableWidget {
    background-color: #0d1117;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    gridline-color: #21262d;
    selection-background-color: #1f6feb;
}

QTableWidget::item {
    padding: 6px 8px;
}

QHeaderView::section {
    background-color: #161b22;
    color: #8b949e;
    border: none;
    border-bottom: 1px solid #30363d;
    padding: 8px;
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
}

/* ========== Progress Bar ========== */
QProgressBar {
    background-color: #21262d;
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}

QProgressBar::chunk {
    background-color: #3fb950;
    border-radius: 4px;
}

/* ========== Scrollbar ========== */
QScrollBar:vertical {
    background-color: #0d1117;
    width: 10px;
    border: none;
}

QScrollBar::handle:vertical {
    background-color: #30363d;
    border-radius: 5px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #484f58;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background-color: #0d1117;
    height: 10px;
    border: none;
}

QScrollBar::handle:horizontal {
    background-color: #30363d;
    border-radius: 5px;
    min-width: 30px;
}

/* ========== Status Bar ========== */
QStatusBar {
    background-color: #161b22;
    color: #8b949e;
    border-top: 1px solid #30363d;
    font-size: 12px;
}

/* ========== Group Box ========== */
QGroupBox {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    margin-top: 16px;
    padding-top: 24px;
    font-weight: 600;
    color: #58a6ff;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

/* ========== Fingerprint viewer ========== */
#fingerprint_viewer {
    background-color: #161b22;
    border: 2px solid #30363d;
    border-radius: 8px;
    min-width: 256px;
    min-height: 256px;
}

#fingerprint_viewer[streaming="true"] {
    border-color: #3fb950;
}

/* ========== Result displays ========== */
#result_match {
    background-color: #0b3d2e;
    border: 2px solid #3fb950;
    border-radius: 12px;
    padding: 20px;
}

#result_no_match {
    background-color: #3d0b0b;
    border: 2px solid #f85149;
    border-radius: 12px;
    padding: 20px;
}
"""
