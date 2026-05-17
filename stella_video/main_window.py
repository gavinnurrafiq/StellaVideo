"""Main window — wires Player, VideoFrame, ControlBar, Playlist together."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSettings, QPoint, QEvent
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QIcon, QGuiApplication, QCursor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QDockWidget, QFileDialog, QMessageBox,
    QLabel, QMenu, QApplication, QStatusBar, QMenuBar
)

from . import __app_name__
from .player import Player
from .video_stack import VideoStack, BackgroundPlayer, DEFAULT_BACKGROUND
from .video_widget import VideoFrame
from .custom_title_bar import CustomTitleBar
from .controls import ControlBar
from .playlist import PlaylistPanel
from .dialogs import VideoAdjustmentsDialog, SyncDialog, AboutDialog
from .thumbnail import ThumbnailProvider, ThumbnailOverlay
from .color_sampler import ColorSampler
from .preferences import AppSettings, PreferencesDialog
from .utils import (
    format_time, is_media, is_subtitle,
    media_file_filter, subtitle_file_filter,
)


# RECENT_FILES_MAX is now read from AppSettings ("general/recent_files_max")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Frameless so we can substitute a custom Mac-style title bar
        # with an animated gradient. UI bars stay safely outside the
        # mpv-painted region.
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setWindowTitle(__app_name__)
        self.resize(1180, 720)
        self.setAcceptDrops(True)

        self._settings = QSettings("StellaVideo", "Stella Video")
        self._app_settings = AppSettings()
        self._recent: list[str] = self._load_recent()
        self._was_fullscreen = False
        self._ab_a: float | None = None
        self._ab_b: float | None = None
        self._adjust_dialog: VideoAdjustmentsDialog | None = None
        self._sync_dialog: SyncDialog | None = None

        # ===== central widget (regular container) =====
        # Plain QWidget so it isn't owned by mpv. mpv only paints into the
        # backdrop frame inside VideoStack, which is bounded to the middle
        # area — UI bars sit at the edges and won't be erased by mpv's
        # D3D11 swapchain (which doesn't respect child windows).
        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        self.video_stack = VideoStack(self)
        self.video_frame = self.video_stack.video_frame
        central_layout.addWidget(self.video_stack, 1)

        self.controls = ControlBar(self)
        central_layout.addWidget(self.controls)

        self.setCentralWidget(central)

        # Mac-style custom title bar — placed in QMainWindow's "menu
        # widget" slot so it appears above the menu bar / central widget,
        # in the position the native title bar used to occupy.
        self.title_bar = CustomTitleBar(self, title=__app_name__)
        self.title_bar.minimizeRequested.connect(self.showMinimized)
        self.title_bar.maximizeToggleRequested.connect(self._toggle_maximize)
        self.title_bar.closeRequested.connect(self.close)

        # Menu bar + status bar in QMainWindow's standard slots so they
        # stay outside the central widget (mpv can never paint over them).
        self._menubar = QMenuBar(self)
        # Combine title bar + menu bar in a single widget that sits in
        # QMainWindow's menu slot.
        _menu_container = QWidget(self)
        _menu_layout = QVBoxLayout(_menu_container)
        _menu_layout.setContentsMargins(0, 0, 0, 0)
        _menu_layout.setSpacing(0)
        _menu_layout.addWidget(self.title_bar)
        _menu_layout.addWidget(self._menubar)
        self.setMenuWidget(_menu_container)
        self._statusbar = QStatusBar(self)
        # Frameless windows need an explicit grip for the user to resize.
        self._statusbar.setSizeGripEnabled(True)
        self._status_info = QLabel("Ready")
        self._statusbar.addWidget(self._status_info, 1)
        self._status_seek_preview = QLabel("")
        self._statusbar.addPermanentWidget(self._status_seek_preview)
        self.setStatusBar(self._statusbar)

        # OSD label overlaid on the video stack
        self._osd = QLabel(self.video_stack)
        self._osd.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._osd.setStyleSheet(
            "color: white; background-color: rgba(0,0,0,160); "
            "padding: 6px 12px; border-radius: 6px; font-size: 12pt;"
        )
        self._osd.hide()
        self._osd_timer = QTimer(self)
        self._osd_timer.setSingleShot(True)
        self._osd_timer.timeout.connect(self._osd.hide)

        # Playlist dock (still uses QMainWindow's dock system)
        self.playlist = PlaylistPanel(self)
        self.dock_playlist = QDockWidget("Playlist", self)
        self.dock_playlist.setObjectName("PlaylistDock")
        self.dock_playlist.setWidget(self.playlist)
        self.dock_playlist.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_playlist)
        self.dock_playlist.hide()

        # Create the player AFTER the video frame is shown (winId requires native window).
        # We delay creation until after show().
        self._player: Player | None = None
        self._background_player: BackgroundPlayer | None = None
        self._thumbnail_provider: ThumbnailProvider | None = None
        self._thumbnail_overlay: ThumbnailOverlay | None = None
        self._last_thumb_time: float = -1.0
        self._color_sampler: ColorSampler | None = None
        # mpv's `keep-open=yes` causes it to re-fire `file-loaded` ~50ms
        # after a stop. We only honour the event when the user actually
        # asked to open something.
        self._expecting_file_load: bool = False
        # mpv fires `end-file` with reason="stop" when the user stops
        # playback. Suppress the playlist auto-advance in that case so
        # stop actually stops instead of jumping to the next item.
        self._suppress_next_eof: bool = False

        # Auto-hide UI during playback: bars (menu, controls, status) hide
        # after a couple of seconds of mouse inactivity and reappear on
        # any movement. Disabled when no video is loaded so the welcome
        # screen always shows the controls.
        self._ui_autohide_enabled: bool = False
        self._ui_visible: bool = True
        self._cursor_over_ui: bool = False
        self._ui_autohide_timer = QTimer(self)
        self._ui_autohide_timer.setSingleShot(True)
        self._ui_autohide_timer.setInterval(2000)
        self._ui_autohide_timer.timeout.connect(self._auto_hide_ui)
        # Resize-from-edges state (only matters with the frameless window).
        self._resize_cursor_set: bool = False
        # Application-wide event filter so we see mouse moves over the
        # title bar / menu / controls / video too. UI-hover Enter/Leave
        # is also routed through here.
        QApplication.instance().installEventFilter(self)
        # MouseMove only fires when a button is pressed unless the widget
        # has mouse tracking enabled. Recursively enable it so hovering
        # near window edges updates the resize cursor.
        self._enable_mouse_tracking(self)

        # Menus + actions
        self._build_menus()
        self._build_shortcuts()
        self._wire_signals()

        # Fullscreen cursor hide
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setSingleShot(True)
        self._cursor_timer.timeout.connect(self._hide_cursor_in_fullscreen)

        # Track menus get repopulated on tracksChanged
        self._audio_actions_group: QActionGroup | None = None
        self._subtitle_actions_group: QActionGroup | None = None

        # First-pass settings application (UI-only — player-side settings
        # are applied inside init_player(), which runs after winId exists).
        self._apply_settings_to_ui()

    # ============================================================
    # Player lifecycle
    # ============================================================
    def init_player(self) -> None:
        """Create the mpv player once the video frame has a native winId."""
        if self._player is not None:
            return
        try:
            self._player = Player(self.video_frame.native_wid(), parent=self)
        except RuntimeError as e:
            QMessageBox.critical(self, "libmpv error", str(e))
            QTimer.singleShot(0, self.close)
            return

        p = self._player
        p.fileLoaded.connect(self._on_file_loaded)
        p.endOfFile.connect(self._on_eof)
        p.pausedChanged.connect(self.controls.update_paused)
        p.durationChanged.connect(self.controls.update_duration)
        p.positionChanged.connect(self._on_position)
        p.volumeChanged.connect(self.controls.update_volume)
        p.muteChanged.connect(self.controls.update_mute)
        p.speedChanged.connect(self.controls.update_speed)
        p.tracksChanged.connect(self._on_tracks)
        p.chaptersChanged.connect(self._on_chapters)
        p.titleChanged.connect(self._on_title)
        p.dimensionsChanged.connect(self._on_player_dimensions)
        p.error.connect(lambda msg: self._statusbar.showMessage(msg, 5000))
        p.osdMessage.connect(self.show_osd)

        # Wire control bar -> player
        c = self.controls
        c.playToggleRequested.connect(p.toggle_pause)
        c.stopRequested.connect(self._action_stop)
        c.seekRequested.connect(lambda s: p.seek(s, exact=True))
        c.seekRelativeRequested.connect(lambda d: p.seek_relative(d, exact=False))
        c.prevRequested.connect(self._play_prev)
        c.nextRequested.connect(self._play_next)
        c.volumeChanged.connect(p.set_volume)
        c.muteToggleRequested.connect(p.toggle_mute)
        c.speedChanged.connect(p.set_speed)
        c.fullscreenToggleRequested.connect(self.toggle_fullscreen)
        c.playlistToggleRequested.connect(self.toggle_playlist)
        c.screenshotRequested.connect(self._action_screenshot)
        c.abLoopRequested.connect(self._action_ab_loop)

        self.playlist.playRequested.connect(lambda path: self._open_path(path, replace=True))

        # Stack forwards mouse events from both the front video frame and
        # the backdrop, so clicks on letterbox area still toggle playback.
        self.video_stack.doubleClicked.connect(self.toggle_fullscreen)
        self.video_stack.leftClicked.connect(self._on_video_left_click)
        self.video_stack.rightClicked.connect(self._show_video_context_menu)
        self.video_stack.mouseMoved.connect(self._on_video_mouse_moved)
        self.video_stack.filesDropped.connect(self._handle_dropped_paths)

        # Animated backdrop bound to the video-stack area (mpv repaints
        # destructively, so we keep it confined to the centre).
        if DEFAULT_BACKGROUND.is_file():
            try:
                self._background_player = BackgroundPlayer(
                    self.video_stack.background_frame.native_wid(),
                    str(DEFAULT_BACKGROUND),
                )
            except Exception as e:  # noqa: BLE001
                self._statusbar.showMessage(f"Backdrop disabled: {e}", 5000)

        # Thumbnail preview: second hidden mpv instance for scrubbing previews.
        try:
            self._thumbnail_provider = ThumbnailProvider(self, thumb_width=240)
            self._thumbnail_provider.thumbnailReady.connect(self._on_thumbnail_ready)
            self._thumbnail_overlay = ThumbnailOverlay(self)
        except Exception as e:  # noqa: BLE001
            # Non-fatal: app still works without scrub previews.
            self._statusbar.showMessage(f"Thumbnail preview disabled: {e}", 5000)

        # Reactive title bar — samples a tiny frame periodically and
        # tints the title gradient with the average colour.
        try:
            self._color_sampler = ColorSampler(self, interval_ms=1500)
            self._color_sampler.colorSampled.connect(self.title_bar.set_base_color)
        except Exception:
            self._color_sampler = None

        # Hide overlay when cursor leaves the seek bar (and not dragging).
        self.controls.seek_bar.mouseLeft.connect(self._hide_thumbnail_overlay)
        self.controls.seek_bar.draggingChanged.connect(self._on_seek_dragging)

        # Apply player-bound settings now that the Player exists.
        self._apply_settings_to_player()

    # ============================================================
    # Frameless window helpers
    # ============================================================
    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def closeEvent(self, event):
        self._save_recent()
        if self._color_sampler is not None:
            self._color_sampler.shutdown()
        if self._thumbnail_overlay is not None:
            self._thumbnail_overlay.hide()
        if self._thumbnail_provider is not None:
            self._thumbnail_provider.shutdown()
        if self._player is not None:
            self._player.shutdown()
        if self._background_player is not None:
            self._background_player.shutdown()
        super().closeEvent(event)

    # ============================================================
    # Menus
    # ============================================================
    def _build_menus(self) -> None:
        mb = self._menubar

        # File
        m_file = mb.addMenu("&File")
        self._act_open = m_file.addAction("&Open File…", self._action_open_file)
        self._act_open.setShortcut(QKeySequence.Open)
        m_file.addAction("Open &URL…", self._action_open_url).setShortcut("Ctrl+U")
        m_file.addAction("Open &Folder…", self._action_open_folder).setShortcut("Ctrl+Shift+O")
        m_file.addSeparator()
        self._menu_recent = m_file.addMenu("Recent Files")
        self._rebuild_recent_menu()
        m_file.addSeparator()
        m_file.addAction("Add Sub&title…", self._action_add_subtitle).setShortcut("Ctrl+T")
        m_file.addSeparator()
        m_file.addAction("&Preferences…", self._action_open_preferences).setShortcut("Ctrl+,")
        m_file.addSeparator()
        m_file.addAction("E&xit", self.close).setShortcut("Ctrl+Q")

        # Playback
        m_play = mb.addMenu("&Playback")
        m_play.addAction("Play / &Pause", self._action_toggle_play).setShortcut("Space")
        m_play.addAction("&Stop", self._action_stop).setShortcut("Ctrl+.")
        m_play.addSeparator()
        m_play.addAction("Seek -5s", lambda: self._seek_rel(-5)).setShortcut(QKeySequence(Qt.Key_Left))
        m_play.addAction("Seek +5s", lambda: self._seek_rel(5)).setShortcut(QKeySequence(Qt.Key_Right))
        m_play.addAction("Seek -30s", lambda: self._seek_rel(-30)).setShortcut("Shift+Left")
        m_play.addAction("Seek +30s", lambda: self._seek_rel(30)).setShortcut("Shift+Right")
        m_play.addAction("Seek -1min", lambda: self._seek_rel(-60)).setShortcut("Ctrl+Left")
        m_play.addAction("Seek +1min", lambda: self._seek_rel(60)).setShortcut("Ctrl+Right")
        m_play.addSeparator()
        m_play.addAction("Speed -", lambda: self._adjust_speed(-0.1)).setShortcut(QKeySequence("["))
        m_play.addAction("Speed +", lambda: self._adjust_speed(0.1)).setShortcut(QKeySequence("]"))
        m_play.addAction("Reset Speed", lambda: self._set_speed(1.0)).setShortcut(QKeySequence("Backspace"))
        m_play.addSeparator()
        m_play.addAction("A-B Loop", self._action_ab_loop).setShortcut("L")
        m_play.addAction("Clear A-B Loop", self._action_ab_clear).setShortcut("Shift+L")
        m_play.addSeparator()
        m_play.addAction("Previous Chapter", lambda: self._player and self._player.prev_chapter()).setShortcut("PgUp")
        m_play.addAction("Next Chapter", lambda: self._player and self._player.next_chapter()).setShortcut("PgDown")

        # Audio
        self._menu_audio = mb.addMenu("&Audio")
        self._menu_audio_tracks = self._menu_audio.addMenu("Audio Track")
        self._menu_audio.addSeparator()
        self._menu_audio.addAction("Volume +", lambda: self._adjust_volume(5)).setShortcut(QKeySequence(Qt.Key_Up))
        self._menu_audio.addAction("Volume -", lambda: self._adjust_volume(-5)).setShortcut(QKeySequence(Qt.Key_Down))
        self._menu_audio.addAction("Mute", lambda: self._player and self._player.toggle_mute()).setShortcut("M")
        self._menu_audio.addSeparator()
        self._menu_audio.addAction("Audio Delay -", lambda: self._adjust_audio_delay(-0.1)).setShortcut(QKeySequence("Ctrl+-"))
        self._menu_audio.addAction("Audio Delay +", lambda: self._adjust_audio_delay(0.1)).setShortcut(QKeySequence("Ctrl++"))

        # Subtitles
        self._menu_subs = mb.addMenu("&Subtitles")
        self._menu_sub_tracks = self._menu_subs.addMenu("Subtitle Track")
        self._menu_subs.addSeparator()
        self._menu_subs.addAction("Add Subtitle…", self._action_add_subtitle).setShortcut("Ctrl+T")
        self._menu_subs.addAction("Toggle Subtitles", lambda: self._player and self._player.cycle_subtitle()).setShortcut("V")
        self._menu_subs.addSeparator()
        self._menu_subs.addAction("Subtitle Delay -", lambda: self._adjust_sub_delay(-0.1)).setShortcut("Z")
        self._menu_subs.addAction("Subtitle Delay +", lambda: self._adjust_sub_delay(0.1)).setShortcut("X")
        self._menu_subs.addAction("Sync Dialog…", self._action_sync_dialog).setShortcut("Ctrl+Y")

        # Video
        m_video = mb.addMenu("&Video")
        m_video.addAction("Adjustments…", self._action_adjustments).setShortcut("Ctrl+E")
        m_video.addSeparator()
        m_aspect = m_video.addMenu("Aspect Ratio")
        aspect_group = QActionGroup(self)
        for label, value in (("Auto", "auto"), ("16:9", "16:9"), ("4:3", "4:3"),
                             ("2.35:1", "2.35:1"), ("2.39:1", "2.39:1"), ("1:1", "1:1")):
            a = m_aspect.addAction(label)
            a.setCheckable(True)
            a.setData(value)
            aspect_group.addAction(a)
            a.triggered.connect(lambda checked, v=value: self._player and self._player.set_aspect(v))
        aspect_group.actions()[0].setChecked(True)
        m_video.addSeparator()
        m_video.addAction("Screenshot", self._action_screenshot).setShortcut("S")
        m_video.addAction("Screenshot to file…", self._action_screenshot_to_file).setShortcut("Shift+S")

        # View
        m_view = mb.addMenu("Vie&w")
        self._act_fullscreen = m_view.addAction("Toggle &Fullscreen", self.toggle_fullscreen)
        self._act_fullscreen.setShortcut("F11")
        m_view.addAction("Toggle &Playlist", self.toggle_playlist).setShortcut("Ctrl+L")
        m_view.addSeparator()
        m_view.addAction("Resize to Video", self._action_resize_to_video).setShortcut("Ctrl+R")
        self._act_on_top = QAction("Always on Top", self)
        self._act_on_top.setCheckable(True)
        self._act_on_top.setShortcut("Ctrl+Shift+T")
        self._act_on_top.toggled.connect(self._action_toggle_on_top)
        m_view.addAction(self._act_on_top)

        # Help
        m_help = mb.addMenu("&Help")
        m_help.addAction("Keyboard Shortcuts", self._action_show_shortcuts).setShortcut("F1")
        m_help.addAction(f"About {__app_name__}", self._action_about)

    def _build_shortcuts(self) -> None:
        # Most shortcuts come from menu actions. Add a few extras that don't fit in menus.
        extras = [
            ("J", lambda: self._adjust_sub_delay(-0.1)),
            ("K", lambda: self._adjust_sub_delay(0.1)),
        ]
        for key, fn in extras:
            act = QAction(self)
            act.setShortcut(QKeySequence(key))
            act.triggered.connect(fn)
            self.addAction(act)

    def _wire_signals(self) -> None:
        self.controls.seek_bar.hovered.connect(self._on_seek_hover)

    # ============================================================
    # Recent files
    # ============================================================
    def _load_recent(self) -> list[str]:
        raw = self._settings.value("recent_files", [], type=list)
        return [str(x) for x in raw if x]

    def _save_recent(self) -> None:
        self._settings.setValue("recent_files", self._recent[:int(self._app_settings.get("general/recent_files_max"))])

    def _push_recent(self, path: str) -> None:
        if not path:
            return
        if path in self._recent:
            self._recent.remove(path)
        self._recent.insert(0, path)
        del self._recent[int(self._app_settings.get("general/recent_files_max")):]
        self._save_recent()
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self) -> None:
        self._menu_recent.clear()
        if not self._recent:
            no = self._menu_recent.addAction("(empty)")
            no.setEnabled(False)
            return
        for i, path in enumerate(self._recent):
            name = Path(path).name
            act = self._menu_recent.addAction(f"&{(i+1) % 10}. {name}")
            act.setToolTip(path)
            act.triggered.connect(lambda checked=False, p=path: self._open_path(p, replace=True))
        self._menu_recent.addSeparator()
        clr = self._menu_recent.addAction("Clear Recent Files")
        clr.triggered.connect(self._clear_recent)

    def _clear_recent(self) -> None:
        self._recent.clear()
        self._save_recent()
        self._rebuild_recent_menu()

    # ============================================================
    # File opening
    # ============================================================
    def _action_open_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Open Media", "", media_file_filter()
        )
        if not paths:
            return
        first = True
        for p in paths:
            self._open_path(p, replace=first, focus=False)
            first = False

    def _action_open_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open Folder")
        if not folder:
            return
        files = sorted(
            str(p) for p in Path(folder).iterdir()
            if p.is_file() and is_media(p)
        )
        if not files:
            QMessageBox.information(self, __app_name__, "No supported media in this folder.")
            return
        first = True
        for p in files:
            self._open_path(p, replace=first, focus=False)
            first = False

    def _action_open_url(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        url, ok = QInputDialog.getText(self, "Open URL", "Stream URL:")
        if ok and url.strip():
            self._open_path(url.strip(), replace=True)

    def _action_add_subtitle(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Subtitle", "", subtitle_file_filter()
        )
        if path and self._player:
            self._player.add_subtitle(path)
            self.show_osd(f"Subtitle: {Path(path).name}")

    def _open_path(self, path: str, *, replace: bool = True, focus: bool = True) -> None:
        if not self._player:
            return
        # Add to playlist
        if replace:
            self.playlist.clear()
        self.playlist.add_paths([path])
        # Play it
        self._expecting_file_load = True
        self._player.load(path, append=False)
        self._push_recent(path)
        if focus:
            self.video_frame.setFocus()

    def _handle_dropped_paths(self, paths: list[str]) -> None:
        media = [p for p in paths if is_media(p)]
        subs = [p for p in paths if is_subtitle(p)]
        if media:
            self.playlist.add_paths(media)
            self._open_path(media[0], replace=False, focus=True)
        for s in subs:
            if self._player:
                self._player.add_subtitle(s)
                self.show_osd(f"Subtitle: {Path(s).name}")

    # ============================================================
    # Playback actions
    # ============================================================
    def _action_toggle_play(self) -> None:
        if self._player:
            self._player.toggle_pause()

    def _action_stop(self) -> None:
        # Ignore any pending / spurious file-loaded events from mpv
        # (keep-open re-fires the same file after stop).
        self._expecting_file_load = False
        self._suppress_next_eof = True
        if self._color_sampler is not None:
            self._color_sampler.stop()
        self.title_bar.reset_base_color()
        if self._player:
            self._player.stop()
        self.controls.update_position(0)
        self.controls.update_duration(0)
        self.controls.update_paused(True)
        self._status_info.setText("Stopped")
        self.setWindowTitle(__app_name__)
        # mpv doesn't always re-fire dwidth/dheight on stop — force the
        # idle layout so the animated backdrop comes back.
        self._on_player_dimensions(0, 0)

    def _seek_rel(self, delta: float) -> None:
        if self._player:
            self._player.seek_relative(delta, exact=False)
            self.show_osd(("+" if delta >= 0 else "") + f"{int(delta)}s")

    def _adjust_volume(self, delta: int) -> None:
        if self._player:
            self._player.set_volume(self._player.volume + delta)
            self.show_osd(f"Volume: {self._player.volume}%")

    def _adjust_speed(self, delta: float) -> None:
        if self._player:
            new_speed = round(self._player.speed + delta, 2)
            self._player.set_speed(new_speed)
            self.show_osd(f"Speed: {new_speed:.2f}x")

    def _set_speed(self, speed: float) -> None:
        if self._player:
            self._player.set_speed(speed)
            self.show_osd(f"Speed: {speed:.2f}x")

    def _adjust_sub_delay(self, delta: float) -> None:
        if not self._player:
            return
        try:
            cur = float(self._player._safe_get("sub-delay", 0.0) or 0.0)
        except Exception:
            cur = 0.0
        new = round(cur + delta, 2)
        self._player.set_subtitle_delay(new)
        self.show_osd(f"Subtitle delay: {new:+.2f}s")

    def _adjust_audio_delay(self, delta: float) -> None:
        if not self._player:
            return
        try:
            cur = float(self._player._safe_get("audio-delay", 0.0) or 0.0)
        except Exception:
            cur = 0.0
        new = round(cur + delta, 2)
        self._player.set_audio_delay(new)
        self.show_osd(f"Audio delay: {new:+.2f}s")

    def _action_ab_loop(self) -> None:
        if not self._player:
            return
        pos = self._player.position
        if self._ab_a is None:
            self._ab_a = pos
            self._player.set_ab_loop_a(pos)
            self.show_osd(f"A-B: A set at {format_time(pos)}")
        elif self._ab_b is None:
            self._ab_b = pos
            self._player.set_ab_loop_b(pos)
            self.show_osd(f"A-B: B set at {format_time(pos)} — looping")
        else:
            self._action_ab_clear()

    def _action_ab_clear(self) -> None:
        self._ab_a = None
        self._ab_b = None
        if self._player:
            self._player.clear_ab_loop()
        self.show_osd("A-B loop cleared")

    def _action_screenshot(self) -> None:
        if self._player:
            self._player.screenshot()
            self.show_osd("Screenshot saved")

    def _action_screenshot_to_file(self) -> None:
        if not self._player:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Screenshot", "screenshot.png",
            "PNG (*.png);;JPEG (*.jpg);;WebP (*.webp)"
        )
        if path:
            self._player.screenshot(path)
            self.show_osd(f"Saved: {Path(path).name}")

    def _action_adjustments(self) -> None:
        if not self._player:
            return
        if self._adjust_dialog is None:
            initial = {k: self._player.get_adjustment(k)
                       for k in ("brightness", "contrast", "saturation", "gamma", "hue")}
            self._adjust_dialog = VideoAdjustmentsDialog(self, initial=initial)
            self._adjust_dialog.valueChanged.connect(self._on_adjustment_changed)
        self._adjust_dialog.show()
        self._adjust_dialog.raise_()
        self._adjust_dialog.activateWindow()

    def _on_adjustment_changed(self, key: str, value: int) -> None:
        if not self._player:
            return
        getattr(self._player, f"set_{key}")(value)

    def _action_sync_dialog(self) -> None:
        if not self._player:
            return
        if self._sync_dialog is None:
            self._sync_dialog = SyncDialog(
                self,
                sub_delay=float(self._player._safe_get("sub-delay", 0.0) or 0.0),
                audio_delay=float(self._player._safe_get("audio-delay", 0.0) or 0.0),
            )
            self._sync_dialog.subDelayChanged.connect(self._player.set_subtitle_delay)
            self._sync_dialog.audioDelayChanged.connect(self._player.set_audio_delay)
        self._sync_dialog.show()
        self._sync_dialog.raise_()
        self._sync_dialog.activateWindow()

    # ============================================================
    # View actions
    # ============================================================
    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            self.title_bar.show()
            self._menubar.show()
            self._statusbar.show()
            self.unsetCursor()
        else:
            self.showFullScreen()
            self.title_bar.hide()
            self._menubar.hide()
            self._statusbar.hide()
            self._restart_cursor_timer()

    def toggle_playlist(self) -> None:
        self.dock_playlist.setVisible(not self.dock_playlist.isVisible())

    def _action_resize_to_video(self) -> None:
        if not self._player:
            return
        try:
            w = int(self._player._safe_get("dwidth", 0) or 0)
            h = int(self._player._safe_get("dheight", 0) or 0)
        except Exception:
            w, h = 0, 0
        if w > 0 and h > 0:
            extra_h = self.controls.height() + self._menubar.height() + self._statusbar.height()
            self.resize(w, h + extra_h)

    def _action_toggle_on_top(self, checked: bool) -> None:
        flags = self.windowFlags()
        if checked:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    # ============================================================
    # Track menus (dynamic)
    # ============================================================
    def _on_tracks(self, tracks: list[dict]) -> None:
        # Audio
        self._menu_audio_tracks.clear()
        self._audio_actions_group = QActionGroup(self)
        a_none = self._menu_audio_tracks.addAction("None")
        a_none.setCheckable(True)
        a_none.triggered.connect(lambda: self._player and self._player.set_audio_track("no"))
        self._audio_actions_group.addAction(a_none)
        for t in tracks:
            if t.get("type") != "audio":
                continue
            label = self._format_track_label(t)
            act = self._menu_audio_tracks.addAction(label)
            act.setCheckable(True)
            tid = t.get("id")
            act.triggered.connect(lambda checked=False, _id=tid: self._player and self._player.set_audio_track(_id))
            if t.get("selected"):
                act.setChecked(True)
            self._audio_actions_group.addAction(act)

        # Subtitle
        self._menu_sub_tracks.clear()
        self._subtitle_actions_group = QActionGroup(self)
        s_none = self._menu_sub_tracks.addAction("None")
        s_none.setCheckable(True)
        s_none.triggered.connect(lambda: self._player and self._player.set_subtitle_track("no"))
        self._subtitle_actions_group.addAction(s_none)
        any_selected = False
        for t in tracks:
            if t.get("type") != "sub":
                continue
            label = self._format_track_label(t)
            act = self._menu_sub_tracks.addAction(label)
            act.setCheckable(True)
            tid = t.get("id")
            act.triggered.connect(lambda checked=False, _id=tid: self._player and self._player.set_subtitle_track(_id))
            if t.get("selected"):
                act.setChecked(True)
                any_selected = True
            self._subtitle_actions_group.addAction(act)
        if not any_selected:
            s_none.setChecked(True)

    @staticmethod
    def _format_track_label(track: dict) -> str:
        parts = [f"#{track.get('id', '?')}"]
        if track.get("title"):
            parts.append(str(track["title"]))
        if track.get("lang"):
            parts.append(f"[{track['lang']}]")
        if track.get("codec"):
            parts.append(f"({track['codec']})")
        return " ".join(parts)

    def _on_chapters(self, chapters: list[dict]) -> None:
        times = [float(c.get("time", 0.0)) for c in chapters]
        self.controls.update_chapters(times)

    # ============================================================
    # Player state handlers
    # ============================================================
    def _on_file_loaded(self, path: str) -> None:
        # mpv with `keep-open=yes` re-fires file-loaded for the same file
        # ~50ms after a stop. Honour the event only when the user actually
        # opened something.
        if not self._expecting_file_load:
            return
        self._expecting_file_load = False

        self.playlist.set_current_path(path)
        name = Path(path).name if not path.startswith(("http://", "https://")) else path
        self.setWindowTitle(f"{name} — {__app_name__}")
        self._status_info.setText(name)
        self._ab_a = self._ab_b = None
        # Sync the thumbnail decoder to the same file so scrub previews work.
        if self._thumbnail_provider is not None:
            self._thumbnail_provider.load(path)
        # Begin reactive colour sampling — title-bar gradient will follow
        # the average colour of whatever frame is currently on screen.
        if self._color_sampler is not None and self._player is not None:
            self._color_sampler.start(path, lambda: self._player.position)
        # mpv's dwidth/dheight observers may not re-fire on a stop->reload
        # cycle when the new file has the same dimensions as the previous
        # one. Re-poll once after the decoder warms up so the backdrop /
        # aspect layout always reflects the current file.
        QTimer.singleShot(250, self._reevaluate_video_dimensions)

    def _reevaluate_video_dimensions(self) -> None:
        if self._player is None:
            return
        # Race guard: a delayed re-eval from a previous load may fire after
        # the user has stopped playback. Skip it so we don't re-hide the
        # backdrop the stop handler just restored.
        if self._player.current_path is None:
            return
        w = int(self._player._safe_get("dwidth", 0) or 0)
        h = int(self._player._safe_get("dheight", 0) or 0)
        self._on_player_dimensions(w, h)

    def _on_eof(self) -> None:
        # User-initiated stop also fires end-file in mpv. Don't auto-advance
        # in that case — that turns stop into "skip to next item".
        if self._suppress_next_eof:
            self._suppress_next_eof = False
            return
        if not self._app_settings.get("playback/auto_advance"):
            return
        nxt = self.playlist.next_path(self._player.current_path if self._player else None)
        if nxt:
            self._open_path(nxt, replace=False, focus=False)

    def _on_position(self, seconds: float) -> None:
        self.controls.update_position(seconds)
        if self._player and self._player.duration > 0:
            self._status_info.setText(
                f"{format_time(seconds, True)} / {format_time(self._player.duration)}"
            )

    def _on_title(self, title: str) -> None:
        if title:
            self.setWindowTitle(f"{title} — {__app_name__}")

    def _on_player_dimensions(self, w: int, h: int) -> None:
        # Real video → hide the animated backdrop (letterbox area shows
        # the stack widget's black palette, calm for the viewer). Idle /
        # audio only → backdrop on, loop animation runs in the video area.
        has_video = w > 0 and h > 0
        if has_video:
            self.video_stack.set_video_aspect(w / h)
            self.video_stack.set_backdrop_visible(False)
            if self._background_player is not None:
                self._background_player.pause()
            self._set_ui_autohide(True)
        else:
            self.video_stack.set_video_aspect(None)
            self.video_stack.set_backdrop_visible(True)
            if self._background_player is not None:
                self._background_player.resume()
            self._set_ui_autohide(False)

    # ============================================================
    # UI auto-hide during playback
    # ============================================================
    def _set_ui_autohide(self, enabled: bool) -> None:
        self._ui_autohide_enabled = enabled
        if enabled:
            # Show UI immediately, then start the countdown.
            self._set_ui_visible(True)
            self._schedule_ui_hide()
        else:
            # Idle → always show, stop any pending auto-hide.
            self._ui_autohide_timer.stop()
            self._set_ui_visible(True)

    def _set_ui_visible(self, visible: bool) -> None:
        if visible == self._ui_visible:
            return
        self._ui_visible = visible
        self._menubar.setVisible(visible)
        self.controls.setVisible(visible)
        self._statusbar.setVisible(visible)

    def _schedule_ui_hide(self) -> None:
        if not self._ui_autohide_enabled or self._cursor_over_ui:
            return
        self._ui_autohide_timer.start()

    def _auto_hide_ui(self) -> None:
        if not self._ui_autohide_enabled or self._cursor_over_ui:
            return
        self._set_ui_visible(False)

    def eventFilter(self, obj, event):
        et = event.type()
        # UI hover (auto-hide pause / restart)
        if et == QEvent.Enter:
            if obj is self._menubar or obj is self.controls or obj is self._statusbar:
                self._cursor_over_ui = True
                self._ui_autohide_timer.stop()
        elif et == QEvent.Leave:
            if obj is self._menubar or obj is self.controls or obj is self._statusbar:
                self._cursor_over_ui = False
                self._schedule_ui_hide()
        # Edge-resize for frameless window
        elif et == QEvent.MouseMove:
            if isinstance(obj, QWidget) and obj.window() is self:
                if event.buttons() == Qt.NoButton:
                    self._update_edge_cursor(event)
        elif et == QEvent.MouseButtonPress:
            if (event.button() == Qt.LeftButton
                    and isinstance(obj, QWidget) and obj.window() is self):
                if self._try_start_edge_resize(event):
                    return True
        return super().eventFilter(obj, event)

    # ---- edge resize helpers ----
    RESIZE_MARGIN = 8     # pixels from window border that count as "an edge"

    @staticmethod
    def _enable_mouse_tracking(widget: QWidget) -> None:
        """Recursively turn on mouseTracking so MouseMove events fire on
        hover (not only when a button is held). Necessary for the edge
        resize cursor to follow the mouse."""
        widget.setMouseTracking(True)
        for child in widget.findChildren(QWidget):
            child.setMouseTracking(True)

    # Qt.Edge values reproduced as a plain int bitmask so we don't depend
    # on PySide6's flag-type quirks across versions.
    _EDGE_LEFT = 1     # Qt.LeftEdge
    _EDGE_RIGHT = 2    # Qt.RightEdge
    _EDGE_TOP = 4      # Qt.TopEdge
    _EDGE_BOTTOM = 8   # Qt.BottomEdge

    def _edge_at(self, global_pos: QPoint) -> int:
        if self.isMaximized() or self.isFullScreen():
            return 0
        pos = self.mapFromGlobal(global_pos)
        if not self.rect().contains(pos):
            return 0
        m = self.RESIZE_MARGIN
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        edges = 0
        if x <= m:
            edges |= self._EDGE_LEFT
        elif x >= w - m:
            edges |= self._EDGE_RIGHT
        if y <= m:
            edges |= self._EDGE_TOP
        elif y >= h - m:
            edges |= self._EDGE_BOTTOM
        return edges

    @classmethod
    def _cursor_for_edge(cls, edges: int):
        tl = cls._EDGE_LEFT | cls._EDGE_TOP
        br = cls._EDGE_RIGHT | cls._EDGE_BOTTOM
        tr = cls._EDGE_RIGHT | cls._EDGE_TOP
        bl = cls._EDGE_LEFT | cls._EDGE_BOTTOM
        if edges == tl or edges == br:
            return Qt.SizeFDiagCursor
        if edges == tr or edges == bl:
            return Qt.SizeBDiagCursor
        if edges in (cls._EDGE_LEFT, cls._EDGE_RIGHT):
            return Qt.SizeHorCursor
        if edges in (cls._EDGE_TOP, cls._EDGE_BOTTOM):
            return Qt.SizeVerCursor
        return None

    def _update_edge_cursor(self, event) -> None:
        edges = self._edge_at(event.globalPosition().toPoint())
        cursor = self._cursor_for_edge(edges) if edges else None
        if cursor is not None:
            self.setCursor(cursor)
            self._resize_cursor_set = True
        elif self._resize_cursor_set:
            self.unsetCursor()
            self._resize_cursor_set = False

    @classmethod
    def _edges_int_to_qt(cls, edges: int):
        """Build a Qt.Edges flag value to hand to startSystemResize."""
        result = Qt.Edge(0) if hasattr(Qt, "Edge") else Qt.LeftEdge & 0
        if edges & cls._EDGE_LEFT:
            result |= Qt.LeftEdge
        if edges & cls._EDGE_RIGHT:
            result |= Qt.RightEdge
        if edges & cls._EDGE_TOP:
            result |= Qt.TopEdge
        if edges & cls._EDGE_BOTTOM:
            result |= Qt.BottomEdge
        return result

    def _try_start_edge_resize(self, event) -> bool:
        edges = self._edge_at(event.globalPosition().toPoint())
        if not edges:
            return False
        handle = self.windowHandle()
        if handle is None:
            return False
        try:
            return bool(handle.startSystemResize(self._edges_int_to_qt(edges)))
        except Exception:
            return False

    def _on_seek_hover(self, seconds: float, x_global: int) -> None:
        self._status_seek_preview.setText(format_time(seconds))
        if self._thumbnail_overlay is None:
            return
        # Place overlay above the seek bar at the cursor's global X.
        bar = self.controls.seek_bar
        anchor_top = bar.mapToGlobal(QPoint(0, 0)).y()
        # Show placeholder immediately so user gets feedback; thumbnail fills in.
        self._thumbnail_overlay.show_placeholder(format_time(seconds, show_ms=True))
        self._thumbnail_overlay.position_above(x_global, anchor_top)
        if not self._thumbnail_overlay.isVisible():
            self._thumbnail_overlay.show()
            self._thumbnail_overlay.raise_()
        self._last_thumb_time = seconds
        if self._thumbnail_provider is not None:
            self._thumbnail_provider.request(seconds)

    def _on_thumbnail_ready(self, time_s: float, pixmap) -> None:
        if self._thumbnail_overlay is None or not self._thumbnail_overlay.isVisible():
            return
        # Only refresh if this thumbnail is still relevant (cursor near same time).
        if abs(time_s - self._last_thumb_time) > 0.5 and not self.controls.seek_bar._dragging:
            return
        self._thumbnail_overlay.update_thumbnail(pixmap, format_time(time_s, show_ms=True))

    def _hide_thumbnail_overlay(self) -> None:
        # Keep visible while the user is dragging even if cursor leaves bar
        # (e.g., dragging slightly above/below the slider).
        if self.controls.seek_bar._dragging:
            return
        if self._thumbnail_overlay is not None and self._thumbnail_overlay.isVisible():
            self._thumbnail_overlay.hide()

    def _on_seek_dragging(self, dragging: bool) -> None:
        if not dragging:
            # Drag ended — hide overlay shortly after to let user see the chosen frame.
            QTimer.singleShot(250, self._hide_thumbnail_overlay)

    # ============================================================
    # Prev / Next navigation
    #
    # When the playlist has more than one entry and the current file is in
    # it, walk the playlist. Otherwise navigate the folder the current file
    # lives in, sorted with natural-numeric order so "Episode 02" still
    # comes before "Episode 10".
    # ============================================================
    def _play_prev(self) -> None:
        self._navigate(direction=-1)

    def _play_next(self) -> None:
        self._navigate(direction=1)

    def _navigate(self, *, direction: int) -> None:
        if not self._player:
            return
        current = self._player.current_path
        if not current:
            return

        # Honour an explicit playlist with multiple entries first.
        playlist_paths = self.playlist.paths()
        if len(playlist_paths) > 1 and current in playlist_paths:
            target = (self.playlist.next_path(current) if direction > 0
                      else self.playlist.prev_path(current))
            if target:
                self._open_path(target, replace=False, focus=False)
                self.show_osd(f"{'Next' if direction > 0 else 'Previous'}: {Path(target).name}")
            return

        # Folder navigation: find the neighbouring media file in the same dir.
        target = self._find_folder_neighbour(current, direction)
        if target:
            self._open_path(target, replace=True, focus=False)
            self.show_osd(f"{'Next' if direction > 0 else 'Previous'}: {Path(target).name}")
        else:
            edge = "last" if direction > 0 else "first"
            self.show_osd(f"Already at {edge} file in folder")

    @staticmethod
    def _natural_sort_key(name: str) -> list:
        import re
        return [
            int(chunk) if chunk.isdigit() else chunk.lower()
            for chunk in re.split(r"(\d+)", name)
        ]

    def _find_folder_neighbour(self, current_path: str, direction: int) -> str | None:
        """Return the path of the previous/next media file alphabetically
        (natural order) in the same folder as `current_path`, or None at
        boundaries / for URLs / inaccessible folders."""
        try:
            p = Path(current_path)
        except (OSError, ValueError):
            return None
        # URLs and non-existent paths get None — Path.is_file is False for both.
        if not p.is_file():
            return None
        try:
            folder = p.parent
            siblings = sorted(
                (f for f in folder.iterdir() if f.is_file() and is_media(f)),
                key=lambda f: self._natural_sort_key(f.name),
            )
        except (OSError, PermissionError):
            return None
        if not siblings:
            return None
        try:
            current_resolved = p.resolve()
        except OSError:
            current_resolved = p
        idx = -1
        for i, f in enumerate(siblings):
            try:
                if f.resolve() == current_resolved:
                    idx = i
                    break
            except OSError:
                continue
        if idx < 0:
            return None
        new_idx = idx + direction
        if 0 <= new_idx < len(siblings):
            return str(siblings[new_idx])
        return None

    # ============================================================
    # Video frame interactions
    # ============================================================
    def _on_video_left_click(self) -> None:
        # single click — defer slightly so double-click can intercept
        # mpv-style: pause on click is configurable; here we keep it click=pause
        if self._player:
            self._player.toggle_pause()

    def _show_video_context_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction(self._act_open)
        menu.addSeparator()
        menu.addAction("Play / Pause", self._action_toggle_play)
        menu.addAction("Stop", self._action_stop)
        menu.addSeparator()
        menu.addAction("Screenshot", self._action_screenshot)
        menu.addAction("Adjustments…", self._action_adjustments)
        menu.addSeparator()
        menu.addAction("Fullscreen", self.toggle_fullscreen)
        menu.addAction("Playlist", self.toggle_playlist)
        menu.exec(QCursor.pos())

    def _on_video_mouse_moved(self) -> None:
        # Any movement during playback resurrects the UI and resets the
        # hide countdown.
        if self._ui_autohide_enabled:
            self._set_ui_visible(True)
            self._schedule_ui_hide()
        if self.isFullScreen():
            self.unsetCursor()
            self._restart_cursor_timer()

    def _restart_cursor_timer(self) -> None:
        self._cursor_timer.start(2000)

    def _hide_cursor_in_fullscreen(self) -> None:
        if self.isFullScreen():
            self.setCursor(Qt.BlankCursor)

    # ============================================================
    # OSD
    # ============================================================
    def show_osd(self, text: str, duration_ms: int = 1500) -> None:
        self._osd.setText(text)
        self._osd.adjustSize()
        margin = 16
        self._osd.move(margin, margin)
        self._osd.show()
        self._osd.raise_()
        self._osd_timer.start(duration_ms)

    # ============================================================
    # Drag & drop on the main window (outside video frame)
    # ============================================================
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.toLocalFile()]
        if paths:
            self._handle_dropped_paths(paths)
            e.acceptProposedAction()

    # ============================================================
    # Help dialogs
    # ============================================================
    # ============================================================
    # Preferences
    # ============================================================
    def _action_open_preferences(self) -> None:
        dlg = PreferencesDialog(self._app_settings, self)
        dlg.settingsApplied.connect(self._on_settings_applied)
        dlg.exec()

    def _on_settings_applied(self) -> None:
        self._apply_settings_to_ui()
        self._apply_subtitle_styling_to_player()

    def _apply_settings_to_ui(self) -> None:
        """Live settings that only touch UI state."""
        s = self._app_settings
        self._ui_autohide_timer.setInterval(int(s.get("interface/autohide_delay")))
        # If user disables autohide, ensure UI is shown.
        if not s.get("interface/autohide_enabled"):
            self._ui_autohide_timer.stop()
            if self._ui_autohide_enabled:
                # Force show now; autohide-enabled flag itself is set per-file
                self._set_ui_visible(True)
        # Title bar animation toggle
        if hasattr(self, "title_bar"):
            anim_on = bool(s.get("interface/title_bar_animation"))
            if anim_on and not self.title_bar._anim_timer.isActive():
                self.title_bar._anim_timer.start()
            elif not anim_on and self.title_bar._anim_timer.isActive():
                self.title_bar._anim_timer.stop()
            # Reactive sampler toggle
            if not s.get("interface/reactive_title_bar"):
                if self._color_sampler is not None:
                    self._color_sampler.stop()
                self.title_bar.reset_base_color()
            elif (self._color_sampler is not None and self._player is not None
                  and self._player.current_path):
                self._color_sampler.start(
                    self._player.current_path,
                    lambda: self._player.position,
                )
        # Backdrop animation toggle
        if self._background_player is not None:
            if s.get("interface/backdrop_animation"):
                # Resume only if currently idle (no video playing)
                if self._player is None or self._player.current_path is None:
                    self._background_player.resume()
            else:
                self._background_player.pause()
        # Recent files max — truncate if user lowered the cap.
        max_recent = int(s.get("general/recent_files_max"))
        if len(self._recent) > max_recent:
            self._recent = self._recent[:max_recent]
            self._save_recent()
            self._rebuild_recent_menu()

    def _apply_settings_to_player(self) -> None:
        """Settings that need a live player (volume default, etc.)."""
        if self._player is None:
            return
        s = self._app_settings
        mpv = self._player._mpv
        try:
            self._player.set_volume(int(s.get("playback/default_volume")))
        except Exception:
            pass
        try:
            self._player.set_speed(float(s.get("playback/default_speed")))
        except Exception:
            pass
        # These mpv properties take effect on the next file load.
        try:
            mpv["hwdec"] = s.get("playback/hwdec")
        except Exception:
            pass
        try:
            mpv["hr-seek"] = "yes" if s.get("playback/hr_seek") else "no"
        except Exception:
            pass
        self._apply_subtitle_styling_to_player()

    def _apply_subtitle_styling_to_player(self) -> None:
        if self._player is None:
            return
        s = self._app_settings
        mpv = self._player._mpv
        try:
            font = s.get("subtitles/font")
            if font:
                mpv["sub-font"] = font
            mpv["sub-font-size"] = int(s.get("subtitles/size"))
            mpv["sub-color"] = s.get("subtitles/color")
            mpv["sub-border-color"] = s.get("subtitles/outline_color")
            mpv["sub-border-size"] = float(s.get("subtitles/outline_size"))
            mpv["sub-bold"] = "yes" if s.get("subtitles/bold") else "no"
            mpv["sub-italic"] = "yes" if s.get("subtitles/italic") else "no"
            mpv["sub-auto"] = "fuzzy" if s.get("subtitles/auto_load") else "no"
        except Exception:
            pass

    def _action_about(self) -> None:
        AboutDialog(self).exec()

    def _action_show_shortcuts(self) -> None:
        text = (
            "Playback\n"
            "  Space            Play / Pause\n"
            "  Left / Right     Seek -5s / +5s\n"
            "  Shift+L/R        Seek -30s / +30s\n"
            "  Ctrl+L/R         Seek -60s / +60s\n"
            "  Drag seek bar    Frame-accurate scrub with thumbnail preview\n"
            "  [  /  ]          Speed -/+\n"
            "  Backspace        Reset speed\n"
            "  L  /  Shift+L    A-B loop set / clear\n"
            "  PgUp / PgDown    Previous / Next chapter (or playlist)\n"
            "\n"
            "Audio / Subtitles\n"
            "  Up / Down        Volume +/-\n"
            "  M                Mute\n"
            "  V                Toggle subtitles\n"
            "  Z / X            Subtitle delay -/+\n"
            "  Ctrl+T           Add subtitle file\n"
            "  Ctrl+Y           Sync dialog\n"
            "\n"
            "View\n"
            "  F11 / DblClick   Fullscreen\n"
            "  Ctrl+L           Toggle playlist\n"
            "  Ctrl+E           Video adjustments\n"
            "  S                Screenshot\n"
            "  Ctrl+R           Resize window to video\n"
            "  Ctrl+Shift+T     Always on top\n"
            "\n"
            "File\n"
            "  Ctrl+O           Open file\n"
            "  Ctrl+U           Open URL\n"
            "  Ctrl+Shift+O     Open folder\n"
            "  Ctrl+Q           Quit\n"
        )
        box = QMessageBox(self)
        box.setWindowTitle("Keyboard Shortcuts")
        box.setText(f"<pre>{text}</pre>")
        box.setTextFormat(Qt.RichText)
        box.exec()
