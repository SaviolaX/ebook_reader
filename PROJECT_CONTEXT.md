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
- Bookmarks, search, a back button in the link window.
- Installer with an "Update now" button.
- Remove leftover debug code; add a license (MIT?).
