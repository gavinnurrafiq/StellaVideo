"""Entry point — creates QApplication, shows splash, then MainWindow."""
from __future__ import annotations

import os
import sys
import locale
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from . import __app_name__, __version__
from .main_window import MainWindow
from .styles import STELLA_DARK_QSS
from .splash import StellaSplashScreen, LOGO_PATH


def _fix_locale_for_mpv() -> None:
    # libmpv requires C numeric locale (otherwise parsing of e.g. "1.0" breaks
    # in non-English locales).
    try:
        locale.setlocale(locale.LC_NUMERIC, "C")
    except locale.Error:
        pass
    os.environ.setdefault("LC_NUMERIC", "C")


def _load_app_icon() -> QIcon:
    """Build a QIcon from the logo PNG. Qt rescales it for whichever size
    the OS requests (taskbar, window-frame, alt-tab, etc.)."""
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
    splash.set_message("Loading interface…")

    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()

    # Initialise the libmpv player after the window has been shown so that
    # the native winId is valid.
    def _post_show() -> None:
        splash.set_message("Initializing player…")
        window.init_player()

        files = [a for a in argv[1:] if not a.startswith("-")]
        if files and window._player is not None:
            splash.set_message(f"Opening {Path(files[0]).name}…")
            for i, f in enumerate(files):
                window._open_path(f, replace=(i == 0), focus=False)

        splash.set_message("Ready")
        splash.finish(window)

    QTimer.singleShot(0, _post_show)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
