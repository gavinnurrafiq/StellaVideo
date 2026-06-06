"""Solid black theme for Stella Video.

UI bars (menu, control, status) use native child windows so libmpv's
backdrop painting doesn't erase them. Native child windows on Windows
are opaque, so each bar has a solid black background. The animated
backdrop only shows in the video area (centre of the window) when idle.
"""

STELLA_DARK_QSS = """
* { font-family: "Segoe UI", "Inter", "Helvetica Neue", sans-serif; font-size: 10pt; }

QMainWindow { background-color: #000000; }
QWidget { color: #e5e7eb; }

/* ---- custom title bar ---- */
QWidget#CustomTitleBar { background: transparent; }
QToolButton#TitleBarBtn {
    background: transparent; color: #e5e7eb; border: none; font-size: 11pt;
}
QToolButton#TitleBarBtn:hover { background-color: rgba(255, 255, 255, 38); }
QToolButton#TitleBarBtn:pressed { background-color: rgba(255, 255, 255, 70); }
QToolButton#TitleBarCloseBtn {
    background: transparent; color: #e5e7eb; border: none; font-size: 11pt;
}
QToolButton#TitleBarCloseBtn:hover { background-color: #e11d48; color: white; }
QToolButton#TitleBarCloseBtn:pressed { background-color: #be123c; }

/* ---- menu bar / menus ---- */
QMenuBar { background-color: #000000; color: #e5e7eb; padding: 2px 4px;
           border-bottom: 1px solid #141414; }
QMenuBar::item { padding: 4px 10px; background: transparent; color: #e5e7eb; }
QMenuBar::item:selected { background-color: #1a1a1a; border-radius: 4px; }
QMenu { background-color: #0a0a0a; color: #e5e7eb; border: 1px solid #1f1f1f; padding: 4px 0; }
QMenu::item { padding: 6px 22px; }
QMenu::item:selected { background-color: #3b82f6; color: white; }
QMenu::separator { height: 1px; background: #1f1f1f; margin: 4px 6px; }

/* ---- status bar ---- */
QStatusBar { background-color: #000000; color: #9ca3af; border-top: 1px solid #141414; }
QStatusBar QLabel { background: transparent; }
QStatusBar::item { border: none; }

/* ---- control bar ---- */
QWidget#ControlBar { background-color: #000000; border-top: 1px solid #141414; }

QLabel#TimeLabel { color: #d1d5db; font-variant-numeric: tabular-nums; min-width: 52px; background: transparent; }
QLabel#VolumeLabel { color: #9ca3af; font-variant-numeric: tabular-nums; background: transparent; }

/* ---- buttons ---- */
QToolButton {
    background: transparent; border: none; color: #e5e7eb;
    font-size: 14pt; padding: 0;
}
QToolButton:hover { background-color: #1a1a1a; border-radius: 6px; }
QToolButton:pressed { background-color: #3b82f6; color: white; border-radius: 6px; }
QToolButton:disabled { color: #4b5563; }

QPushButton {
    background-color: #161616; color: #e5e7eb; border: 1px solid #262626;
    border-radius: 6px; padding: 5px 12px;
}
QPushButton:hover { background-color: #1f1f1f; border-color: #303030; }
QPushButton:pressed { background-color: #3b82f6; color: white; border-color: #3b82f6; }
QPushButton#PanelButton { padding: 4px 10px; }

/* ---- combo box (speed dropdown etc.) ---- */
QComboBox {
    background-color: #161616; color: #e5e7eb; border: 1px solid #262626;
    border-radius: 6px; padding: 3px 8px;
}
QComboBox:hover { background-color: #1f1f1f; border-color: #303030; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background-color: #0a0a0a; color: #e5e7eb;
    selection-background-color: #3b82f6;
    border: 1px solid #262626;
}

/* ---- sliders (seek bar, volume) ---- */
QSlider::groove:horizontal {
    height: 4px; background: #1a1a1a; border-radius: 2px;
}
/* sub-page is rendered by SeekBar.paintEvent (animated gradient). */
QSlider::sub-page:horizontal { background: transparent; }
QSlider::handle:horizontal {
    background: #e5e7eb; width: 12px; height: 12px;
    margin: -5px 0; border-radius: 6px;
    border: 1px solid #000000;
}
QSlider::handle:horizontal:hover { background: #ffffff; }

QSlider::groove:vertical { width: 4px; background: #1a1a1a; border-radius: 2px; }
QSlider::sub-page:vertical { background: #1a1a1a; }
QSlider::add-page:vertical { background: #3b82f6; border-radius: 2px; }
QSlider::handle:vertical { background: #e5e7eb; height: 12px; width: 12px; margin: 0 -5px; border-radius: 6px; }

/* ---- playlist list ---- */
QListWidget {
    background-color: #050505; color: #e5e7eb;
    border: 1px solid #1a1a1a; border-radius: 6px; outline: none;
    padding: 2px;
}
QListWidget::item { padding: 6px 8px; border-radius: 4px; }
QListWidget::item:alternate { background-color: #0a0a0a; }
QListWidget::item:selected { background-color: #3b82f6; color: white; }
QListWidget::item:hover { background-color: #141414; }

QLabel#PanelTitle { font-weight: 600; font-size: 11pt; color: #e5e7eb; background: transparent; }
QLabel#PanelCount { color: #9ca3af; padding: 0 6px; background: transparent; }
QLabel#MutedLabel { color: #9ca3af; background: transparent; }
QLabel#LiveStatus {
    color: #e5e7eb; background-color: #050505; border: 1px solid #1f1f1f;
    border-radius: 6px; padding: 8px 10px;
}

/* ---- dock widget (playlist panel) ---- */
QDockWidget {
    color: #e5e7eb; background-color: #000000;
    titlebar-close-icon: none; titlebar-normal-icon: none;
}
QDockWidget::title {
    background: #000000; padding: 6px 10px; border-bottom: 1px solid #1a1a1a;
}

/* ---- dialogs ---- */
QDialog { background-color: #000000; color: #e5e7eb; }
QGroupBox {
    border: 1px solid #1a1a1a; border-radius: 6px;
    margin-top: 14px; padding: 10px 8px 8px 8px; color: #e5e7eb;
    background: #050505;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #9ca3af; background: transparent; }

QDoubleSpinBox, QSpinBox {
    background-color: #161616; color: #e5e7eb; border: 1px solid #262626;
    border-radius: 4px; padding: 3px 6px;
}
QLineEdit, QTextEdit {
    background-color: #101010; color: #e5e7eb; border: 1px solid #262626;
    border-radius: 6px; padding: 5px 8px;
    selection-background-color: #3b82f6;
}
QLineEdit:focus, QTextEdit:focus { border-color: #3b82f6; }
QCheckBox { color: #9ca3af; background: transparent; }

/* ---- scroll bars ---- */
QScrollBar:vertical { background: #000000; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #262626; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #3a3a3a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #000000; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #262626; border-radius: 5px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #3a3a3a; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ---- tooltips ---- */
QToolTip {
    background-color: #0a0a0a; color: #e5e7eb;
    border: 1px solid #1f1f1f; padding: 4px 6px;
}

/* ---- message box ---- */
QMessageBox { background-color: #000000; }
"""
