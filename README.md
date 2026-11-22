# Ebooks Reader

A simple desktop e-book reader for Windows, written in Python with PySide6 (Qt).
Currently supports **EPUB**; the code is structured so more formats can be added.

## Features

- Continuous scrolling view of the whole book, with images
- Images open full-size in a separate viewer window (zoom, pan, save, copy, fullscreen)
- Contents tree in a side panel (click or press Enter to jump, expand/collapse all)
- 9 built-in color schemes for reading, grouped into Light (Light, Sepia, Paper, Soft Gray, Eye Green) and Dark (Dark, Night, Charcoal, Warm Night). Your own themes are sorted into the groups automatically
- Theme editor: create your own schemes (name, background, text) with a live preview
- Share a color scheme with a friend by copying and pasting a short code
- Text settings: font, font size, line spacing, page margins
- Chapter and section titles (h1-h5) are bold, centered and scale with the font size
- Update check from the Help menu, with an optional check at startup
- Book links (footnotes, cross-references) open in a separate window, so you keep your place in the main text
- Remembers the last opened book, reading position per book, window layout, colors and text settings

## Requirements

- Windows
- [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 and all dependencies for you)

## Run from source

```bash
git clone https://github.com/SaviolaX/ebook_reader.git ebooks-reader
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
| Change colors | `Theme` menu (built-in and your own schemes) |
| Create or edit color schemes | `Theme → Edit themes...` (`Ctrl+Shift+T`) |
| Open a link in the linked window | Click the link (default) |
| Open a link in a brand-new window | `Ctrl+click`, or right-click → "Open link in new window" |
| Jump in the same window | Right-click → "Open link here" |
| Open an image full-size | Click a link that points to an image, or right-click a picture → "Open image in viewer", or double-click it |
| Open an image link as text instead | `Ctrl+click` the link (opens the linked window at that place) |
| Turn off separate link windows | `View → Open book links in separate window` |
| Don't reopen the last book at startup | `File → Reopen last book on startup` |
| Check for a new version | `Help → Check for updates...` |
| Turn off the startup update check | `Help → Check for updates on startup` |
| Show the version | `Help → About` |

Clicking further links reuses the same linked window. Links to web pages open in your default browser.

## Headings

Titles are drawn bigger than the body text and always scale with your font size. Sizes are relative to the body font:

| Level | Size | Alignment |
| --- | --- | --- |
| h1 | 2.0x | centered |
| h2 | 1.5x | centered |
| h3 | 1.2x | centered |
| h4 | 1.3x | centered |
| h5 | 1.15x | centered |
| h6 | 1.05x | left |

To change them, edit `HEADING_LEVELS` at the top of `src/ebooks_reader/ui/reader_view.py` (name, size multiplier, centered or not).
Qt's text widget ignores font sizes inside real heading blocks, so the reader turns each `<h1>`-`<h6>` into a styled paragraph when it shows the book.

## Image viewer

A plain click on a book link that points to an image opens the original, full-size picture in a separate window; the main text stays where it is. You can also right-click any picture in the text and choose **Open image in viewer**, or double-click it. Further images reuse the same window, and it follows your color theme. It closes when you open another book or quit.

| Action | How |
| --- | --- |
| Zoom | Mouse wheel (2% to 4000%) |
| Move around | Drag with the mouse |
| Fit to window | `0` (small images are never enlarged) |
| Actual size (100%) | `1` |
| Save the original file | `Ctrl+S` |
| Copy the image | `Ctrl+C` |
| Fullscreen | `F11` |
| Leave fullscreen / close | `Esc` |

All of these are also in the viewer's right-click menu.

## Color themes

Open `Theme → Edit themes...`. The window stays open while you read, so you can try colors on the book live.

- **Left:** list of themes (built-in and your own), grouped into Light and Dark by background color.
- **Right:** theme name, background and text color (type a hex code like `#1e1e1e` or press **Pick...**), with a live preview.
- **Save** stores the scheme under that name and applies it; it then appears in the `Theme` menu. Built-in themes can't be overwritten or deleted, so give your scheme its own name.
- **Apply** uses the colors without saving. **Delete** removes a custom theme.

### Sharing a scheme

1. Press **Copy scheme**. A one-line code like `EBR1:eyJuYW1l...` is copied to the clipboard.
2. Send it to someone (chat, email, anywhere).
3. They copy the message, open the same window, press **Paste scheme** and then **Save**.

The code can sit inside a longer message. It contains only the name and the two colors.

## Saved settings

Settings are stored in the Windows registry under `HKEY_CURRENT_USER\Software\EbooksReader`:
colors, your custom themes, text settings, window layout, last book, update-check preference and the reading position of each book.

## Updates

`Help → Check for updates...` asks GitHub for the latest release of this repository and compares it with the installed version. If a newer one exists, the app offers to open the release page. The check also runs 3 seconds after startup (in the background, silent unless an update exists); turn it off in the Help menu.

The app does not install updates itself: download the zip from the release page and replace the old folder. Your settings are kept, because they live in the registry.

## Releasing a new version

1. Commit your changes.
2. Run `bash release.sh X.Y.Z` (for example `bash release.sh 0.2.4`).

The script sets the version in `src/ebooks_reader/version.py` and `pyproject.toml`, commits, creates the tag `vX.Y.Z` and pushes. GitHub Actions (`.github/workflows/release.yml`) then builds the exe on Windows and attaches `EbooksReader-vX.Y.Z.zip` to a new release. The build fails on purpose if the tag does not match `version.py`.

The repository must be public for the update check to see the releases. The update source is set in `GITHUB_REPO` in `version.py`.

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
  release.sh            # bump version, tag and push a release
  .github/workflows/release.yml  # builds and publishes releases on tags
  src/ebooks_reader/
    __init__.py         # main()
    __main__.py         # python -m ebooks_reader
    version.py          # version number and GitHub repo for update checks
    app.py              # QApplication setup
    core/
      models.py         # TocEntry, LoadedBook (format-independent)
      registry.py       # format registry and load_book() dispatcher
      updater.py        # background update check against GitHub releases
    formats/
      __init__.py       # imports every loader so it self-registers
      epub.py           # EPUB loader
    ui/
      main_window.py    # window, menus, contents tree, saved state
      reader_view.py    # scrolling text viewer
      viewer_window.py  # window for opened links (one chapter at a time)
      image_viewer.py   # full-size image window (zoom, pan, save, copy)
      themes.py         # built-in presets, custom themes, scheme sharing codes
      theme_dialog.py   # theme editor window
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
- Qt's text widget renders a simplified subset of HTML; SVG images are removed, so images wrapped in SVG can't be shown or opened in the viewer
- Which link points to an image is detected by a heuristic in `formats/epub.py` (an element with an id right under a short image block counts as the image's caption); an unusual book can fool it
- The whole book is one Qt document in the main window, so very large books can open and resize slowly
- PDF is not supported yet (it would need a different viewer)

## Ideas for later

- FB2, TXT and other reflowable formats
- PDF support
- Chapter-based loading for large books
- Bookmarks and search
- Installer (Inno Setup) with an in-app "Update now" button
