import pytest
from pdf_helpers import make_pdf

from ebooks_reader.formats import load_book
from ebooks_reader.formats.pdf import _page_entries
from ebooks_reader.ui.notes import NoteStore, export_markdown, flatten

PAGES = [
    ["alpha beta gamma", "second line here"],
    ["nothing special"],
    ["Delta ALPHA", "tail"],
    ["last page"],
]
OUTLINE = [
    ("Chapter 1", 0, [("Section 1.1", 1, [])]),
    ("Chapter 2", 2, []),
]


@pytest.fixture
def pdf(tmp_path):
    return make_pdf(tmp_path / "book.pdf", PAGES, OUTLINE)


@pytest.fixture
def view(qapp, pdf):
    from ebooks_reader.ui.pdf_view import PdfView

    v = PdfView()
    v.history_enabled = True
    v.resize(800, 600)
    v.show()
    qapp.processEvents()
    v.open_pdf(str(pdf))
    qapp.processEvents()
    yield v
    v.close_pdf()


# ---------- loader ----------
def test_loader_outline_cover_and_pages(qapp, pdf):
    b = load_book(str(pdf))
    assert b.pdf_path == str(pdf) and b.page_count == 4 and b.html == ""
    assert b.title == "book"  # no title in the file: the file name
    assert [e.key for e in b.toc] == ["p0", "p2"]
    assert b.toc[0].children[0].title == "Section 1.1"
    assert b.toc[0].children[0].key == "p1"
    assert b.cover and b.cover[:4] == b"\x89PNG"


def test_loader_without_outline_gives_page_entries(qapp, tmp_path):
    p = make_pdf(tmp_path / "plain.pdf", PAGES)
    b = load_book(str(p))
    assert [e.title for e in b.toc] == ["Page 1", "Page 2", "Page 3", "Page 4"]
    assert [e.key for e in b.toc] == ["p0", "p1", "p2", "p3"]


def test_page_entries_are_grouped_for_long_books():
    short = _page_entries(60)
    assert len(short) == 60 and short[0].title == "Page 1"
    mid = _page_entries(100)
    assert len(mid) == 10 and mid[1].key == "p10" and mid[1].title.startswith("Pages 11")
    long = _page_entries(700)
    assert len(long) == 14 and long[-1].key == "p650"


def test_bad_and_missing_files_raise_clear_errors(qapp, tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_text("this is not a pdf")
    with pytest.raises(ValueError, match="damaged|not a PDF"):
        load_book(str(bad))
    with pytest.raises(ValueError, match="not found"):
        load_book(str(tmp_path / "missing.pdf"))


# ---------- positions, anchors, history ----------
def test_anchor_jump_back_forward(view):
    from ebooks_reader.ui.pdf_view import POS_SCALE

    assert view.current_position() == 0 and not view.can_go_back()
    view.go_to_anchor("p2")
    assert view.current_position() == 2 * POS_SCALE and view.can_go_back()
    view.go_to_anchor("p2")  # same spot: no new Back entry
    assert len(view._back) == 1
    view.go_back()
    assert view.current_position() == 0 and view.can_go_forward()
    view.go_forward()
    assert view.current_position() == 2 * POS_SCALE
    view.go_to_anchor("nope")
    view.go_to_anchor("p99")
    assert view.current_position() == 2 * POS_SCALE


def test_percent_label_and_anchor_map(view):
    from ebooks_reader.ui.pdf_view import POS_SCALE

    assert view.percent_at(2 * POS_SCALE) == 50
    assert view.label_at(2 * POS_SCALE) == "Page 3 of 4"
    assert view.anchor_positions() == {f"p{i}": i * POS_SCALE for i in range(4)}


def test_zoom_and_resize_keep_the_place(view):
    from ebooks_reader.ui.pdf_view import POS_SCALE

    view.jump_to_position(1 * POS_SCALE + 40000)
    before = view.current_position()
    view.zoom_by(1.5)
    assert abs(view.current_position() - before) < 500
    view.set_fit("page")
    assert abs(view.current_position() - before) < 500
    view.actual_size()
    assert view.zoom_percent() == 100
    view.set_fit("width")
    view.resize(500, 700)
    assert abs(view.current_position() - before) < 500


def test_failed_open_keeps_the_current_book(view, tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_text("nope")
    with pytest.raises(ValueError):
        view.open_pdf(str(bad))
    assert view.page_count == 4


# ---------- colors ----------
def _page_pixel(view):
    img = view.viewport().grab().toImage()
    vw = view.viewport().width()
    w, top, h = view._w[0], view._tops[0], view._h[0]
    x = (max(vw, view._total_w) - w) // 2 + w - 30  # empty right side of page 1
    y = min(top + h // 2, img.height() - 5)
    from PySide6.QtGui import QColor

    return QColor(img.pixel(x, y)).name()


def test_pages_are_recolored_and_original_colors_work(view, qapp):
    view.apply_colors("#1e1e1e", "#d4d4d4")
    qapp.processEvents()
    assert _page_pixel(view) == "#1e1e1e"
    view.apply_colors("#f4ecd8", "#5b4636")
    assert _page_pixel(view) == "#f4ecd8"
    view.set_original_colors(True)
    assert _page_pixel(view) == "#ffffff"


# ---------- search ----------
def test_search_next_prev_wrap_and_case(view):
    from ebooks_reader.ui.pdf_view import POS_SCALE

    assert view.pdf_search("alpha", False, False, False) == "found"
    assert view._hit[0] == 0 and view._hit_rects  # a highlight rectangle exists
    assert view.pdf_search("alpha", False, False, False) == "found"
    assert view._hit[0] == 2  # "Delta ALPHA" (case-insensitive)
    assert view.pdf_search("alpha", False, False, False) == "wrapped"
    assert view._hit[0] == 0
    assert view.pdf_search("alpha", True, False, False) == "wrapped"  # backwards wraps to the end
    assert view._hit[0] == 2
    # match case: only one hit ("ALPHA" on page 3), so "next" wraps around onto itself
    assert view.pdf_search("ALPHA", False, True, False) == "wrapped"
    assert view._hit[0] == 2
    assert view.pdf_search("zzz", False, False, False) == "none"
    assert view._hit[0] == 2  # a failed search keeps the old hit
    assert view._hit_visible()  # the hit is scrolled into view
    assert view.current_position() // POS_SCALE <= 2


def test_search_highlight_is_on_the_right_line(view):
    view.pdf_search("second line", False, True, False)
    r = view._hit_rects[0]
    page_h_pt = view._sizes[0][1]
    # line 2 of the page is a bit below the top: between 5% and 25% of the page height
    assert 0.05 * page_h_pt < r.top() < 0.25 * page_h_pt


def test_search_in_pdf_without_text(qapp, tmp_path):
    from ebooks_reader.ui.pdf_view import PdfView

    p = make_pdf(tmp_path / "blank.pdf", [[""], [""]])
    v = PdfView()
    v.resize(600, 500)
    v.show()
    v.open_pdf(str(p))
    assert v.pdf_search("x", False, False, False) == "notext"
    v.close_pdf()


def test_find_bar_drives_the_pdf_view(view, qapp):
    from ebooks_reader.ui.find_bar import FindBar

    bar = FindBar(view)
    bar.show()
    bar.edit.setText("alpha")  # incremental search runs by itself
    assert view._hit and view._hit[0] == 0
    assert view.can_go_back()  # the first hit of a search adds one Back entry
    bar.find_next()
    assert view._hit[0] == 2
    bar.find_next()
    assert bar.status.text() == "Search wrapped"
    bar.edit.setText("zzz")
    assert bar.status.text() == "Not found"
    bar.edit.setText("")
    assert view._hit is None  # empty text clears the highlight
    bar.edit.setText("alpha")
    bar.close_bar()  # closing clears the highlight, no text cursor involved
    assert view._hit is None and not bar.isVisible()
    view.go_back()  # Back returns to where the search started
    assert view.current_position() == 0


# ---------- notes on a PDF ----------
def test_notes_work_with_pdf_contents(qapp, tmp_path):
    # two outline entries on the same page share a key: flatten() must keep ids unique
    p = make_pdf(
        tmp_path / "n.pdf",
        PAGES,
        [("Part A", 0, [("Chapter 1", 0, []), ("Chapter 2", 2, [])]), ("Part B", 3, [])],
    )
    toc = load_book(str(p)).toc
    flat = flatten(toc)
    assert [f.note_id for f in flat] == ["p0", "p0~2", "p2", "p3"]
    store = NoteStore(tmp_path / "notes.json")
    store.set("p0~2", "Chapter 1", "my note")
    store.save()
    again = NoteStore(tmp_path / "notes.json")
    assert again.get("p0~2") == "my note"
    md = export_markdown("n", flat, again)
    assert "## Part A" in md and "### Chapter 1" in md and "my note" in md
    assert "Part B" not in md
