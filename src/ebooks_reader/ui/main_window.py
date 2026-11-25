import hashlib
import os
from bisect import bisect_right
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths, QTimer, Qt
from PySide6.QtGui import QAction, QColor, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.models import TocEntry
from ..formats import file_dialog_filter, load_book
from .bookmarks import Bookmark, load_bookmarks, save_bookmarks
from .find_bar import FindBar
from .image_viewer import ImageViewer
from .notes import NoteStore, flatten
from .notes_window import NotesWindow
from .reader_view import ReaderView
from .covers import save_auto_cover
from .recent import add_recent, clear_recent, load_recent, set_title
from .themes import DEFAULT_THEME, THEMES, apply_palette
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from ..core.updater import UpdateChecker
from ..version import __version__
from .theme_dialog import ThemeDialog
from .themes import all_themes, grouped_themes
from .typography import Typography, TypographyDialog
from .viewer_window import ViewerWindow

APP_TITLE = "Ebooks Reader"


def _position_key(path: str) -> str:
    norm = os.path.normcase(os.path.abspath(path))
    return "positions/" + hashlib.md5(norm.encode("utf-8")).hexdigest()


def _bookmarks_key(path: str) -> str:
    return "bookmarks/" + _position_key(path).split("/", 1)[1]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings()
        self.on_show_launcher = None  # set by the app: shows the start window
        self.current_path: str | None = None
        self.extra_windows: list[ViewerWindow] = []
        self.chapters: list[str] = []
        self.bookmarks: list[Bookmark] = []
        self._section_starts: list[int] = []  # sorted character offsets
        self._section_titles: list[str] = []
        self._section_items: list[QTreeWidgetItem | None] = []
        self._entry_items: dict[int, QTreeWidgetItem] = {}  # id(TocEntry) -> tree item
        self._current_section = -1  # index into _section_starts
        self.image_viewer: ImageViewer | None = None
        self.notes_window: NotesWindow | None = None
        self.note_store: NoteStore | None = None
        self._flat: list = []
        self._note_ids: dict[int, str | None] = {}  # id(TocEntry) -> note id
        self._book_title = ""
        self._section_entries: list[TocEntry] = []
        self.setWindowTitle(APP_TITLE)
        self.resize(1100, 800)

        self.reader = ReaderView()
        self.reader.linkRequested.connect(self.open_link_window)
        self.reader.imageRequested.connect(self.open_image)
        self.reader.history_enabled = True
        self.reader.historyChanged.connect(self._update_history_actions)
        self.reader.links_in_window = self.settings.value("links_in_window", True, type=bool)
        self.find_bar = FindBar(self.reader)
        central = QWidget()
        box = QVBoxLayout(central)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        box.addWidget(self.reader, 1)
        box.addWidget(self.find_bar)
        self.setCentralWidget(central)

        # save the reading position 1 s after scrolling stops
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1000)
        self._save_timer.timeout.connect(self._save_position)
        self.reader.verticalScrollBar().valueChanged.connect(
            lambda _: self._save_timer.start()
        )

        # reading progress in the status bar (refreshed 120 ms after scrolling)
        self.progress_label = QLabel("")
        self.progress_label.setContentsMargins(0, 0, 8, 0)
        self.statusBar().addPermanentWidget(self.progress_label)
        self._progress_timer = QTimer(self)
        self._progress_timer.setSingleShot(True)
        self._progress_timer.setInterval(120)
        self._progress_timer.timeout.connect(self._update_progress)
        self.reader.verticalScrollBar().valueChanged.connect(
            lambda _: self._progress_timer.start()
        )

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._goto)
        self.tree.itemActivated.connect(self._goto)

        self.dock = QDockWidget("Contents", self)
        self.dock.setObjectName("contents_dock")
        self.dock.setWidget(self.tree)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock)
        self.resizeDocks([self.dock], [320], Qt.Orientation.Horizontal)

        self._build_menus()

        default_bg, default_fg = THEMES[DEFAULT_THEME]
        self.apply_colors(
            str(self.settings.value("bg", default_bg)),
            str(self.settings.value("fg", default_fg)),
        )
        self.typography = Typography.load(self.settings)
        self.reader.apply_typography(self.typography)

        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        state = self.settings.value("window_state")
        if state:
            self.restoreState(state)

    # ---------- menus ----------
    def _build_menus(self):
        m_file = self.menuBar().addMenu("&File")
        act_open = QAction("&Open...", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.triggered.connect(self.open_dialog)
        m_file.addAction(act_open)

        self.m_recent = m_file.addMenu("Recent &books")
        self.rebuild_recent_menu()

        act_start = QAction("&Library...", self)
        act_start.triggered.connect(self.show_launcher)
        m_file.addAction(act_start)

        # off: the last book is reopened at startup instead of showing the window
        self.act_show_start = QAction("Show start window on startup", self)
        self.act_show_start.setCheckable(True)
        self.act_show_start.setChecked(self.settings.value("show_start", True, type=bool))
        self.act_show_start.toggled.connect(lambda v: self.settings.setValue("show_start", v))
        m_file.addAction(self.act_show_start)
        m_file.aboutToShow.connect(  # the launcher has the same checkbox
            lambda: self.act_show_start.setChecked(
                self.settings.value("show_start", True, type=bool)
            )
        )

        m_file.addSeparator()
        act_quit = QAction("&Quit", self)
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

        m_edit = self.menuBar().addMenu("&Edit")
        act_find = QAction("&Find in book...", self)
        act_find.setShortcut("Ctrl+F")
        act_find.triggered.connect(self.find_bar.open)
        m_edit.addAction(act_find)
        act_find_next = QAction("Find &next", self)
        act_find_next.setShortcut("F3")
        act_find_next.triggered.connect(self.find_bar.find_next)
        m_edit.addAction(act_find_next)
        act_find_prev = QAction("Find &previous", self)
        act_find_prev.setShortcut("Shift+F3")
        act_find_prev.triggered.connect(self.find_bar.find_prev)
        m_edit.addAction(act_find_prev)

        m_view = self.menuBar().addMenu("&View")
        toggle = self.dock.toggleViewAction()
        toggle.setText("Show &contents")
        toggle.setShortcut("F9")
        m_view.addAction(toggle)
        for text, fn in (
            ("Expand all", self.tree.expandAll),
            ("Collapse all", self.tree.collapseAll),
        ):
            a = QAction(text, self)
            a.triggered.connect(fn)
            m_view.addAction(a)
        m_view.addSeparator()

        self.act_links = QAction("Open book links in separate window", self)
        self.act_links.setCheckable(True)
        self.act_links.setChecked(self.reader.links_in_window)
        self.act_links.toggled.connect(self.set_links_in_window)
        m_view.addAction(self.act_links)
        m_view.addSeparator()

        a_text = QAction("&Text settings...", self)
        a_text.setShortcut("Ctrl+T")
        a_text.triggered.connect(self.open_text_settings)
        m_view.addAction(a_text)
        zin = QAction("Larger font", self)
        zin.setShortcut("Ctrl+=")
        zin.triggered.connect(lambda: self.change_size(+1))
        zout = QAction("Smaller font", self)
        zout.setShortcut("Ctrl+-")
        zout.triggered.connect(lambda: self.change_size(-1))
        m_view.addAction(zin)
        m_view.addAction(zout)

        m_go = self.menuBar().addMenu("&Go")
        self.act_back = QAction("&Back", self)
        self.act_back.setShortcut("Alt+Left")
        self.act_back.triggered.connect(self.reader.go_back)
        m_go.addAction(self.act_back)
        self.act_forward = QAction("&Forward", self)
        self.act_forward.setShortcut("Alt+Right")
        self.act_forward.triggered.connect(self.reader.go_forward)
        m_go.addAction(self.act_forward)
        self._update_history_actions()

        self.m_bookmarks = self.menuBar().addMenu("&Bookmarks")
        act_add_bm = QAction("&Add bookmark here", self)
        act_add_bm.setShortcut("Ctrl+D")
        act_add_bm.triggered.connect(self.add_bookmark)
        self.m_bookmarks.addAction(act_add_bm)
        self._bm_sep = self.m_bookmarks.addSeparator()
        self.m_bm_remove = self.m_bookmarks.addMenu("&Remove bookmark")
        self._bm_actions: list[QAction] = []
        self._rebuild_bookmark_menu()

        m_notes = self.menuBar().addMenu("&Notes")
        act_show_notes = QAction("&Show notes...", self)
        act_show_notes.setShortcut("Ctrl+Shift+N")
        act_show_notes.triggered.connect(lambda: self.show_notes())
        m_notes.addAction(act_show_notes)
        act_add_note = QAction("&Add note for current section", self)
        act_add_note.setShortcut("Ctrl+N")
        act_add_note.triggered.connect(self.add_note_here)
        m_notes.addAction(act_add_note)

        self.m_theme = self.menuBar().addMenu("&Theme")
        self.rebuild_theme_menu()

        m_help = self.menuBar().addMenu("&Help")
        a_update = QAction("Check for &updates...", self)
        a_update.triggered.connect(lambda: self.check_updates(silent=False))
        m_help.addAction(a_update)
        self.act_auto_update = QAction("Check for updates on startup", self)
        self.act_auto_update.setCheckable(True)
        self.act_auto_update.setChecked(self.settings.value("auto_update", True, type=bool))
        self.act_auto_update.toggled.connect(lambda v: self.settings.setValue("auto_update", v))
        m_help.addAction(self.act_auto_update)
        m_help.addSeparator()
        a_about = QAction("&About", self)
        a_about.triggered.connect(self.show_about)
        m_help.addAction(a_about)

    # ---------- themes ----------
    def rebuild_theme_menu(self):
        self.m_theme.clear()
        themes = all_themes(self.settings)
        for group, names in grouped_themes(self.settings):
            if not names:
                continue
            header = QAction(f"{group} themes", self.m_theme)
            header.setEnabled(False)
            self.m_theme.addAction(header)
            for name in names:
                bg, fg = themes[name]
                a = QAction(name, self.m_theme)
                a.triggered.connect(lambda _=False, b=bg, f=fg: self.apply_colors(b, f))
                self.m_theme.addAction(a)
            self.m_theme.addSeparator()
        a_edit = QAction("Edit themes...", self.m_theme)
        a_edit.setShortcut("Ctrl+Shift+T")
        a_edit.triggered.connect(self.open_theme_editor)
        self.m_theme.addAction(a_edit)

    def open_theme_editor(self):
        dlg = getattr(self, "_theme_dlg", None)
        try:
            if dlg is not None and dlg.isVisible():
                dlg.raise_()
                dlg.activateWindow()
                return
        except RuntimeError:  # window was already deleted
            pass
        dlg = ThemeDialog(self.settings, self.bg, self.fg, self.apply_colors, self)
        dlg.themesChanged.connect(self.rebuild_theme_menu)
        self._theme_dlg = dlg
        dlg.show()

    # ---------- colors ----------
    def apply_colors(self, bg: str, fg: str):
        self.bg, self.fg = bg, fg
        apply_palette(self.tree, bg, fg)
        self.reader.apply_colors(bg, fg)
        for w in self.extra_windows:
            w.reader.apply_colors(bg, fg)
        if self.image_viewer is not None:
            self.image_viewer.apply_colors(bg, fg)
        if self.notes_window is not None:
            self.notes_window.apply_colors(bg, fg)
        self.settings.setValue("bg", bg)
        self.settings.setValue("fg", fg)

    def pick_bg(self):
        c = QColorDialog.getColor(QColor(self.bg), self, "Background color")
        if c.isValid():
            self.apply_colors(c.name(), self.fg)

    def pick_fg(self):
        c = QColorDialog.getColor(QColor(self.fg), self, "Text color")
        if c.isValid():
            self.apply_colors(self.bg, c.name())

    # ---------- typography ----------
    def open_text_settings(self):
        dlg = TypographyDialog(self.typography, self)
        if dlg.exec():
            self.set_typography(dlg.result_value())

    def change_size(self, delta: int):
        size = max(6, min(72, self.typography.size + delta))
        self.set_typography(replace(self.typography, size=size))

    def set_typography(self, t: Typography):
        self.typography = t
        t.save(self.settings)
        self.reader.apply_typography(t)
        for w in self.extra_windows:
            w.reader.apply_typography(t)

    # ---------- books ----------
    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open book", "", file_dialog_filter())
        if path:
            self.open_book(path)

    def open_book(self, path: str):
        self._save_position()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            book = load_book(path)
            for w in list(self.extra_windows):
                w.close()
            if self.image_viewer is not None:
                self.image_viewer.close()
            if self.notes_window is not None:
                self.notes_window.close()  # saves its note first
            self.find_bar.close_bar()
            self.reader.set_book(book.html, book.resources, book.image_anchors)
            self.chapters = book.chapters
            self.tree.clear()
            self._entry_items = {}
            self._current_section = -1
            self._add_entries(self.tree.invisibleRootItem(), book.toc)
            self.tree.expandToDepth(0)
            self._index_sections(book.toc)
            self.setWindowTitle(f"{book.title} - {APP_TITLE}")
            self.current_path = path
            self.settings.setValue("last_book", path)
            add_recent(self.settings, path)
            set_title(self.settings, path, book.title)
            if book.cover:
                save_auto_cover(path, book.cover)
            self.rebuild_recent_menu()
            self.bookmarks = load_bookmarks(self.settings, _bookmarks_key(path))
            self._rebuild_bookmark_menu()
            self._load_notes(path, book)

            self._update_progress()
            pos = self.settings.value(_position_key(path), 0, type=int)
            if pos:
                self.reader.restore_position(pos)
        except Exception as e:
            QMessageBox.critical(self, "Could not open book", f"{type(e).__name__}: {e}")
        finally:
            QApplication.restoreOverrideCursor()

    def rebuild_recent_menu(self):
        self.m_recent.clear()
        paths = [p for p in load_recent(self.settings) if Path(p).is_file()]
        if not paths:
            none = QAction("(no recent books)", self.m_recent)
            none.setEnabled(False)
            self.m_recent.addAction(none)
            return
        for p in paths:
            a = QAction(Path(p).name.replace("&", "&&"), self.m_recent)
            a.setToolTip(p)
            a.setStatusTip(p)
            a.triggered.connect(lambda _=False, path=p: self.open_book(path))
            self.m_recent.addAction(a)
        self.m_recent.addSeparator()
        clear = QAction("Clear list", self.m_recent)
        clear.triggered.connect(self._clear_recent)
        self.m_recent.addAction(clear)

    def _clear_recent(self):
        clear_recent(self.settings)
        self.rebuild_recent_menu()

    def show_launcher(self):
        if self.on_show_launcher is not None:
            self.on_show_launcher()

    def reopen_last_book(self):
        path = str(self.settings.value("last_book", ""))
        if path and Path(path).is_file():
            self.open_book(path)

    def _save_position(self):
        if self.current_path:
            self.settings.setValue(
                _position_key(self.current_path), self.reader.current_position()
            )

    def _add_entries(self, parent, entries: list[TocEntry]):
        for e in entries:
            item = QTreeWidgetItem(parent, [e.title])
            self._entry_items[id(e)] = item
            item.setData(0, Qt.ItemDataRole.UserRole, e.key)
            self._add_entries(item, e.children)

    def _goto(self, item, *_):
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key:
            self.reader.go_to_anchor(key)  # remembers where I was (Back)

    def _update_history_actions(self):
        if hasattr(self, "act_back"):
            self.act_back.setEnabled(self.reader.can_go_back())
            self.act_forward.setEnabled(self.reader.can_go_forward())

    # ---------- bookmarks ----------
    def _percent_at(self, pos: int) -> int:
        total = max(self.reader.document().characterCount() - 1, 1)
        return min(100, int(pos * 100 / total))

    def _snippet(self, pos: int, length: int = 60) -> str:
        doc = self.reader.document()
        cur = QTextCursor(doc)
        cur.setPosition(max(0, min(pos, doc.characterCount() - 1)))
        cur.movePosition(
            QTextCursor.MoveOperation.NextCharacter,
            QTextCursor.MoveMode.KeepAnchor,
            length,
        )
        text = cur.selectedText()
        for old, new in (("\u2029", " "), ("\u2028", " "), ("\ufffc", "[image]")):
            text = text.replace(old, new)
        return " ".join(text.split())

    def add_bookmark(self):
        if not self.current_path:
            return
        pos = self.reader.current_position()
        if any(abs(b.pos - pos) < 50 for b in self.bookmarks):
            self.statusBar().showMessage("There is already a bookmark here", 3000)
            return
        label = f"{self._percent_at(pos)}%  {self._snippet(pos)}".strip()
        self.bookmarks.append(Bookmark(pos, label))
        self.bookmarks.sort(key=lambda b: b.pos)
        save_bookmarks(self.settings, _bookmarks_key(self.current_path), self.bookmarks)
        self._rebuild_bookmark_menu()
        self.statusBar().showMessage("Bookmark added", 3000)

    def remove_bookmark(self, bm: Bookmark):
        if bm in self.bookmarks and self.current_path:
            self.bookmarks.remove(bm)
            save_bookmarks(self.settings, _bookmarks_key(self.current_path), self.bookmarks)
            self._rebuild_bookmark_menu()

    def _rebuild_bookmark_menu(self):
        for a in self._bm_actions:
            self.m_bookmarks.removeAction(a)
            a.deleteLater()
        self._bm_actions = []
        self.m_bm_remove.clear()
        if not self.bookmarks:
            none = QAction("(no bookmarks in this book)", self.m_bookmarks)
            none.setEnabled(False)
            self.m_bookmarks.insertAction(self._bm_sep, none)
            self._bm_actions.append(none)
        for bm in self.bookmarks:
            text = bm.label.replace("&", "&&")
            go = QAction(text, self.m_bookmarks)
            go.triggered.connect(lambda _=False, p=bm.pos: self.reader.jump_to_position(p))
            self.m_bookmarks.insertAction(self._bm_sep, go)
            self._bm_actions.append(go)
            rm = self.m_bm_remove.addAction(text)
            rm.triggered.connect(lambda _=False, b=bm: self.remove_bookmark(b))
        self.m_bm_remove.setEnabled(bool(self.bookmarks))

    # ---------- reading progress ----------
    def _index_sections(self, toc: list[TocEntry]):
        """Remember where each contents entry starts, to name the current section."""
        anchors = self.reader.anchor_positions()
        found: list[tuple[int, str, TocEntry]] = []

        def walk(entries):
            for e in entries:
                if e.key in anchors:
                    found.append((anchors[e.key], e.title, e))
                walk(e.children)

        walk(toc)
        found.sort(key=lambda t: t[0])  # stable: a child follows its parent
        self._section_starts = [p for p, _, _ in found]
        self._section_titles = [t for _, t, _ in found]
        self._section_items = [self._entry_items.get(id(e)) for _, _, e in found]
        self._section_entries = [e for _, _, e in found]
        self._current_section = -1

    # a click on a contents entry can leave the top line a few characters
    # before the anchor; look slightly ahead so the clicked section wins
    SECTION_LOOKAHEAD = 10

    def _section_index(self, pos: int) -> int:
        return bisect_right(self._section_starts, pos + self.SECTION_LOOKAHEAD) - 1

    def _section_at(self, pos: int) -> str:
        i = self._section_index(pos)
        return self._section_titles[i] if i >= 0 else ""

    def _select_section(self, pos: int) -> None:
        """Highlight the section at `pos` in the contents tree."""
        i = self._section_index(pos)
        if i == self._current_section:
            return
        self._current_section = i
        item = self._section_items[i] if i >= 0 else None
        self.tree.blockSignals(True)
        try:
            if item is None:
                self.tree.setCurrentItem(None)
                self.tree.clearSelection()
            else:
                parent = item.parent()
                while parent is not None:
                    parent.setExpanded(True)
                    parent = parent.parent()
                self.tree.setCurrentItem(item)
                self.tree.scrollToItem(item)
        finally:
            self.tree.blockSignals(False)

    def _update_progress(self):
        if not self.current_path:
            self.progress_label.setText("")
            return
        bar = self.reader.verticalScrollBar()
        pos = self.reader.current_position()
        at_end = bar.maximum() > 0 and bar.value() >= bar.maximum()
        percent = 100 if at_end else self._percent_at(pos)
        self._select_section(pos)
        title = self._section_at(pos)
        if len(title) > 60:
            title = title[:59] + "…"
        self.progress_label.setText(f"{title}  ·  {percent}%" if title else f"{percent}%")

    # ---------- notes ----------
    def _notes_dir(self) -> Path:
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        return Path(base) / "notes"

    def _load_notes(self, path: str, book) -> None:
        name = _position_key(path).split("/", 1)[1]  # same md5 as positions and bookmarks
        self.note_store = NoteStore(self._notes_dir() / f"{name}.json")
        self._flat = flatten(book.toc)
        self._note_ids = {id(f.entry): f.note_id for f in self._flat}
        self._book_title = book.title
        self._update_note_markers()

    def _update_note_markers(self) -> None:
        store = self.note_store
        for f in self._flat:
            item = self._entry_items.get(id(f.entry))
            if item is None:
                continue
            mark = store is not None and store.has(f.note_id)
            item.setText(0, f.entry.title + ("  \u270e" if mark else ""))

    def show_notes(self, note_id: str | None = None) -> None:
        if not self.current_path or self.note_store is None:
            return
        w = self.notes_window
        if w is None:
            w = NotesWindow(
                self.note_store,
                self._flat,
                self._book_title,
                (self.bg, self.fg),
                self.reader.go_to_anchor,
            )
            w.notesChanged.connect(self._update_note_markers)
            w.closed.connect(self._notes_window_closed)
            self.notes_window = w
        w.show()
        w.raise_()
        w.activateWindow()
        if note_id:
            w.select_note(note_id)

    def add_note_here(self) -> None:
        if not self.current_path:
            return
        i = self._section_index(self.reader.current_position())
        entry = self._section_entries[i] if 0 <= i < len(self._section_entries) else None
        note_id = self._note_ids.get(id(entry)) if entry is not None else None
        if note_id is None:
            self.statusBar().showMessage(
                "No contents section at this place; showing all notes", 4000
            )
        self.show_notes(note_id)

    def _notes_window_closed(self, _w) -> None:
        self.notes_window = None

    # ---------- extra windows ----------
    def set_links_in_window(self, value: bool):
        self.reader.links_in_window = value
        self.settings.setValue("links_in_window", value)

    def open_link_window(self, fragment: str, force_new: bool = False):
        # Reuse the most recent linked window unless a new one is requested
        if not force_new and self.extra_windows:
            self.extra_windows[-1].show_fragment(fragment)
            return
        w = ViewerWindow(
            self.chapters or [self.reader.html_source],
            self.reader.resources,
            fragment,
            (self.bg, self.fg),
            self.typography,
            self.open_link_window,
            self.reader.image_anchors,
            self.open_image,
        )
        w.closed.connect(self._window_closed)
        self.extra_windows.append(w)
        w.show()

    def _window_closed(self, w):
        if w in self.extra_windows:
            self.extra_windows.remove(w)

    # ---------- image viewer ----------
    def open_image(self, name: str):
        data = self.reader.resources.get(name)
        if data is None:
            return
        if self.image_viewer is None:
            self.image_viewer = ImageViewer((self.bg, self.fg))
            self.image_viewer.closed.connect(self._image_viewer_closed)
        if not self.image_viewer.show_image(name, data):
            QMessageBox.warning(self, "Image", "This image format can't be displayed.")

    def _image_viewer_closed(self, _w):
        self.image_viewer = None

    # ---------- updates ----------
    def startup_update_check(self):
        if self.settings.value("auto_update", True, type=bool):
            self.check_updates(silent=True)

    def check_updates(self, silent: bool = False):
        checker = getattr(self, "_checker", None)
        if checker is not None and checker.isRunning():
            return
        self._checker = UpdateChecker(self)
        self._checker.result.connect(lambda r: self._on_update_result(r, silent))
        self._checker.start()

    def _on_update_result(self, r: dict, silent: bool):
        status = r.get("status")
        if status == "update":
            text = f"Version {r['version']} is available (you have {__version__})."
            if r.get("notes"):
                text += "\n\n" + r["notes"]
            text += "\n\nOpen the download page?"
            answer = QMessageBox.question(self, "Update available", text)
            if answer == QMessageBox.StandardButton.Yes and r.get("url"):
                QDesktopServices.openUrl(QUrl(r["url"]))
        elif not silent:
            if status == "latest":
                QMessageBox.information(
                    self, "Check for updates", f"You have the latest version ({__version__})."
                )
            else:
                QMessageBox.warning(
                    self, "Check for updates", r.get("message", "Could not check for updates.")
                )

    def show_about(self):
        QMessageBox.about(
            self, f"About {APP_TITLE}", f"{APP_TITLE}\nVersion {__version__}"
        )

    # ---------- shutdown ----------
    def closeEvent(self, event):
        self._save_position()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("window_state", self.saveState())
        if self.notes_window is not None:
            self.notes_window.close()
        if self.image_viewer is not None:
            self.image_viewer.close()
        for w in list(self.extra_windows):
            w.close()
        super().closeEvent(event)
