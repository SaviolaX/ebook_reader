from ebooks_reader.core.models import TocEntry
from ebooks_reader.ui.notes import NoteStore, export_markdown, flatten


def toc():
    return [
        TocEntry("Part 1", "c1", [TocEntry("Chapter 1", "c1"), TocEntry("Chapter 2", "c2_x")]),
        TocEntry("Cover", None),
        TocEntry("Part 2", "c3"),
    ]


def test_flatten_makes_ids_unique_and_keeps_order():
    flat = flatten(toc())
    assert [f.note_id for f in flat] == ["c1", "c1~2", "c2_x", None, "c3"]
    assert [f.depth for f in flat] == [0, 1, 1, 0, 0]


def test_set_get_and_blank_deletes(tmp_path):
    s = NoteStore(tmp_path / "n.json")
    assert s.set("c1", "Part 1", "hello") is True
    assert s.set("c1", "Part 1", "hello") is False  # unchanged
    assert s.get("c1") == "hello" and s.count() == 1
    assert s.set("c1", "Part 1", "  \n") is True  # blank -> removed
    assert s.count() == 0 and s.set("c1", "Part 1", "") is False


def test_save_and_reload(tmp_path):
    p = tmp_path / "sub" / "n.json"
    s = NoteStore(p)
    s.set("c1", "Часть 1", "тест")
    s.save()
    assert NoteStore(p).get("c1") == "тест"
    s.set("c1", "Часть 1", "")
    s.save()
    assert not p.exists()  # no notes -> no file


def test_damaged_file_is_set_aside(tmp_path):
    p = tmp_path / "n.json"
    p.write_text("{not json", encoding="utf-8")
    s = NoteStore(p)
    assert s.count() == 0
    assert (tmp_path / "n.json.bad").exists()


def test_export_markdown_includes_parents_and_orphans(tmp_path):
    s = NoteStore(tmp_path / "n.json")
    s.set("c2_x", "Chapter 2", "my thoughts")
    s.set("gone", "Old entry", "orphan text")
    md = export_markdown("Book", flatten(toc()), s)
    assert "## Part 1" in md and "### Chapter 2" in md and "my thoughts" in md
    assert "Chapter 1" not in md and "Part 2" not in md
    assert "## Unattached notes" in md and "orphan text" in md
