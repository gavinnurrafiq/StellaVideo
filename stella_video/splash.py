"""Splash screen shown while the main window and libmpv initialize.

Renders a looping video (loop.mp4) inside a dark rounded panel, with the
app name, version, and a status line that callers can update while heavy
startup work runs. Falls back to a static logo PNG if the loop video or
libmpv is unavailable.
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QPaintEvent
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication

from . import __app_name__, __version__
from .video_widget import VideoFrame
from .player import _setup_libmpv_search_path


ASSETS_DIR = Path(__file__).resolve().parent / "assets"
LOGO_PATH = ASSETS_DIR / "logo.png"
LOOP_VIDEO_PATH = ASSETS_DIR / "loop.mp4"


class _SplashVideoPlayer:
    """Tiny libmpv instance that loops the splash video silently.

    Mirrors the BackgroundPlayer shape but is duplicated here so splash.py
    doesn't import from video_stack.py (which pulls in more than we need
    just to show a logo).
    """

    def __init__(self, wid: int, source: str):
        _setup_libmpv_search_path()
        import mpv

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
        try:
            self._mpv.command("loadfile", source, "replace")
        except Exception:
            pass

    def shutdown(self) -> None:
        try:
            self._mpv.terminate()
        except Exception:
            pass


class StellaSplashScreen(QWidget):
    """Frameless, translucent splash window with a looping video and a
    status line for startup progress."""

    PANEL_W = 420
    PANEL_H = 520
    VIDEO_DIM = 280       # square video viewport
    LOGO_DIM = 260        # fallback PNG size

    def __init__(self, parent: QWidget | None = None):
        super().__init__(
            parent,
            Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(self.PANEL_W, self.PANEL_H)

        self._shown_at: float = 0.0
        self._min_visible_ms: int = 900
        self._video_player: _SplashVideoPlayer | None = None
        self._use_video: bool = LOOP_VIDEO_PATH.is_file()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 36, 40, 28)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignHCenter)

        # Video viewport (or fallback static logo)
        if self._use_video:
            self.video_frame: VideoFrame | None = VideoFrame(self)
            # Splash shouldn't react to clicks or drags — disable the mouse
            # plumbing the regular VideoFrame ships with.
            self.video_frame.setAcceptDrops(False)
            self.video_frame.setFocusPolicy(Qt.NoFocus)
            self.video_frame.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.video_frame.setFixedSize(QSize(self.VIDEO_DIM, self.VIDEO_DIM))
            layout.addWidget(self.video_frame, 0, Qt.AlignHCenter)
            self.logo_label = None
        else:
            self.video_frame = None
            self.logo_label = QLabel(self)
            self.logo_label.setAlignment(Qt.AlignCenter)
            if LOGO_PATH.is_file():
                pix = QPixmap(str(LOGO_PATH))
                if not pix.isNull():
                    pix = pix.scaled(
                        QSize(self.LOGO_DIM, self.LOGO_DIM),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                    self.logo_label.setPixmap(pix)
            self.logo_label.setMinimumHeight(self.LOGO_DIM)
            layout.addWidget(self.logo_label)

        # App name
        self.name_label = QLabel(__app_name__, self)
        f = QFont()
        f.setPointSize(22)
        f.setBold(True)
        self.name_label.setFont(f)
        self.name_label.setStyleSheet("color: #e5e7eb; background: transparent;")
        self.name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.name_label)

        # Version
        self.version_label = QLabel(f"v{__version__}", self)
        vf = QFont()
        vf.setPointSize(10)
        self.version_label.setFont(vf)
        self.version_label.setStyleSheet("color: #9ca3af; background: transparent;")
        self.version_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.version_label)

        layout.addStretch(1)

        # Status / progress line
        self.status_label = QLabel("Starting…", self)
        sf = QFont()
        sf.setPointSize(10)
        self.status_label.setFont(sf)
        self.status_label.setStyleSheet("color: #9ca3af; background: transparent;")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

    # ---- public api ----
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

        # Attach libmpv now that the video frame's native window exists.
        if self._use_video and self.video_frame is not None and self._video_player is None:
            try:
                self._video_player = _SplashVideoPlayer(
                    self.video_frame.native_wid(),
                    str(LOOP_VIDEO_PATH),
                )
            except Exception:
                self._video_player = None   # silently fall through; panel stays black

    def set_message(self, message: str) -> None:
        self.status_label.setText(message)
        QApplication.processEvents()

    def finish(self, target_widget: QWidget | None = None) -> None:
        """Close the splash, respecting a minimum visible duration so the
        artwork doesn't flash by on a fast machine."""
        elapsed_ms = int((time.monotonic() - self._shown_at) * 1000)
        remaining = max(0, self._min_visible_ms - elapsed_ms)
        if remaining == 0:
            self._finish_now(target_widget)
        else:
            QTimer.singleShot(remaining, lambda: self._finish_now(target_widget))

    def _finish_now(self, target_widget: QWidget | None) -> None:
        if self._video_player is not None:
            self._video_player.shutdown()
            self._video_player = None
        self.close()
        if target_widget is not None:
            target_widget.activateWindow()
            target_widget.raise_()

    # ---- painting ----
    def paintEvent(self, _event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        # Subtle outer shadow ring
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 100))
        p.drawRoundedRect(2, 4, self.width() - 4, self.height() - 4, 16, 16)
        # Main dark panel
        p.setBrush(QColor(0, 0, 0, 245))
        p.drawRoundedRect(0, 0, self.width() - 4, self.height() - 6, 14, 14)
        # Thin highlight border
        p.setPen(QColor(40, 40, 40, 230))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(0, 0, self.width() - 4, self.height() - 6, 14, 14)
        p.end()
