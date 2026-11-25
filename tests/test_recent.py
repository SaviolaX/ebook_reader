import json

from ebooks_reader.ui.recent import (
    MAX_RECENT,
    add_recent,
    clear_recent,
    load_recent,
    remove_recent,
)


class FakeSettings:
    def __init__(self):
        self.d = {}

    def value(self, key, default=None):
        return self.d.get(key, default)

    def setValue(self, key, value):
        self.d[key] = value


def test_add_puts_newest_first_and_dedupes(tmp_path):
    s = FakeSettings()
    a, b = str(tmp_path / "a.epub"), str(tmp_path / "b.epub")
    add_recent(s, a)
    add_recent(s, b)
    add_recent(s, a)  # again: moves to the top, no duplicate
    assert load_recent(s) == [a, b]


def test_limit(tmp_path):
    s = FakeSettings()
    for i in range(MAX_RECENT + 5):
        add_recent(s, str(tmp_path / f"{i}.epub"))
    items = load_recent(s)
    assert len(items) == MAX_RECENT
    assert items[0].endswith(f"{MAX_RECENT + 4}.epub")


def test_remove_and_clear(tmp_path):
    s = FakeSettings()
    a, b = str(tmp_path / "a.epub"), str(tmp_path / "b.epub")
    add_recent(s, a)
    add_recent(s, b)
    remove_recent(s, a)
    assert load_recent(s) == [b]
    clear_recent(s)
    assert load_recent(s) == []


def test_bad_data_gives_empty_list():
    s = FakeSettings()
    s.setValue("recent_books", "{not json")
    assert load_recent(s) == []
    s.setValue("recent_books", json.dumps({"a": 1}))
    assert load_recent(s) == []
    s.setValue("recent_books", json.dumps([1, "ok.epub", None]))
    assert load_recent(s) == ["ok.epub"]


def test_titles_and_book_id(tmp_path):
    from ebooks_reader.ui.recent import book_id, get_title, set_title

    s = FakeSettings()
    p = str(tmp_path / "a.epub")
    assert get_title(s, p) == ""
    set_title(s, p, "Моя книга")
    assert get_title(s, p) == "Моя книга"
    assert book_id(p) == book_id(str(tmp_path / "." / "a.epub"))
