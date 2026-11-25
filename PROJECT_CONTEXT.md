# Ebooks Reader: context for the assistant

Features, usage, structure, build and release: see README.md. This file only holds working
rules, the reasons behind design decisions, quirks, and the roadmap.

Windows desktop e-book reader, Python 3.12, PySide6 (Qt), uv. Repo (public, the update check
needs that): https://github.com/SaviolaX/ebook_reader. EPUB, FB2 and PDF (FB2 and PDF: code done, checks on real books pending).
Released: 0.3.1. Next release number is the owner's choice (0.4.0 suggested). Goal: 1.0.0.

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
- When a feature changes, update README.md in the same step. Keep this file short: no
  feature lists that the README already has.

## Design decisions (and why)
- Internal links open in a separate, reused window so I keep my place in the main text.
  Ctrl+click opens a new window. Image links open the ImageViewer instead.
- Back/Forward: ReaderView keeps character offsets, only when `history_enabled` (main window
  only). `remember_position()` is called right BEFORE a jump (anchors, bookmarks, first search
  hit). A jump that lands on the same spot is undone, because the tree fires clicked AND
  activated. One search session adds one Back entry.
- Search starts from what is on screen. A failed search restores the previous selection.
- Contents tree follows reading: `_select_section` runs from `_update_progress` (120 ms after
  scrolling stops), with the tree's signals blocked so it never calls `_goto`.
  `_section_index(pos) = bisect_right(starts, pos + SECTION_LOOKAHEAD) - 1`; the lookahead
  (10 chars) exists because a click on an entry can leave the top line slightly before the
  anchor. `open_book` must build the tree BEFORE `_index_sections` (it needs the items).
  Accepted side effect: the tree gradually expands as I read nested contents.
  `_section_entries` is parallel to `_section_starts`; it lets "Add note here" map a
  position to a TocEntry.
- Notes are keyed by contents entry (`TocEntry.key`), NOT by character offset, so they
  survive loader and layout changes. Keys are not unique (a parent without its own link
  borrows its first child's key), so `flatten()` gives repeated keys `~2`, `~3`, ... in
  contents order. Entries without a key can't hold a note. This relies on the loader
  producing the same contents order: cover it in task 7.
- Notes live in one JSON file per book (`AppDataLocation/notes/<md5 of path>.json`,
  `{"version": 1, "notes": {id: {title, text}}}`), not in the registry: long text I care
  about, easy to back up and migrate. Written atomically (temp file + rename). A damaged
  file is renamed `.json.bad` and notes start empty. Blank text deletes a note. Orphaned
  notes stay in the file and show as "Unattached notes" in the export.
- `ui/notes.py` has no Qt widgets so it can be tested alone; the window is `notes_window.py`.
- Settings are in the Windows registry (QSettings, "EbooksReader"): colors, custom themes,
  typography, window layout, last book, update preference, per-book position and bookmarks.
  Positions, bookmarks and notes are tied to the md5 of the file path.
- Reading position is restored with repeated scroll ticks while the layout settles.
- Startup: `app.Controller` owns the launcher (`ui/launcher.py`, cards) and creates the
  MainWindow only when a book is chosen. A file argument, or `show_start` off, skips the
  launcher. This replaced `reopen_last`. A failed open hides the reader and shows the
  launcher again. Covers: loaders fill `LoadedBook.cover`; `open_book` saves it to
  `AppDataLocation/covers/<md5>.auto.png`; a user cover is `<md5>.custom.png` and wins.
  Titles for the cards are cached in settings (`titles/<md5>`).
  Recent books are a JSON list of absolute paths in `recent_books` (max 10, `ui/recent.py`);
  a book is added only after it opened successfully. Missing files are shown greyed out in
  the dialog and hidden in the File menu, but stay in the list (external drives).
- Updates only notify and open the release page. No auto-install.
- FB2 (`formats/fb2.py`, stdlib `xml.etree` only, namespaces ignored): chapter 0 = title page,
  then one chapter per top-level section of the main body; a body with a `name` (notes) is one
  chapter, so footnote links open the notes list. Sections without an id get generated anchors
  (`c<n>___sec<k>`, deterministic by order) so they can hold notes. Contents: book title,
  titled sections, then the notes body. Untitled sections add no entry; a book with no titled
  sections falls back to "Section N". Headings: top-level section = h2, h1 = book title.
- PDF (`formats/pdf.py` loader, `ui/pdf_view.py` viewer; QtPdf renders the pages): the book has
  no HTML, only `pdf_path`. MainWindow keeps two views in a QStackedWidget and `self.reader`
  points at the one showing now (`is_pdf`). The viewer is our own QAbstractScrollArea, not
  QPdfView, because every page is recolored (white -> background, black -> text color;
  "original colors" turns it off). A position is one int, `page * 100000 + fraction of the
  page`, so bookmarks, Back/Forward and the saved position work unchanged. Anchor keys are
  `p<page>`; outline entries land on the top of the page (their y-offsets are ignored). No
  outline: "Page N" entries, grouped by 10 or 50 for long books. Text settings are disabled
  for PDF; Ctrl+= / Ctrl+- zoom. Step 2 still open: search in PDF, tests, notes checks on PDF.

## Known quirks (don't re-discover these)
- Qt ignores explicit font sizes inside real <h1>-<h6> blocks. Fix in use: `_prepared_html()`
  turns headings into styled <p> using HEADING_LEVELS in reader_view.py. <div> doesn't work
  (it merges following bare text into the title line).
- Qt's HTML subset is limited; the loader removes SVG, so SVG-wrapped images (often the
  cover) don't show (task 6).
- The whole book is one Qt document, so image-heavy books open slowly (about 2 s for my art
  book; the loader takes 0.18 s).
- setHtml() fires a resize event while the new layout is unfinished, and the position
  remembered then is the END of the book. set_book/apply_typography call
  `_forget_resize_position()`. The resize restore only runs for WIDTH changes: a height-only
  change (find bar, status bar) must not restore, or it would clear the search selection.
- Qt doesn't keep an empty anchor as a text fragment; it sits in the block's charFormat.
  `anchor_positions()` checks both, like QTextBrowser.scrollToAnchor.
- Image-link detection in epub.py is a heuristic (`_has_image`, `_image_above`): an element
  with an id directly under a short image block counts as that image's caption, so a footnote
  paragraph right below a picture would open the image. If a book breaks it, ask for the HTML.
- `QAbstractTextDocumentLayout.imageAt()` hit-tests pictures; the name it returns is the
  epub:///path URL.
- Delayed calls on a window must use `QTimer.singleShot(ms, self, fn)` (with a context
  object); a plain lambda raises "QTimer already deleted" if the window closed first.
- Tree selection in code must keep the tree's signals blocked, or itemClicked/itemActivated
  call `_goto` and the view jumps while I read.
- Character offsets (position, bookmarks, section starts) depend on how the loader converts a
  book; changing the loader or the document structure shifts them.
- uv.lock can show an older project version than pyproject.toml. `release.sh` doesn't commit
  uv.lock and refuses to run with uncommitted changes, so commit uv.lock first.
- pyproject depends on `pyside6`, which pulls in WebEngine (unused, big builds). The app now
  uses QtPdf for PDF books, which `pyside6-essentials` does not have: when slimming the
  dependencies (task 3) keep QtPdf (`pyside6-pdf`, a separate package in uv.lock).
- README and HEADING_LEVELS agree that h4 (1.3x) is larger than h3 (1.2x); probably a typo.
  Ask me before changing it, and update the README table with it.
- Leftover debug code: `_apply_headings`, `_heading_css`, EBR_DEBUG prints in reader_view.py
  and the EBR_FRESH switch in app.py (EBR_FRESH is handy for testing with a throwaway
  settings profile; ask before removing). Check that nothing depends on them.

---

## Road to 1.0.0

Goal: "I'm comfortable giving this to a stranger". Do tasks top to bottom unless a dependency
says otherwise. Tick the box when done and commit this file.

### Phase 1: Ship what exists, add notes, clean up
- [x] **1. Contents-tree follow feature.** Verified and released as 0.3.1.
- [x] **2. Notes per chapter and part.** Code and README are committed (`notes.py` + pytest,
  `notes_window.py` + Notes menu + tree markers). Pending: checks on real books. Ctrl+N lands
  on the current section; greyed/selected entries stay readable in every theme; flat
  ("Section N") contents and entries without a link behave; nothing is lost when switching
  entries quickly or closing; notes survive reopening the book. Open ideas, only if wanted:
  search inside notes; jump on double-click instead of every click.
- [ ] **3. Cleanup.** Remove debug code (EBR_DEBUG, EBR_FRESH, and `_apply_headings` /
  `_heading_css` if redundant). Resolve the h4/h3 size order (ask me). Switch the dependency
  to `pyside6-essentials` and check the build still works and is smaller. Add a LICENSE
  (MIT?) and a real description in `pyproject.toml`.

### Phase 2: Trust and stability (must have for 1.0)
- [ ] **4. Tests and CI.** pytest is set up (notes tests exist). Add tests for
  `parse_version`, `export_theme`/`import_theme`, `load_custom` with bad data, registry lookup
  (`.fb2.zip` style extensions), and the epub anchor/image detection (synthetic EPUB made
  with ebooklib as a fixture). Add ruff. Run both in `release.yml` before the build, so a
  broken release can't be published.
- [ ] **5. Error handling on open.** Corrupted EPUB, DRM-protected one, empty file, wrong
  extension, a book moved or deleted since last time (reopen at startup must not crash). Clear
  messages, never a traceback.
- [ ] **6. SVG-wrapped images and covers.** Convert `<svg><image xlink:href>` to a normal
  `<img>` and register the image as a resource, instead of deleting all SVG.
- [ ] **7. Saved-data stability (do BEFORE task 8).** Positions and bookmarks are character
  offsets keyed by the md5 of the file path: moving a file loses them (and its notes), and a
  loader change shifts offsets. Add a settings schema version with a migration step (notes
  files already carry `"version": 1`) and a sturdier anchor (chapter index plus offset, or
  nearest anchor name). Consider keying books by content hash or EPUB identifier instead of
  the path. Make sure note ids (`~2` suffixes) stay stable.
- [ ] **8. Large-book performance.** Options: chapter-based loading in the main window, or
  `QWebEngineView` (loader and settings stay). Needs task 7 first because it changes how
  offsets work. Keep search, progress percent, bookmarks, Back/Forward, the contents tree and
  notes working.

### Phase 3: Reading experience people expect
- [ ] **9. Drag-and-drop a file onto the window to open it.** (Start window and "Recent books"
  submenu: done, pending checks on Windows.)
- [ ] **10. Space / Shift+Space / Page Down / Page Up paging.**
- [ ] **11. Fullscreen reading mode (F11),** like the image viewer; hide menu, status bar and
  contents; Esc leaves.
- [ ] **12. Match counter in search** ("3 of 27") without making typing laggy on big books.
- [x] **13. FB2 loader** (`.fb2`, `.fb2.zip`), proves the registry design. HTML with
  `c<chapter>_<id>` anchors, fill `LoadedBook.chapters`.
- [ ] **14. TXT loader** (ask me about encoding detection and chapter splitting).
- [ ] **14b. PDF support.** Step 1 (viewing: open, zoom, colors, contents, positions,
  bookmarks, Back/Forward, cover) is committed, pending checks on real PDFs on Windows and in
  the PyInstaller build. Step 2: search in PDF, tests (loader, position math), notes checks
  on PDF, drag-and-drop.

### Phase 4: Distribution and release readiness
- [ ] **15. Installer.** Inno Setup with an "Update now" button (silent update). If too much
  for 1.0, say clearly in the README that the exe is unsigned and how to get past SmartScreen.
- [ ] **16. Final documentation pass.** README features, usage, structure, limitations;
  trim this file.
- [ ] **17. Release candidate.** Use the app on my real books for a while (long books, art
  books, nested contents, several formats), fix what turns up, then `bash release.sh 1.0.0`.

### Not for 1.0 (after the release)
- A back button in the link window.
- A setting to switch tree auto-expand off.
- `QTextBrowser` -> `QWebEngineView` only if chapter-based loading (task 8) isn't fast enough.
- Real auto-install of updates (beyond the installer's "Update now").
