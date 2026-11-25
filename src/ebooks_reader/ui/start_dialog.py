from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from ..formats import file_dialog_filter
from .recent import load_recent, remove_recent


class StartDialog(QDialog):
    """Shown at startup: pick a recent book or browse for another one.

    After exec(), `chosen` holds the path to open, or None.
    """

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.chosen: str | None = None
        self.setWindowTitle("Open a book")
        self.resize(640, 440)

        self.list = QListWidget()
        self.empty = QLabel('No recent books yet. Use "Open another book...".')
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_open = QPushButton("Open")
        self.btn_open.setDefault(True)
        self.btn_browse = QPushButton("Open another book...")
        self.btn_remove = QPushButton("Remove from list")
        self.btn_close = QPushButton("Continue without a book")

        self.show_check = QCheckBox("Show this window at startup")
        self.show_check.setChecked(settings.value("show_start", True, type=bool))

        buttons = QHBoxLayout()
        buttons.addWidget(self.btn_open)
        buttons.addWidget(self.btn_browse)
        buttons.addWidget(self.btn_remove)
        buttons.addStretch()
        buttons.addWidget(self.btn_close)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("<b>Recent books</b>"))
        root.addWidget(self.list, 1)
        root.addWidget(self.empty, 1)
        root.addLayout(buttons)
        root.addWidget(self.show_check)

        self.list.itemActivated.connect(lambda _i: self._open_selected())
        self.list.currentItemChanged.connect(lambda *_: self._update_buttons())
        self.btn_open.clicked.connect(self._open_selected)
        self.btn_browse.clicked.connect(self._browse)
        self.btn_remove.clicked.connect(self._remove)
        self.btn_close.clicked.connect(self.reject)
        self.show_check.toggled.connect(lambda v: self.settings.setValue("show_start", v))

        self._fill()

    def _fill(self) -> None:
        self.list.clear()
        first_ok = None
        for path in load_recent(self.settings):
            p = Path(path)
            exists = p.is_file()
            label = f"{p.name}\n{p.parent}"
            if not exists:
                label = f"{p.name}  (file not found)\n{p.parent}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            if not exists:
                item.setFlags(Qt.ItemFlag.ItemIsSelectable)  # visible, can be removed, not opened
            self.list.addItem(item)
            if exists and first_ok is None:
                first_ok = item
        has_items = self.list.count() > 0
        self.list.setVisible(has_items)
        self.empty.setVisible(not has_items)
        if first_ok is not None:
            self.list.setCurrentItem(first_ok)
            self.list.setFocus()
        self._update_buttons()

    def _update_buttons(self) -> None:
        item = self.list.currentItem()
        enabled = item is not None and bool(item.flags() & Qt.ItemFlag.ItemIsEnabled)
        self.btn_open.setEnabled(enabled)
        self.btn_remove.setEnabled(item is not None)

    def _open_selected(self) -> None:
        item = self.list.currentItem()
        if item is None or not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            return
        self.chosen = str(item.data(Qt.ItemDataRole.UserRole))
        self.accept()

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open book", "", file_dialog_filter())
        if path:
            self.chosen = path
            self.accept()

    def _remove(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        remove_recent(self.settings, str(item.data(Qt.ItemDataRole.UserRole)))
        self._fill()
