from pathlib import Path

from PySide6.QtCore import QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPalette, QPen, QPixmap, QTextOption
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from ..formats import file_dialog_filter
from .covers import has_custom_cover, load_cover, remove_custom_cover, set_custom_cover
from .recent import book_id, get_title, load_recent, remove_recent
from .themes import DEFAULT_THEME, THEMES

CARD_W, CARD_H = 170, 290
COVER_W, COVER_H = 140, 196

_USER = Qt.ItemDataRole.UserRole.value
ROLE_PATH = _USER
ROLE_COVER = _USER + 1
ROLE_EXISTS = _USER + 2
ROLE_TITLE = _USER + 3
ROLE_HUE = _USER + 4


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(
        int(a.red() * (1 - t) + b.red() * t),
        int(a.green() * (1 - t) + b.green() * t),
        int(a.blue() * (1 - t) + b.blue() * t),
    )


class CardDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(CARD_W, CARD_H)

    def paint(self, painter, option, index):
        pal = option.palette
        base = pal.color(QPalette.ColorRole.Base)
        text = pal.color(QPalette.ColorRole.Text)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        exists = bool(index.data(ROLE_EXISTS))
        title = str(index.data(ROLE_TITLE) or "")

        card = option.rect.adjusted(6, 6, -6, -6)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not exists:
            painter.setOpacity(0.45)

        fill = _mix(base, text, 0.14 if (selected or hover) else 0.07)
        border = text if selected else _mix(base, text, 0.25)
        painter.setPen(QPen(border, 2 if selected else 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(card, 10, 10)

        cover = QRect(card.left() + (card.width() - COVER_W) // 2, card.top() + 12, COVER_W, COVER_H)
        pm = index.data(ROLE_COVER)
        if isinstance(pm, QPixmap) and not pm.isNull():
            x = cover.left() + (COVER_W - pm.width()) // 2
            y = cover.bottom() - pm.height() + 1  # bottom-aligned, so titles line up
            painter.drawPixmap(x, y, pm)
        else:
            hue = int(index.data(ROLE_HUE) or 0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor.fromHsv(hue, 110, 130))
            painter.drawRoundedRect(cover, 6, 6)
            letter = next((c for c in title if c.isalnum()), "?").upper()
            font = painter.font()
            font.setPointSize(36)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255, 220))
            painter.drawText(cover, Qt.AlignmentFlag.AlignCenter, letter)

        label = title if exists else f"{title}\n(file not found)"
        text_rect = QRect(
            card.left() + 8,
            cover.bottom() + 10,
            card.width() - 16,
            card.bottom() - cover.bottom() - 16,
        )
        font = painter.font()
        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(text)
        painter.setClipRect(text_rect)
        opt = QTextOption(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        opt.setWrapMode(QTextOption.WrapMode.WordWrap)
        painter.drawText(QRectF(text_rect), label, opt)
        painter.restore()


class LauncherWindow(QMainWindow):
    """Start window: your books as cards. The reader opens only after a choice."""

    bookChosen = Signal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle("Ebooks Reader")
        self.resize(940, 660)

        self.list = QListWidget()
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setUniformItemSizes(True)
        self.list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list.setFrameShape(QListWidget.Shape.NoFrame)
        self.list.setMouseTracking(True)
        self.list.setItemDelegate(CardDelegate(self.list))
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self.empty = QLabel('No books yet. Use "Open another book...".')
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_open = QPushButton("Open")
        self.btn_open.setDefault(True)
        self.btn_browse = QPushButton("Open another book...")
        self.btn_cover = QPushButton("Set cover...")
        self.btn_remove = QPushButton("Remove from list")

        self.show_check = QCheckBox("Show this window at startup")
        self.show_check.setChecked(settings.value("show_start", True, type=bool))

        buttons = QHBoxLayout()
        buttons.addWidget(self.btn_open)
        buttons.addWidget(self.btn_browse)
        buttons.addStretch()
        buttons.addWidget(self.btn_cover)
        buttons.addWidget(self.btn_remove)

        central = QWidget()
        root = QVBoxLayout(central)
        root.addWidget(QLabel("<h2>Your books</h2>"))
        root.addWidget(self.list, 1)
        root.addWidget(self.empty, 1)
        root.addLayout(buttons)
        root.addWidget(self.show_check)
        self.setCentralWidget(central)

        self.list.itemActivated.connect(self._open_item)
        self.list.currentItemChanged.connect(lambda *_: self._update_buttons())
        self.list.customContextMenuRequested.connect(self._menu)
        self.btn_open.clicked.connect(lambda: self._open_item(self.list.currentItem()))
        self.btn_browse.clicked.connect(self._browse)
        self.btn_cover.clicked.connect(self.set_cover)
        self.btn_remove.clicked.connect(self.remove_selected)
        self.show_check.toggled.connect(lambda v: self.settings.setValue("show_start", v))

        self.refresh()

    # ---------- look ----------
    def _apply_theme(self) -> None:
        bg0, fg0 = THEMES[DEFAULT_THEME]
        bg = QColor(str(self.settings.value("bg", bg0)))
        fg = QColor(str(self.settings.value("fg", fg0)))
        pal = self.list.palette()
        pal.setColor(QPalette.ColorRole.Base, bg)
        pal.setColor(QPalette.ColorRole.Text, fg)
        self.list.setPalette(pal)
        win = self.palette()
        win.setColor(QPalette.ColorRole.Window, bg)
        win.setColor(QPalette.ColorRole.WindowText, fg)
        self.setPalette(win)

    # ---------- content ----------
    def refresh(self, select: str | None = None) -> None:
        if select is None:
            cur = self.list.currentItem()
            select = str(cur.data(ROLE_PATH)) if cur is not None else None
        self._apply_theme()
        self.show_check.setChecked(self.settings.value("show_start", True, type=bool))
        self.list.clear()
        first_ok = None
        to_select = None
        for path in load_recent(self.settings):
            exists = Path(path).is_file()
            title = get_title(self.settings, path) or Path(path).stem
            item = QListWidgetItem()
            item.setData(ROLE_PATH, path)
            item.setData(ROLE_EXISTS, exists)
            item.setData(ROLE_TITLE, title)
            item.setData(ROLE_HUE, int(book_id(path)[:4], 16) % 360)
            pm = load_cover(path)
            if pm is not None:
                pm = pm.scaled(
                    COVER_W,
                    COVER_H,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                item.setData(ROLE_COVER, pm)
            item.setToolTip(path)
            self.list.addItem(item)
            if exists and first_ok is None:
                first_ok = item
            if path == select:
                to_select = item
        has = self.list.count() > 0
        self.list.setVisible(has)
        self.empty.setVisible(not has)
        target = to_select or first_ok
        if target is not None:
            self.list.setCurrentItem(target)
            self.list.setFocus()
        self._update_buttons()

    def _update_buttons(self) -> None:
        item = self.list.currentItem()
        self.btn_open.setEnabled(item is not None and bool(item.data(ROLE_EXISTS)))
        self.btn_cover.setEnabled(item is not None)
        self.btn_remove.setEnabled(item is not None)

    # ---------- actions ----------
    def _open_item(self, item) -> None:
        if item is None:
            return
        if not item.data(ROLE_EXISTS):
            self.statusBar().showMessage("This file was not found.", 4000)
            return
        self.bookChosen.emit(str(item.data(ROLE_PATH)))

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open book", "", file_dialog_filter())
        if path:
            self.bookChosen.emit(path)

    def set_cover(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        path = str(item.data(ROLE_PATH))
        f, _ = QFileDialog.getOpenFileName(
            self,
            "Choose a cover image",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;All files (*)",
        )
        if not f:
            return
        if set_custom_cover(path, f):
            self.refresh(select=path)
        else:
            QMessageBox.warning(self, "Cover", "This image could not be read.")

    def remove_cover(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            path = str(item.data(ROLE_PATH))
            remove_custom_cover(path)
            self.refresh(select=path)

    def remove_selected(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            remove_recent(self.settings, str(item.data(ROLE_PATH)))
            self.refresh(select="")

    def _menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        self.list.setCurrentItem(item)
        path = str(item.data(ROLE_PATH))
        menu = QMenu(self)
        a_open = menu.addAction("Open")
        a_open.setEnabled(bool(item.data(ROLE_EXISTS)))
        menu.addSeparator()
        a_set = menu.addAction("Set cover image...")
        a_rm_cover = menu.addAction("Remove custom cover")
        a_rm_cover.setEnabled(has_custom_cover(path))
        menu.addSeparator()
        a_remove = menu.addAction("Remove from list")
        chosen = menu.exec(self.list.viewport().mapToGlobal(pos))
        if chosen is a_open:
            self._open_item(item)
        elif chosen is a_set:
            self.set_cover()
        elif chosen is a_rm_cover:
            self.remove_cover()
        elif chosen is a_remove:
            self.remove_selected()
