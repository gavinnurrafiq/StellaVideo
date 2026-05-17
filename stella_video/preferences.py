"""Application preferences: typed settings helper + dialog UI.

`AppSettings` wraps QSettings with defaults and type coercion so callers
don't have to handle the platform-specific quirks (Windows registry
returns strings, Linux INI returns strings, macOS plist returns native
types). `PreferencesDialog` exposes those settings in a four-tab UI.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QWidget, QTabWidget,
    QLabel, QSpinBox, QDoubleSpinBox, QCheckBox, QComboBox, QFontComboBox,
    QPushButton, QDialogButtonBox, QColorDialog, QGroupBox, QPlainTextEdit
)


# ---------------------------------------------------------------------------
# Defaults & schema
# ---------------------------------------------------------------------------
DEFAULTS: dict[str, Any] = {
    # General
    "general/recent_files_max": 12,
    "general/save_window_state": True,
    "general/reopen_last_file": False,
    # Playback
    "playback/default_volume": 100,
    "playback/default_speed": 1.0,
    "playback/hwdec": "auto-safe",
    "playback/hr_seek": True,
    "playback/auto_advance": True,
    # Interface
    "interface/autohide_enabled": True,
    "interface/autohide_delay": 2000,
    "interface/backdrop_animation": True,
    "interface/title_bar_animation": True,
    "interface/reactive_title_bar": True,
    "interface/show_splash": True,
    "interface/thumbnail_preview": True,
    # Subtitles
    "subtitles/font": "",
    "subtitles/size": 55,
    "subtitles/color": "#ffffff",
    "subtitles/outline_color": "#000000",
    "subtitles/outline_size": 3.0,
    "subtitles/bold": False,
    "subtitles/italic": False,
    "subtitles/auto_load": True,
}


def _coerce(value: Any, default: Any) -> Any:
    """QSettings.value() can return strings on some platforms even for
    typed values. Coerce to the type of `default`."""
    if value is None:
        return default
    if isinstance(default, bool):
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value)
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    if isinstance(default, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    return value


class AppSettings:
    """Thin typed wrapper around QSettings."""

    def __init__(self):
        self._q = QSettings("StellaVideo", "Stella Video")

    def get(self, key: str) -> Any:
        if key not in DEFAULTS:
            raise KeyError(f"Unknown setting: {key}")
        default = DEFAULTS[key]
        return _coerce(self._q.value(key, default), default)

    def set(self, key: str, value: Any) -> None:
        if key not in DEFAULTS:
            raise KeyError(f"Unknown setting: {key}")
        self._q.setValue(key, value)

    def reset_all(self) -> None:
        for key in DEFAULTS:
            self._q.remove(key)

    def sync(self) -> None:
        self._q.sync()

    # Convenience for the small subset of keys still managed elsewhere
    # (recent_files list, last window geometry).
    @property
    def qsettings(self) -> QSettings:
        return self._q


# ---------------------------------------------------------------------------
# Color picker button
# ---------------------------------------------------------------------------
class ColorButton(QPushButton):
    """A button whose swatch shows the currently selected color."""

    colorChanged = Signal(QColor)

    def __init__(self, parent: QWidget | None = None,
                 initial: str = "#ffffff"):
        super().__init__(parent)
        self.setFixedSize(80, 24)
        self.setCursor(Qt.PointingHandCursor)
        self._color: QColor = QColor(initial)
        self._refresh()
        self.clicked.connect(self._pick)

    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor | str) -> None:
        c = QColor(color) if isinstance(color, str) else color
        if c.isValid() and c != self._color:
            self._color = c
            self._refresh()
            self.colorChanged.emit(self._color)

    def _refresh(self) -> None:
        self.setText(self._color.name())
        text_color = "#000000" if self._color.lightness() > 128 else "#ffffff"
        self.setStyleSheet(
            f"QPushButton {{ background-color: {self._color.name()};"
            f"color: {text_color}; border: 1px solid #2a2a2a;"
            f"border-radius: 4px; padding: 0 6px; font-size: 9pt; }}"
        )

    def _pick(self) -> None:
        c = QColorDialog.getColor(self._color, self, "Select Color")
        if c.isValid():
            self.set_color(c)


# ---------------------------------------------------------------------------
# Preferences dialog
# ---------------------------------------------------------------------------
class PreferencesDialog(QDialog):
    """Tabbed preferences UI. Emits `settingsApplied` whenever the user
    clicks Apply or OK, so the main window can re-apply live settings."""

    settingsApplied = Signal()

    def __init__(self, settings: AppSettings, parent: QWidget | None = None):
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("Preferences")
        self.setMinimumSize(560, 500)

        root = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_general(), "General")
        self.tabs.addTab(self._build_playback(), "Playback")
        self.tabs.addTab(self._build_interface(), "Interface")
        self.tabs.addTab(self._build_subtitles(), "Subtitles")
        root.addWidget(self.tabs, 1)

        info = QLabel("Settings marked with ‡ take effect after restart.")
        info.setStyleSheet("color: #9ca3af; font-size: 9pt;")
        root.addWidget(info)

        bb = QDialogButtonBox(
            QDialogButtonBox.RestoreDefaults
            | QDialogButtonBox.Cancel
            | QDialogButtonBox.Apply
            | QDialogButtonBox.Ok
        )
        bb.button(QDialogButtonBox.Apply).clicked.connect(self._apply)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.RestoreDefaults).clicked.connect(
            self._restore_defaults
        )
        root.addWidget(bb)

        self._load()

    # ---- tabs ----
    def _build_general(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignRight)

        self.recent_max = QSpinBox()
        self.recent_max.setRange(0, 50)
        form.addRow("Maximum recent files:", self.recent_max)

        self.save_window_state = QCheckBox()
        form.addRow("Remember window position & size:", self.save_window_state)

        self.reopen_last = QCheckBox()
        form.addRow("Reopen last file on launch:", self.reopen_last)

        form.addRow(QLabel())  # spacer
        return w

    def _build_playback(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignRight)

        self.default_volume = QSpinBox()
        self.default_volume.setRange(0, 150)
        self.default_volume.setSuffix(" %")
        form.addRow("Default volume:", self.default_volume)

        self.default_speed = QDoubleSpinBox()
        self.default_speed.setRange(0.1, 8.0)
        self.default_speed.setSingleStep(0.05)
        self.default_speed.setDecimals(2)
        form.addRow("Default speed:", self.default_speed)

        self.hwdec = QComboBox()
        self.hwdec.addItems(["auto-safe", "auto", "auto-copy", "no"])
        form.addRow("Hardware decoder ‡:", self.hwdec)

        self.hr_seek = QCheckBox()
        form.addRow("Frame-accurate seeking ‡:", self.hr_seek)

        self.auto_advance = QCheckBox()
        form.addRow("Auto-advance playlist on EOF:", self.auto_advance)

        return w

    def _build_interface(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignRight)

        self.autohide_enabled = QCheckBox()
        form.addRow("Auto-hide UI during playback:", self.autohide_enabled)

        self.autohide_delay = QSpinBox()
        self.autohide_delay.setRange(500, 10000)
        self.autohide_delay.setSuffix(" ms")
        self.autohide_delay.setSingleStep(100)
        form.addRow("Auto-hide delay:", self.autohide_delay)

        self.backdrop_anim = QCheckBox()
        form.addRow("Animated backdrop (idle):", self.backdrop_anim)

        self.title_anim = QCheckBox()
        form.addRow("Animated title bar gradient:", self.title_anim)

        self.reactive_title = QCheckBox()
        form.addRow("Reactive title bar (sample video):", self.reactive_title)

        self.show_splash = QCheckBox()
        form.addRow("Splash screen on launch ‡:", self.show_splash)

        self.thumb_preview = QCheckBox()
        form.addRow("Scrub bar thumbnail preview ‡:", self.thumb_preview)

        return w

    def _build_subtitles(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignRight)

        self.sub_font = QFontComboBox()
        form.addRow("Font:", self.sub_font)

        self.sub_size = QSpinBox()
        self.sub_size.setRange(10, 200)
        form.addRow("Size:", self.sub_size)

        color_row = QHBoxLayout()
        self.sub_color = ColorButton()
        self.sub_outline_color = ColorButton()
        color_row.addWidget(QLabel("Text"))
        color_row.addWidget(self.sub_color)
        color_row.addSpacing(12)
        color_row.addWidget(QLabel("Outline"))
        color_row.addWidget(self.sub_outline_color)
        color_row.addStretch(1)
        color_holder = QWidget()
        color_holder.setLayout(color_row)
        form.addRow("Colors:", color_holder)

        self.sub_outline_size = QDoubleSpinBox()
        self.sub_outline_size.setRange(0.0, 10.0)
        self.sub_outline_size.setSingleStep(0.5)
        self.sub_outline_size.setDecimals(1)
        form.addRow("Outline thickness:", self.sub_outline_size)

        style_row = QHBoxLayout()
        self.sub_bold = QCheckBox("Bold")
        self.sub_italic = QCheckBox("Italic")
        style_row.addWidget(self.sub_bold)
        style_row.addWidget(self.sub_italic)
        style_row.addStretch(1)
        style_holder = QWidget()
        style_holder.setLayout(style_row)
        form.addRow("Style:", style_holder)

        self.sub_auto_load = QCheckBox()
        form.addRow("Auto-load subtitle next to video:", self.sub_auto_load)

        return w

    # ---- load / save ----
    def _load(self) -> None:
        s = self._settings
        # General
        self.recent_max.setValue(s.get("general/recent_files_max"))
        self.save_window_state.setChecked(s.get("general/save_window_state"))
        self.reopen_last.setChecked(s.get("general/reopen_last_file"))
        # Playback
        self.default_volume.setValue(s.get("playback/default_volume"))
        self.default_speed.setValue(s.get("playback/default_speed"))
        idx = self.hwdec.findText(str(s.get("playback/hwdec")))
        self.hwdec.setCurrentIndex(idx if idx >= 0 else 0)
        self.hr_seek.setChecked(s.get("playback/hr_seek"))
        self.auto_advance.setChecked(s.get("playback/auto_advance"))
        # Interface
        self.autohide_enabled.setChecked(s.get("interface/autohide_enabled"))
        self.autohide_delay.setValue(s.get("interface/autohide_delay"))
        self.backdrop_anim.setChecked(s.get("interface/backdrop_animation"))
        self.title_anim.setChecked(s.get("interface/title_bar_animation"))
        self.reactive_title.setChecked(s.get("interface/reactive_title_bar"))
        self.show_splash.setChecked(s.get("interface/show_splash"))
        self.thumb_preview.setChecked(s.get("interface/thumbnail_preview"))
        # Subtitles
        font_name = s.get("subtitles/font")
        if font_name:
            self.sub_font.setCurrentFont(QFont(font_name))
        self.sub_size.setValue(s.get("subtitles/size"))
        self.sub_color.set_color(s.get("subtitles/color"))
        self.sub_outline_color.set_color(s.get("subtitles/outline_color"))
        self.sub_outline_size.setValue(s.get("subtitles/outline_size"))
        self.sub_bold.setChecked(s.get("subtitles/bold"))
        self.sub_italic.setChecked(s.get("subtitles/italic"))
        self.sub_auto_load.setChecked(s.get("subtitles/auto_load"))

    def _save(self) -> None:
        s = self._settings
        s.set("general/recent_files_max", self.recent_max.value())
        s.set("general/save_window_state", self.save_window_state.isChecked())
        s.set("general/reopen_last_file", self.reopen_last.isChecked())

        s.set("playback/default_volume", self.default_volume.value())
        s.set("playback/default_speed", self.default_speed.value())
        s.set("playback/hwdec", self.hwdec.currentText())
        s.set("playback/hr_seek", self.hr_seek.isChecked())
        s.set("playback/auto_advance", self.auto_advance.isChecked())

        s.set("interface/autohide_enabled", self.autohide_enabled.isChecked())
        s.set("interface/autohide_delay", self.autohide_delay.value())
        s.set("interface/backdrop_animation", self.backdrop_anim.isChecked())
        s.set("interface/title_bar_animation", self.title_anim.isChecked())
        s.set("interface/reactive_title_bar", self.reactive_title.isChecked())
        s.set("interface/show_splash", self.show_splash.isChecked())
        s.set("interface/thumbnail_preview", self.thumb_preview.isChecked())

        s.set("subtitles/font", self.sub_font.currentFont().family())
        s.set("subtitles/size", self.sub_size.value())
        s.set("subtitles/color", self.sub_color.color().name())
        s.set("subtitles/outline_color", self.sub_outline_color.color().name())
        s.set("subtitles/outline_size", self.sub_outline_size.value())
        s.set("subtitles/bold", self.sub_bold.isChecked())
        s.set("subtitles/italic", self.sub_italic.isChecked())
        s.set("subtitles/auto_load", self.sub_auto_load.isChecked())
        s.sync()

    def _apply(self) -> None:
        self._save()
        self.settingsApplied.emit()

    def _accept(self) -> None:
        self._save()
        self.settingsApplied.emit()
        self.accept()

    def _restore_defaults(self) -> None:
        self._settings.reset_all()
        self._load()
