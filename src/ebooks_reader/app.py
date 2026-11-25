import os
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .ui.launcher import LauncherWindow
from .ui.main_window import MainWindow

ICON_PATH = Path(__file__).parent / "resources" / "icon.ico"
APP_ID = "EbooksReader.App"


class Controller:
    """Owns the launcher and the reader window. The reader is created on first use."""

    def __init__(self) -> None:
        self.settings = QSettings()
        self.win: MainWindow | None = None
        self.launcher: LauncherWindow | None = None

    def main_window(self) -> MainWindow:
        if self.win is None:
            self.win = MainWindow()
            self.win.on_show_launcher = self.show_launcher
            QTimer.singleShot(3000, self.win, self.win.startup_update_check)
        return self.win

    def show_launcher(self) -> None:
        if self.launcher is None:
            self.launcher = LauncherWindow(self.settings)
            self.launcher.bookChosen.connect(self.open_book)
        self.launcher.refresh()
        self.launcher.show()
        self.launcher.raise_()
        self.launcher.activateWindow()

    def open_book(self, path: str) -> None:
        win = self.main_window()
        had_book = win.current_path is not None
        win.show()
        win.raise_()
        win.activateWindow()
        if self.launcher is not None:
            self.launcher.hide()

        def go() -> None:
            # open AFTER the window was painted once (colors, layout)
            win.open_book(path)
            if not had_book and win.current_path is None:
                win.hide()  # opening failed: back to the launcher
                self.show_launcher()

        QTimer.singleShot(50, win, go)

    def start(self, argv: list[str]) -> None:
        if len(argv) > 1 and Path(argv[1]).is_file():
            self.open_book(argv[1])
            return
        last = str(self.settings.value("last_book", ""))
        show_start = self.settings.value("show_start", True, type=bool)
        if not show_start and last and Path(last).is_file():
            self.open_book(last)
            return
        self.show_launcher()


def run() -> None:
    # Without this, Windows groups the app under python.exe
    # and shows Python's icon in the taskbar.
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setOrganizationName("EbooksReader")
    app.setApplicationName(
        "EbooksReaderTest" if os.environ.get("EBR_FRESH") else "EbooksReader"
    )
    app.setWindowIcon(QIcon(str(ICON_PATH)))  # applies to every window

    controller = Controller()
    controller.start(sys.argv)

    sys.exit(app.exec())
