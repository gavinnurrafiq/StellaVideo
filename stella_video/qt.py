"""Qt binding compatibility layer.

The modern build uses PySide6/Qt6. The Windows 10 1511 legacy build uses
PySide2/Qt5 because Qt6 builds used by PySide6 require newer Windows 10.
"""
from __future__ import annotations

import importlib
import os
from typing import Any


def _binding_candidates() -> list[str]:
    preferred = os.environ.get("STELLA_QT_BINDING", "").strip()
    if preferred:
        normalized = {"pyside6": "PySide6", "pyside2": "PySide2"}.get(
            preferred.lower(),
            preferred,
        )
        return [normalized, "PySide6", "PySide2"]
    return ["PySide6", "PySide2"]


_last_error: Exception | None = None
for _binding in dict.fromkeys(_binding_candidates()):
    try:
        QtCore = importlib.import_module(f"{_binding}.QtCore")
        QtGui = importlib.import_module(f"{_binding}.QtGui")
        QtWidgets = importlib.import_module(f"{_binding}.QtWidgets")
        QT_BINDING = _binding
        break
    except Exception as exc:  # noqa: BLE001
        _last_error = exc
else:
    raise RuntimeError("PySide6 or PySide2 is required to run Stella Video.") from _last_error

QT_MAJOR = 6 if QT_BINDING == "PySide6" else 5

Qt = QtCore.Qt
Signal = QtCore.Signal
QObject = QtCore.QObject
QSettings = QtCore.QSettings
QTimer = QtCore.QTimer
QUrl = QtCore.QUrl
QPoint = QtCore.QPoint
QEvent = QtCore.QEvent
QRect = QtCore.QRect
QRectF = QtCore.QRectF
QSize = QtCore.QSize
QProcess = QtCore.QProcess

QDesktopServices = QtGui.QDesktopServices
QKeySequence = QtGui.QKeySequence
QIcon = QtGui.QIcon
QGuiApplication = QtGui.QGuiApplication
QCursor = QtGui.QCursor
QColor = QtGui.QColor
QFont = QtGui.QFont
QPalette = QtGui.QPalette
QMouseEvent = QtGui.QMouseEvent
QDragEnterEvent = QtGui.QDragEnterEvent
QDropEvent = QtGui.QDropEvent
QPainter = QtGui.QPainter
QPen = QtGui.QPen
QPixmap = QtGui.QPixmap
QImage = QtGui.QImage
QTransform = QtGui.QTransform
QLinearGradient = QtGui.QLinearGradient
QPainterPath = QtGui.QPainterPath
QPaintEvent = QtGui.QPaintEvent
QRegion = QtGui.QRegion

QApplication = QtWidgets.QApplication
QMainWindow = QtWidgets.QMainWindow
QWidget = QtWidgets.QWidget
QVBoxLayout = QtWidgets.QVBoxLayout
QHBoxLayout = QtWidgets.QHBoxLayout
QFormLayout = QtWidgets.QFormLayout
QDockWidget = QtWidgets.QDockWidget
QFileDialog = QtWidgets.QFileDialog
QMessageBox = QtWidgets.QMessageBox
QLabel = QtWidgets.QLabel
QMenu = QtWidgets.QMenu
QStatusBar = QtWidgets.QStatusBar
QMenuBar = QtWidgets.QMenuBar
QLineEdit = QtWidgets.QLineEdit
QPushButton = QtWidgets.QPushButton
QComboBox = QtWidgets.QComboBox
QTextEdit = QtWidgets.QTextEdit
QGroupBox = QtWidgets.QGroupBox
QCheckBox = QtWidgets.QCheckBox
QFrame = QtWidgets.QFrame
QToolButton = QtWidgets.QToolButton
QSlider = QtWidgets.QSlider
QSizePolicy = QtWidgets.QSizePolicy
QDialog = QtWidgets.QDialog
QTabWidget = QtWidgets.QTabWidget
QSpinBox = QtWidgets.QSpinBox
QDoubleSpinBox = QtWidgets.QDoubleSpinBox
QFontComboBox = QtWidgets.QFontComboBox
QDialogButtonBox = QtWidgets.QDialogButtonBox
QColorDialog = QtWidgets.QColorDialog
QPlainTextEdit = QtWidgets.QPlainTextEdit
QListWidget = QtWidgets.QListWidget
QListWidgetItem = QtWidgets.QListWidgetItem
QAbstractItemView = QtWidgets.QAbstractItemView
QStackedLayout = QtWidgets.QStackedLayout
QInputDialog = QtWidgets.QInputDialog

QAction = getattr(QtGui, "QAction", None) or getattr(QtWidgets, "QAction")
QActionGroup = getattr(QtGui, "QActionGroup", None) or getattr(QtWidgets, "QActionGroup")


def qt_exec(obj: Any, *args: Any) -> Any:
    method = getattr(obj, "exec", None) or getattr(obj, "exec_", None)
    if method is None:
        raise AttributeError(f"{type(obj).__name__} has no exec/exec_ method")
    return method(*args)


def event_position_x(event: Any) -> float:
    if hasattr(event, "position"):
        return float(event.position().x())
    return float(event.pos().x())


def event_global_pos(event: Any) -> QPoint:
    if hasattr(event, "globalPosition"):
        return event.globalPosition().toPoint()
    return event.globalPos()


def event_global_x(event: Any) -> int:
    return int(event_global_pos(event).x())


def screen_at(point: QPoint):
    screen_at_fn = getattr(QGuiApplication, "screenAt", None)
    if callable(screen_at_fn):
        return screen_at_fn(point)
    for screen in QGuiApplication.screens():
        if screen.geometry().contains(point):
            return screen
    return QGuiApplication.primaryScreen()
