"""Book covers kept as small PNG files in AppDataLocation/covers.

Two kinds per book: "auto" (taken from the book when it is opened) and "custom"
(chosen by the user, always wins). Files are named by the same md5 as positions.
"""

from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtGui import QImage, QPixmap

from .recent import book_id

MAX_W, MAX_H = 300, 420


def covers_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    return Path(base) / "covers"


def _file(path: str, kind: str) -> Path:
    return covers_dir() / f"{book_id(path)}.{kind}.png"


def _store(img: QImage, dest: Path) -> bool:
    if img.isNull():
        return False
    if img.width() > MAX_W or img.height() > MAX_H:
        img = img.scaled(
            MAX_W,
            MAX_H,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    return img.save(str(dest), "PNG")


def save_auto_cover(path: str, data: bytes) -> bool:
    dest = _file(path, "auto")
    if dest.exists():
        return True
    return _store(QImage.fromData(data), dest)


def set_custom_cover(path: str, image_file: str) -> bool:
    return _store(QImage(image_file), _file(path, "custom"))


def remove_custom_cover(path: str) -> None:
    try:
        _file(path, "custom").unlink()
    except FileNotFoundError:
        pass


def has_custom_cover(path: str) -> bool:
    return _file(path, "custom").exists()


def load_cover(path: str) -> QPixmap | None:
    for kind in ("custom", "auto"):
        f = _file(path, kind)
        if f.exists():
            pm = QPixmap(str(f))
            if not pm.isNull():
                return pm
    return None
