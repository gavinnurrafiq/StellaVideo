"""Frameless title bar with animated gradient background.

Layout (left → right):
    Stella Video                                              [ — ] [ □ ] [ × ]

Title text on the left, window controls on the right (Windows convention).
The background is a slow horizontal gradient that subtly cycles hues in
the dark blue → purple range so the bar feels alive without distracting
the viewer.
"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal, QPoint, QTimer
from PySide6.QtGui import (
    QMouseEvent, QPainter, QColor, QLinearGradient, QFont, QPaintEvent
)
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QToolButton


class CustomTitleBar(QWidget):
    """Animated title bar replacing the native Windows chrome."""

    HEIGHT = 34

    minimizeRequested = Signal()
    maximizeToggleRequested = Signal()
    closeRequested = Signal()

    DEFAULT_BASE_COLOR = QColor.fromHsv(220, 130, 38)   # idle blue/purple

    def __init__(self, parent: QWidget | None = None, *, title: str = ""):
        super().__init__(parent)
        self.setObjectName("CustomTitleBar")
        self.setFixedHeight(self.HEIGHT)
        self.setAutoFillBackground(False)

        # Animation state
        self._phase: float = 0.0
        # Current and target colour for smooth tween. Title bar starts on
        # the idle palette; `set_base_color()` from the colour sampler
        # nudges the target toward video-tinted hues.
        self._base_color: QColor = QColor(self.DEFAULT_BASE_COLOR)
        self._target_color: QColor = QColor(self.DEFAULT_BASE_COLOR)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(33)            # ~30 fps
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_timer.start()

        # Drag-to-move state
        self._drag_active: bool = False
        self._drag_offset: QPoint = QPoint()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 0, 0)
        layout.setSpacing(0)

        # Title text on the left
        self.title_label = QLabel(title, self)
        f = QFont()
        f.setPointSize(9)
        f.setBold(True)
        self.title_label.setFont(f)
        self.title_label.setStyleSheet("color: #f3f4f6; background: transparent;")
        self.title_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        layout.addWidget(self.title_label)
        layout.addStretch(1)

        # Window controls on the right
        self.btn_min = self._make_btn("—", "Minimize")
        self.btn_max = self._make_btn("☐", "Maximize")
        self.btn_close = self._make_btn("✕", "Close", danger=True)
        for b in (self.btn_min, self.btn_max, self.btn_close):
            layout.addWidget(b)

        self.btn_min.clicked.connect(self.minimizeRequested)
        self.btn_max.clicked.connect(self.maximizeToggleRequested)
        self.btn_close.clicked.connect(self.closeRequested)

    def _make_btn(self, glyph: str, tooltip: str, *, danger: bool = False) -> QToolButton:
        b = QToolButton(self)
        b.setText(glyph)
        b.setToolTip(tooltip)
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedSize(46, self.HEIGHT)
        b.setAutoRaise(True)
        b.setObjectName("TitleBarCloseBtn" if danger else "TitleBarBtn")
        return b

    # ---- public api ----
    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_base_color(self, color: QColor) -> None:
        """Set the target colour for the title-bar gradient. The bar
        eases toward this colour over the next ~1 second so abrupt
        scene changes don't visually slam the gradient."""
        if color is None or not color.isValid():
            return
        self._target_color = QColor(color)

    def reset_base_color(self) -> None:
        """Return to the idle blue/purple palette (call when no video
        is loaded)."""
        self._target_color = QColor(self.DEFAULT_BASE_COLOR)

    # ---- animation ----
    def _on_anim_tick(self) -> None:
        # Tween toward target colour. t ≈ 0.06 gives ~1 second full ease.
        if self._base_color != self._target_color:
            self._base_color = self._lerp_color(
                self._base_color, self._target_color, 0.06
            )
        # Slow hue sweep around the base.
        self._phase = (self._phase + 0.0017) % 1.0
        self.update()

    @staticmethod
    def _lerp_color(c1: QColor, c2: QColor, t: float) -> QColor:
        return QColor(
            int(c1.red() + (c2.red() - c1.red()) * t),
            int(c1.green() + (c2.green() - c1.green()) * t),
            int(c1.blue() + (c2.blue() - c1.blue()) * t),
        )

    def paintEvent(self, _event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        # Pull the base HSV from the tweened colour, then sweep hue
        # slightly with the animation phase for a "living" feel.
        base_h, base_s, base_v, _ = self._base_color.getHsv()
        if base_h < 0:                       # achromatic frames return -1
            base_h = 220
        # Clamp saturation so the bar never becomes either washed out
        # or eye-burning — sampled colours can be extreme.
        sat = max(80, min(170, base_s))
        # Keep the bar always dark enough for the white title text.
        val = max(22, min(46, base_v))
        hue_offset = math.sin(self._phase * 2 * math.pi) * 18

        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.0,
            QColor.fromHsv(int(base_h + hue_offset) % 360, sat, val))
        grad.setColorAt(0.5,
            QColor.fromHsv(int(base_h + hue_offset + 28) % 360, sat, max(18, val - 6)))
        grad.setColorAt(1.0,
            QColor.fromHsv(int(base_h + hue_offset + 56) % 360, sat, max(16, val - 12)))
        p.fillRect(self.rect(), grad)

        p.setPen(QColor(0, 0, 0, 140))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.end()

    # ---- drag-to-move ----
    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.LeftButton:
            # If the click landed on a window-edge resize zone, hand off
            # to the main window so the OS can drive the resize loop.
            window = self.window()
            if hasattr(window, "_try_start_edge_resize"):
                if window._try_start_edge_resize(e):
                    return
            self._drag_active = True
            self._drag_offset = (
                e.globalPosition().toPoint()
                - self.window().frameGeometry().topLeft()
            )
            e.accept()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if not self._drag_active:
            return
        window = self.window()
        if window.isMaximized():
            ratio = e.position().x() / max(1, self.width())
            window.showNormal()
            new_w = window.width()
            x = e.globalPosition().toPoint().x() - int(ratio * new_w)
            y = e.globalPosition().toPoint().y() - self.height() // 2
            window.move(x, y)
            self._drag_offset = (
                e.globalPosition().toPoint() - window.frameGeometry().topLeft()
            )
            return
        window.move(e.globalPosition().toPoint() - self._drag_offset)
        e.accept()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        self._drag_active = False

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.LeftButton:
            self.maximizeToggleRequested.emit()
            e.accept()
