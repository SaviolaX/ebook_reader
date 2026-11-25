from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TocEntry:
    title: str
    key: str | None  # anchor name inside the book's HTML
    children: list["TocEntry"] = field(default_factory=list)


@dataclass
class LoadedBook:
    title: str
    html: str
    toc: list[TocEntry]
    resources: dict[str, bytes]  # internal path -> image bytes
    # anchors whose target is an image (or a caption of an image)
    image_anchors: dict[str, str] = field(default_factory=dict)  # anchor -> image path
    # HTML of each chapter separately (chapter i has anchors named c<i>_...)
    chapters: list[str] = field(default_factory=list)
    cover: bytes | None = None  # cover image file contents, if the book has one
    # PDF books are fixed-layout: no HTML, the PDF viewer opens the file itself
    pdf_path: str | None = None
    page_count: int = 0
