"""Stacked video display — main video frame on top, looped backdrop behind.

The backdrop is bounded to the stack's own area (not the whole window),
because mpv paints with a D3D11 swapchain that doesn't respect child
window z-order — anything inside an mpv-painted widget gets erased every
frame. Keeping UI bars OUTSIDE the stack (in QMainWindow's slots) keeps
them visible.
"""
from __future__ import annotations

from pathlib import Path

from .qt import QColor, QPalette, QRect, Qt, Signal, QWidget

from .video_widget import VideoFrame
from .player import _setup_libmpv_search_path


ASSETS_DIR = Path(__file__).resolve().parent / "assets"
DEFAULT_BACKGROUND = ASSETS_DIR / "background.mp4"


class BackgroundPlayer:
    """Minimal libmpv instance that loops a single file with no audio/UI."""

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

    def pause(self) -> None:
        try:
            self._mpv["pause"] = True
        except Exception:
            pass

    def resume(self) -> None:
        try:
            self._mpv["pause"] = False
        except Exception:
            pass

    def shutdown(self) -> None:
        try:
            self._mpv.terminate()
        except Exception:
            pass


class VideoStack(QWidget):
    """Two native VideoFrames stacked: backdrop fills the widget, front
    frame is resized to match the current video aspect so the letterbox
    area exposes the looping backdrop. When a real video plays, the
    backdrop is hidden and the black palette of this widget shows
    through — solid black around the video for viewer comfort."""

    doubleClicked = Signal()
    leftClicked = Signal()
    rightClicked = Signal()
    mouseMoved = Signal()
    filesDropped = Signal(list)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumSize(320, 180)

        # When the animated backdrop is hidden during playback, the bare
        # palette of this widget shows in the letterbox area.
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor("#000000"))
        self.setAutoFillBackground(True)
        self.setPalette(pal)

        self.background_frame = VideoFrame(self)
        self.video_frame = VideoFrame(self)
        # The front frame must start hidden — otherwise its default-sized
        # native window paints a black rectangle on top of the backdrop
        # at startup, before any video is loaded. It gets sized and shown
        # in set_video_aspect() once the player reports real dimensions.
        self.video_frame.hide()

        self._video_aspect: float | None = None
        self._canvas_aspect: float = 16 / 9
        self._video_frame_visible: bool = False
        self._backdrop_visible: bool = True

        for vf in (self.background_frame, self.video_frame):
            vf.doubleClicked.connect(self.doubleClicked)
            vf.leftClicked.connect(self.leftClicked)
            vf.rightClicked.connect(self.rightClicked)
            vf.mouseMoved.connect(self.mouseMoved)
            vf.filesDropped.connect(self.filesDropped)

        self._relayout()

    # ---- public api ----
    def set_backdrop_visible(self, visible: bool) -> None:
        if visible == self._backdrop_visible:
            return
        self._backdrop_visible = visible
        self.background_frame.setVisible(visible)

    def set_video_aspect(self, aspect: float | None) -> None:
        if aspect is not None and aspect <= 0:
            aspect = None
        self._video_aspect = aspect
        if aspect is None:
            if self._video_frame_visible:
                self.video_frame.hide()
                self._video_frame_visible = False
        else:
            if not self._video_frame_visible:
                self.video_frame.show()
                self._video_frame_visible = True
        self._relayout()

    def set_canvas_aspect(self, aspect: float) -> None:
        if aspect <= 0:
            return
        self._canvas_aspect = aspect
        self._relayout()

    def has_video(self) -> bool:
        return self._video_aspect is not None

    # ---- layout ----
    def resizeEvent(self, event):
        self._relayout()
        super().resizeEvent(event)

    def _relayout(self) -> None:
        canvas = self._canvas_rect()
        self.background_frame.setGeometry(canvas)
        if self._video_aspect is None:
            return
        w = canvas.width()
        h = canvas.height()
        if h <= 0 or w <= 0:
            return
        container_ratio = w / h
        if container_ratio > self._video_aspect:
            vh = h
            vw = int(round(h * self._video_aspect))
        else:
            vw = w
            vh = int(round(w / self._video_aspect))
        x = canvas.x() + (w - vw) // 2
        y = canvas.y() + (h - vh) // 2
        self.video_frame.setGeometry(x, y, vw, vh)
        self.video_frame.raise_()

    def _canvas_rect(self):
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return self.rect()
        container_ratio = w / h
        if container_ratio > self._canvas_aspect:
            ch = h
            cw = int(round(h * self._canvas_aspect))
        else:
            cw = w
            ch = int(round(w / self._canvas_aspect))
        x = (w - cw) // 2
        y = (h - ch) // 2
        return QRect(x, y, cw, ch)
