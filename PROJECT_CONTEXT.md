# Ebooks Reader: context for the assistant

## About the project
Windows desktop e-book reader in Python 3.12, PySide6 (Qt), managed with uv.
Repo: https://github.com/SaviolaX/ebook_reader (public). Only EPUB is supported now; the
structure is meant to allow more formats (FB2, TXT, PDF, ...). See README.md for features and layout.

Current version in the files: 0.3.0 (`version.py`, `pyproject.toml`). The "contents tree follows
scrolling" feature was added after that; the next release number is the owner's choice
(0.4.0 suggested). Goal: reach 1.0.0, see "Road to 1.0.0" at the bottom.

## How to work with me (the user)
- I run everything in Git Bash on Windows and copy-paste your commands.
- Give code as bash commands: `cat > file << 'EOF'` for new files, and Python patch scripts
  (`uv run python - << 'EOF'`) for edits that assert each pattern matches exactly once and
  write nothing if any pattern is missing.
- Give a `git commit` command after each change.
- Ask questions when something is unclear. Don't guess my book's markup: ask for the HTML.
- Don't claim something works if you haven't tested it. You may test in a sandbox:
  PySide6-Essentials runs there with QT_QPA_PLATFORM=offscreen (real clicks and keys via
  QTest, a synthetic EPUB made with ebooklib). Windows-only behavior can't be tested there;
  say what was not tested.
- I do not edit the version by hand: `release.sh` does it. I only choose the number.

## Architecture
- src/ebooks_reader/core/models.py: TocEntry, LoadedBook (title, html, toc, resources,
  image_anchors, chapters).
- core/registry.py: @register(name, extensions) decorator, load_book(path),
  file_dialog_filter(). Formats self-register when imported in formats/__init__.py.
- core/updater.py: background update check (QThread) against GitHub releases.
- formats/epub.py: EPUB loader. It strips book CSS/styles, renames anchors to c<chapter>_<id>,
  rewrites links to #anchors and images to epub:///path, detects image anchors, removes SVG.
- ui/reader_view.py: QTextBrowser subclass (font, margins, line spacing, headings,
  position restore, Back/Forward, link handling, image cache).
- ui/viewer_window.py: separate window for opened links; loads only one chapter at a time.
- ui/image_viewer.py: ImageViewer window (QGraphicsView) for one original image taken from
  LoadedBook.resources; one instance is reused for every image.
- ui/find_bar.py: FindBar, the Ctrl+F search bar under the text.
- ui/bookmarks.py: Bookmark (pos, label) and load/save helpers (QSettings, JSON).
- (planned, roadmap task 2) ui/notes.py + ui/notes_window.py: notes per contents entry and the
  window that lists them.
- ui/main_window.py: menus, contents tree, saved state, themes, updates, progress, and the
  contents-tree highlighting (see below).
- ui/themes.py, theme_dialog.py: built-in/custom themes, light/dark groups, share codes "EBR1:...".
- ui/typography.py: Typography dataclass (family, size, line height, margin) and its dialog.
- app.py: QApplication setup, opens the book given on the command line or the last book,
  schedules the startup update check 3 s after launch.
- version.py: __version__ and GITHUB_REPO.
- Entry points: `ebooks-reader` script (pyproject), `python -m ebooks_reader`, run_app.py (PyInstaller).
- Files: build.sh (PyInstaller), make_icon.py (icon.svg -> icon.ico), release.sh,
  .github/workflows/release.yml.

### Contents tree and sections (main_window.py)
- `open_book` builds the tree FIRST (`_add_entries` fills `_entry_items`: id(TocEntry) -> tree item),
  then calls `_index_sections`. The order matters: indexing needs the items.
- `_index_sections` stores parallel lists sorted by character offset: `_section_starts`,
  `_section_titles`, `_section_items`. Offsets come from `ReaderView.anchor_positions()`.
- `_section_index(pos)` = `bisect_right(starts, pos + SECTION_LOOKAHEAD) - 1`.
  `SECTION_LOOKAHEAD = 10` characters: after a click on a contents entry the top line can sit
  a few characters before the anchor, and without the lookahead the previous section would win.
- `_select_section(pos)` is called from `_update_progress` (120 ms after scrolling stops). It
  does nothing if the section did not change (`_current_section`). Otherwise it expands the
  parents, sets the current item and scrolls the tree to it, with the tree's signals blocked,
  so it never triggers `_goto` (no jump loop, no Back/Forward entries).
- The status-bar section label uses the same `_section_index`, so it always matches the
  highlighted entry.

## Behavior decisions
- Clicking an internal link opens the target in a separate, reused window (so I keep my place
  in the main text). Ctrl+click opens a new window. Setting: View > Open book links in
  separate window.
- Image links: a plain click on a link whose target is an image (LoadedBook.image_anchors:
  anchor -> image path inside the book) opens the original in the ImageViewer; Ctrl+click
  opens the linked window instead. Right-click on any picture in the text offers "Open image
  in viewer"; double-click on a picture opens it too. Viewer keys: 0 fit, 1 100%, wheel zoom
  (2%-4000%), drag to pan, Ctrl+S save original, Ctrl+C copy, F11 fullscreen, Esc (leave
  fullscreen, then close). It closes when another book is opened or the app quits.
- Search (find_bar.py): incremental, Enter / Shift+Enter, F3 / Shift+F3, wraps around, match
  case, starts from what is on screen, the hit is placed about a third down
  (ReaderView.reveal_cursor). A failed search restores the previous selection. One search
  session adds one Back entry (the position before the first hit).
- Back/Forward: ReaderView keeps lists of character offsets, only when history_enabled (the
  main window turns it on; the link window doesn't). remember_position() is called right
  before a jump: go_to_anchor (contents tree, links), jump_to_position (bookmarks), first
  search hit. A jump that lands on the same spot is undone (the tree fires clicked AND
  activated). Limit 50, cleared in set_book. Alt+Left / Alt+Right and mouse side buttons.
- Bookmarks: per book in QSettings key bookmarks/<md5 of the path> (same hash as the reading
  position), JSON list of {pos, label}, pos = character offset. Bookmarks menu: Ctrl+D adds,
  entries jump, "Remove bookmark" submenu.
- Progress: status bar label "<section>  ·  <percent>%". Percent = character offset of the top
  line / book length (100 when scrolled to the end). The section comes from the contents
  entries, located once per opened book with ReaderView.anchor_positions().
- Contents tree follows reading: while scrolling, the entry of the current section is selected,
  its parents are expanded and the tree scrolls to it. Side effect (accepted for now): the tree
  gradually opens up as I read nested contents. Possible alternative if it annoys me: only
  scroll to the item without expanding.
- Settings are in the Windows registry (QSettings, org/app "EbooksReader"): colors, custom
  themes, typography, window layout, last book, update-check preference, per-book reading
  position and bookmarks (character offsets).
- Reading position is restored with repeated scroll ticks while the layout settles.
- Updates: Help > Check for updates only notifies and opens the release page (also checked 3 s
  after startup unless turned off). No auto-install.

## Known quirks (don't re-discover these)
- Qt ignores explicit font sizes inside real <h1>-<h6> blocks (CSS, spans and direct char
  formats all fail). Fix in use: _prepared_html() converts headings to styled <p> elements
  with sizes from HEADING_LEVELS in reader_view.py. Using <div> merges following bare text
  into the title line, so it must be <p>.
- Qt's HTML subset is limited; SVG is removed by the loader, so SVG-wrapped images (often the
  cover) don't show.
- The whole book is one Qt document in the main window, so image-heavy books open slowly
  (about 2 s for my art book). The loader itself takes 0.18 s.
- setHtml() fires a resize event while the new layout is unfinished, and the position
  remembered then is the END of the book (the view jumped there 150 ms later).
  set_book/apply_typography call _forget_resize_position() afterwards. The resize restore
  only runs for WIDTH changes: a height-only change (find bar, status bar) must not restore,
  because it would clear the search selection and undo the scroll to the hit.
- Qt doesn't keep an empty anchor as a text fragment; it sits in the block's
  charFormat. anchor_positions() checks both, like QTextBrowser.scrollToAnchor does.
- Image-link detection in epub.py is a heuristic (_has_image, _image_above): an element with an
  id directly under a short image block counts as that image's caption, so a footnote
  paragraph right below a picture would open the image. If a book breaks it, ask me for the
  HTML around the problem.
- QAbstractTextDocumentLayout.imageAt() works for hit-testing pictures in the text (used for
  double-click and right-click); the name it returns is the epub:///path URL.
- Delayed calls on a window must use QTimer.singleShot(ms, self, fn) (with a context object);
  a plain lambda raises "QTimer already deleted" if the window was closed first.
- Tree selection in code must keep the tree's signals blocked, otherwise itemClicked/itemActivated
  would call `_goto` and make the view jump while I read.
- Character offsets (position, bookmarks, section starts) are tied to how the loader converts a
  book. Changing the loader or the document structure (e.g. chapter-based loading) shifts them.
- uv.lock can show an older project version than pyproject.toml (it showed 0.2.3 while the
  project was 0.3.0). release.sh does not commit uv.lock and refuses to run with uncommitted
  changes, so commit uv.lock first if `uv sync`/`uv run` changed it.
- pyproject depends on `pyside6`, which pulls in WebEngine and PDF modules the app doesn't use
  (big builds). `pyside6-essentials` is enough for the current code.
- Docs mismatch: README says h3 is 1.2x and h4 is 1.3x, matching HEADING_LEVELS. h4 being larger
  than h3 is probably a typo; ask me before changing it (and update the README table with it).
- Leftover debug code: _apply_headings, _heading_css, EBR_DEBUG prints in reader_view.py and the
  EBR_FRESH switch in app.py. Check that nothing depends on them before deleting.

## Build and release
- Build: `bash build.sh` (PyInstaller one-folder, dist/EbooksReader/EbooksReader.exe).
  Unsigned exe: Windows SmartScreen may warn.
- Release: commit changes, then `bash release.sh X.Y.Z`. It sets the version in version.py and
  pyproject.toml, commits, tags vX.Y.Z and pushes. GitHub Actions (.github/workflows/release.yml)
  builds on Windows and attaches the zip to a release; it fails if the tag does not match
  version.py. The repo must stay public for the update check.
- Version numbers: patch (0.x.Y) for small fixes, minor (0.X.0) for new features. Before 1.0
  this is loose.

---

## Road to 1.0.0

Goal of 1.0.0: "I'm comfortable giving this to a stranger". Tasks are in priority order; do them
top to bottom unless a dependency says otherwise. Tick the box when done and commit this file.

### Phase 1: Ship what exists, add notes, clean up
- [ ] **1. Verify and release the contents-tree follow feature.** Test on real books: the tree
  follows scrolling, a click on an entry stays on that entry (if it flips to the previous one,
  raise `SECTION_LOOKAHEAD`), nested contents behave acceptably. Commit `uv.lock`, then
  `bash release.sh 0.4.0`.
- [ ] **2. Notes per chapter and part.** I read a chapter and want to keep my main thoughts, so I
  write notes for each chapter or part and see all of them in a separate window.
  Wanted result in the notes window (one book at a time):
  ```
  Chapter #
    Part #
      some notes
    Part #
      some notes
  Chapter #
    ...
  ```
  Planned design (ask me before deviating):
  - **Structure:** follows the contents tree (`TocEntry`): every contents entry can hold one note,
    nested entries appear as nested parts. Entries without notes can be hidden or shown greyed
    (a toggle in the window).
  - **Window:** `ui/notes_window.py`, a separate non-modal `QMainWindow` like ImageViewer (one
    instance reused, closes when another book opens, follows the color theme through
    `apply_colors`). Left: tree of chapters and parts; right: a plain-text editor for the selected
    entry. Edits autosave after a short pause, and on close.
  - **Opening it:** new `Notes` menu: "Show notes..." (Ctrl+Shift+N?) and "Add note for current
    section" (Ctrl+N?), which opens the window on the section at the top of the page
    (`_section_index(current_position())`; reuse the contents-tree logic). Clicking a note's
    title in the window jumps the main reader to that section (`go_to_anchor`, so Back works).
    A small marker in the contents tree for entries that have a note is a nice extra.
  - **Storage:** key notes by the contents entry's anchor key (`TocEntry.key`, e.g. `c3_part2`) plus
    a snapshot of its title, NOT by character offset, so notes survive loader and layout changes.
    Per book, under the same md5-of-path hash as positions and bookmarks (`notes/<hash>`),
    JSON like `{key: {"title": ..., "text": ...}}`. Open question for me: QSettings (registry) is
    fine for small notes, but long notes may be better in a JSON file in the user data folder
    (`QStandardPaths.AppDataLocation`); decide together with task 7 (saved-data stability), and
    include notes in its schema version and migration.
  - **Extras, only if cheap:** search inside notes, "Copy all notes" / export to Markdown or TXT
    (chapter and part headings followed by the text), and a note count in the window title.
  - **Keep in mind:** notes must not break Back/Forward, search or progress; a book whose contents
    are missing or flat (fallback "Section N" entries) still needs to work; add pytest cases for
    the notes load/save helpers (a small `ui/notes.py` like `bookmarks.py`, no Qt widgets in it).
- [ ] **3. Cleanup.** Remove debug code (EBR_DEBUG, EBR_FRESH, and `_apply_headings` /
  `_heading_css` if redundant). Resolve the h4/h3 size order (ask me). Switch the dependency to
  `pyside6-essentials` and check the build still works and is smaller. Add a LICENSE (MIT?) and
  a real description in `pyproject.toml`. Update the README (contents tree follows reading).

### Phase 2: Trust and stability (must have for 1.0)
- [ ] **4. Tests and CI.** pytest for `parse_version`, `export_theme`/`import_theme`,
  `load_custom` with bad data, registry lookup (`.fb2.zip` style extensions), and the epub
  anchor/image detection (synthetic EPUB made with ebooklib as a fixture). Add ruff. Run both in
  `release.yml` before the build, so a broken release can't be published.
- [ ] **5. Error handling on open.** Check a corrupted EPUB, a DRM-protected one, an empty file,
  a wrong extension, and a book moved or deleted since last time (reopen at startup must not
  crash). Show clear messages, never a traceback.
- [ ] **6. SVG-wrapped images and covers.** Many EPUBs wrap the cover in `<svg><image>`; today the
  loader deletes all SVG so the cover is empty. Convert `<svg><image xlink:href>` to a normal
  `<img>` and register the image as a resource.
- [ ] **7. Saved-data stability (do BEFORE task 8).** Positions and bookmarks are character
  offsets keyed by the md5 of the file path: moving a file loses them and a loader change
  shifts them. Add a settings schema version with a migration step, and store a sturdier anchor
  (chapter index plus offset, or nearest anchor name). Consider keying books by content hash or
  by EPUB identifier instead of the path.
- [ ] **8. Large-book performance.** The whole book is one Qt document (about 2 s for the art
  book). Options: chapter-based loading in the main window, or `QWebEngineView` (the loader and
  settings stay). Needs task 7 first because it changes how offsets work. Keep search, progress
  percent, bookmarks, Back/Forward and the contents tree working.

### Phase 3: Reading experience people expect
- [ ] **9. Drag-and-drop a file onto the window to open it, and a "Recent books" submenu in File.**
- [ ] **10. Space / Shift+Space / Page Down / Page Up paging.**
- [ ] **11. Fullscreen reading mode (F11),** like the image viewer; hide menu, status bar and
  contents; Esc leaves.
- [ ] **12. Match counter in search** ("3 of 27") without making typing laggy on big books.
- [ ] **13. FB2 loader** (`.fb2`, `.fb2.zip`), proves the registry design. Produce HTML with
  `c<chapter>_<id>` anchors and fill `LoadedBook.chapters`.
- [ ] **14. TXT loader** (simple; ask me about encoding detection and chapter splitting).

### Phase 4: Distribution and release readiness
- [ ] **15. Installer.** Inno Setup installer with an "Update now" button (silent update), so no
  manual zip replacement. If it is too much for 1.0, state clearly in the README that the exe is
  unsigned and how to get past SmartScreen.
- [ ] **16. Final documentation pass.** README features, usage table, project structure,
  known limitations; update this file's architecture and quirks.
- [ ] **17. Release candidate.** Use the app on my real books for a while (long books, art books,
  nested contents, several formats), fix what turns up, then `bash release.sh 1.0.0`.

### Not for 1.0 (after the release)
- PDF support (needs QtPdf and a different viewer).
- A back button in the link window.
- Highlighting is done; a possible refinement is a setting to switch tree auto-expand off.
- Replacing `QTextBrowser` with `QWebEngineView` only if chapter-based loading (task 8) is not
  fast enough.
- Real auto-install of updates (beyond the installer's "Update now").