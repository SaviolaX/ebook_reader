"""FB2 loader: .fb2, .fb2.zip and .fbz (a zip holding one .fb2).

Uses only the standard library. Layout of the produced book:
  chapter 0       title page: cover, title, authors, annotation, body-level extras
  chapter 1..N    every top-level <section> of the main body, one chapter each
                  (a body with a name, e.g. "notes", is ONE chapter, so a footnote
                  link opens the notes list in the linked window)
Anchors are named c<chapter>_<id>, like the EPUB loader. Sections without an id get
a generated anchor, so every contents entry can hold a note.
"""

from __future__ import annotations

import base64
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from html import escape
from urllib.parse import quote

from ..core.models import LoadedBook, TocEntry
from ..core.registry import register

_SAFE_RE = re.compile(r"[^\w.\-]")
_INLINE = {
    "strong": "b",
    "emphasis": "i",
    "strikethrough": "s",
    "sub": "sub",
    "sup": "sup",
    "code": "code",
}


# ---------- small XML helpers (namespaces are ignored on purpose) ----------
def _local(name) -> str:
    return name.rsplit("}", 1)[-1] if isinstance(name, str) else ""


def _tag(el) -> str:
    return _local(el.tag)


def _attr(el, name: str):
    """Attribute by local name, so xlink:href, l:href and plain href all work."""
    for k, v in el.attrib.items():
        if _local(k) == name:
            return v
    return None


def _children(el, name: str) -> list:
    return [c for c in el if _tag(c) == name]


def _child(el, name: str):
    if el is None:
        return None
    for c in el:
        if _tag(c) == name:
            return c
    return None


def _text(el) -> str:
    return " ".join("".join(el.itertext()).split())


def _safe(name: str) -> str:
    return _SAFE_RE.sub("_", name)


def _read_xml_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        data = f.read()
    if data[:2] == b"PK":  # zip, whatever the extension says
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = [n for n in z.namelist() if n.lower().endswith(".fb2")]
                if not names:
                    raise ValueError("The archive does not contain an .fb2 file.")
                return z.read(names[0])
        except zipfile.BadZipFile:
            raise ValueError("The file is not a valid zip archive.")
    return data


class _Converter:
    def __init__(self, resources: dict[str, bytes], chapter_of: dict[str, int]):
        self.resources = resources
        self.chapter_of = chapter_of  # element id -> chapter index
        self.image_anchors: dict[str, str] = {}
        self.chapter = 0
        self.counter = 0  # for generated section anchors
        self.notes_mode = False  # titles of notes are bold lines, not headings

    # ---------- anchors ----------
    def _anchor(self, el) -> str:
        i = el.get("id")
        return f'<a name="c{self.chapter}_{_safe(i)}"></a>' if i else ""

    # ---------- inline ----------
    def _inline(self, el) -> str:
        out = [escape(el.text or "", quote=False)]
        for ch in el:
            out.append(self._inline_el(ch))
            out.append(escape(ch.tail or "", quote=False))
        return "".join(out)

    def _inline_el(self, el) -> str:
        tag = _tag(el)
        if tag == "image":
            return self._image(el)
        inner = self._inline(el)
        anchor = self._anchor(el)
        if tag in _INLINE:
            t = _INLINE[tag]
            return f"{anchor}<{t}>{inner}</{t}>"
        if tag == "a":
            href = _attr(el, "href") or ""
            if href.startswith("#"):
                target = href[1:]
                if target in self.chapter_of:
                    return (
                        f'{anchor}<a href="#c{self.chapter_of[target]}_{_safe(target)}">'
                        f"{inner}</a>"
                    )
            elif href.split(":", 1)[0].lower() in ("http", "https", "mailto"):
                return f'{anchor}<a href="{escape(href, quote=True)}">{inner}</a>'
            return anchor + inner  # dead link: keep the text only
        return anchor + inner  # style, unknown tags

    def _image(self, el) -> str:
        href = _attr(el, "href") or ""
        name = href[1:] if href.startswith("#") else ""
        if name not in self.resources:
            return ""
        i = el.get("id")
        if i:
            self.image_anchors[f"c{self.chapter}_{_safe(i)}"] = name
        return f'{self._anchor(el)}<img src="epub:///{quote(name)}">'

    # ---------- blocks ----------
    def _title_html(self, title_el) -> str:
        lines = [self._anchor(p) + self._inline(p) for p in _children(title_el, "p")]
        lines = [x for x in lines if x.strip()]
        return "<br>".join(lines)

    def _blocks(self, el) -> str:
        return "".join(self._block(c) for c in el)

    def _block(self, el) -> str:
        tag = _tag(el)
        anchor = self._anchor(el)
        if tag == "p":
            return f"<p>{anchor}{self._inline(el)}</p>"
        if tag == "empty-line":
            return "<p>&nbsp;</p>"
        if tag == "subtitle":
            return f'<p align="center">{anchor}<b>{self._inline(el)}</b></p>'
        if tag == "image":
            img = self._image(el)
            return f'<p align="center">{img}</p>' if img else ""
        if tag == "text-author":
            return f'<p align="right">{anchor}<i>{self._inline(el)}</i></p>'
        if tag == "title":
            inner = self._title_html(el)
            return f'<p align="center"><b>{anchor}{inner}</b></p>' if inner else anchor
        if tag in ("epigraph", "cite", "annotation"):
            return f"{anchor}<blockquote>{self._blocks(el)}</blockquote>"
        if tag == "poem":
            return anchor + self._blocks(el)  # title, epigraph, stanza, text-author, date
        if tag == "stanza":
            out, lines = [anchor], []
            for c in el:
                if _tag(c) == "v":
                    lines.append(self._anchor(c) + self._inline(c))
                else:
                    out.append(self._block(c))
            if lines:
                out.append("<p>" + "<br>".join(lines) + "</p>")
            return "".join(out)
        if tag == "table":
            return anchor + self._table(el)
        if tag == "section":  # section inside something unexpected
            return self._section(el, 1, [])
        text = self._inline(el)
        return f"<p>{anchor}{text}</p>" if text.strip() else anchor

    def _table(self, el) -> str:
        rows = ['<table border="1" cellspacing="0" cellpadding="4">']
        for tr in _children(el, "tr"):
            rows.append("<tr>")
            for c in tr:
                t = _tag(c)
                if t not in ("th", "td"):
                    continue
                attrs = ""
                for a in ("colspan", "rowspan"):
                    v = _attr(c, a)
                    if v and v.isdigit():
                        attrs += f' {a}="{v}"'
                al = _attr(c, "align")
                if al in ("left", "right", "center"):
                    attrs += f' align="{al}"'
                rows.append(f"<{t}{attrs}>{self._inline(c)}</{t}>")
            rows.append("</tr>")
        rows.append("</table>")
        return "".join(rows)

    # ---------- sections ----------
    def _section(self, el, depth: int, toc_out: list[TocEntry], is_root: bool = False) -> str:
        sid = el.get("id")
        if sid:
            key = f"c{self.chapter}_{_safe(sid)}"
            anchor = f'<a name="{key}"></a>'
        elif is_root:  # the chapter's own anchor already exists
            key, anchor = f"c{self.chapter}", ""
        else:
            self.counter += 1
            key = f"c{self.chapter}___sec{self.counter}"
            anchor = f'<a name="{key}"></a>'

        title_el = _child(el, "title")
        title_text = _text(title_el) if title_el is not None else ""
        inner = self._title_html(title_el) if title_el is not None else ""
        if inner:
            if self.notes_mode:
                head = f"<p><b>{anchor}{inner}</b></p>"
            else:
                lvl = min(depth + 1, 6)  # top-level section = h2 (h1 is the book title)
                head = f"<h{lvl}>{anchor}{inner}</h{lvl}>"
        else:
            head = anchor

        target = toc_out
        if title_text and not self.notes_mode:
            entry = TocEntry(title_text, key, [])
            toc_out.append(entry)
            target = entry.children

        body = []
        for c in el:
            t = _tag(c)
            if t == "title":
                continue
            if t == "section":
                body.append(self._section(c, depth + 1, target))
            else:
                body.append(self._block(c))
        return head + "".join(body)


def _decode_binaries(root) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for b in _children(root, "binary"):
        bid = b.get("id")
        if not bid:
            continue
        try:
            data = base64.b64decode(b.text or "")
        except Exception:
            continue
        if data:
            out[bid] = data
    return out


@register("FB2", [".fb2", ".fb2.zip", ".fbz"])
def load_fb2(path: str) -> LoadedBook:
    data = _read_xml_bytes(path)
    try:
        root = ET.fromstring(data.lstrip())
    except ET.ParseError as e:
        raise ValueError(f"The FB2 file is damaged or is not valid XML ({e}).")
    if _tag(root) != "FictionBook":
        raise ValueError("This is not an FB2 book (no FictionBook element).")

    ti = _child(_child(root, "description"), "title-info")
    bt = _child(ti, "book-title") if ti is not None else None
    title = _text(bt) if bt is not None and _text(bt) else "Untitled"

    authors = []
    for a in _children(ti, "author") if ti is not None else []:
        names = [_text(x) for x in (_child(a, "first-name"), _child(a, "middle-name"),
                                    _child(a, "last-name")) if x is not None]
        name = " ".join(n for n in names if n) or (
            _text(_child(a, "nickname")) if _child(a, "nickname") is not None else ""
        )
        if name:
            authors.append(name)

    resources = _decode_binaries(root)

    bodies = _children(root, "body")
    if not bodies:
        raise ValueError("The FB2 file has no text (no body element).")

    # ---- split into the title page and chapters ----
    main_title = None
    front_extra = []  # body-level epigraphs and images
    units: list[tuple] = []  # (element, is_notes_body)
    for body in bodies:
        if body.get("name"):  # "notes", "comments": one chapter for the whole body
            units.append((body, True))
            continue
        for c in body:
            t = _tag(c)
            if t == "section":
                units.append((c, False))
            elif t == "title":
                if main_title is None:
                    main_title = c
            else:
                front_extra.append(c)

    annotation = _child(ti, "annotation") if ti is not None else None
    cover_name = ""
    cp = _child(ti, "coverpage") if ti is not None else None
    if cp is not None:
        img = _child(cp, "image")
        href = (_attr(img, "href") or "") if img is not None else ""
        if href.startswith("#") and href[1:] in resources:
            cover_name = href[1:]

    # ---- which chapter holds each id (links need it before rendering) ----
    chapter_of: dict[str, int] = {}

    def register_ids(elements, idx: int) -> None:
        for el in elements:
            for e in el.iter():
                i = e.get("id")
                if i and i not in chapter_of:
                    chapter_of[i] = idx

    register_ids([x for x in (annotation, main_title) if x is not None] + front_extra, 0)
    for n, (el, _notes) in enumerate(units, 1):
        register_ids([el], n)

    # ---- render ----
    conv = _Converter(resources, chapter_of)
    toc: list[TocEntry] = []
    parts: list[str] = []

    front = []
    if cover_name:
        front.append(f'<p align="center"><img src="epub:///{quote(cover_name)}"></p>')
    head = conv._title_html(main_title) if main_title is not None else ""
    front.append(f"<h1>{head or escape(title, quote=False)}</h1>")
    if authors:
        front.append(f'<p align="center"><i>{escape(", ".join(authors), quote=False)}</i></p>')
    if annotation is not None:
        front.append(conv._block(annotation))
    for el in front_extra:
        front.append(conv._block(el))
    parts.append(f'<a name="c0"></a>{"".join(front)}<hr>')
    toc.append(TocEntry(title, "c0"))

    main_toc: list[TocEntry] = []
    tail_toc: list[TocEntry] = []
    for n, (el, notes) in enumerate(units, 1):
        conv.chapter = n
        conv.notes_mode = notes
        if notes:
            bt_el = _child(el, "title")
            name = (_text(bt_el) if bt_el is not None else "") or el.get("name") or "Notes"
            html = f"<h2>{escape(name, quote=False)}</h2>"
            for c in el:
                if _tag(c) == "title":
                    continue
                html += conv._section(c, 1, []) if _tag(c) == "section" else conv._block(c)
            tail_toc.append(TocEntry(name, f"c{n}"))
        else:
            html = conv._section(el, 1, main_toc, is_root=True)
        parts.append(f'<a name="c{n}"></a>{html}<hr>')

    if not main_toc:  # no titled sections: one entry per chapter
        main_toc = [
            TocEntry(f"Section {n}", f"c{n}")
            for n, (_el, notes) in enumerate(units, 1)
            if not notes
        ]
    toc += main_toc + tail_toc

    html = "<html><body>" + "\n".join(parts) + "</body></html>"
    return LoadedBook(
        title=title,
        html=html,
        toc=toc,
        resources=resources,
        image_anchors=conv.image_anchors,
        chapters=parts,
    )
