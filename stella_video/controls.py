"""Control bar — seek bar, play controls, volume, time display, speed."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize, QTimer, QRectF
from PySide6.QtGui import (
    QMouseEvent, QPainter, QColor, QPen, QIcon, QPixmap, QImage, QTransform,
    QLinearGradient, QPainterPath
)
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QSlider, QLabel,
    QComboBox, QToolButton, QSizePolicy
)

from .utils import format_time


ICONS_DIR = Path(__file__).resolve().parent / "assets" / "icons"


def load_icon(filename: str) -> QIcon:
    """Load a PNG icon from the assets folder. Returns an empty QIcon if missing."""
    path = ICONS_DIR / filename
    return QIcon(str(path)) if path.is_file() else QIcon()


def load_icon_flipped_h(filename: str) -> QIcon:
    """Load a PNG and mirror it horizontally — used to derive a 'previous'
    icon from the 'next' artwork so the visual style stays consistent."""
    path = ICONS_DIR / filename
    if not path.is_file():
        return QIcon()
    pix = QPixmap(str(path))
    if pix.isNull():
        return QIcon()
    flipped = pix.transformed(QTransform().scale(-1, 1), Qt.SmoothTransformation)
    return QIcon(flipped)


class SeekBar(QSlider):
    """Click-to-seek slider with hover preview tooltip and chapter marks."""

    seeked = Signal(float)        # seconds (absolute) on release
    hovered = Signal(float, int)  # (seconds, x_pos_global) during hover/drag
    mouseLeft = Signal()          # cursor left the slider area
    draggingChanged = Signal(bool)  # True while user is actively dragging

    SHINE_PERIOD_S = 2.5      # one full left-to-right sweep
    GROOVE_HEIGHT = 4         # must match the QSS rule

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.setRange(0, 1000)
        self.setSingleStep(1)
        self.setPageStep(10)
        self.setTracking(True)
        self.setMouseTracking(True)
        self._duration = 0.0
        self._dragging = False
        self._chapters: list[float] = []
        self.setMinimumHeight(22)

        # Animated shine overlay for the filled portion.
        self._anim_phase: float = 0.0
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(33)               # ~30 fps
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_timer.start()

    def set_duration(self, seconds: float) -> None:
        self._duration = max(0.0, float(seconds))

    def set_position(self, seconds: float) -> None:
        if self._dragging or self._duration <= 0:
            return
        ratio = max(0.0, min(1.0, seconds / self._duration))
        self.blockSignals(True)
        self.setValue(int(ratio * self.maximum()))
        self.blockSignals(False)

    def set_chapter_times(self, times: list[float]) -> None:
        self._chapters = list(times)
        self.update()

    def _x_to_seconds(self, x: int) -> float:
        if self._duration <= 0:
            return 0.0
        ratio = max(0.0, min(1.0, x / max(1, self.width())))
        return ratio * self._duration

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.LeftButton and self._duration > 0:
            self._dragging = True
            self.draggingChanged.emit(True)
            self._set_from_x(e.position().x())
            self.hovered.emit(self._x_to_seconds(e.position().x()), int(e.globalPosition().x()))
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._duration > 0:
            self.hovered.emit(self._x_to_seconds(e.position().x()), int(e.globalPosition().x()))
            if self._dragging:
                self._set_from_x(e.position().x())
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self.draggingChanged.emit(False)
            self.seeked.emit(self._value_to_seconds(self.value()))
        super().mouseReleaseEvent(e)

    def leaveEvent(self, event) -> None:
        self.mouseLeft.emit()
        super().leaveEvent(event)

    def _set_from_x(self, x: float) -> None:
        ratio = max(0.0, min(1.0, x / max(1, self.width())))
        self.setValue(int(ratio * self.maximum()))

    def _value_to_seconds(self, value: int) -> float:
        if self.maximum() <= 0:
            return 0.0
        return (value / self.maximum()) * self._duration

    def _on_anim_tick(self) -> None:
        # 33 ms / 2500 ms ≈ 0.0132 per tick
        self._anim_phase = (self._anim_phase + 33.0 / (self.SHINE_PERIOD_S * 1000.0)) % 1.0
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)        # groove background + handle
        if self._duration <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # ---- animated filled portion (sub-page) ----
        max_val = max(1, self.maximum())
        filled_ratio = self.value() / max_val
        if filled_ratio > 0:
            fill_w = max(1, int(filled_ratio * self.width()))
            groove_h = self.GROOVE_HEIGHT
            groove_y = (self.height() - groove_h) // 2

            base = QColor("#3b82f6")
            bright = QColor("#7dd3fc")           # pale sky-blue highlight
            phase = self._anim_phase
            band = 0.22                          # ±22% of filled width

            # Build colour stops with a brighter peak at `phase`.
            stops: list[tuple[float, QColor]] = []
            stops.append((0.0, base))
            for pos, colour in (
                (phase - band, base),
                (phase, bright),
                (phase + band, base),
            ):
                if 0.0 < pos < 1.0:
                    stops.append((pos, colour))
            stops.append((1.0, base))
            stops.sort(key=lambda s: s[0])

            grad = QLinearGradient(0, 0, fill_w, 0)
            seen = -1.0
            for pos, colour in stops:
                if pos > seen + 1e-4:
                    grad.setColorAt(pos, colour)
                    seen = pos

            path = QPainterPath()
            path.addRoundedRect(QRectF(0, groove_y, fill_w, groove_h), 2, 2)
            painter.fillPath(path, grad)

        # ---- chapter marks ----
        if self._chapters:
            painter.setRenderHint(QPainter.Antialiasing, False)
            pen = QPen(QColor("#ffd866"))
            pen.setWidth(2)
            painter.setPen(pen)
            h = self.height()
            for t in self._chapters:
                if t <= 0:
                    continue
                ratio = t / self._duration
                x = int(ratio * self.width())
                painter.drawLine(x, 2, x, h - 2)
        painter.end()


class IconButton(QToolButton):
    """Flat tool button that accepts either a QIcon or a Unicode glyph.

    Pass `icon=QIcon(...)` for pixmap-based buttons; otherwise `text` is used
    as a Unicode glyph fallback (kept for the few buttons that don't have
    PNG art yet — A-B loop, screenshot, mute, playlist, fullscreen).
    """

    def __init__(self, tooltip: str, parent=None, *,
                 icon: QIcon | None = None, text: str | None = None,
                 icon_size: int = 20):
        super().__init__(parent)
        if icon is not None and not icon.isNull():
            self.setIcon(icon)
            self.setIconSize(QSize(icon_size, icon_size))
            self.setToolButtonStyle(Qt.ToolButtonIconOnly)
        elif text is not None:
            self.setText(text)
        self.setToolTip(tooltip)
        self.setAutoRaise(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFixedSize(QSize(34, 34))


class ControlBar(QWidget):
    """Bottom control bar."""

    playToggleRequested = Signal()
    stopRequested = Signal()
    seekRequested = Signal(float)         # absolute seconds
    seekRelativeRequested = Signal(float)
    prevRequested = Signal()
    nextRequested = Signal()
    volumeChanged = Signal(int)
    muteToggleRequested = Signal()
    speedChanged = Signal(float)
    canvasOrientationChanged = Signal(str)
    fullscreenToggleRequested = Signal()
    playlistToggleRequested = Signal()
    screenshotRequested = Signal()
    abLoopRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ControlBar")
        # Mouse tracking + edge-resize hand-off (see mousePressEvent below)
        self.setMouseTracking(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 8)
        root.setSpacing(4)

        # ---- seek row ----
        seek_row = QHBoxLayout()
        seek_row.setSpacing(8)
        self.time_current = QLabel("00:00")
        self.time_current.setObjectName("TimeLabel")
        self.time_total = QLabel("--:--")
        self.time_total.setObjectName("TimeLabel")
        self.seek_bar = SeekBar()
        seek_row.addWidget(self.time_current)
        seek_row.addWidget(self.seek_bar, 1)
        seek_row.addWidget(self.time_total)
        root.addLayout(seek_row)

        # ---- buttons row ----
        btn_row = QHBoxLayout()
        btn_row.setSpacing(2)

        # Load icon set once so play↔pause toggle reuses the same QIcon objects.
        self._icon_play = load_icon("play.png")
        self._icon_pause = load_icon("pause.png")
        icon_next = load_icon("next.png")
        icon_prev = load_icon_flipped_h("next.png")   # mirror "next" for consistent style
        icon_back = load_icon("back.png")
        icon_fwd = load_icon("forward.png")
        icon_stop = load_icon("stop.png")

        self.btn_prev = IconButton("Previous (PgUp)", icon=icon_prev)
        self.btn_back = IconButton("Back 5s (Left)", icon=icon_back)
        self.btn_play = IconButton("Play / Pause (Space)", icon=self._icon_play, icon_size=24)
        self.btn_play.setFixedSize(QSize(42, 34))
        self.btn_fwd = IconButton("Forward 5s (Right)", icon=icon_fwd)
        self.btn_next = IconButton("Next (PgDown)", icon=icon_next)
        self.btn_stop = IconButton("Stop", icon=icon_stop)

        for b in (self.btn_prev, self.btn_back, self.btn_play,
                  self.btn_fwd, self.btn_next, self.btn_stop):
            btn_row.addWidget(b)

        btn_row.addSpacing(8)

        # speed
        self.speed_combo = QComboBox()
        self.speed_combo.setEditable(False)
        for label, value in (("0.25x", 0.25), ("0.5x", 0.5), ("0.75x", 0.75),
                             ("1.0x", 1.0), ("1.25x", 1.25), ("1.5x", 1.5),
                             ("1.75x", 1.75), ("2.0x", 2.0), ("3.0x", 3.0), ("4.0x", 4.0)):
            self.speed_combo.addItem(label, value)
        self.speed_combo.setCurrentIndex(3)
        self.speed_combo.setToolTip("Playback speed")
        self.speed_combo.setFixedWidth(78)
        btn_row.addWidget(self.speed_combo)

        self.canvas_combo = QComboBox()
        self.canvas_combo.addItem("Horizontal (Landscape - 16:9)", "landscape")
        self.canvas_combo.addItem("Vertikal (Portrait - 9:16)", "portrait")
        self.canvas_combo.setToolTip("Canvas orientation")
        self.canvas_combo.setFixedWidth(210)
        btn_row.addWidget(self.canvas_combo)

        # A-B loop
        self.btn_ab = IconButton("A-B Loop (L)", text="A↔B")
        btn_row.addWidget(self.btn_ab)

        # screenshot
        self.btn_shot = IconButton("Screenshot (S)", text="◉")
        btn_row.addWidget(self.btn_shot)

        btn_row.addStretch(1)

        # volume
        self.btn_mute = IconButton("Mute (M)", text="🔊")
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 150)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(110)
        self.volume_slider.setToolTip("Volume")
        self.volume_label = QLabel("100")
        self.volume_label.setObjectName("VolumeLabel")
        self.volume_label.setFixedWidth(28)
        self.volume_label.setAlignment(Qt.AlignCenter)
        btn_row.addWidget(self.btn_mute)
        btn_row.addWidget(self.volume_slider)
        btn_row.addWidget(self.volume_label)

        # playlist + fullscreen
        self.btn_playlist = IconButton("Playlist (Ctrl+L)", text="☰")
        self.btn_fs = IconButton("Fullscreen (F11)", text="⛶")
        btn_row.addSpacing(6)
        btn_row.addWidget(self.btn_playlist)
        btn_row.addWidget(self.btn_fs)

        root.addLayout(btn_row)

        # wire up
        self.btn_play.clicked.connect(self.playToggleRequested)
        self.btn_stop.clicked.connect(self.stopRequested)
        self.btn_back.clicked.connect(lambda: self.seekRelativeRequested.emit(-5.0))
        self.btn_fwd.clicked.connect(lambda: self.seekRelativeRequested.emit(5.0))
        self.btn_prev.clicked.connect(self.prevRequested)
        self.btn_next.clicked.connect(self.nextRequested)
        self.btn_mute.clicked.connect(self.muteToggleRequested)
        self.btn_fs.clicked.connect(self.fullscreenToggleRequested)
        self.btn_playlist.clicked.connect(self.playlistToggleRequested)
        self.btn_shot.clicked.connect(self.screenshotRequested)
        self.btn_ab.clicked.connect(self.abLoopRequested)
        self.seek_bar.seeked.connect(self.seekRequested)
        self.volume_slider.valueChanged.connect(self._on_volume_slider)
        self.speed_combo.currentIndexChanged.connect(self._on_speed_index)
        self.canvas_combo.currentIndexChanged.connect(self._on_canvas_orientation_index)

    # ---- updates from player state ----
    def update_position(self, seconds: float) -> None:
        self.seek_bar.set_position(seconds)
        self.time_current.setText(format_time(seconds))

    def update_duration(self, seconds: float) -> None:
        self.seek_bar.set_duration(seconds)
        self.time_total.setText(format_time(seconds))

    def update_paused(self, paused: bool) -> None:
        self.btn_play.setIcon(self._icon_play if paused else self._icon_pause)

    def update_volume(self, volume: int) -> None:
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(max(0, min(self.volume_slider.maximum(), volume)))
        self.volume_slider.blockSignals(False)
        self.volume_label.setText(str(volume))

    def update_mute(self, muted: bool) -> None:
        self.btn_mute.setText("🔇" if muted else "🔊")

    def update_speed(self, speed: float) -> None:
        # match nearest preset; otherwise leave combo as-is
        for i in range(self.speed_combo.count()):
            if abs(self.speed_combo.itemData(i) - speed) < 1e-3:
                self.speed_combo.blockSignals(True)
                self.speed_combo.setCurrentIndex(i)
                self.speed_combo.blockSignals(False)
                return

    def update_chapters(self, chapter_times: list[float]) -> None:
        self.seek_bar.set_chapter_times(chapter_times)

    def update_canvas_orientation(self, orientation: str) -> None:
        idx = self.canvas_combo.findData(orientation)
        if idx >= 0:
            self.canvas_combo.blockSignals(True)
            self.canvas_combo.setCurrentIndex(idx)
            self.canvas_combo.blockSignals(False)

    def _on_volume_slider(self, value: int) -> None:
        self.volume_label.setText(str(value))
        self.volumeChanged.emit(value)

    def _on_speed_index(self, idx: int) -> None:
        value = self.speed_combo.itemData(idx)
        if value is not None:
            self.speedChanged.emit(float(value))

    def _on_canvas_orientation_index(self, idx: int) -> None:
        value = self.canvas_combo.itemData(idx)
        if value is not None:
            self.canvasOrientationChanged.emit(str(value))

    # ---- frameless window resize hand-off ----
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            window = self.window()
            if hasattr(window, "_try_start_edge_resize"):
                if window._try_start_edge_resize(event):
                    return
        super().mousePressEvent(event)
