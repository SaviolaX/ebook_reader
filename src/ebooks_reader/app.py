import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow

ICON_PATH = Path(__file__).parent / "resources" / "icon.ico"
APP_ID = "EbooksReader.App"


def run() -> None:
    # Without this, Windows groups the app under python.exe
    # and shows Python's icon in the taskbar.
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setOrganizationName("EbooksReader")
    import os
    app.setApplicationName(
        "EbooksReaderTest" if os.environ.get("EBR_FRESH") else "EbooksReader"
    )
    app.setWindowIcon(QIcon(str(ICON_PATH)))  # applies to every window

    win = MainWindow()
    win.show()

    # Open the book AFTER the window has been painted once,
    # so you see the window (with your colors) instead of a white screen.
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        target = sys.argv[1]
        QTimer.singleShot(50, lambda: win.open_book(target))
    else:
        QTimer.singleShot(50, win.startup_open)

    QTimer.singleShot(3000, win.startup_update_check)

    sys.exit(app.exec())
