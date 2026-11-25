from __future__ import annotations

import posixpath
from urllib.parse import quote, unquote, urldefrag, urlparse

import ebooklib
from bs4 import BeautifulSoup
from bs4.element import Tag
from ebooklib import epub

from ..core.models import LoadedBook, TocEntry
from ..core.registry import register


def _resolve(base_name: str, href: str) -> tuple[str, str]:
    """Resolve href relative to a chapter file. Returns (zip name, fragment)."""
    path, frag = urldefrag(href)
    path = unquote(path)
    if not path:
        return base_name, frag
    joined = posixpath.join(posixpath.dirname(base_name), path)
    return posixpath.normpath(joined), frag


_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_SCAN_LIMIT = 60  # max nodes inspected per element


def _probe(tag):
    """Cheap look inside an element: (has_image, text_length, is_small).

    Inspects at most _SCAN_LIMIT nodes, so big containers cost almost nothing.
    """
    has_img = tag.name == "img"
    text = 0
    for n, node in enumerate(tag.descendants):
        if n >= _SCAN_LIMIT:
            return has_img, text, False
        if isinstance(node, Tag):
            if node.name == "img":
                has_img = True
        else:
            text += len(node.strip())
    return has_img, text, True


def _has_image(tag) -> bool:
    """The element is an image, a figure, or a short block holding an image."""
    if tag.name in ("img", "figure"):
        return True
    has_img, text, small = _probe(tag)
    return small and has_img and text < 200


def _is_image_block(tag) -> bool:
    if tag.name in ("img", "figure"):
        return True
    has_img, text, small = _probe(tag)
    return small and has_img and text < 50


def _image_above(tag):
    """If `tag` looks like a caption of the image right above it, return that image."""
    if tag.name in _HEADINGS:
        return None
    _, text, small = _probe(tag)
    if not small or text > 300:
        return None
    prev = tag.find_previous_sibling(True)
    if prev is not None and _is_image_block(prev):
        return prev
    return None


def _img_name(tag, doc_name: str) -> str:
    """Path (inside the book) of the image shown by `tag`, or "" if unknown."""
    img = tag if tag.name == "img" else tag.find("img")
    if img is None:
        return ""
    src = img.get("src")
    if not src or urlparse(src).scheme:
        return ""
    return _resolve(doc_name, src)[0]


def _find_cover(book, resources: dict[str, bytes]) -> bytes | None:
    """Cover image bytes of an EPUB, or None."""
    try:
        for _value, attrs in book.get_metadata("OPF", "cover"):
            item = book.get_item_with_id((attrs or {}).get("content", ""))
            if item is not None and (item.media_type or "").startswith("image/"):
                data = item.get_content()
                if data:
                    return data
    except Exception:
        pass
    try:
        for item in book.get_items_of_type(ebooklib.ITEM_COVER):
            data = item.get_content()
            if data:
                return data
    except Exception:
        pass
    for name, data in resources.items():
        if "cover" in posixpath.basename(name).lower():
            return data
    return None


@register("EPUB", [".epub"])
def load_epub(path: str) -> LoadedBook:
    book = epub.read_epub(path, options={"ignore_ncx": False})

    meta = book.get_metadata("DC", "title")
    title = meta[0][0] if meta else "Untitled"

    # Chapters in reading order
    docs = []
    for idref, _linear in book.spine:
        item = book.get_item_with_id(idref)
        if item is not None and item.get_type() == ebooklib.ITEM_DOCUMENT:
            docs.append(item)
    index = {d.get_name(): i for i, d in enumerate(docs)}

    resources = {
        it.get_name(): it.get_content()
        for it in book.get_items()
        if (it.media_type or "").startswith("image/")
    }

    parts: list[str] = []
    keys: set[str] = set()
    image_keys: dict[str, str] = {}  # anchor -> image path inside the book

    for i, doc in enumerate(docs):
        soup = BeautifulSoup(doc.get_content(), "html.parser")
        for t in soup(["script", "style", "link", "meta", "title", "head", "svg"]):
            t.decompose()

        # Strip styling so our color scheme always wins
        for tag in soup.find_all(True):
            for attr in ("style", "color", "bgcolor"):
                tag.attrs.pop(attr, None)

        # Old-style <a name="x"> anchors
        for a in soup.find_all("a", attrs={"name": True}):
            key = f"c{i}_{a['name']}"
            keys.add(key)
            nxt = a.find_next_sibling(True)
            holder = None
            if a.parent is not None and _has_image(a.parent):
                holder = a.parent
            elif nxt is not None and _has_image(nxt):
                holder = nxt
            if holder is not None:
                image_keys[key] = _img_name(holder, doc.get_name())
            a["name"] = key

        # id="x" anchors -> add explicit <a name> before the element
        for tag in soup.find_all(id=True):
            key = f"c{i}_{tag['id']}"
            keys.add(key)
            place = tag
            if _has_image(tag):
                image_keys[key] = _img_name(tag, doc.get_name())
            else:
                above = _image_above(tag)
                if above is not None:  # caption -> point at the picture itself
                    place = above
                    image_keys[key] = _img_name(above, doc.get_name())
            anchor = soup.new_tag("a")
            anchor["name"] = key
            place.insert_before(anchor)
            del tag["id"]

        # Internal links -> "#anchor"
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if urlparse(href).scheme in ("http", "https", "mailto"):
                continue
            name, frag = _resolve(doc.get_name(), href)
            if name in index:
                a["href"] = "#" + (f"c{index[name]}_{frag}" if frag else f"c{index[name]}")
            else:
                del a["href"]

        # Images -> epub:///path (served by the reader widget)
        for img in soup.find_all("img"):
            src = img.get("src")
            if not src or urlparse(src).scheme:
                continue
            name, _ = _resolve(doc.get_name(), src)
            img["src"] = f"epub:///{quote(name)}"
            img.attrs.pop("width", None)
            img.attrs.pop("height", None)

        body = soup.body or soup
        parts.append(f'<a name="c{i}"></a>{body.decode_contents()}<hr>')

    html = "<html><body>" + "\n".join(parts) + "</body></html>"

    # Table of contents
    def make_entry(link, children: list[TocEntry]) -> TocEntry:
        key = None
        href = getattr(link, "href", "") or ""
        if href:
            name, frag = urldefrag(href)
            name = posixpath.normpath(unquote(name))
            if name in index:
                k = f"c{index[name]}_{frag}" if frag else ""
                key = k if k in keys else f"c{index[name]}"
        if key is None and children:
            key = children[0].key
        return TocEntry(getattr(link, "title", None) or "(untitled)", key, children)

    def convert(nodes) -> list[TocEntry]:
        out = []
        for node in nodes:
            if isinstance(node, tuple):
                section, children = node
                out.append(make_entry(section, convert(children)))
            else:
                out.append(make_entry(node, []))
        return out

    toc = convert(book.toc)
    if not toc:  # fallback: one entry per chapter
        toc = [TocEntry(f"Section {i + 1}", f"c{i}") for i in range(len(docs))]

    return LoadedBook(
        title=title,
        html=html,
        toc=toc,
        resources=resources,
        image_anchors=image_keys,
        chapters=parts,
        cover=_find_cover(book, resources),
    )
