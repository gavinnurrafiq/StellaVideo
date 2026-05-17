"""Scrubbing thumbnails — uses ffmpeg as an external decoder to render preview
frames on demand as the user hovers/drags the seek bar.

We tried using a second libmpv instance, but `screenshot-raw` requires an
active video output (VO) context that's tricky to set up off-screen. ffmpeg
gives reliable, frame-accurate single-frame extraction across all platforms
where mpv is already installed.

Frame-accurate seek strategy (hybrid):
    ffmpeg -ss <coarse> -i <file> -ss <fine> -frames:v 1 ...
The coarse `-ss` BEFORE `-i` does a fast keyframe seek; the fine `-ss` AFTER
`-i` advances through frames to the exact timestamp.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Qt, QPoint, QSize, Signal
from PySide6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QFont, QGuiApplication
)
from PySide6.QtWidgets import QWidget

from .utils import format_time


def find_ffmpeg() -> str | None:
    """Locate an ffmpeg executable on PATH or in well-known install locations."""
    for name in ("ffmpeg", "ffmpeg.exe"):
        path = shutil.which(name)
        if path:
            return path
    # Common Windows install paths
    candidates = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    ]
    for c in candidates:
        if Path(c).is_file():
            return c
    return None


class ThumbnailProvider(QObject):
    """Spawns ffmpeg to extract a single frame per request. Coalesces rapid
    requests via a debounce timer — only the latest position is processed
    while a previous one is still running."""

    thumbnailReady = Signal(float, object)   # (time_s, QPixmap)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None, *, thumb_width: int = 240,
                 debounce_ms: int = 80):
        super().__init__(parent)
        self._ffmpeg = find_ffmpeg()
        if not self._ffmpeg:
            raise RuntimeError(
                "ffmpeg not found. Install ffmpeg and ensure it is on PATH "
                "for scrub thumbnails to work."
            )

        self._loaded_path: str | None = None
        self._thumb_width = int(thumb_width)
        self._pending_time: float | None = None
        self._current_time: float | None = None
        self._proc: QProcess | None = None
        self._buf = bytearray()
        self._enabled = True

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(int(debounce_ms))
        self._timer.timeout.connect(self._process_pending)

    # ---- file lifecycle ----
    def load(self, path: str) -> None:
        # No setup needed — ffmpeg opens the file fresh on each request. We
        # just remember the path.
        self._loaded_path = path

    def clear(self) -> None:
        self._loaded_path = None
        self._kill_current()

    # ---- requests ----
    def request(self, time_s: float) -> None:
        if not self._enabled or self._loaded_path is None:
            return
        self._pending_time = max(0.0, float(time_s))
        if not self._timer.isActive():
            self._timer.start()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        if not enabled:
            self._pending_time = None
            self._timer.stop()

    # ---- worker ----
    def _process_pending(self) -> None:
        if self._pending_time is None or self._loaded_path is None:
            return
        if self._proc is not None and self._proc.state() != QProcess.NotRunning:
            # ffmpeg still working — re-arm timer; we'll get to the latest
            # pending time when it returns.
            self._timer.start()
            return
        t = self._pending_time
        self._pending_time = None
        self._current_time = t
        self._spawn_ffmpeg(t)

    def _spawn_ffmpeg(self, time_s: float) -> None:
        self._buf.clear()
        coarse, fine = self._split_seek(time_s)

        args = [
            "-loglevel", "error",
            "-nostdin",
            "-y",
        ]
        if coarse > 0.0:
            args += ["-ss", f"{coarse:.3f}"]
        args += ["-i", self._loaded_path]
        if fine > 0.0:
            args += ["-ss", f"{fine:.3f}"]
        args += [
            "-frames:v", "1",
            "-vf", f"scale={self._thumb_width}:-2",
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "-q:v", "5",
            "-",
        ]

        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.SeparateChannels)
        proc.readyReadStandardOutput.connect(self._on_data)
        proc.finished.connect(self._on_done)
        proc.errorOccurred.connect(self._on_error)
        self._proc = proc
        proc.start(self._ffmpeg, args)

    @staticmethod
    def _split_seek(time_s: float) -> tuple[float, float]:
        """Split a target time into (coarse, fine) for ffmpeg's hybrid seek.

        Keyframes are usually at most a few seconds apart, so a 2-second
        fine window covers any well-formed video. Long fine windows would
        decode too many frames; short windows risk missing the keyframe.
        """
        window = 2.0
        if time_s <= window:
            return 0.0, time_s
        coarse = time_s - window
        fine = window
        return coarse, fine

    def _on_data(self) -> None:
        if self._proc is None:
            return
        self._buf.extend(self._proc.readAllStandardOutput().data())

    def _on_done(self, exit_code: int, _exit_status: QProcess.ExitStatus) -> None:
        # Drain any remaining bytes (signal order vs final emit is undefined).
        if self._proc is not None:
            self._buf.extend(self._proc.readAllStandardOutput().data())

        if exit_code == 0 and len(self._buf) > 100 and self._current_time is not None:
            pm = QPixmap()
            if pm.loadFromData(bytes(self._buf), "JPEG"):
                self.thumbnailReady.emit(self._current_time, pm)
            else:
                self.failed.emit("could not decode JPEG from ffmpeg output")
        elif exit_code != 0:
            err = ""
            if self._proc is not None:
                err = bytes(self._proc.readAllStandardError().data()).decode(
                    "utf-8", errors="replace"
                ).strip()
            self.failed.emit(f"ffmpeg exit {exit_code}: {err[:200]}")

        self._buf.clear()
        self._proc = None

        # If a newer request landed while we were busy, process it now.
        if self._pending_time is not None:
            self._timer.start(0)

    def _on_error(self, error) -> None:
        self.failed.emit(f"ffmpeg process error: {error}")

    def _kill_current(self) -> None:
        if self._proc is not None and self._proc.state() != QProcess.NotRunning:
            self._proc.kill()
            self._proc.waitForFinished(500)
        self._proc = None
        self._buf.clear()

    # ---- cleanup ----
    def shutdown(self) -> None:
        self._timer.stop()
        self._pending_time = None
        self._kill_current()


class ThumbnailOverlay(QWidget):
    """Frameless tooltip-like widget that shows a preview frame + timestamp."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent,
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._pixmap: QPixmap | None = None
        self._time_text: str = ""
        self._caption_h = 22
        self._padding = 4
        self._placeholder_size = QSize(240, 135)
        self.hide()

    def update_thumbnail(self, pixmap: QPixmap, time_text: str) -> None:
        self._pixmap = pixmap
        self._time_text = time_text
        self._resize_to_content()
        self.update()

    def show_placeholder(self, time_text: str) -> None:
        self._time_text = time_text
        # Keep the last pixmap so the overlay doesn't flash empty between
        # frames while the user is actively scrubbing.
        self._resize_to_content()
        self.update()

    def clear(self) -> None:
        self._pixmap = None
        self._time_text = ""

    def position_above(self, global_x: int, anchor_y_top: int) -> None:
        """Anchor horizontally on global_x, sit above anchor_y_top."""
        self._resize_to_content()
        w = self.width()
        h = self.height()
        x = global_x - w // 2
        y = anchor_y_top - h - 8
        screen = QGuiApplication.screenAt(QPoint(global_x, anchor_y_top))
        if screen:
            geo = screen.availableGeometry()
            x = max(geo.left() + 4, min(x, geo.right() - w - 4))
            y = max(geo.top() + 4, y)
        self.move(x, y)

    def _resize_to_content(self) -> None:
        if self._pixmap is not None:
            w = self._pixmap.width()
            h = self._pixmap.height() + self._caption_h
        else:
            w = self._placeholder_size.width()
            h = self._caption_h + 4
        self.resize(w + self._padding * 2, h + self._padding * 2)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        pad = self._padding
        p.setPen(QColor("#262626"))
        p.setBrush(QColor(0, 0, 0, 240))
        p.drawRoundedRect(0, 0, self.width() - 1, self.height() - 1, 6, 6)
        if self._pixmap is not None:
            p.drawPixmap(pad, pad, self._pixmap)
            cap_y = pad + self._pixmap.height()
            cap_w = self._pixmap.width()
        else:
            cap_y = pad
            cap_w = self.width() - pad * 2
        f = QFont()
        f.setPointSize(10)
        f.setBold(True)
        p.setFont(f)
        p.setPen(Qt.white)
        p.drawText(pad, cap_y, cap_w, self._caption_h, Qt.AlignCenter, self._time_text)
        p.end()
