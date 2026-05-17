"""Periodic dominant-colour sampler.

Spawns ffmpeg every `interval_ms` to extract a tiny downscaled frame
from the currently-playing file at the current playback position, then
averages its pixels and emits the result as a `QColor`. Used to tint
the title-bar gradient with the colours that are on screen — the bar
shifts to reds during a sunset shot, blues underwater, etc.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from PySide6.QtGui import QColor, QImage


def find_ffmpeg() -> str | None:
    for name in ("ffmpeg", "ffmpeg.exe"):
        path = shutil.which(name)
        if path:
            return path
    for c in (r"C:\ffmpeg\bin\ffmpeg.exe",
              r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"):
        if Path(c).is_file():
            return c
    return None


class ColorSampler(QObject):
    """Samples the average colour of a tiny frame from the current video."""

    colorSampled = Signal(QColor)

    SAMPLE_SIZE = 32           # pixels per side — small for speed
    DEFAULT_INTERVAL_MS = 1500

    def __init__(self, parent: QObject | None = None,
                 interval_ms: int = DEFAULT_INTERVAL_MS):
        super().__init__(parent)
        self._ffmpeg = find_ffmpeg()
        self._path: str | None = None
        self._get_position: Callable[[], float] | None = None
        self._proc: QProcess | None = None
        self._buf = bytearray()

        self._timer = QTimer(self)
        self._timer.setInterval(int(interval_ms))
        self._timer.timeout.connect(self._sample)

    # ---- public api ----
    def start(self, path: str, position_getter: Callable[[], float]) -> None:
        if not self._ffmpeg:
            return
        self._path = path
        self._get_position = position_getter
        self._timer.start()
        # Take an immediate sample so the title bar gets a colour as soon
        # as the video frame is decoded.
        QTimer.singleShot(300, self._sample)

    def stop(self) -> None:
        self._timer.stop()
        self._path = None
        self._kill_current()

    def shutdown(self) -> None:
        self.stop()

    # ---- worker ----
    def _sample(self) -> None:
        if (not self._path or not self._ffmpeg
                or self._get_position is None):
            return
        if self._proc is not None and self._proc.state() != QProcess.NotRunning:
            return  # still busy

        try:
            position = float(self._get_position() or 0.0)
        except Exception:
            position = 0.0
        coarse = max(0.0, position - 1.0)
        fine = position - coarse

        args = [
            "-loglevel", "error",
            "-nostdin",
            "-y",
            "-an",                          # skip audio for speed
        ]
        if coarse > 0:
            args += ["-ss", f"{coarse:.3f}"]
        args += ["-i", self._path]
        if fine > 0:
            args += ["-ss", f"{fine:.3f}"]
        args += [
            "-frames:v", "1",
            "-vf", f"scale={self.SAMPLE_SIZE}:{self.SAMPLE_SIZE}",
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "-q:v", "8",
            "-",
        ]

        self._buf.clear()
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.SeparateChannels)
        proc.readyReadStandardOutput.connect(self._on_data)
        proc.finished.connect(self._on_done)
        self._proc = proc
        proc.start(self._ffmpeg, args)

    def _on_data(self) -> None:
        if self._proc is None:
            return
        self._buf.extend(self._proc.readAllStandardOutput().data())

    def _on_done(self, exit_code: int, _status) -> None:
        if self._proc is not None:
            self._buf.extend(self._proc.readAllStandardOutput().data())

        if exit_code == 0 and len(self._buf) > 100:
            img = QImage()
            if img.loadFromData(bytes(self._buf), "JPEG"):
                colour = self._average_color(img)
                if colour is not None:
                    self.colorSampled.emit(colour)
        self._buf.clear()
        self._proc = None

    def _kill_current(self) -> None:
        if self._proc is not None and self._proc.state() != QProcess.NotRunning:
            self._proc.kill()
            self._proc.waitForFinished(500)
        self._proc = None
        self._buf.clear()

    @staticmethod
    def _average_color(img: QImage) -> QColor | None:
        if img.isNull():
            return None
        img = img.convertToFormat(QImage.Format_RGB32)
        w, h = img.width(), img.height()
        if w == 0 or h == 0:
            return None
        r_total = g_total = b_total = 0
        count = 0
        # Sample a fixed-density grid (already 32x32 so just walk all pixels)
        for y in range(0, h, 2):
            for x in range(0, w, 2):
                c = img.pixelColor(x, y)
                r_total += c.red()
                g_total += c.green()
                b_total += c.blue()
                count += 1
        if count == 0:
            return None
        return QColor(r_total // count, g_total // count, b_total // count)
