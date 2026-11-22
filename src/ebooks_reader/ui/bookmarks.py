import json
from dataclasses import dataclass


@dataclass
class Bookmark:
    pos: int  # character offset in the book text
    label: str  # shown in the menu: percent + start of the text


def load_bookmarks(settings, key: str) -> list[Bookmark]:
    try:
        raw = json.loads(str(settings.value(key, "[]")))
        items = [Bookmark(int(d["pos"]), str(d["label"])) for d in raw]
    except Exception:
        return []
    return sorted(items, key=lambda b: b.pos)


def save_bookmarks(settings, key: str, items: list[Bookmark]) -> None:
    data = [{"pos": b.pos, "label": b.label} for b in items]
    settings.setValue(key, json.dumps(data, ensure_ascii=False))
