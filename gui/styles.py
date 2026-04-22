"""Minimal dark theme for the fingerprint worker GUI."""

DARK_THEME = """
QMainWindow {
    background-color: #0b1118;
}

QWidget {
    background-color: transparent;
    color: #d6dee7;
    font-family: "Segoe UI", "Noto Sans", "Liberation Sans", sans-serif;
    font-size: 14px;
}

QLabel {
    background-color: transparent;
}

QScrollArea {
    border: none;
}

QFrame[card="true"] {
    background-color: #141c24;
    border: 1px solid #2b3642;
    border-radius: 14px;
}

QLabel#page_title {
    color: #f0f6fc;
    font-size: 24px;
    font-weight: 700;
}

QLabel#page_description {
    color: #90a0b4;
    font-size: 13px;
}

QLabel#section_title {
    color: #f0f6fc;
    font-size: 16px;
    font-weight: 600;
}

QLabel#section_description {
    color: #90a0b4;
    font-size: 13px;
}

QLabel#metric_label {
    color: #7f8da1;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}

QLabel#metric_value {
    color: #f0f6fc;
    font-size: 30px;
    font-weight: 700;
}

QLabel#metric_helper {
    color: #90a0b4;
    font-size: 12px;
}

QLabel#inline_stat_label {
    color: #8b949e;
    font-size: 12px;
    font-weight: 600;
}

QLabel#inline_stat_value {
    color: #f0f6fc;
    font-size: 12px;
    font-weight: 600;
}

QPushButton {
    background-color: #1c2733;
    color: #e6edf3;
    border: 1px solid #334152;
    border-radius: 10px;
    padding: 9px 14px;
    min-height: 18px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #243242;
    border-color: #4d5f74;
}

QPushButton:pressed {
    background-color: #18212b;
}

QPushButton:disabled {
    background-color: #121820;
    color: #637083;
    border-color: #24303c;
}

QPushButton#btn_primary,
QPushButton#btn_accent {
    background-color: #2563eb;
    border-color: #2563eb;
    color: #ffffff;
}

QPushButton#btn_primary:hover,
QPushButton#btn_accent:hover {
    background-color: #3b82f6;
    border-color: #3b82f6;
}

QPushButton#btn_danger {
    background-color: #8f2d35;
    border-color: #8f2d35;
    color: #ffffff;
}

QPushButton#btn_danger:hover {
    background-color: #b33a44;
    border-color: #b33a44;
}

QLineEdit,
QSpinBox,
QComboBox {
    background-color: #0f1620;
    color: #f0f6fc;
    border: 1px solid #2f3a46;
    border-radius: 10px;
    padding: 8px 10px;
    min-height: 20px;
}

QLineEdit::placeholder {
    color: #6f7d90;
}

QLineEdit:focus,
QSpinBox:focus,
QComboBox:focus {
    border-color: #4c8dff;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #141c24;
    color: #e6edf3;
    border: 1px solid #334152;
    selection-background-color: #2563eb;
}

QTabWidget::pane {
    border: 1px solid #2b3642;
    border-radius: 12px;
    top: -1px;
    background-color: #101720;
}

QTabBar::tab {
    background-color: #141c24;
    color: #8b949e;
    border: 1px solid #2b3642;
    border-bottom: none;
    padding: 10px 16px;
    min-width: 120px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    margin-right: 6px;
}

QTabBar::tab:selected {
    background-color: #101720;
    color: #f0f6fc;
}

QTableWidget {
    background-color: #0f1620;
    color: #e6edf3;
    border: 1px solid #2b3642;
    border-radius: 12px;
    gridline-color: #1d2732;
    selection-background-color: #1e3a5f;
}

QTableWidget::item {
    padding: 8px 10px;
}

QHeaderView::section {
    background-color: #141c24;
    color: #90a0b4;
    border: none;
    border-bottom: 1px solid #2b3642;
    padding: 10px;
    font-weight: 700;
    font-size: 12px;
}

QProgressBar {
    background-color: #202b36;
    border: none;
    border-radius: 5px;
    height: 10px;
    text-align: center;
    color: transparent;
}

QProgressBar::chunk {
    background-color: #3fb950;
    border-radius: 5px;
}

QStatusBar {
    background-color: #101720;
    color: #8b949e;
    border-top: 1px solid #222e3b;
}

QScrollBar:vertical {
    background-color: #0b1118;
    width: 10px;
    border: none;
}

QScrollBar::handle:vertical {
    background-color: #2c3947;
    border-radius: 5px;
    min-height: 28px;
}

QScrollBar::handle:vertical:hover {
    background-color: #46576a;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background-color: #0b1118;
    height: 10px;
    border: none;
}

QScrollBar::handle:horizontal {
    background-color: #2c3947;
    border-radius: 5px;
    min-width: 28px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #46576a;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0px;
}
"""
