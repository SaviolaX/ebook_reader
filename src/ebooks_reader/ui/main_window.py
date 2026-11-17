import hashlib
import os
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
)

from ..core.models import TocEntry
from ..formats import file_dialog_filter, load_book
from .reader_view import ReaderView
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings()
        self.current_path: str | None = None
        self.extra_windows: list[ViewerWindow] = []
        self.chapters: list[str] = []
        self.setWindowTitle(APP_TITLE)
        self.resize(1100, 800)

        self.reader = ReaderView()
        self.reader.linkRequested.connect(self.open_link_window)
        self.reader.links_in_window = self.settings.value("links_in_window", True, type=bool)
        self.setCentralWidget(self.reader)

        # save the reading position 1 s after scrolling stops
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1000)
        self._save_timer.timeout.connect(self._save_position)
        self.reader.verticalScrollBar().valueChanged.connect(
            lambda _: self._save_timer.start()
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

        self.act_reopen = QAction("Reopen last book on startup", self)
        self.act_reopen.setCheckable(True)
        self.act_reopen.setChecked(self.settings.value("reopen_last", True, type=bool))
        self.act_reopen.toggled.connect(lambda v: self.settings.setValue("reopen_last", v))
        m_file.addAction(self.act_reopen)

        m_file.addSeparator()
        act_quit = QAction("&Quit", self)
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

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
            self.reader.set_book(book.html, book.resources, book.image_anchors)
            self.chapters = book.chapters
            self.tree.clear()
            self._add_entries(self.tree.invisibleRootItem(), book.toc)
            self.tree.expandToDepth(0)
            self.setWindowTitle(f"{book.title} - {APP_TITLE}")
            self.current_path = path
            self.settings.setValue("last_book", path)

            pos = self.settings.value(_position_key(path), 0, type=int)
            if pos:
                self.reader.restore_position(pos)
        except Exception as e:
            QMessageBox.critical(self, "Could not open book", f"{type(e).__name__}: {e}")
        finally:
            QApplication.restoreOverrideCursor()

    def reopen_last_book(self):
        if not self.settings.value("reopen_last", True, type=bool):
            return
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
            item.setData(0, Qt.ItemDataRole.UserRole, e.key)
            self._add_entries(item, e.children)

    def _goto(self, item, *_):
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key:
            self.reader.scrollToAnchor(key)

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
        )
        w.closed.connect(self._window_closed)
        self.extra_windows.append(w)
        w.show()

    def _window_closed(self, w):
        if w in self.extra_windows:
            self.extra_windows.remove(w)

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
        for w in list(self.extra_windows):
            w.close()
        super().closeEvent(event)
