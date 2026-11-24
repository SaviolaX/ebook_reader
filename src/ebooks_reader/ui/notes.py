"""Notes per contents entry. No Qt widgets here, so it can be tested alone.

A note is stored under a note id derived from TocEntry.key. Keys are not
always unique (a parent without its own link borrows its first child's key),
so repeated keys get "~2", "~3", ... in contents order. Entries without a key
can't hold a note (note_id is None).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..core.models import TocEntry

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class FlatEntry:
    depth: int
    entry: TocEntry
    note_id: str | None


def flatten(entries: list[TocEntry]) -> list[FlatEntry]:
    """Contents tree -> list in reading order, each with a unique note id."""
    seen: dict[str, int] = {}
    out: list[FlatEntry] = []

    def walk(items: list[TocEntry], depth: int) -> None:
        for e in items:
            nid = None
            if e.key:
                n = seen.get(e.key, 0) + 1
                seen[e.key] = n
                nid = e.key if n == 1 else f"{e.key}~{n}"
            out.append(FlatEntry(depth, e, nid))
            walk(e.children, depth + 1)

    walk(entries, 0)
    return out


class NoteStore:
    """Notes of one book, kept in a JSON file: {"version": 1, "notes": {id: {title, text}}}."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.notes: dict[str, dict[str, str]] = {}
        self.load()

    # ---------- file ----------
    def load(self) -> None:
        self.notes = {}
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for nid, d in raw["notes"].items():
                self.notes[str(nid)] = {
                    "title": str(d.get("title", "")),
                    "text": str(d.get("text", "")),
                }
        except Exception:
            # damaged file: keep a copy, start empty (never crash, never overwrite silently)
            self.notes = {}
            try:
                os.replace(self.path, self.path.with_suffix(".json.bad"))
            except OSError:
                pass

    def save(self) -> None:
        if not self.notes:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(
            {"version": SCHEMA_VERSION, "notes": self.notes},
            ensure_ascii=False,
            indent=1,
        )
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp, self.path)  # atomic: no half-written file
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ---------- notes ----------
    def get(self, note_id: str) -> str:
        return self.notes.get(note_id, {}).get("text", "")

    def has(self, note_id: str | None) -> bool:
        return bool(note_id) and note_id in self.notes

    def count(self) -> int:
        return len(self.notes)

    def set(self, note_id: str, title: str, text: str) -> bool:
        """Store a note (blank text deletes it). Returns True if anything changed."""
        if not text.strip():
            return self.notes.pop(note_id, None) is not None
        new = {"title": title, "text": text}
        if self.notes.get(note_id) == new:
            return False
        self.notes[note_id] = new
        return True


def export_markdown(book_title: str, flat: list[FlatEntry], store: NoteStore) -> str:
    """Headings for entries that have notes (and their parents), then the text."""
    n = len(flat)
    keep = [False] * n
    for i, f in enumerate(flat):
        if not store.has(f.note_id):
            continue
        keep[i] = True
        need = f.depth
        for j in range(i - 1, -1, -1):  # mark the parents
            if flat[j].depth < need:
                keep[j] = True
                need = flat[j].depth
                if need == 0:
                    break

    lines = [f"# {book_title}", ""]
    used = {f.note_id for f in flat if f.note_id}
    for i, f in enumerate(flat):
        if not keep[i]:
            continue
        lines.append(f"{'#' * min(f.depth + 2, 6)} {f.entry.title}")
        lines.append("")
        if store.has(f.note_id):
            lines.append(store.get(f.note_id).strip())
            lines.append("")
    orphans = [nid for nid in store.notes if nid not in used]
    if orphans:  # notes whose contents entry no longer exists
        lines += ["## Unattached notes", ""]
        for nid in orphans:
            lines += [f"### {store.notes[nid]['title']}", "", store.get(nid).strip(), ""]
    return "\n".join(lines).rstrip() + "\n"
