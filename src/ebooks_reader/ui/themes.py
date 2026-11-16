from PySide6.QtGui import QColor, QPalette

# name -> (background, text)
THEMES = {
    "Light": ("#ffffff", "#1a1a1a"),
    "Sepia": ("#f4ecd8", "#5b4636"),
    "Dark": ("#1e1e1e", "#d4d4d4"),
    "Night (black)": ("#000000", "#9a9a9a"),
}
DEFAULT_THEME = "Light"


def apply_palette(widget, bg: str, fg: str) -> None:
    pal = widget.palette()
    pal.setColor(QPalette.ColorRole.Base, QColor(bg))
    pal.setColor(QPalette.ColorRole.Text, QColor(fg))
    pal.setColor(QPalette.ColorRole.Link, QColor(fg))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(fg))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(bg))
    widget.setPalette(pal)
