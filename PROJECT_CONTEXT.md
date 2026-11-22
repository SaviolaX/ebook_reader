# Ebooks Reader: context for the assistant

## About the project
Windows desktop e-book reader in Python 3.12, PySide6 (Qt), managed with uv.
Repo: https://github.com/SaviolaX/ebook_reader (public). Only EPUB is supported now; the
structure is meant to allow more formats (FB2, PDF, ...). See README.md for features and layout.

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

## Architecture
- src/ebooks_reader/core/models.py: TocEntry, LoadedBook (title, html, toc, resources,
  image_anchors, chapters).
- core/registry.py: @register(name, extensions) decorator and load_book(path).
- core/updater.py: background update check against GitHub releases.
- formats/epub.py: EPUB loader. It strips book CSS/styles, renames anchors to c<chapter>_<id>,
  rewrites links to #anchors and images to epub:///path, detects image anchors.
- ui/reader_view.py: QTextBrowser subclass (font, margins, line spacing, headings,
  position restore, link handling, image cache).
- ui/viewer_window.py: separate window for opened links; loads only one chapter at a time.
- ui/image_viewer.py: ImageViewer window (QGraphicsView) for one original image taken from
  LoadedBook.resources; one instance is reused for every image.
- ui/find_bar.py: FindBar, the Ctrl+F search bar under the text.
- ui/bookmarks.py: Bookmark (pos, label) and load/save helpers (QSettings, JSON).
- ui/main_window.py: menus, contents tree, saved state, themes, updates.
- ui/themes.py, theme_dialog.py: built-in/custom themes, light/dark groups, share codes "EBR1:...".
- ui/typography.py: text settings dialog.
- version.py: __version__ and GITHUB_REPO.

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
- Settings are in the Windows registry (QSettings, org/app "EbooksReader"): colors, custom
  themes, typography, window layout, last book, per-book reading position (character offset).
- Reading position is restored with repeated scroll ticks while the layout settles.

## Known quirks (don't re-discover these)
- Qt ignores explicit font sizes inside real <h1>-<h6> blocks (CSS, spans and direct char
  formats all fail). Fix in use: _prepared_html() converts headings to styled <p> elements
  with sizes from HEADING_LEVELS in reader_view.py. Using <div> merges following bare text
  into the title line, so it must be <p>.
- Qt's HTML subset is limited; SVG is removed by the loader, so SVG-wrapped images don't show.
- The whole book is one Qt document in the main window, so image-heavy books open slowly
  (about 2 s for my art book). The loader itself takes 0.18 s.
- setHtml() fires a resize event while the new layout is unfinished, and the position
  remembered then is the END of the book (the view jumped there 150 ms later).
  set_book/apply_typography call _forget_resize_position() afterwards. The resize restore
  only runs for WIDTH changes: a height-only change (find bar, status bar) must not restore,
  because it would clear the search selection and undo the scroll to the hit.
- Qt doesn't keep an empty <a name> anchor as a text fragment; it sits in the block's
  charFormat. anchor_positions() checks both, like QTextBrowser.scrollToAnchor does.
- Image-link detection in epub.py is a heuristic (_has_image, _image_above): an element with an
  id directly under a short image block counts as that image's caption, so a footnote
  paragraph right below a picture would open the image. If a book breaks it, ask me for the
  HTML around the problem.
- QAbstractTextDocumentLayout.imageAt() works for hit-testing pictures in the text (used for
  double-click and right-click); the name it returns is the epub:///path URL.
- Delayed calls on a window must use QTimer.singleShot(ms, self, fn) (with a context object);
  a plain lambda raises "QTimer already deleted" if the window was closed first.
- Leftover debug code that could be removed: _apply_headings, _heading_css, EBR_DEBUG prints,
  EBR_FRESH switch in app.py.

## Build and release
- Build: `bash build.sh` (PyInstaller one-folder, dist/EbooksReader/EbooksReader.exe).
- Release: commit changes, then `bash release.sh X.Y.Z`. It sets the version in version.py and
  pyproject.toml, commits, tags vX.Y.Z and pushes. GitHub Actions (.github/workflows/release.yml)
  builds on Windows and attaches the zip to a release; it fails if the tag does not match
  version.py.
- The app's Help > Check for updates only notifies (opens the release page). No auto-install.
  An Inno Setup installer with silent update was planned but postponed.

## Ideas and possible next steps
- FB2/TXT loaders (register in formats/).
- PDF (needs a different viewer, QtPdf).
- Performance: chapter-based loading in the main window, or switch QTextBrowser to
  QWebEngineView (keeps the loader and settings).
- A back button in the link window.
- Reading experience, still to do: recent books submenu (File); Space / Page Down paging and
  drag-and-drop a file onto the window to open it; fullscreen reading mode (F11, like the
  image viewer); highlight the current section in the contents tree; match counter in search.
- Quick fixes: h4 (1.3) is larger than h3 (1.2) in HEADING_LEVELS, probably a typo (ask me
  first); depend on pyside6-essentials instead of pyside6 to shrink the build; remove the
  debug code; real description/author in pyproject.toml; add a LICENSE.
- Tests: pytest for parse_version, import/export_theme and the epub anchor detection (a
  synthetic EPUB made with ebooklib works as a fixture); ruff in CI.
- Installer with an "Update now" button.
- Remove leftover debug code; add a license (MIT?).
