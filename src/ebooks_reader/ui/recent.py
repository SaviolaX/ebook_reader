"""Recently opened books, stored in QSettings as a JSON list of paths.

No Qt widgets here, so it can be tested alone (any object with value()/setValue() works).
"""

import json
import os

MAX_RECENT = 10
_KEY = "recent_books"


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def load_recent(settings) -> list[str]:
    try:
        raw = json.loads(str(settings.value(_KEY, "[]")))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    return [p for p in raw if isinstance(p, str) and p]


def save_recent(settings, paths: list[str]) -> None:
    settings.setValue(_KEY, json.dumps(paths[:MAX_RECENT], ensure_ascii=False))


def add_recent(settings, path: str) -> None:
    """Put `path` at the top; an older entry for the same file is dropped."""
    path = os.path.abspath(path)
    key = _norm(path)
    items = [p for p in load_recent(settings) if _norm(p) != key]
    items.insert(0, path)
    save_recent(settings, items)


def remove_recent(settings, path: str) -> None:
    key = _norm(path)
    save_recent(settings, [p for p in load_recent(settings) if _norm(p) != key])


def clear_recent(settings) -> None:
    save_recent(settings, [])
