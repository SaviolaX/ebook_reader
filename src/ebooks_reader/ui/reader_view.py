import os
import re

from PySide6.QtCore import QPoint, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import (
    QDesktopServices,
    QFont,
    QImage,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtWidgets import QApplication, QTextBrowser

from .themes import apply_palette
from .typography import Typography


# (tag, size relative to body text, centered) - edit sizes here
HEADING_LEVELS = [
    ("h1", 2.4, True),
    ("h2", 2.0, True),
    ("h3", 1.7, True),
    ("h4", 1.5, True),
    ("h5", 1.35, True),
    ("h6", 1.05, False),
]


class ReaderView(QTextBrowser):
    """Scrollable viewer for reflowable (HTML-based) books."""

    # (anchor name, force_new_window)
    linkRequested = Signal(str, bool)

    def __init__(self):
        super().__init__()
        self.resources: dict[str, bytes] = {}
        self.html_source = ""
        self.typography = Typography()
        # True: plain click on an internal link asks for a separate window.
        # False: plain click scrolls inside this view.
        self.links_in_window = False
        self.center_anchors = False  # True: link targets land mid-window
        # optional hook: called before jumping to an anchor, returns True
        # if it replaced the document content (e.g. loaded another chapter)
        self.before_anchor = None
        self.image_anchors: set[str] = set()
        self._img_cache: dict[tuple[str, int], QImage] = {}
        self._resize_pos = None
        self._restore_pos = None
        self._restore_tries = 0
        self.verticalScrollBar().actionTriggered.connect(self._cancel_restore)
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)
        self._resize_timer.timeout.connect(self._finish_resize)
        self.setOpenLinks(False)  # we handle links ourselves
        self.anchorClicked.connect(self._on_anchor)
        self._apply_font_and_margin()

    # ---------- content ----------
    def set_book(self, html: str, resources: dict[str, bytes], image_anchors=None) -> None:
        self.resources = resources
        self.image_anchors = set(image_anchors or ())
        self._img_cache.clear()
        self._restore_pos = None
        self.html_source = html
        self.setHtml(self._prepared_html())
        self._apply_line_height()

    def loadResource(self, rtype, url):
        if url.scheme() == "epub":
            data = self.resources.get(url.path().lstrip("/"))
            if data is None:
                return QImage()
            margin = self.typography.margin
            max_w = max(100, self.viewport().width() - 2 * margin - 20)
            key = (url.path(), max_w)
            img = self._img_cache.get(key)
            if img is None:
                img = QImage.fromData(data)
                if img.width() > max_w:
                    img = img.scaledToWidth(
                        max_w, Qt.TransformationMode.SmoothTransformation
                    )
                if len(self._img_cache) > 300:
                    self._img_cache.clear()
                self._img_cache[key] = img
            return img
        return super().loadResource(rtype, url)

    # ---------- look ----------
    def apply_colors(self, bg: str, fg: str) -> None:
        apply_palette(self, bg, fg)

    def apply_typography(self, t: Typography) -> None:
        pos = self.top_position() if self.html_source else 0
        self.typography = t
        self._apply_font_and_margin()
        if self.html_source:
            self.setHtml(self._prepared_html())  # re-layout (also re-fits images)
            self._apply_line_height()
            QTimer.singleShot(0, lambda: self.scroll_to_position(pos))

    def _apply_font_and_margin(self) -> None:
        t = self.typography
        self.setFont(QFont(t.family, t.size))
        self.document().setDocumentMargin(t.margin)
        self.document().setDefaultStyleSheet(self._heading_css(t))

    @staticmethod
    def _heading_css(t: Typography) -> str:
        # (tag, size relative to body text, centered)
        levels = HEADING_LEVELS
        rules = []
        for tag, scale, centered in levels:
            align = "center" if centered else "left"
            rules.append(
                f"{tag} {{ font-size: {t.size * scale:.1f}pt; font-weight: bold; "
                f"text-align: {align}; margin-top: {int(t.size * scale)}px; "
                f"margin-bottom: {int(t.size * 0.8)}px; }}"
            )
        return "\n".join(rules)

    def _apply_line_height(self) -> None:
        cur = QTextCursor(self.document())
        cur.select(QTextCursor.SelectionType.Document)
        fmt = QTextBlockFormat()
        fmt.setLineHeight(
            float(self.typography.line_height),
            QTextBlockFormat.LineHeightTypes.ProportionalHeight.value,
        )
        cur.mergeBlockFormat(fmt)
        self._apply_headings()

    def _prepared_html(self) -> str:
        """Book HTML with every <h1>-<h6> turned into a sized, bold <div>.

        Qt ignores explicit font sizes inside real heading blocks, but honors
        them on a plain <div>.
        """
        t = self.typography

        def repl(m):
            level = int(m.group(1)[1])
            _tag, scale, centered = HEADING_LEVELS[level - 1]
            size = t.size * scale
            align = "center" if centered else "left"
            return (
                f'<p style="font-size:{size:.1f}pt; font-weight:bold; '
                f"text-align:{align}; margin-top:{int(size)}px; "
                f'margin-bottom:{int(t.size * 0.8)}px">{m.group(3)}</p>'
            )

        return re.sub(
            r"<(h[1-6])(\b[^>]*)>(.*?)</\1>",
            repl,
            self.html_source,
            flags=re.S | re.I,
        )

    def _apply_headings(self) -> None:
        """Set size, weight, alignment and spacing of heading blocks directly."""
        t = self.typography
        doc = self.document()
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        block = doc.begin()
        while block.isValid():
            level = block.blockFormat().headingLevel()
            if level and os.environ.get("EBR_DEBUG"):
                print("heading", level, repr(block.text()[:40]))
            if 1 <= level <= len(HEADING_LEVELS):
                _tag, scale, centered = HEADING_LEVELS[level - 1]
                cur.setPosition(block.position())
                cur.setPosition(
                    block.position() + max(block.length() - 1, 0),
                    QTextCursor.MoveMode.KeepAnchor,
                )
                cf = QTextCharFormat()
                cf.setProperty(QTextFormat.Property.FontSizeAdjustment, 0)
                cf.setFontPointSize(t.size * scale)
                cf.setFontWeight(QFont.Weight.Bold)
                cur.mergeCharFormat(cf)
                bf = QTextBlockFormat()
                bf.setAlignment(
                    Qt.AlignmentFlag.AlignHCenter if centered else Qt.AlignmentFlag.AlignLeft
                )
                bf.setTopMargin(t.size * scale)
                bf.setBottomMargin(t.size * 0.8)
                cur.mergeBlockFormat(bf)
                if os.environ.get("EBR_DEBUG"):
                    probe = QTextCursor(doc)
                    probe.setPosition(block.position() + 1)
                    print(
                        f"  h{level}: wanted {t.size * scale:.1f}pt, "
                        f"got {probe.charFormat().fontPointSize():.1f}pt "
                        f"(body {t.size}pt)"
                    )
            block = block.next()
        cur.endEditBlock()

    # ---------- reading position ----------
    def top_position(self) -> int:
        """Character offset of the text at the top of the viewport."""
        x = int(self.document().documentMargin()) + 2
        return self.cursorForPosition(QPoint(x, 2)).position()

    def scroll_to_position(self, pos: int) -> None:
        doc = self.document()
        cur = QTextCursor(doc)
        cur.setPosition(max(0, min(pos, doc.characterCount() - 1)))
        self.setTextCursor(cur)
        bar = self.verticalScrollBar()
        bar.setValue(bar.value() + self.cursorRect().top())

    # ---------- restoring a saved position ----------
    def restore_position(self, pos: int) -> None:
        """Scroll to `pos`, re-applying it a few times while the layout settles."""
        self._resize_timer.stop()
        self._resize_pos = None
        self._restore_pos = pos
        self._restore_tries = 0
        self._restore_tick()

    def _restore_tick(self) -> None:
        if self._restore_pos is None:
            return
        self.scroll_to_position(self._restore_pos)
        self._restore_tries += 1
        if self._restore_tries < 8:
            QTimer.singleShot(150, self._restore_tick)
        else:
            self._restore_pos = None

    def _cancel_restore(self, *_) -> None:
        # called when the user scrolls by hand
        self._restore_pos = None

    def current_position(self) -> int:
        """Position worth saving: the pending target, or the text at the top."""
        if self._restore_pos is not None:
            return self._restore_pos
        return self.top_position()

    # ---------- resizing ----------
    def resizeEvent(self, event):
        # Remember the top text only at the START of a resize,
        # restore it once the resizing has stopped.
        if self._restore_pos is not None:
            super().resizeEvent(event)  # restore ticks keep the position
            return
        if self.html_source and self._resize_pos is None:
            self._resize_pos = self.top_position()
        super().resizeEvent(event)
        if self._resize_pos is not None:
            self._resize_timer.start()

    def _finish_resize(self):
        pos, self._resize_pos = self._resize_pos, None
        if pos is not None:
            self.scroll_to_position(pos)

    def go_to_anchor(self, name: str) -> None:
        # An explicit jump cancels any pending "restore after resize"
        self._resize_timer.stop()
        self._resize_pos = None
        reloaded = bool(self.before_anchor and self.before_anchor(name))
        if reloaded:
            # new content was just set: give the layout a moment first
            QTimer.singleShot(30, lambda: self._scroll_to_anchor(name))
        else:
            self._scroll_to_anchor(name)

    def _scroll_to_anchor(self, name: str) -> None:
        self.scrollToAnchor(name)
        if self.center_anchors:
            bar = self.verticalScrollBar()
            if name in self.image_anchors:
                # image: show it from its top edge, with a small gap
                bar.setValue(bar.value() - 24)
            else:
                # text: put it in the middle of the window
                bar.setValue(bar.value() - self.viewport().height() // 2)

    # ---------- links ----------
    def _on_anchor(self, url: QUrl) -> None:
        if url.scheme() in ("http", "https", "mailto"):
            QDesktopServices.openUrl(url)
            return
        fragment = url.fragment()
        if not fragment:
            return
        ctrl = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier)
        if ctrl:
            self.linkRequested.emit(fragment, True)  # always a brand-new window
        elif self.links_in_window:
            self.linkRequested.emit(fragment, False)  # reuse the linked window
        else:
            self.go_to_anchor(fragment)

    def contextMenuEvent(self, event):
        href = self.anchorAt(event.pos())
        menu = self.createStandardContextMenu()
        if href:
            menu.addSeparator()
            if href.startswith("#"):
                frag = href[1:]
                a_new = menu.addAction("Open link in new window")
                a_new.triggered.connect(lambda: self.linkRequested.emit(frag, True))
                a_here = menu.addAction("Open link here")
                a_here.triggered.connect(lambda: self.go_to_anchor(frag))
            else:
                act = menu.addAction("Open link in browser")
                act.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(href)))
        menu.exec(event.globalPos())
