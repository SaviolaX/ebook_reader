from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .notes import FlatEntry, NoteStore, export_markdown
from .themes import apply_palette

MARK = "  \u270e"  # pencil, shown after titles that have a note
AUTOSAVE_MS = 800


class NotesWindow(QMainWindow):
    """Notes of the open book: contents tree on the left, text editor on the right."""

    closed = Signal(object)
    notesChanged = Signal()  # a note was added, changed or removed

    def __init__(
        self,
        store: NoteStore,
        flat: list[FlatEntry],
        book_title: str,
        colors,
        on_jump,
    ):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        avail = QGuiApplication.primaryScreen().availableGeometry()
        self.resize(min(1000, avail.width() - 80), min(650, avail.height() - 80))

        self.store = store
        self.flat = flat
        self.book_title = book_title
        self.on_jump = on_jump  # called with an anchor key
        self._colors = tuple(colors)
        self._current = -1  # index into self.flat of the entry being edited
        self._dirty = False
        self._loading = False
        self._items: list[QTreeWidgetItem] = []

        # ---- left: tree + filter ----
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.only_notes = QCheckBox("Only entries with notes")
        left = QWidget()
        lbox = QVBoxLayout(left)
        lbox.setContentsMargins(0, 0, 0, 0)
        lbox.addWidget(self.tree, 1)
        lbox.addWidget(self.only_notes)

        stack: list[tuple[int, QTreeWidgetItem]] = []
        for i, f in enumerate(flat):
            while stack and stack[-1][0] >= f.depth:
                stack.pop()
            parent = stack[-1][1] if stack else self.tree.invisibleRootItem()
            item = QTreeWidgetItem(parent, [f.entry.title])
            item.setData(0, Qt.ItemDataRole.UserRole, i)
            if f.note_id is None:  # no anchor: can't hold a note
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            stack.append((f.depth, item))
            self._items.append(item)
        self.tree.expandAll()

        # ---- right: editor + buttons ----
        self.title_label = QLabel("")
        self.title_label.setWordWrap(True)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Select a chapter or part on the left to write a note.")
        self.editor.setEnabled(False)
        self.btn_export = QPushButton("Export Markdown...")
        self.btn_copy = QPushButton("Copy all notes")
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.btn_copy)
        buttons.addWidget(self.btn_export)
        right = QWidget()
        rbox = QVBoxLayout(right)
        rbox.setContentsMargins(0, 0, 0, 0)
        rbox.addWidget(self.title_label)
        rbox.addWidget(self.editor, 1)
        rbox.addLayout(buttons)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([320, 620])
        self.setCentralWidget(splitter)

        # ---- autosave ----
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(AUTOSAVE_MS)
        self._timer.timeout.connect(self._flush)

        self.tree.currentItemChanged.connect(self._on_current_changed)
        self.tree.itemClicked.connect(self._on_clicked)
        self.editor.textChanged.connect(self._on_text)
        self.only_notes.toggled.connect(lambda _: self._apply_filter())
        self.btn_export.clicked.connect(self.export_file)
        self.btn_copy.clicked.connect(self.copy_all)

        self.apply_colors(*colors)
        self._update_title()

    # ---------- look ----------
    def apply_colors(self, bg: str, fg: str) -> None:
        self._colors = (bg, fg)
        apply_palette(self.tree, bg, fg)
        apply_palette(self.editor, bg, fg)
        self._style_items()

    def _style_items(self) -> None:
        bg, fg = QColor(self._colors[0]), QColor(self._colors[1])
        grey = QColor(
            (fg.red() + bg.red()) // 2,
            (fg.green() + bg.green()) // 2,
            (fg.blue() + bg.blue()) // 2,
        )
        current = self.tree.currentItem()
        for f, item in zip(self.flat, self._items):
            has = self.store.has(f.note_id)
            font = item.font(0)
            font.setBold(has)
            item.setFont(0, font)
            item.setText(0, f.entry.title + (MARK if has else ""))
            if item is current:
                brush = QBrush(bg)  # matches the highlight colors of apply_palette
            else:
                brush = QBrush(fg if has else grey)
            item.setForeground(0, brush)

    def _apply_filter(self) -> None:
        only = self.only_notes.isChecked()

        def visit(item: QTreeWidgetItem) -> bool:
            i = item.data(0, Qt.ItemDataRole.UserRole)
            useful = self.store.has(self.flat[i].note_id)
            for c in range(item.childCount()):
                if visit(item.child(c)):
                    useful = True
            item.setHidden(only and not useful)
            return useful

        root = self.tree.invisibleRootItem()
        for c in range(root.childCount()):
            visit(root.child(c))

    def _update_title(self) -> None:
        self.setWindowTitle(f"Notes ({self.store.count()}) - {self.book_title}")

    # ---------- selecting ----------
    def select_note(self, note_id: str) -> None:
        for i, f in enumerate(self.flat):
            if f.note_id == note_id:
                item = self._items[i]
                if item.isHidden():
                    self.only_notes.setChecked(False)
                self.tree.setCurrentItem(item)
                self.tree.scrollToItem(item)
                self.editor.setFocus()
                return

    def _on_current_changed(self, item, _prev) -> None:
        self._flush()  # save the entry we are leaving
        self._current = -1
        self._loading = True
        try:
            if item is None:
                self.editor.setPlainText("")
                self.editor.setEnabled(False)
                self.title_label.setText("")
                return
            i = item.data(0, Qt.ItemDataRole.UserRole)
            self._current = i
            f = self.flat[i]
            self.editor.setEnabled(True)
            self.editor.setPlainText(self.store.get(f.note_id))
            self.title_label.setText(f"<b>{f.entry.title.replace('<', '&lt;')}</b>")
        finally:
            self._loading = False
        self._style_items()
        if self.only_notes.isChecked():
            self._apply_filter()

    def _on_clicked(self, item, _col) -> None:
        i = item.data(0, Qt.ItemDataRole.UserRole)
        key = self.flat[i].entry.key
        if key:
            self.on_jump(key)  # go_to_anchor: Back works

    # ---------- saving ----------
    def _on_text(self) -> None:
        if self._loading or self._current < 0:
            return
        self._dirty = True
        self._timer.start()

    def _flush(self) -> None:
        self._timer.stop()
        if not self._dirty or self._current < 0:
            self._dirty = False
            return
        self._dirty = False
        f = self.flat[self._current]
        if not self.store.set(f.note_id, f.entry.title, self.editor.toPlainText()):
            return
        try:
            self.store.save()
        except OSError as e:
            QMessageBox.warning(self, "Notes", f"Could not save notes:\n{e}")
        self._style_items()
        self._update_title()
        self.notesChanged.emit()

    # ---------- export ----------
    def _markdown(self) -> str:
        self._flush()
        return export_markdown(self.book_title, self.flat, self.store)

    def copy_all(self) -> None:
        if not self.store.count():
            self.statusBar().showMessage("There are no notes yet", 3000)
            return
        QApplication.clipboard().setText(self._markdown())
        self.statusBar().showMessage("All notes copied", 3000)

    def export_file(self) -> None:
        if not self.store.count():
            self.statusBar().showMessage("There are no notes yet", 3000)
            return
        safe = "".join(c for c in self.book_title if c not in '\\/:*?"<>|').strip() or "notes"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export notes", f"{safe} - notes.md", "Markdown (*.md);;Text (*.txt)"
        )
        if not path:
            return
        try:
            Path(path).write_text(self._markdown(), encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, "Export notes", str(e))
            return
        self.statusBar().showMessage("Exported", 3000)

    def closeEvent(self, event):
        self._flush()
        self.closed.emit(self)
        super().closeEvent(event)
