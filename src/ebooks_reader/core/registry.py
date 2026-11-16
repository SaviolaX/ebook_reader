from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .models import LoadedBook

Loader = Callable[[str], LoadedBook]


class UnsupportedFormatError(Exception):
    pass


@dataclass(frozen=True)
class BookFormat:
    name: str
    extensions: tuple[str, ...]  # lowercase, with leading dot, e.g. ".fb2.zip"
    loader: Loader


_FORMATS: list[BookFormat] = []


def register(name: str, extensions: list[str]) -> Callable[[Loader], Loader]:
    """Decorator that registers a loader function for a book format."""

    def decorator(fn: Loader) -> Loader:
        _FORMATS.append(BookFormat(name, tuple(e.lower() for e in extensions), fn))
        return fn

    return decorator


def find_format(path: str) -> BookFormat | None:
    filename = Path(path).name.lower()
    for fmt in _FORMATS:
        if any(filename.endswith(ext) for ext in fmt.extensions):
            return fmt
    return None


def load_book(path: str) -> LoadedBook:
    fmt = find_format(path)
    if fmt is None:
        raise UnsupportedFormatError(f"Unsupported file type: {Path(path).name}")
    return fmt.loader(path)


def file_dialog_filter() -> str:
    """Qt file-dialog filter string built from all registered formats."""
    all_patterns = " ".join(f"*{e}" for f in _FORMATS for e in f.extensions)
    parts = [f"All supported books ({all_patterns})"]
    for f in _FORMATS:
        patterns = " ".join(f"*{e}" for e in f.extensions)
        parts.append(f"{f.name} ({patterns})")
    return ";;".join(parts)
