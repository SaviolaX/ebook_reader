import re

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMainWindow

from .reader_view import ReaderView
from .typography import Typography

_CHAPTER_RE = re.compile(r"^c(\d+)(?:_|$)")


class ViewerWindow(QMainWindow):
    """Extra window that shows one chapter of the book at a time."""

    closed = Signal(object)

    def __init__(
        self,
        chapters: list[str],
        resources,
        fragment: str,
        colors,
        typography: Typography,
        on_link,
        image_anchors=None,
    ):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Linked view")
        avail = QGuiApplication.primaryScreen().availableGeometry()
        self.resize(
            min(1280, avail.width() - 80),
            min(720, avail.height() - 80),
        )

        self.chapters = chapters
        self.resources = resources
        self.image_anchors = image_anchors
        self.current = -1  # index of the chapter currently shown

        self.reader = ReaderView()
        self.reader.typography = typography
        self.reader._apply_font_and_margin()
        self.reader.links_in_window = False  # clicks scroll inside this window
        self.reader.center_anchors = True  # targets appear in the middle
        self.reader.before_anchor = self._ensure_chapter
        self.reader.linkRequested.connect(on_link)  # only Ctrl+click / context menu
        self.setCentralWidget(self.reader)
        self.reader.apply_colors(*colors)

        self._ensure_chapter(fragment)
        QTimer.singleShot(50, lambda: self.reader.go_to_anchor(fragment))

    def _chapter_index(self, name: str) -> int:
        m = _CHAPTER_RE.match(name)
        if m and int(m.group(1)) < len(self.chapters):
            return int(m.group(1))
        return max(self.current, 0)

    def _ensure_chapter(self, name: str) -> bool:
        """Load the chapter holding `name`. Returns True if content was replaced."""
        idx = self._chapter_index(name)
        if idx == self.current:
            return False
        self.current = idx
        html = "<html><body>" + self.chapters[idx] + "</body></html>"
        self.reader.set_book(html, self.resources, self.image_anchors)
        return True

    def show_fragment(self, fragment: str) -> None:
        self.reader.go_to_anchor(fragment)
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        self.closed.emit(self)
        super().closeEvent(event)
