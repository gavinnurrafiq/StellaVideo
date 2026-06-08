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
    binding = _preferred_qt_binding()
    if version.major == 10 and version.build >= 10586 and binding == "PySide2":
        return

    message = (
        "Stella Video membutuhkan Windows 10 1809 (build 17763) atau lebih baru.\n\n"
        "Untuk Windows 10 1511 (build 10586), gunakan build legacy Stella Video "
        "yang dibuat dengan PySide2/Qt5."
    )
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "Stella Video", 0x10)
    finally:
        raise SystemExit(1)


def _preferred_qt_binding() -> str | None:
    preferred = os.environ.get("STELLA_QT_BINDING", "").strip()
    candidates = []
    if preferred:
        candidates.append({"pyside6": "PySide6", "pyside2": "PySide2"}.get(
            preferred.lower(),
            preferred,
        ))
    candidates.extend(["PySide6", "PySide2"])
    for name in dict.fromkeys(candidates):
        if importlib.util.find_spec(name):
            return name
    return None


def _bootstrap_qt_runtime_paths() -> None:
    """Make Qt plugin discovery deterministic in frozen builds.

    On some Windows 10 machines, Qt can find PySide itself but fail to locate
    the platform plugin (qwindows.dll). That often shows up to users as a
    vague PySide/Qt DLL error. Set the plugin path before importing Qt.
    """
    candidates: list[Path] = []
    binding = _preferred_qt_binding() or "PySide6"

    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        candidates.append(Path(frozen_root) / binding / "plugins")

    spec = importlib.util.find_spec(binding)
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

from .qt import QApplication, QGuiApplication, QIcon, QT_MAJOR, Qt, QTimer, qt_exec

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

    if QT_MAJOR < 6:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

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

    return qt_exec(app)


if __name__ == "__main__":
    raise SystemExit(main())
