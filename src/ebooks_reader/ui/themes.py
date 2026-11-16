import base64
import json
import re

from PySide6.QtGui import QColor, QPalette

# name -> (background, text)
THEMES = {
    "Light": ("#ffffff", "#1a1a1a"),
    "Sepia": ("#f4ecd8", "#5b4636"),
    "Dark": ("#1e1e1e", "#d4d4d4"),
    "Night (black)": ("#000000", "#9a9a9a"),
    "Paper": ("#f5f1e6", "#2b2b2b"),
    "Soft Gray": ("#e6e6e6", "#2a2a2a"),
    "Eye Green": ("#c7edcc", "#2e3a2f"),
    "Charcoal": ("#2b2b2b", "#cccccc"),
    "Warm Night": ("#1c1a17", "#c9bfae"),
}
DEFAULT_THEME = "Light"

_CODE_RE = re.compile(r"EBR1:[A-Za-z0-9_\-=]+")


def apply_palette(widget, bg: str, fg: str) -> None:
    pal = widget.palette()
    pal.setColor(QPalette.ColorRole.Base, QColor(bg))
    pal.setColor(QPalette.ColorRole.Text, QColor(fg))
    pal.setColor(QPalette.ColorRole.Link, QColor(fg))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(fg))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(bg))
    widget.setPalette(pal)


# ---------- custom themes (stored in settings) ----------
def load_custom(settings) -> dict[str, tuple[str, str]]:
    try:
        raw = json.loads(str(settings.value("custom_themes", "{}")))
        return {
            str(n): (str(c[0]), str(c[1]))
            for n, c in raw.items()
            if is_valid_color(c[0]) and is_valid_color(c[1])
        }
    except Exception:
        return {}


def save_custom(settings, themes: dict[str, tuple[str, str]]) -> None:
    settings.setValue("custom_themes", json.dumps(themes, ensure_ascii=False))


def all_themes(settings) -> dict[str, tuple[str, str]]:
    return {**THEMES, **load_custom(settings)}


# ---------- sharing ----------
def is_valid_color(value) -> bool:
    return isinstance(value, str) and value.startswith("#") and QColor(value).isValid()


def export_theme(name: str, bg: str, fg: str) -> str:
    data = json.dumps({"name": name, "bg": bg, "fg": fg}, ensure_ascii=False)
    return "EBR1:" + base64.urlsafe_b64encode(data.encode("utf-8")).decode("ascii")


def import_theme(text: str) -> tuple[str, str, str]:
    """Find a scheme code inside `text`. Returns (name, bg, fg) or raises ValueError."""
    m = _CODE_RE.search(text or "")
    if not m:
        raise ValueError("No color scheme code found in the clipboard.")
    try:
        payload = m.group(0)[5:]
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
        name, bg, fg = str(data["name"]).strip(), data["bg"], data["fg"]
    except Exception:
        raise ValueError("The color scheme code is damaged or incomplete.")
    if not is_valid_color(bg) or not is_valid_color(fg):
        raise ValueError("The color scheme code contains invalid colors.")
    return name or "Imported theme", QColor(bg).name(), QColor(fg).name()
