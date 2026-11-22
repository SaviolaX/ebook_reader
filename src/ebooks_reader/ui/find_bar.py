from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)


class _FindEdit(QLineEdit):
    nextRequested = Signal()
    prevRequested = Signal()
    escapePressed = Signal()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.prevRequested.emit()
            else:
                self.nextRequested.emit()
            return
        if key == Qt.Key.Key_Escape:
            self.escapePressed.emit()
            return
        super().keyPressEvent(event)


class FindBar(QWidget):
    """Slim search bar shown under the reader (Ctrl+F).

    Enter = next, Shift+Enter = previous, Esc = close. The search wraps around.
    """

    def __init__(self, reader, parent=None):
        super().__init__(parent)
        self.reader = reader
        self._session_pushed = False  # Back history entry made for this search?

        self.edit = _FindEdit()
        self.edit.setPlaceholderText("Find in book")
        self.edit.setClearButtonEnabled(True)
        self.btn_prev = QPushButton("Previous")
        self.btn_next = QPushButton("Next")
        self.case = QCheckBox("Match case")
        self.status = QLabel("")
        self.btn_close = QPushButton("Close")

        row = QHBoxLayout(self)
        row.setContentsMargins(6, 3, 6, 3)
        row.addWidget(self.edit, 1)
        row.addWidget(self.btn_prev)
        row.addWidget(self.btn_next)
        row.addWidget(self.case)
        row.addWidget(self.status)
        row.addWidget(self.btn_close)

        self.edit.textChanged.connect(self._on_text)
        self.edit.nextRequested.connect(self.find_next)
        self.edit.prevRequested.connect(self.find_prev)
        self.edit.escapePressed.connect(self.close_bar)
        self.btn_next.clicked.connect(self.find_next)
        self.btn_prev.clicked.connect(self.find_prev)
        self.btn_close.clicked.connect(self.close_bar)
        self.case.toggled.connect(lambda _: self._on_text(self.edit.text()))
        self.hide()

    # ---------- show / hide ----------
    def open(self) -> None:
        sel = self.reader.textCursor().selectedText()
        if sel and "\u2029" not in sel and len(sel) <= 100:
            self.edit.setText(sel)  # search for the selected text
        self._session_pushed = False
        self.show()
        self.edit.setFocus()
        self.edit.selectAll()

    def close_bar(self) -> None:
        cur = self.reader.textCursor()
        cur.clearSelection()
        self.reader.setTextCursor(cur)
        self.status.setText("")
        self.hide()
        self.reader.setFocus()

    # ---------- searching ----------
    def find_next(self) -> bool:
        return self._find(backwards=False)

    def find_prev(self) -> bool:
        return self._find(backwards=True)

    def _on_text(self, _text) -> None:
        # incremental search: look from the current hit (or the top of the page)
        self._find(backwards=False, incremental=True)

    def _flags(self, backwards: bool):
        flags = QTextDocument.FindFlag(0)
        if self.case.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if backwards:
            flags |= QTextDocument.FindFlag.FindBackward
        return flags

    def _hit_visible(self) -> bool:
        cur = self.reader.textCursor()
        if not cur.hasSelection():
            return False
        probe = QTextCursor(cur)
        probe.setPosition(cur.selectionStart())
        top = self.reader.cursorRect(probe).top()
        return 0 <= top < self.reader.viewport().height()

    def _place_cursor(self, keep_hit_start: bool) -> None:
        """Make the search start from what the person is looking at."""
        cur = self.reader.textCursor()
        if self._hit_visible():
            if keep_hit_start:
                cur.setPosition(cur.selectionStart())
                self.reader.setTextCursor(cur)
            return
        cur = QTextCursor(self.reader.document())
        cur.setPosition(self.reader.current_position())
        self.reader.setTextCursor(cur)

    def _find(self, backwards: bool, incremental: bool = False) -> bool:
        text = self.edit.text()
        if not text:
            self.status.setText("")
            return False
        r = self.reader
        old = r.textCursor()  # restored if nothing is found: the current hit stays
        self._place_cursor(keep_hit_start=incremental)
        flags = self._flags(backwards)
        before = r.current_position()  # where I was, before the search scrolls
        found = r.find(text, flags)
        wrapped = False
        if not found:
            cur = QTextCursor(r.document())
            cur.movePosition(
                QTextCursor.MoveOperation.End
                if backwards
                else QTextCursor.MoveOperation.Start
            )
            r.setTextCursor(cur)
            found = r.find(text, flags)
            wrapped = found
        if not found:
            r.setTextCursor(old)
            self.status.setText("Not found")
            return False
        if not self._session_pushed:
            self._session_pushed = True
            r.remember_position(at=before)  # Back returns to where I was
        r.reveal_cursor()
        self.status.setText("Search wrapped" if wrapped else "")
        return True
