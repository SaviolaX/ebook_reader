"""PDF loader. A PDF is fixed-layout, so there is no HTML: the book only carries the
file path, the page count, the contents and a cover. The viewer (ui/pdf_view.py)
opens the file itself.

Contents: the PDF's own outline (bookmarks). Anchor keys are "p<page>" (page counted
from 0); an outline entry always lands on the top of its page. A PDF without an
outline gets "Page N" entries (grouped for long books), like "Section N" in EPUB.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QModelIndex, QSize
from PySide6.QtPdf import QPdfBookmarkModel, QPdfDocument

from ..core.models import LoadedBook, TocEntry
from ..core.registry import register

COVER_W, COVER_H = 300, 420
_ROLE_PAGE = QPdfBookmarkModel.Role.Page.value


def _error_text(err) -> str:
    E = QPdfDocument.Error
    if err == E.IncorrectPassword:
        return "This PDF is password-protected. Password-protected PDFs are not supported yet."
    if err == E.UnsupportedSecurityScheme:
        return "This PDF uses a security scheme that is not supported."
    if err == E.FileNotFound:
        return "The file was not found."
    if err == E.InvalidFileFormat:
        return "The file is damaged or is not a PDF."
    return f"The PDF could not be opened ({getattr(err, 'name', err)})."


def _outline(doc: QPdfDocument) -> list[TocEntry]:
    model = QPdfBookmarkModel()
    model.setDocument(doc)
    pages = doc.pageCount()

    def walk(parent: QModelIndex) -> list[TocEntry]:
        out: list[TocEntry] = []
        for row in range(model.rowCount(parent)):
            idx = model.index(row, 0, parent)
            title = " ".join(str(idx.data() or "").split()) or "(untitled)"
            page = idx.data(_ROLE_PAGE)
            children = walk(idx)
            key = f"p{page}" if isinstance(page, int) and 0 <= page < pages else None
            if key is None and children:
                key = children[0].key  # like the EPUB loader: borrow the first child's target
            out.append(TocEntry(title, key, children))
        return out

    return walk(QModelIndex())


def _page_entries(pages: int) -> list[TocEntry]:
    step = 1 if pages <= 60 else 10 if pages <= 600 else 50
    out = []
    for start in range(0, pages, step):
        end = min(start + step, pages)
        title = f"Page {start + 1}" if step == 1 else f"Pages {start + 1}\u2013{end}"
        out.append(TocEntry(title, f"p{start}"))
    return out


def _cover(doc: QPdfDocument) -> bytes | None:
    """First page as a PNG."""
    try:
        size = doc.pagePointSize(0)
        k = min(COVER_W / size.width(), COVER_H / size.height())
        img = doc.render(0, QSize(max(1, int(size.width() * k)), max(1, int(size.height() * k))))
        if img.isNull():
            return None
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        return bytes(buf.data())
    except Exception:
        return None


@register("PDF", [".pdf"])
def load_pdf(path: str) -> LoadedBook:
    doc = QPdfDocument()
    doc.load(path)
    if doc.status() != QPdfDocument.Status.Ready:
        raise ValueError(_error_text(doc.error()))
    try:
        pages = doc.pageCount()
        if pages <= 0:
            raise ValueError("The PDF has no pages.")
        title = str(doc.metaData(QPdfDocument.MetaDataField.Title) or "").strip()
        toc = _outline(doc) or _page_entries(pages)
        cover = _cover(doc)
    finally:
        doc.close()
    return LoadedBook(
        title=title or Path(path).stem,
        html="",
        toc=toc,
        resources={},
        cover=cover,
        pdf_path=path,
        page_count=pages,
    )
