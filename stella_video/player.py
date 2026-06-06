"""libmpv wrapper — emits Qt signals for property changes."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal


def _candidate_dll_dirs() -> list[Path]:
    """Directories to search for the libmpv shared library."""
    here = Path(__file__).resolve().parent          # .../stella_video/stella_video
    project = here.parent                            # .../stella_video
    return [
        project / "libs",
        here / "libs",
        project,
        Path.cwd() / "libs",
        Path.cwd(),
    ]


def _setup_libmpv_search_path() -> Path | None:
    """Add candidate directories to the DLL search path. Returns the first dir
    that actually contains a libmpv DLL, or None."""
    dll_names = ("libmpv-2.dll", "mpv-2.dll", "mpv-1.dll")
    found_dir: Path | None = None
    for d in _candidate_dll_dirs():
        if not d.is_dir():
            continue
        if any((d / n).is_file() for n in dll_names):
            found_dir = d
            if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(str(d))
                except (OSError, FileNotFoundError):
                    pass
            # Also prepend to PATH for older Python / ctypes fallbacks.
            os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
            break
    return found_dir


def _import_mpv():
    found = _setup_libmpv_search_path()
    try:
        import mpv  # type: ignore
        return mpv
    except OSError as e:
        hint_dir = Path(__file__).resolve().parent.parent / "libs"
        raise RuntimeError(
            "Failed to load libmpv shared library.\n\n"
            "Windows setup:\n"
            f"  1. Download libmpv-2.dll (64-bit) from\n"
            f"     https://sourceforge.net/projects/mpv-player-windows/files/libmpv/\n"
            f"     (pick the newest 'mpv-dev-x86_64-*.7z')\n"
            f"  2. Extract libmpv-2.dll into:\n"
            f"     {hint_dir}\n\n"
            "Linux:  sudo apt install libmpv2  (or libmpv-dev)\n"
            "macOS:  brew install mpv\n\n"
            f"Original error: {e}"
        ) from e
    except ImportError as e:
        raise RuntimeError(
            "python-mpv is not installed. Run:\n  pip install python-mpv"
        ) from e


class Player(QObject):
    """High-level wrapper around libmpv with Qt signals.

    Frame-accurate seeking is enabled by default (hr-seek=yes).
    """

    # State
    fileLoaded = Signal(str)             # path
    endOfFile = Signal()
    pausedChanged = Signal(bool)
    durationChanged = Signal(float)      # seconds
    positionChanged = Signal(float)      # seconds
    volumeChanged = Signal(int)          # 0-100+
    muteChanged = Signal(bool)
    speedChanged = Signal(float)
    aspectChanged = Signal(str)
    seekingChanged = Signal(bool)

    # Tracks / chapters
    tracksChanged = Signal(list)         # list of track dicts
    chaptersChanged = Signal(list)       # list of chapter dicts
    chapterChanged = Signal(int)         # current chapter index

    # Misc
    titleChanged = Signal(str)
    dimensionsChanged = Signal(int, int)   # display width, height (0,0 = unloaded)
    error = Signal(str)
    osdMessage = Signal(str)

    def __init__(self, wid: int, parent: QObject | None = None):
        super().__init__(parent)
        mpv = _import_mpv()
        self._mpv_mod = mpv

        # Create mpv instance embedded in a Qt widget by window-id
        self._mpv = mpv.MPV(
            wid=str(int(wid)),
            vo="gpu,gpu-next,direct3d,opengl",
            hwdec="auto-safe",
            keep_open="yes",          # don't quit at EOF — let UI control it
            osc=False,                # we draw our own controls
            input_default_bindings=False,
            input_vo_keyboard=False,
            input_cursor=False,
            cursor_autohide="no",
            hr_seek="yes",            # frame-accurate seeking
            hr_seek_framedrop="no",   # do not drop frames when seeking
            hr_seek_demuxer_offset=0.0,
            ytdl=True,
            sub_auto="fuzzy",
            volume=100,
            terminal=False,
            msg_level="all=warn",
        )

        self._duration: float = 0.0
        self._position: float = 0.0
        self._paused: bool = True
        self._volume: int = 100
        self._muted: bool = False
        self._speed: float = 1.0
        self._current_path: str | None = None
        self._dwidth: int = 0
        self._dheight: int = 0

        self._observe("pause", self._on_pause)
        self._observe("duration", self._on_duration)
        self._observe("time-pos", self._on_position)
        self._observe("volume", self._on_volume)
        self._observe("mute", self._on_mute)
        self._observe("speed", self._on_speed)
        self._observe("video-aspect-override", self._on_aspect)
        self._observe("seeking", self._on_seeking)
        self._observe("track-list", self._on_tracks)
        self._observe("chapter-list", self._on_chapters)
        self._observe("chapter", self._on_chapter)
        self._observe("media-title", self._on_title)
        self._observe("eof-reached", self._on_eof)
        self._observe("dwidth", self._on_dwidth)
        self._observe("dheight", self._on_dheight)

        @self._mpv.event_callback("file-loaded")
        def _file_loaded(event):  # noqa: F811
            path = self._safe_get("path")
            self._current_path = path
            if path:
                self.fileLoaded.emit(str(path))

        # NB: deliberately *not* emitting endOfFile from the "end-file"
        # event. That event also fires for non-natural reasons (`stop`,
        # `redirect`, etc.) — every loadfile-replace would trigger
        # auto-advance and add duplicates to the playlist. The
        # `eof-reached` property observer below only flips True when the
        # file actually reaches the end of playback.

    # ---- observation helpers ----
    def _observe(self, name: str, cb: Callable[[Any], None]) -> None:
        @self._mpv.property_observer(name)
        def _wrap(_n, value):
            try:
                cb(value)
            except Exception as e:  # noqa: BLE001
                self.error.emit(f"observer {name}: {e}")

    def _safe_get(self, name: str, default: Any = None) -> Any:
        # Use _get_property directly: MPV.__getitem__ first tries the option
        # namespace, which raises for runtime-only properties like "path".
        try:
            v = self._mpv._get_property(name)
            return default if v is None else v
        except Exception:
            return default

    def _safe_set(self, name: str, value: Any) -> None:
        try:
            self._mpv[name] = value
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"set {name}: {e}")

    # ---- property handlers ----
    def _on_pause(self, value):
        self._paused = bool(value)
        self.pausedChanged.emit(self._paused)

    def _on_duration(self, value):
        self._duration = float(value or 0.0)
        self.durationChanged.emit(self._duration)

    def _on_position(self, value):
        if value is None:
            return
        self._position = float(value)
        self.positionChanged.emit(self._position)

    def _on_volume(self, value):
        if value is None:
            return
        self._volume = int(round(float(value)))
        self.volumeChanged.emit(self._volume)

    def _on_mute(self, value):
        self._muted = bool(value)
        self.muteChanged.emit(self._muted)

    def _on_speed(self, value):
        if value is None:
            return
        self._speed = float(value)
        self.speedChanged.emit(self._speed)

    def _on_aspect(self, value):
        self.aspectChanged.emit(str(value) if value is not None else "")

    def _on_seeking(self, value):
        self.seekingChanged.emit(bool(value))

    def _on_tracks(self, value):
        self.tracksChanged.emit(list(value or []))

    def _on_chapters(self, value):
        self.chaptersChanged.emit(list(value or []))

    def _on_chapter(self, value):
        try:
            self.chapterChanged.emit(int(value) if value is not None else -1)
        except (TypeError, ValueError):
            self.chapterChanged.emit(-1)

    def _on_title(self, value):
        self.titleChanged.emit(str(value) if value else "")

    def _on_eof(self, value):
        if value:
            self.endOfFile.emit()

    def _on_dwidth(self, value):
        self._dwidth = int(value or 0)
        self.dimensionsChanged.emit(self._dwidth, self._dheight)

    def _on_dheight(self, value):
        self._dheight = int(value or 0)
        self.dimensionsChanged.emit(self._dwidth, self._dheight)

    # ---- public API ----
    @property
    def duration(self) -> float:
        return self._duration

    @property
    def position(self) -> float:
        return self._position

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def volume(self) -> int:
        return self._volume

    @property
    def muted(self) -> bool:
        return self._muted

    @property
    def speed(self) -> float:
        return self._speed

    @property
    def current_path(self) -> str | None:
        return self._current_path

    def load(self, path: str, *, append: bool = False) -> None:
        try:
            mode = "append-play" if append else "replace"
            self._mpv.command("loadfile", path, mode)
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"load: {e}")

    def play(self) -> None:
        self._safe_set("pause", False)

    def pause(self) -> None:
        self._safe_set("pause", True)

    def toggle_pause(self) -> None:
        self._safe_set("pause", not self._paused)

    def stop(self) -> None:
        # `keep-open=yes` makes mpv re-fire `file-loaded` for the same file
        # ~50ms after a plain stop, which would reset our app's "no video
        # loaded" state. Clearing the playlist first prevents the re-fire.
        try:
            self._mpv.command("playlist-clear")
        except Exception:
            pass
        try:
            self._mpv.command("stop")
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"stop: {e}")
        self._current_path = None
        self._dwidth = 0
        self._dheight = 0
        self.dimensionsChanged.emit(0, 0)

    def seek(self, seconds: float, *, exact: bool = True, absolute: bool = True) -> None:
        try:
            mode_ref = "absolute" if absolute else "relative"
            precision = "exact" if exact else "keyframes"
            self._mpv.command("seek", seconds, f"{mode_ref}+{precision}")
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"seek: {e}")

    def seek_relative(self, delta: float, *, exact: bool = False) -> None:
        self.seek(delta, exact=exact, absolute=False)

    def frame_step(self) -> None:
        try:
            self._mpv.command("frame-step")
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"frame-step: {e}")

    def frame_back_step(self) -> None:
        try:
            self._mpv.command("frame-back-step")
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"frame-back-step: {e}")

    def set_volume(self, value: int) -> None:
        self._safe_set("volume", max(0, min(200, int(value))))

    def set_mute(self, muted: bool) -> None:
        self._safe_set("mute", bool(muted))

    def toggle_mute(self) -> None:
        self.set_mute(not self._muted)

    def set_speed(self, value: float) -> None:
        self._safe_set("speed", max(0.1, min(8.0, float(value))))

    def set_aspect(self, ratio: str) -> None:
        # "" / "-1" for auto, or "16:9", "4:3", "2.35:1", etc.
        if ratio in ("", "auto"):
            self._safe_set("video-aspect-override", "-1")
        else:
            self._safe_set("video-aspect-override", ratio)

    def set_canvas_fit(self) -> None:
        self._safe_set("keepaspect", True)
        self._safe_set("panscan", 0.0)
        self._safe_set("video-aspect-override", "-1")

    # ---- audio / subtitle tracks ----
    def set_audio_track(self, track_id: int | str) -> None:
        self._safe_set("aid", track_id)

    def set_subtitle_track(self, track_id: int | str) -> None:
        self._safe_set("sid", track_id)

    def cycle_subtitle(self) -> None:
        try:
            self._mpv.command("cycle", "sub")
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"cycle sub: {e}")

    def add_subtitle(self, path: str) -> None:
        try:
            self._mpv.command("sub-add", path, "select")
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"sub-add: {e}")

    def set_subtitle_delay(self, seconds: float) -> None:
        self._safe_set("sub-delay", float(seconds))

    def set_audio_delay(self, seconds: float) -> None:
        self._safe_set("audio-delay", float(seconds))

    # ---- chapters ----
    def next_chapter(self) -> None:
        try:
            self._mpv.command("add", "chapter", 1)
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"chapter+: {e}")

    def prev_chapter(self) -> None:
        try:
            self._mpv.command("add", "chapter", -1)
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"chapter-: {e}")

    def goto_chapter(self, index: int) -> None:
        self._safe_set("chapter", int(index))

    # ---- video filters / adjustments ----
    def set_brightness(self, value: int) -> None:  # -100..100
        self._safe_set("brightness", int(value))

    def set_contrast(self, value: int) -> None:
        self._safe_set("contrast", int(value))

    def set_saturation(self, value: int) -> None:
        self._safe_set("saturation", int(value))

    def set_gamma(self, value: int) -> None:
        self._safe_set("gamma", int(value))

    def set_hue(self, value: int) -> None:
        self._safe_set("hue", int(value))

    def get_adjustment(self, name: str) -> int:
        return int(self._safe_get(name, 0) or 0)

    # ---- A-B loop ----
    def set_ab_loop_a(self, seconds: float | None) -> None:
        self._safe_set("ab-loop-a", "no" if seconds is None else float(seconds))

    def set_ab_loop_b(self, seconds: float | None) -> None:
        self._safe_set("ab-loop-b", "no" if seconds is None else float(seconds))

    def clear_ab_loop(self) -> None:
        self.set_ab_loop_a(None)
        self.set_ab_loop_b(None)

    # ---- screenshots ----
    def screenshot(self, path: str | None = None, *, include_subs: bool = True) -> None:
        try:
            kind = "subtitles" if include_subs else "video"
            if path:
                self._mpv.command("screenshot-to-file", path, kind)
            else:
                self._mpv.command("screenshot", kind)
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"screenshot: {e}")

    # ---- OSD ----
    def show_text(self, message: str, duration_ms: int = 1500) -> None:
        try:
            self._mpv.command("show-text", message, str(duration_ms))
            self.osdMessage.emit(message)
        except Exception:
            self.osdMessage.emit(message)

    # ---- cleanup ----
    def shutdown(self) -> None:
        try:
            self._mpv.terminate()
        except Exception:
            pass
