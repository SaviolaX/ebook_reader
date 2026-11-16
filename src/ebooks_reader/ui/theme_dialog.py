from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .themes import (
    THEMES,
    all_themes,
    export_theme,
    import_theme,
    is_valid_color,
    load_custom,
    save_custom,
)


class ColorRow(QWidget):
    changed = Signal()

    def __init__(self, title: str, value: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.swatch = QLabel()
        self.swatch.setFixedSize(28, 22)
        self.edit = QLineEdit()
        self.edit.setMaxLength(7)
        self.edit.setFixedWidth(90)
        self.button = QPushButton("Pick...")

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.swatch)
        row.addWidget(self.edit)
        row.addWidget(self.button)
        row.addStretch()

        self.button.clicked.connect(self._pick)
        self.edit.textChanged.connect(self._text_changed)
        self.set_value(value)

    def value(self) -> str | None:
        text = self.edit.text().strip()
        return QColor(text).name() if is_valid_color(text) else None

    def set_value(self, value: str) -> None:
        self.edit.setText(QColor(value).name())

    def _text_changed(self, _):
        v = self.value()
        css = f"background:{v};" if v else "background:transparent;"
        self.swatch.setStyleSheet(css + "border:1px solid #888;")
        self.changed.emit()

    def _pick(self):
        c = QColorDialog.getColor(QColor(self.value() or "#ffffff"), self, self.title)
        if c.isValid():
            self.set_value(c.name())


class ThemeDialog(QDialog):
    themesChanged = Signal()  # the list of saved themes changed

    def __init__(self, settings, bg: str, fg: str, on_apply, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Color themes")
        self.resize(640, 420)
        self.settings = settings
        self.on_apply = on_apply

        # left: list
        self.list = QListWidget()
        self.list.setFixedWidth(190)
        self.list.currentItemChanged.connect(self._on_select)

        # right: editor
        self.name_edit = QLineEdit()
        self.bg_row = ColorRow("Background color", bg)
        self.fg_row = ColorRow("Text color", fg)
        self.bg_row.changed.connect(self._update_preview)
        self.fg_row.changed.connect(self._update_preview)

        form = QFormLayout()
        form.addRow("Theme name:", self.name_edit)
        form.addRow("Background:", self.bg_row)
        form.addRow("Text:", self.fg_row)

        self.preview = QLabel(
            "The quick brown fox jumps over the lazy dog.\n"
            "This is how your book text will look."
        )
        self.preview.setWordWrap(True)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(110)

        self.btn_save = QPushButton("Save")
        self.btn_apply = QPushButton("Apply")
        self.btn_delete = QPushButton("Delete")
        self.btn_copy = QPushButton("Copy scheme")
        self.btn_paste = QPushButton("Paste scheme")
        self.btn_save.clicked.connect(self.save_theme)
        self.btn_apply.clicked.connect(self.apply_current)
        self.btn_delete.clicked.connect(self.delete_theme)
        self.btn_copy.clicked.connect(self.copy_scheme)
        self.btn_paste.clicked.connect(self.paste_scheme)

        row1 = QHBoxLayout()
        for b in (self.btn_save, self.btn_apply, self.btn_delete):
            row1.addWidget(b)
        row2 = QHBoxLayout()
        for b in (self.btn_copy, self.btn_paste):
            row2.addWidget(b)

        self.status = QLabel("")
        self.status.setWordWrap(True)

        right = QVBoxLayout()
        right.addLayout(form)
        right.addWidget(self.preview)
        right.addLayout(row1)
        right.addLayout(row2)
        right.addWidget(self.status)
        right.addStretch()

        root = QHBoxLayout(self)
        root.addWidget(self.list)
        root.addLayout(right, 1)

        self.name_edit.setText("My theme")
        self._fill_list()
        self._select_matching(bg, fg)
        self._update_preview()

    # ---------- list ----------
    def _fill_list(self, select: str | None = None):
        self.list.blockSignals(True)
        self.list.clear()
        custom = load_custom(self.settings)
        for name in all_themes(self.settings):
            label = name if name in custom else f"{name}  (built-in)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.list.addItem(item)
            if name == select:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        self._update_buttons()

    def _select_matching(self, bg: str, fg: str):
        for name, (b, f) in all_themes(self.settings).items():
            if QColor(b) == QColor(bg) and QColor(f) == QColor(fg):
                self._fill_list(select=name)
                self.name_edit.setText(name)
                return

    def _selected_name(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_select(self, item, _prev):
        if item is None:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        bg, fg = all_themes(self.settings)[name]
        self.name_edit.setText(name)
        self.bg_row.set_value(bg)
        self.fg_row.set_value(fg)
        self.status.setText("")
        self._update_buttons()

    def _update_buttons(self):
        name = self._selected_name()
        self.btn_delete.setEnabled(bool(name) and name not in THEMES)

    # ---------- helpers ----------
    def _colors(self) -> tuple[str, str] | None:
        bg, fg = self.bg_row.value(), self.fg_row.value()
        if bg is None or fg is None:
            self.status.setText("Enter colors as #rrggbb, for example #1e1e1e.")
            return None
        return bg, fg

    def _update_preview(self):
        bg = self.bg_row.value() or "#ffffff"
        fg = self.fg_row.value() or "#000000"
        self.preview.setStyleSheet(
            f"background:{bg}; color:{fg}; font-size:15px; padding:12px; border:1px solid #888;"
        )

    # ---------- actions ----------
    def apply_current(self):
        colors = self._colors()
        if colors:
            self.on_apply(*colors)
            self.status.setText("Applied.")

    def save_theme(self):
        colors = self._colors()
        if not colors:
            return
        name = self.name_edit.text().strip()
        if not name:
            self.status.setText("Enter a theme name.")
            return
        if name in THEMES:
            self.status.setText(f"\"{name}\" is a built-in theme. Choose another name.")
            return
        custom = load_custom(self.settings)
        custom[name] = colors
        save_custom(self.settings, custom)
        self._fill_list(select=name)
        self.on_apply(*colors)
        self.themesChanged.emit()
        self.status.setText(f"Saved \"{name}\" and applied it.")

    def delete_theme(self):
        name = self._selected_name()
        if not name or name in THEMES:
            return
        answer = QMessageBox.question(self, "Delete theme", f"Delete theme \"{name}\"?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        custom = load_custom(self.settings)
        custom.pop(name, None)
        save_custom(self.settings, custom)
        self._fill_list()
        self.themesChanged.emit()
        self.status.setText(f"Deleted \"{name}\".")

    def copy_scheme(self):
        colors = self._colors()
        if not colors:
            return
        name = self.name_edit.text().strip() or "Shared theme"
        QApplication.clipboard().setText(export_theme(name, *colors))
        self.status.setText("Scheme copied. Send it to a friend; they use Paste scheme.")

    def paste_scheme(self):
        try:
            name, bg, fg = import_theme(QApplication.clipboard().text())
        except ValueError as e:
            self.status.setText(str(e))
            return
        self.name_edit.setText(name)
        self.bg_row.set_value(bg)
        self.fg_row.set_value(fg)
        self.status.setText(f"Pasted \"{name}\". Click Save to keep it.")
