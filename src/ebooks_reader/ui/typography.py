from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFormLayout,
    QSpinBox,
)


@dataclass(frozen=True)
class Typography:
    family: str = "Georgia"
    size: int = 13
    line_height: int = 140  # percent
    margin: int = 32  # pixels, around the text

    @classmethod
    def load(cls, s: QSettings) -> "Typography":
        d = cls()
        return cls(
            family=str(s.value("typo/family", d.family)),
            size=s.value("typo/size", d.size, type=int),
            line_height=s.value("typo/line_height", d.line_height, type=int),
            margin=s.value("typo/margin", d.margin, type=int),
        )

    def save(self, s: QSettings) -> None:
        s.setValue("typo/family", self.family)
        s.setValue("typo/size", self.size)
        s.setValue("typo/line_height", self.line_height)
        s.setValue("typo/margin", self.margin)


class TypographyDialog(QDialog):
    def __init__(self, current: Typography, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Text settings")

        self.font_box = QFontComboBox()
        self.font_box.setCurrentFont(QFont(current.family))

        self.size_box = QSpinBox()
        self.size_box.setRange(6, 72)
        self.size_box.setSuffix(" pt")
        self.size_box.setValue(current.size)

        self.line_box = QSpinBox()
        self.line_box.setRange(100, 300)
        self.line_box.setSingleStep(5)
        self.line_box.setSuffix(" %")
        self.line_box.setValue(current.line_height)

        self.margin_box = QSpinBox()
        self.margin_box.setRange(0, 400)
        self.margin_box.setSingleStep(4)
        self.margin_box.setSuffix(" px")
        self.margin_box.setValue(current.margin)

        form = QFormLayout(self)
        form.addRow("Font:", self.font_box)
        form.addRow("Font size:", self.size_box)
        form.addRow("Line spacing:", self.line_box)
        form.addRow("Page margins:", self.margin_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def result_value(self) -> Typography:
        return Typography(
            family=self.font_box.currentFont().family(),
            size=self.size_box.value(),
            line_height=self.line_box.value(),
            margin=self.margin_box.value(),
        )
