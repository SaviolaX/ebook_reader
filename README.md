# Ebooks Reader

A simple desktop e-book reader for Windows, written in Python with PySide6 (Qt).
Version 0.1.0. Currently supports **EPUB**; the code is structured so more formats can be added.

## Features

- Continuous scrolling view of the whole book, with images
- Contents tree in a side panel (click or press Enter to jump, expand/collapse all)
- Color schemes: Light, Sepia, Dark, Night, plus custom background and text colors
- Text settings: font, font size, line spacing, page margins
- Book links (footnotes, cross-references) open in a separate window, so you keep your place in the main text
- Remembers the last opened book, reading position per book, window layout, colors and text settings

## Requirements

- Windows
- [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 and all dependencies for you)

## Run from source

```bash
git clone <your-repo-url> ebooks-reader
cd ebooks-reader
uv sync
uv run ebooks-reader
```

Open a book directly:

```bash
uv run ebooks-reader "C:/path/to/book.epub"
```

## Usage

| Action | How |
| --- | --- |
| Open a book | `File → Open...` (`Ctrl+O`) |
| Show/hide contents | `View → Show contents` (`F9`) |
| Text settings | `View → Text settings...` (`Ctrl+T`) |
| Larger / smaller font | `Ctrl+=` / `Ctrl+-` |
| Change colors | `Theme` menu (presets or custom colors) |
| Open a link in the linked window | Click the link (default) |
| Open a link in a brand-new window | `Ctrl+click`, or right-click → "Open link in new window" |
| Jump in the same window | Right-click → "Open link here" |
| Turn off separate link windows | `View → Open book links in separate window` |
| Don't reopen the last book at startup | `File → Reopen last book on startup` |

Clicking further links reuses the same linked window. Links to web pages open in your default browser.

## Saved settings

Settings are stored in the Windows registry under `HKEY_CURRENT_USER\Software\EbooksReader`:
colors, text settings, window layout, last book and the reading position of each book.

## Build a Windows executable

```bash
bash build.sh
```

This creates `dist/EbooksReader/EbooksReader.exe` (PyInstaller, one-folder mode).
Keep the whole folder together; zip it to share. An unsigned exe may trigger
Windows SmartScreen ("More info → Run anyway").

## Project structure

```
ebooks-reader/
  pyproject.toml
  build.sh              # PyInstaller build
  make_icon.py          # generates icon.ico from icon.svg
  run_app.py            # entry point for PyInstaller
  src/ebooks_reader/
    __init__.py         # main()
    __main__.py         # python -m ebooks_reader
    app.py              # QApplication setup
    core/
      models.py         # TocEntry, LoadedBook (format-independent)
      registry.py       # format registry and load_book() dispatcher
    formats/
      __init__.py       # imports every loader so it self-registers
      epub.py           # EPUB loader
    ui/
      main_window.py    # window, menus, contents tree, saved state
      reader_view.py    # scrolling text viewer
      viewer_window.py  # window for opened links (one chapter at a time)
      themes.py         # color presets
      typography.py     # text settings and dialog
    resources/
      icon.svg
      icon.ico
```

## Adding a new format

1. Create `src/ebooks_reader/formats/<name>.py` with a loader function that returns a `LoadedBook`:

   ```python
   from ..core.models import LoadedBook
   from ..core.registry import register

   @register("FB2", [".fb2", ".fb2.zip"])
   def load_fb2(path: str) -> LoadedBook:
       ...
   ```

2. Add one import line to `formats/__init__.py`: `from . import fb2`

The open-file dialog and the window pick the new format up automatically.
Reflowable formats should produce HTML with anchors named `c<chapter>_<id>` and fill
`LoadedBook.chapters`, so the linked window can load a single chapter.

## Known limitations

- The book's own CSS and inline styles are removed so your colors always apply, so some formatting is lost
- Qt's text widget renders a simplified subset of HTML; SVG images are removed
- The whole book is one Qt document in the main window, so very large books can open and resize slowly
- PDF is not supported yet (it would need a different viewer)

## Ideas for later

- FB2, TXT and other reflowable formats
- PDF support
- Chapter-based loading for large books
- Bookmarks and search
- Installer (Inno Setup) and an About dialog
