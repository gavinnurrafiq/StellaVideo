"""Video output widget — gives libmpv a native window-id to render into."""
from __future__ import annotations

from .qt import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFrame,
    QMouseEvent,
    QPalette,
    Qt,
    Signal,
)


class VideoFrame(QFrame):
    """Native widget that hosts the mpv video output.

    Notes:
    - Qt.WA_NativeWindow ensures winId() returns a real OS window handle,
      which libmpv needs for embedding.
    - We disable widget repainting on this frame so mpv's renderer owns the
      pixels (no Qt flicker over the video).
    """

    doubleClicked = Signal()
    leftClicked = Signal()
    rightClicked = Signal()
    mouseMoved = Signal()
    filesDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_NativeWindow)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setUpdatesEnabled(False)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 180)
        self.setFrameShape(QFrame.NoFrame)

        pal = self.palette()
        pal.setColor(QPalette.Window, QColor("#000000"))
        self.setAutoFillBackground(True)
        self.setPalette(pal)

    def native_wid(self) -> int:
        return int(self.winId())

    # ---- mouse ----
    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.LeftButton:
            # If the click is on the parent window's resize edge, hand off
            # to the OS resize loop instead of treating it as a video click.
            window = self.window()
            if hasattr(window, "_try_start_edge_resize"):
                if window._try_start_edge_resize(e):
                    return
            self.leftClicked.emit()
        elif e.button() == Qt.RightButton:
            self.rightClicked.emit()
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.LeftButton:
            self.doubleClicked.emit()
        super().mouseDoubleClickEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        self.mouseMoved.emit()
        super().mouseMoveEvent(e)

    # ---- drag & drop ----
    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent) -> None:
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.toLocalFile()]
        if paths:
            self.filesDropped.emit(paths)
            e.acceptProposedAction()
