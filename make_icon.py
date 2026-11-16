from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

res = Path("src/ebooks_reader/resources")
app = QGuiApplication([])

img = QImage(256, 256, QImage.Format.Format_ARGB32)
img.fill(Qt.GlobalColor.transparent)
painter = QPainter(img)
painter.setRenderHint(QPainter.RenderHint.Antialiasing)
QSvgRenderer(str(res / "icon.svg")).render(painter)
painter.end()

png = res / "_icon_tmp.png"
img.save(str(png))
Image.open(png).save(
    res / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
)
png.unlink()
print("created", res / "icon.ico")
