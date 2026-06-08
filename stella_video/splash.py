"""Splash screen shown while the main window and libmpv initialize.

The splash starts with the static logo PNG as a guaranteed first frame, then
switches to loop.mp4 only after mpv reports that the video has loaded. This
keeps the launch screen polished without allowing the native video surface to
cover the artwork with a blank/black frame.
"""
from __future__ import annotations

import time
from pathlib import Path

from .qt import (
    QApplication,
    QColor,
    QFont,
    QLabel,
    QObject,
    QPaintEvent,
    QPainter,
    QPainterPath,
    QPixmap,
    QRectF,
    QRegion,
    QSize,
    QStackedLayout,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
    Signal,
)

from . import __app_name__, __version__
from .player import _setup_libmpv_search_path
from .video_widget import VideoFrame


ASSETS_DIR = Path(__file__).resolve().parent / "assets"
LOGO_PATH = ASSETS_DIR / "logo.png"
LOOP_VIDEO_PATH = ASSETS_DIR / "loop.mp4"


def _rounded_logo_pixmap(path: Path, size: QSize, radius: int) -> QPixmap:
    source = QPixmap(str(path))
    if source.isNull():
        return QPixmap()

    scaled = source.scaled(
        size,
        Qt.KeepAspectRatioByExpanding,
        Qt.SmoothTransformation,
    )
    canvas = QPixmap(size)
    canvas.fill(Qt.transparent)

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

    clip = QPainterPath()
    clip.addRoundedRect(
        QRectF(0, 0, size.width(), size.height()),
        radius,
        radius,
    )
    painter.setClipPath(clip)
    painter.drawPixmap(
        (size.width() - scaled.width()) // 2,
        (size.height() - scaled.height()) // 2,
        scaled,
    )
    painter.end()
    return canvas


def _rounded_region(size: QSize, radius: int) -> QRegion:
    path = QPainterPath()
    path.addRoundedRect(
        QRectF(0, 0, size.width(), size.height()),
        radius,
        radius,
    )
    return QRegion(path.toFillPolygon().toPolygon())


class _SplashVideoSignals(QObject):
    ready = Signal()


class _SplashVideoPlayer:
    """Small silent mpv instance for the splash loop."""

    def __init__(self, wid: int, source: str, signals: _SplashVideoSignals):
        _setup_libmpv_search_path()
        import mpv

        self._signals = signals
        self._ready_emitted = False
        self._mpv = mpv.MPV(
            wid=str(int(wid)),
            vo="gpu,gpu-next,direct3d,opengl",
            hwdec="auto-safe",
            audio="no",
            mute=True,
            loop_file="inf",
            keep_open="yes",
            terminal=False,
            osc=False,
            input_default_bindings=False,
            input_vo_keyboard=False,
            input_cursor=False,
            cursor_autohide="no",
            ytdl=False,
            msg_level="all=no",
            video_sync="audio",
            interpolation="no",
            panscan=1.0,
        )

        @self._mpv.event_callback("file-loaded")
        def _file_loaded(_event):  # noqa: F811
            self._emit_ready_once()

        @self._mpv.property_observer("video-params")
        def _video_params(_name, value):  # noqa: F811
            if value:
                self._emit_ready_once()

        self._mpv.command("loadfile", source, "replace")

    def _emit_ready_once(self) -> None:
        if self._ready_emitted:
            return
        self._ready_emitted = True
        self._signals.ready.emit()

    def shutdown(self) -> None:
        try:
            self._mpv.terminate()
        except Exception:
            pass


class StellaSplashScreen(QWidget):
    """Frameless, translucent splash window with protected loop video."""

    PANEL_W = 420
    PANEL_H = 520
    LOGO_DIM = 280
    LOGO_RADIUS = 26

    def __init__(self, parent: QWidget | None = None):
        super().__init__(
            parent,
            Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(self.PANEL_W, self.PANEL_H)

        self._shown_at: float = 0.0
        self._min_visible_ms: int = 950
        self._video_player: _SplashVideoPlayer | None = None
        self._video_signals = _SplashVideoSignals(self)
        self._video_signals.ready.connect(self._on_video_ready)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 36, 40, 28)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignHCenter)

        self.artwork = QWidget(self)
        self.artwork.setFixedSize(QSize(self.LOGO_DIM, self.LOGO_DIM))
        self.artwork_stack = QStackedLayout(self.artwork)
        self.artwork_stack.setContentsMargins(0, 0, 0, 0)
        self.artwork_stack.setStackingMode(QStackedLayout.StackOne)

        self.logo_label = QLabel(self.artwork)
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setFixedSize(QSize(self.LOGO_DIM, self.LOGO_DIM))
        if LOGO_PATH.is_file():
            pix = _rounded_logo_pixmap(
                LOGO_PATH,
                QSize(self.LOGO_DIM, self.LOGO_DIM),
                self.LOGO_RADIUS,
            )
            if not pix.isNull():
                self.logo_label.setPixmap(pix)
        self.artwork_stack.addWidget(self.logo_label)

        self.video_frame: VideoFrame | None = None
        if LOOP_VIDEO_PATH.is_file():
            self.video_frame = VideoFrame(self.artwork)
            self.video_frame.setFixedSize(QSize(self.LOGO_DIM, self.LOGO_DIM))
            self.video_frame.setMinimumSize(QSize(self.LOGO_DIM, self.LOGO_DIM))
            self.video_frame.setAcceptDrops(False)
            self.video_frame.setFocusPolicy(Qt.NoFocus)
            self.video_frame.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.video_frame.setMask(
                _rounded_region(QSize(self.LOGO_DIM, self.LOGO_DIM), self.LOGO_RADIUS)
            )
            self.artwork_stack.addWidget(self.video_frame)

        self.artwork_stack.setCurrentWidget(self.logo_label)
        layout.addWidget(self.artwork, 0, Qt.AlignHCenter)

        self.name_label = QLabel(__app_name__, self)
        name_font = QFont()
        name_font.setPointSize(22)
        name_font.setBold(True)
        self.name_label.setFont(name_font)
        self.name_label.setStyleSheet("color: #e5e7eb; background: transparent;")
        self.name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.name_label)

        self.version_label = QLabel(f"v{__version__}", self)
        version_font = QFont()
        version_font.setPointSize(10)
        self.version_label.setFont(version_font)
        self.version_label.setStyleSheet("color: #9ca3af; background: transparent;")
        self.version_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.version_label)

        layout.addStretch(1)

        self.status_label = QLabel("Starting...", self)
        status_font = QFont()
        status_font.setPointSize(10)
        self.status_label.setFont(status_font)
        self.status_label.setStyleSheet("color: #9ca3af; background: transparent;")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

    def show_centered(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            x = geo.center().x() - self.width() // 2
            y = geo.center().y() - self.height() // 2
            self.move(x, y)
        self.show()
        self._shown_at = time.monotonic()
        QApplication.processEvents()
        self._start_video_loop()

    def set_message(self, message: str) -> None:
        self.status_label.setText(message)
        QApplication.processEvents()

    def finish(self, target_widget: QWidget | None = None) -> None:
        elapsed_ms = int((time.monotonic() - self._shown_at) * 1000)
        remaining = max(0, self._min_visible_ms - elapsed_ms)
        if remaining == 0:
            self._finish_now(target_widget)
        else:
            QTimer.singleShot(remaining, lambda: self._finish_now(target_widget))

    def _start_video_loop(self) -> None:
        if self.video_frame is None or self._video_player is not None:
            return
        try:
            self._video_player = _SplashVideoPlayer(
                self.video_frame.native_wid(),
                str(LOOP_VIDEO_PATH),
                self._video_signals,
            )
        except Exception:
            self._video_player = None

    def _on_video_ready(self) -> None:
        # Give the native renderer one beat after load before revealing it.
        QTimer.singleShot(180, self._show_video_frame)

    def _show_video_frame(self) -> None:
        if self._video_player is None or self.video_frame is None:
            return
        self.artwork_stack.setCurrentWidget(self.video_frame)

    def _finish_now(self, target_widget: QWidget | None) -> None:
        if self._video_player is not None:
            self._video_player.shutdown()
            self._video_player = None
        self.close()
        if target_widget is not None:
            target_widget.activateWindow()
            target_widget.raise_()

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 100))
        painter.drawRoundedRect(2, 4, self.width() - 4, self.height() - 4, 16, 16)

        painter.setBrush(QColor(0, 0, 0, 245))
        painter.drawRoundedRect(0, 0, self.width() - 4, self.height() - 6, 14, 14)

        painter.setPen(QColor(40, 40, 40, 230))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(0, 0, self.width() - 4, self.height() - 6, 14, 14)
        painter.end()
