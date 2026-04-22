"""Shared UI helpers for the worker GUI."""

from typing import Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


_TONE_COLORS = {
    "default": "#c9d1d9",
    "muted": "#8b949e",
    "success": "#3fb950",
    "warning": "#d29922",
    "danger": "#f85149",
    "accent": "#6cb6ff",
}

_CARD_STYLES = {
    "default": ("#141c24", "#2b3642"),
    "success": ("#10281f", "#2ea043"),
    "warning": ("#2d220f", "#d29922"),
    "danger": ("#2b1417", "#f85149"),
    "accent": ("#132337", "#1f6feb"),
}


def make_page_header(title: str, description: str) -> QWidget:
    """Create a consistent page title block."""
    wrapper = QWidget()
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)

    title_label = QLabel(title)
    title_label.setObjectName("page_title")
    layout.addWidget(title_label)

    desc_label = QLabel(description)
    desc_label.setObjectName("page_description")
    desc_label.setWordWrap(True)
    layout.addWidget(desc_label)
    return wrapper


def make_card(title: Optional[str] = None, description: Optional[str] = None) -> Tuple[QFrame, QVBoxLayout]:
    """Create a standard content card and its body layout."""
    card = QFrame()
    card.setObjectName("panel_card")
    card.setProperty("card", True)

    layout = QVBoxLayout(card)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)

    if title:
        title_label = QLabel(title)
        title_label.setObjectName("section_title")
        layout.addWidget(title_label)

    if description:
        desc_label = QLabel(description)
        desc_label.setObjectName("section_description")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

    return card, layout


def make_metric_card(label: str, value: str = "--", helper: str = "") -> Tuple[QFrame, QLabel, QLabel]:
    """Create a compact metric card."""
    card, layout = make_card()
    layout.setSpacing(6)

    label_widget = QLabel(label.upper())
    label_widget.setObjectName("metric_label")
    layout.addWidget(label_widget)

    value_widget = QLabel(value)
    value_widget.setObjectName("metric_value")
    value_widget.setAlignment(Qt.AlignCenter)
    layout.addWidget(value_widget)

    helper_widget = QLabel(helper)
    helper_widget.setObjectName("metric_helper")
    helper_widget.setAlignment(Qt.AlignCenter)
    helper_widget.setWordWrap(True)
    layout.addWidget(helper_widget)

    return card, value_widget, helper_widget


def set_label_tone(label: QLabel, tone: str, size: int = 13, bold: bool = False) -> None:
    """Apply a semantic text color to a label."""
    color = _TONE_COLORS.get(tone, _TONE_COLORS["default"])
    weight = 700 if bold else 500
    label.setStyleSheet(
        "color: {color}; font-size: {size}px; font-weight: {weight};".format(
            color=color, size=size, weight=weight
        )
    )


def set_card_tone(frame: QFrame, tone: str = "default") -> None:
    """Apply a semantic card treatment for result panels."""
    background, border = _CARD_STYLES.get(tone, _CARD_STYLES["default"])
    frame.setStyleSheet(
        "QFrame {{ background-color: {background}; border: 1px solid {border}; "
        "border-radius: 14px; }}".format(
            background=background,
            border=border,
        )
    )


def set_preview_state(label: QLabel, active: bool) -> None:
    """Toggle preview border color for sensor images."""
    border = "#4b5563"
    text = "#6b7280"
    if active:
        border = "#3fb950"
        text = "#c9d1d9"
    label.setStyleSheet(
        "QLabel { background-color: #0f1620; border: 1px solid %s; "
        "border-radius: 16px; color: %s; }" % (border, text)
    )


def make_inline_stat(label: str, value: str) -> QWidget:
    """Create a small label/value row for summaries."""
    wrapper = QWidget()
    layout = QHBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    label_widget = QLabel(label)
    label_widget.setObjectName("inline_stat_label")
    layout.addWidget(label_widget)

    value_widget = QLabel(value)
    value_widget.setObjectName("inline_stat_value")
    value_widget.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    layout.addWidget(value_widget, stretch=1)
    return wrapper
