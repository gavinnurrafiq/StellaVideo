"""Entry point: creates QApplication, shows splash, then MainWindow."""
from __future__ import annotations

import importlib.util
import locale
import os
import sys
from pathlib import Path


def _guard_supported_windows() -> None:
    """Fail early with a clear message on unsupported Windows releases."""
    if sys.platform != "win32":
        return

    version = sys.getwindowsversion()
    if version.major > 10:
        return
    if version.major == 10 and version.build >= 17763:
        return

    message = (
        "Stella Video membutuhkan Windows 10 1809 (build 17763) atau lebih baru.\n\n"
        "Windows 8/8.1 tidak didukung oleh Qt 6/PySide6, sehingga aplikasi "
        "bisa gagal dengan pesan seperti PySide6.dll tidak ditemukan."
    )
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "Stella Video", 0x10)
    finally:
        raise SystemExit(1)


def _bootstrap_qt_runtime_paths() -> None:
    """Make Qt plugin discovery deterministic in frozen builds.

    On some Windows 10 machines, Qt can find PySide6 itself but fail to locate
    the platform plugin (qwindows.dll). That often shows up to users as a
    vague PySide6/Qt DLL error. Set the plugin path before importing PySide6.
    """
    candidates: list[Path] = []

    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        candidates.append(Path(frozen_root) / "PySide6" / "plugins")

    spec = importlib.util.find_spec("PySide6")
    if spec and spec.submodule_search_locations:
        candidates.append(Path(next(iter(spec.submodule_search_locations))) / "plugins")

    for plugins in candidates:
        platforms = plugins / "platforms"
        if (platforms / "qwindows.dll").is_file():
            os.environ["QT_PLUGIN_PATH"] = str(plugins)
            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platforms)
            os.environ.setdefault("QT_QPA_PLATFORM", "windows")
            break


_guard_supported_windows()
_bootstrap_qt_runtime_paths()

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from . import __app_name__, __version__
from .main_window import MainWindow
from .splash import LOGO_PATH, StellaSplashScreen
from .styles import STELLA_DARK_QSS


def _fix_locale_for_mpv() -> None:
    # libmpv requires C numeric locale. Otherwise parsing values like "1.0"
    # breaks in some non-English locales.
    try:
        locale.setlocale(locale.LC_NUMERIC, "C")
    except locale.Error:
        pass
    os.environ.setdefault("LC_NUMERIC", "C")


def _load_app_icon() -> QIcon:
    """Build a QIcon from the logo PNG for taskbar and window-frame use."""
    if LOGO_PATH.is_file():
        return QIcon(str(LOGO_PATH))
    return QIcon()


def main(argv: list[str] | None = None) -> int:
    _fix_locale_for_mpv()
    argv = list(argv or sys.argv)

    QGuiApplication.setApplicationDisplayName(__app_name__)
    QApplication.setApplicationName(__app_name__)
    QApplication.setOrganizationName("StellaVideo")
    QApplication.setApplicationVersion(__version__)

    app = QApplication(argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STELLA_DARK_QSS)

    icon = _load_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    splash = StellaSplashScreen()
    splash.show_centered()
    splash.set_message("Loading interface...")

    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()

    # Initialise the libmpv player after the window has been shown so the
    # native winId is valid.
    def _post_show() -> None:
        splash.set_message("Initializing player...")
        window.init_player()

        files = [a for a in argv[1:] if not a.startswith("-")]
        if files and window._player is not None:
            splash.set_message(f"Opening {Path(files[0]).name}...")
            for i, file_path in enumerate(files):
                window._open_path(file_path, replace=(i == 0), focus=False)

        splash.set_message("Ready")
        splash.finish(window)

    QTimer.singleShot(0, _post_show)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
