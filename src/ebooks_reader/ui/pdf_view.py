"""Page viewer for PDF books (fixed layout: no font settings, only zoom).

Same role as ReaderView for text books, with the methods MainWindow calls
(current_position, go_to_anchor, go_back, restore_position, apply_colors ...).

A position is ONE int: page * POS_SCALE + fraction of the page (0..POS_SCALE-1).
So bookmarks, Back/Forward and the saved reading position keep working as plain ints.
Anchor keys are "p<page>" (see formats/pdf.py).

Colors: every page is rendered by QtPdf and then recolored, white -> background and
black -> text color (colors in between are mixed per channel). Pictures get tinted
too; "original colors" shows the pages unchanged.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections import OrderedDict

from PySide6.QtCore import QRect, QRectF, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QAbstractScrollArea

POS_SCALE = 100_000
MARGIN = 12  # px around the pages
GAP = 28  # px between pages (the page number is drawn in it)
POINT_TO_PX = 96 / 72  # 100% zoom = 96 dpi
ZOOM_MIN, ZOOM_MAX = 0.1, 8.0
CACHE_BYTES = 160 * 1024 * 1024  # rendered pages kept in memory
HIGHLIGHT = QColor(255, 200, 0, 110)  # search hit

_KEY_RE = re.compile(r"p(\d+)")
_FMT = QImage.Format.Format_ARGB32_Premultiplied
_CM = QPainter.CompositionMode


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(
        int(a.red() * (1 - t) + b.red() * t),
        int(a.green() * (1 - t) + b.green() * t),
        int(a.blue() * (1 - t) + b.blue() * t),
    )


def _opaque(img: QImage) -> QImage:
    """The page on a white sheet, so it is never transparent."""
    out = QImage(img.size(), _FMT)
    out.fill(QColor(255, 255, 255))
    p = QPainter(out)
    p.drawImage(0, 0, img)
    p.end()
    return out


def _recolor(img: QImage, bg: QColor, fg: QColor) -> QImage:
    """out = v*bg + (1-v)*fg per channel, v = the original value (white=1, black=0)."""
    a = _opaque(img)  # becomes v * bg
    b = a.copy()  # becomes (1 - v) * fg
    p = QPainter(a)
    p.setCompositionMode(_CM.CompositionMode_Multiply)
    p.fillRect(a.rect(), bg)
    p.end()
    p = QPainter(b)
    p.setCompositionMode(_CM.CompositionMode_Difference)
    p.fillRect(b.rect(), QColor(255, 255, 255))  # 255 - v
    p.setCompositionMode(_CM.CompositionMode_Multiply)
    p.fillRect(b.rect(), fg)
    p.end()
    p = QPainter(a)
    p.setCompositionMode(_CM.CompositionMode_Plus)
    p.drawImage(0, 0, b)
    p.end()
    return a


class PdfView(QAbstractScrollArea):
    historyChanged = Signal()  # Back/Forward became (un)available
    zoomChanged = Signal()

    HISTORY_LIMIT = 50
    supports_pdf_search = True  # FindBar checks this

    def __init__(self):
        super().__init__()
        self.doc: QPdfDocument | None = None
        self.path = ""
        self.page_count = 0
        self.history_enabled = False  # only the main window turns this on
        self.original_colors = False
        self._bg, self._fg = "#ffffff", "#1a1a1a"
        self._mode = "width"  # "width", "page" or "custom"
        self._zoom = 1.0  # used in "custom" mode (1.0 = 100%)
        self._scale = POINT_TO_PX  # pixels per PDF point right now
        self._sizes: list[tuple[float, float]] = []  # page sizes in points
        self._max_w = self._max_h = 1.0
        self._w: list[int] = []  # page sizes in pixels
        self._h: list[int] = []
        self._tops: list[int] = []  # y of every page top
        self._total_w = self._total_h = 0
        self._cache: OrderedDict = OrderedDict()
        self._back: list[int] = []
        self._forward: list[int] = []
        self._forward_backup: list[int] = []
        self._restore_pos: int | None = None
        self._restore_tries = 0
        self._texts: dict[int, str] = {}  # page -> text, for searching
        self._hit: tuple[int, int, int] | None = None  # page, start, length
        self._hit_rects: list[QRectF] = []  # in PDF points

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # always on: a scrollbar that comes and goes would change the width and the zoom
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.verticalScrollBar().setSingleStep(60)
        self.horizontalScrollBar().setSingleStep(40)
        self.verticalScrollBar().actionTriggered.connect(self._cancel_restore)

    # ---------- document ----------
    def open_pdf(self, path: str) -> None:
        doc = QPdfDocument(self)
        doc.load(path)
        count = doc.pageCount() if doc.status() == QPdfDocument.Status.Ready else 0
        if count <= 0:
            doc.deleteLater()
            raise ValueError("The PDF could not be opened.")
        sizes = []
        for i in range(count):
            s = doc.pagePointSize(i)
            ok = s.width() > 0 and s.height() > 0
            sizes.append((s.width(), s.height()) if ok else (595.0, 842.0))
        self.close_pdf()  # only after the new file proved readable
        self.doc, self.path, self.page_count = doc, path, count
        self._sizes = sizes
        self._max_w = max(w for w, _ in sizes)
        self._max_h = max(h for _, h in sizes)
        self._mode, self._zoom = "width", 1.0
        self._relayout(keep=False)
        self.verticalScrollBar().setValue(0)
        self.viewport().update()

    def close_pdf(self) -> None:
        if self.doc is not None:
            self.doc.close()
            self.doc.deleteLater()
        self.doc, self.path, self.page_count = None, "", 0
        self._sizes, self._w, self._h, self._tops = [], [], [], []
        self._cache.clear()
        self._texts.clear()
        self._hit, self._hit_rects = None, []
        self._restore_pos = None
        self._clear_history()
        self.verticalScrollBar().setRange(0, 0)
        self.horizontalScrollBar().setRange(0, 0)
        self.viewport().update()

    # ---------- look ----------
    def apply_colors(self, bg: str, fg: str) -> None:
        self._bg, self._fg = bg, fg
        self._cache.clear()
        self.viewport().update()

    def set_original_colors(self, on: bool) -> None:
        self.original_colors = bool(on)
        self._cache.clear()
        self.viewport().update()

    # ---------- zoom ----------
    def zoom_percent(self) -> int:
        return round(self._scale / POINT_TO_PX * 100)

    def set_fit(self, mode: str) -> None:
        self._mode = mode  # "width" or "page"
        self._relayout(keep=True)
        self.zoomChanged.emit()

    def zoom_by(self, factor: float) -> None:
        z = self._scale / POINT_TO_PX * factor
        self._zoom = max(ZOOM_MIN, min(ZOOM_MAX, z))
        self._mode = "custom"
        self._relayout(keep=True)
        self.zoomChanged.emit()

    def actual_size(self) -> None:
        self._zoom, self._mode = 1.0, "custom"
        self._relayout(keep=True)
        self.zoomChanged.emit()

    def _compute_scale(self) -> float:
        vw = max(self.viewport().width(), 100)
        vh = max(self.viewport().height(), 100)
        if self._mode == "width":
            s = (vw - 2 * MARGIN) / self._max_w
        elif self._mode == "page":
            s = min((vw - 2 * MARGIN) / self._max_w, (vh - 2 * MARGIN) / self._max_h)
        else:
            s = self._zoom * POINT_TO_PX
        return max(ZOOM_MIN * POINT_TO_PX, min(ZOOM_MAX * POINT_TO_PX, s))

    # ---------- layout ----------
    def _relayout(self, keep: bool = True) -> None:
        if not self._sizes:
            return
        pos = None
        if keep and self._tops and self._restore_pos is None:
            pos = self._top_position()  # the text at the top stays at the top
        self._scale = s = self._compute_scale()
        self._w = [max(1, round(w * s)) for w, _ in self._sizes]
        self._h = [max(1, round(h * s)) for _, h in self._sizes]
        self._tops = []
        y = MARGIN
        for h in self._h:
            self._tops.append(y)
            y += h + GAP
        self._total_h = y  # the last page keeps room for its number too
        self._total_w = max(self._w) + 2 * MARGIN
        vp = self.viewport()
        vbar, hbar = self.verticalScrollBar(), self.horizontalScrollBar()
        vbar.setRange(0, max(0, self._total_h - vp.height()))
        vbar.setPageStep(vp.height())
        hbar.setRange(0, max(0, self._total_w - vp.width()))
        hbar.setPageStep(vp.width())
        if pos is not None:
            self._set_scroll_pos(pos)
        elif self._restore_pos is not None:
            self._set_scroll_pos(self._restore_pos)
        vp.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout(keep=True)

    # ---------- positions ----------
    def _top_position(self) -> int:
        if not self._tops:
            return 0
        v = self.verticalScrollBar().value()
        i = max(0, bisect_right(self._tops, v) - 1)
        frac = (v - self._tops[i]) / max(self._h[i], 1)
        frac = min(max(frac, 0.0), 0.99999)
        return i * POS_SCALE + int(frac * POS_SCALE)

    def _set_scroll_pos(self, pos: int) -> None:
        if not self._tops:
            return
        page, f = divmod(max(pos, 0), POS_SCALE)
        page = min(page, len(self._tops) - 1)
        y = self._tops[page] + f / POS_SCALE * self._h[page]
        self.verticalScrollBar().setValue(round(y))

    def current_position(self) -> int:
        """Position worth saving: the pending target, or the top of the window."""
        if self._restore_pos is not None:
            return self._restore_pos
        return self._top_position()

    def percent_at(self, pos: int) -> int:
        total = max(self.page_count * POS_SCALE, 1)
        return min(100, int(pos * 100 / total))

    def label_at(self, pos: int) -> str:
        return f"Page {pos // POS_SCALE + 1} of {self.page_count}"

    def anchor_positions(self) -> dict[str, int]:
        return {f"p{i}": i * POS_SCALE for i in range(self.page_count)}

    def _anchor_pos(self, name: str) -> int | None:
        m = _KEY_RE.fullmatch(name or "")
        if not m or not 0 <= int(m.group(1)) < self.page_count:
            return None
        return int(m.group(1)) * POS_SCALE

    # ---------- restoring a saved position ----------
    def restore_position(self, pos: int) -> None:
        """Scroll to `pos`, re-applying it a few times while the window settles."""
        self._restore_pos = pos
        self._restore_tries = 0
        self._restore_tick()

    def _restore_tick(self) -> None:
        if self._restore_pos is None:
            return
        self._set_scroll_pos(self._restore_pos)
        self._restore_tries += 1
        if self._restore_tries < 5:
            QTimer.singleShot(100, self, self._restore_tick)
        else:
            self._restore_pos = None

    def _cancel_restore(self, *_) -> None:
        self._restore_pos = None  # the user scrolled by hand

    def _scroll_now(self, pos: int) -> None:
        self._restore_pos = None
        self._set_scroll_pos(pos)

    # ---------- jumps, back / forward ----------
    def go_to_anchor(self, name: str) -> None:
        pos = self._anchor_pos(name)
        if pos is None:
            return
        start = self.current_position()
        pushed = self.remember_position()
        self._scroll_now(pos)
        if pushed and self.current_position() == start:
            self._undo_remember()  # landed on the same spot: nothing to go back to

    def jump_to_position(self, pos: int) -> None:
        self.remember_position()
        self._scroll_now(pos)

    def _clear_history(self) -> None:
        had = bool(self._back or self._forward)
        self._back.clear()
        self._forward.clear()
        self._forward_backup = []
        if had:
            self.historyChanged.emit()

    def can_go_back(self) -> bool:
        return bool(self._back)

    def can_go_forward(self) -> bool:
        return bool(self._forward)

    def remember_position(self, at: int | None = None) -> bool:
        """Call right BEFORE a jump. Returns True if a Back entry was added."""
        if not self.history_enabled or not self.doc:
            return False
        pos = self.current_position() if at is None else at
        if self._back and self._back[-1] == pos:
            return False
        self._forward_backup = list(self._forward)
        self._back.append(pos)
        del self._back[: -self.HISTORY_LIMIT]
        self._forward.clear()
        self.historyChanged.emit()
        return True

    def _undo_remember(self) -> None:
        if self._back:
            self._back.pop()
        self._forward = self._forward_backup
        self.historyChanged.emit()

    def go_back(self) -> None:
        if not self._back:
            return
        self._forward.append(self.current_position())
        self._scroll_now(self._back.pop())
        self.historyChanged.emit()

    def go_forward(self) -> None:
        if not self._forward:
            return
        self._back.append(self.current_position())
        self._scroll_now(self._forward.pop())
        self.historyChanged.emit()

    # ---------- input ----------
    def mousePressEvent(self, event):
        if self.history_enabled:
            if event.button() == Qt.MouseButton.BackButton:
                self.go_back()
                return
            if event.button() == Qt.MouseButton.ForwardButton:
                self.go_forward()
                return
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            dy = event.angleDelta().y()
            if dy:
                self.zoom_by(1.1 if dy > 0 else 1 / 1.1)
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event):
        bar = self.verticalScrollBar()
        if event.key() == Qt.Key.Key_Home:
            self._restore_pos = None
            bar.setValue(bar.minimum())
            return
        if event.key() == Qt.Key.Key_End:
            self._restore_pos = None
            bar.setValue(bar.maximum())
            return
        super().keyPressEvent(event)

    # ---------- search (needs a text layer) ----------
    def _text_of(self, page: int) -> str:
        t = self._texts.get(page)
        if t is None:
            raw = self.doc.getAllText(page).text()
            t = raw.replace("\r", " ").replace("\n", " ")  # same length: indexes stay valid
            self._texts[page] = t
        return t

    def clear_search(self) -> None:
        self._hit, self._hit_rects = None, []
        self.viewport().update()

    def _hit_visible(self) -> bool:
        if not self._hit or not self._hit_rects:
            return False
        y = (
            self._tops[self._hit[0]]
            + self._hit_rects[0].top() * self._scale
            - self.verticalScrollBar().value()
        )
        return 0 <= y < self.viewport().height()

    def pdf_search(self, text: str, backwards: bool, case: bool, incremental: bool) -> str:
        """Find the next hit. Returns "found", "wrapped", "none" or "notext"."""
        if not self.doc or not text:
            return "none"
        needle = text if case else text.lower()
        n = self.page_count
        if self._hit and self._hit_visible():
            page, start, length = self._hit
            pos = start if (incremental or backwards) else start + length
        else:  # start from what is on screen
            top = self._top_position()
            page = top // POS_SCALE
            pos = int(top % POS_SCALE / POS_SCALE * len(self._text_of(page)))
        found = None
        for step in range(n + 1):  # n + 1: the start page is searched twice (wrap-around)
            p = (page + (-step if backwards else step)) % n
            hay = self._text_of(p)
            if not case:
                hay = hay.lower()
            if backwards:
                i = hay.rfind(needle, 0, pos) if step == 0 else hay.rfind(needle)
            else:
                i = hay.find(needle, pos) if step == 0 else hay.find(needle)
            if i >= 0:
                wrapped = (page - step < 0) if backwards else (page + step >= n)
                found = (p, i, wrapped)
                break
        if found is None:
            has_text = any(self._text_of(i).strip() for i in range(n))
            return "none" if has_text else "notext"
        p, i, wrapped = found
        self._hit = (p, i, len(needle))
        sel = self.doc.getSelectionAtIndex(p, i, len(needle))
        self._hit_rects = [poly.boundingRect() for poly in sel.bounds()]
        self._reveal_hit()
        self.viewport().update()
        return "wrapped" if wrapped else "found"

    def _reveal_hit(self) -> None:
        self._restore_pos = None
        page = self._hit[0]
        if not self._hit_rects:
            self._set_scroll_pos(page * POS_SCALE)
            return
        r, s = self._hit_rects[0], self._scale
        vbar, hbar = self.verticalScrollBar(), self.horizontalScrollBar()
        vw, vh = self.viewport().width(), self.viewport().height()
        y = self._tops[page] + r.top() * s
        if not (vbar.value() + vh // 6 <= y <= vbar.value() + vh * 5 // 6):
            vbar.setValue(round(y - vh // 3))
        x = (max(vw, self._total_w) - self._w[page]) // 2 + r.left() * s
        if x < hbar.value() or x > hbar.value() + vw - 40:
            hbar.setValue(round(x - vw // 3))

    # ---------- painting ----------
    def _page_image(self, i: int, w: int, h: int, dpr: float) -> QImage | None:
        key = (i, w, h, round(dpr * 100), self.original_colors, self._bg, self._fg)
        img = self._cache.get(key)
        if img is not None:
            self._cache.move_to_end(key)
            return img
        size = QSize(max(1, round(w * dpr)), max(1, round(h * dpr)))
        img = self.doc.render(i, size)
        if img.isNull():
            return None
        if self.original_colors:
            img = _opaque(img)
        else:
            img = _recolor(img, QColor(self._bg), QColor(self._fg))
        self._cache[key] = img
        while len(self._cache) > 3 and sum(v.sizeInBytes() for v in self._cache.values()) > CACHE_BYTES:
            self._cache.popitem(last=False)
        return img

    def paintEvent(self, event):
        p = QPainter(self.viewport())
        bg, fg = QColor(self._bg), QColor(self._fg)
        p.fillRect(event.rect(), _mix(bg, fg, 0.12))
        if not self.doc or not self._tops:
            p.end()
            return
        vw, vh = self.viewport().width(), self.viewport().height()
        v = self.verticalScrollBar().value()
        hx = self.horizontalScrollBar().value()
        dpr = self.devicePixelRatioF()
        border = _mix(bg, fg, 0.3)
        label_color = _mix(bg, fg, 0.7)
        font = self.font()
        font.setPointSize(9)
        p.setFont(font)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(max(0, bisect_right(self._tops, v) - 1), self.page_count):
            top = self._tops[i] - v
            if top > vh:
                break
            w, h = self._w[i], self._h[i]
            x = (max(vw, self._total_w) - w) // 2 - hx
            rect = QRect(x, top, w, h)
            if not rect.adjusted(0, 0, 0, GAP).intersects(event.rect()):
                continue
            img = self._page_image(i, w, h, dpr)
            if img is not None:
                p.drawImage(rect, img)
            if self._hit and self._hit[0] == i:
                s = self._scale
                for r in self._hit_rects:
                    p.fillRect(
                        QRectF(x + r.x() * s, top + r.y() * s, r.width() * s, r.height() * s),
                        HIGHLIGHT,
                    )
            p.setPen(QPen(border, 1))
            p.drawRect(rect.adjusted(-1, -1, 0, 0))
            p.setPen(QPen(label_color, 1))
            p.drawText(
                QRect(x, top + h, w, GAP),
                Qt.AlignmentFlag.AlignCenter,
                f"{i + 1} / {self.page_count}",
            )
        p.end()
