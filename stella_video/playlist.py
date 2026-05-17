"""Playlist dock panel."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QAbstractItemView, QMenu
)


class PlaylistPanel(QWidget):
    """Simple playlist with add/remove/clear, double-click to play."""

    playRequested = Signal(str)        # path
    currentRemoved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PlaylistPanel")

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("Playlist")
        title.setObjectName("PanelTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.count_label = QLabel("0")
        self.count_label.setObjectName("PanelCount")
        header.addWidget(self.count_label)
        root.addLayout(header)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.itemDoubleClicked.connect(self._on_double_click)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._on_context_menu)
        root.addWidget(self.list_widget, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self.btn_remove = QPushButton("Remove")
        self.btn_clear = QPushButton("Clear")
        self.btn_up = QPushButton("↑")
        self.btn_down = QPushButton("↓")
        for b in (self.btn_remove, self.btn_clear):
            b.setObjectName("PanelButton")
        for b in (self.btn_up, self.btn_down):
            b.setObjectName("PanelButton")
            b.setFixedWidth(30)
        btn_row.addWidget(self.btn_remove)
        btn_row.addWidget(self.btn_clear)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_up)
        btn_row.addWidget(self.btn_down)
        root.addLayout(btn_row)

        self.btn_remove.clicked.connect(self.remove_selected)
        self.btn_clear.clicked.connect(self.clear)
        self.btn_up.clicked.connect(lambda: self._move_selected(-1))
        self.btn_down.clicked.connect(lambda: self._move_selected(1))

        # delete key
        del_action = QAction(self)
        del_action.setShortcut(QKeySequence("Delete"))
        del_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        del_action.triggered.connect(self.remove_selected)
        self.addAction(del_action)

    # ---- public api ----
    def add_paths(self, paths: list[str]) -> int:
        added = 0
        for p in paths:
            if not p:
                continue
            item = QListWidgetItem(Path(p).name)
            item.setData(Qt.UserRole, p)
            item.setToolTip(p)
            self.list_widget.addItem(item)
            added += 1
        self._update_count()
        return added

    def paths(self) -> list[str]:
        return [self.list_widget.item(i).data(Qt.UserRole)
                for i in range(self.list_widget.count())]

    def set_current_path(self, path: str | None) -> None:
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.UserRole) == path:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                self.list_widget.setCurrentRow(i)
            else:
                font = item.font()
                font.setBold(False)
                item.setFont(font)

    def next_path(self, current: str | None) -> str | None:
        paths = self.paths()
        if not paths:
            return None
        if current is None or current not in paths:
            return paths[0]
        idx = paths.index(current)
        return paths[idx + 1] if idx + 1 < len(paths) else None

    def prev_path(self, current: str | None) -> str | None:
        paths = self.paths()
        if not paths:
            return None
        if current is None or current not in paths:
            return paths[0]
        idx = paths.index(current)
        return paths[idx - 1] if idx > 0 else None

    def clear(self) -> None:
        self.list_widget.clear()
        self._update_count()

    def remove_selected(self) -> None:
        for item in reversed(self.list_widget.selectedItems()):
            self.list_widget.takeItem(self.list_widget.row(item))
        self._update_count()
        self.currentRemoved.emit()

    # ---- internals ----
    def _on_double_click(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if path:
            self.playRequested.emit(path)

    def _on_context_menu(self, pos) -> None:
        item = self.list_widget.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        play_act = menu.addAction("Play")
        remove_act = menu.addAction("Remove")
        menu.addSeparator()
        copy_path_act = menu.addAction("Copy path")
        action = menu.exec(self.list_widget.mapToGlobal(pos))
        if action == play_act:
            self.playRequested.emit(item.data(Qt.UserRole))
        elif action == remove_act:
            self.list_widget.takeItem(self.list_widget.row(item))
            self._update_count()
        elif action == copy_path_act:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(item.data(Qt.UserRole))

    def _move_selected(self, delta: int) -> None:
        rows = sorted({self.list_widget.row(i) for i in self.list_widget.selectedItems()})
        if not rows:
            return
        if delta < 0:
            rows.sort()
        else:
            rows.sort(reverse=True)
        for row in rows:
            new_row = row + delta
            if 0 <= new_row < self.list_widget.count():
                item = self.list_widget.takeItem(row)
                self.list_widget.insertItem(new_row, item)
                item.setSelected(True)

    def _update_count(self) -> None:
        self.count_label.setText(str(self.list_widget.count()))
