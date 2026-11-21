from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QGuiApplication, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QMainWindow,
    QMessageBox,
)


class _View(QGraphicsView):
    zoomed = Signal()

    def wheelEvent(self, event):
        dy = event.angleDelta().y()
        if dy == 0:
            return
        step = 1.15 if dy > 0 else 1 / 1.15
        new = self.transform().m11() * step
        if (step < 1 and new < 0.02) or (step > 1 and new > 40):
            return
        self.scale(step, step)
        self.zoomed.emit()


class ImageViewer(QMainWindow):
    """Shows one original (unscaled) image from the book."""

    closed = Signal(object)

    def __init__(self, colors):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        avail = QGuiApplication.primaryScreen().availableGeometry()
        self.resize(min(1200, avail.width() - 80), min(850, avail.height() - 80))

        self._img = QImage()
        self._data = b""
        self._name = ""
        self._item = None
        self._fit = True

        self.scene = QGraphicsScene(self)
        self.view = _View(self.scene)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.view.zoomed.connect(self._manual_zoom)
        self.setCentralWidget(self.view)

        def add(text, shortcut, fn):
            a = QAction(text, self)
            a.setShortcut(shortcut)
            a.triggered.connect(fn)
            self.view.addAction(a)

        add("Fit to window", "0", self.fit)
        add("Actual size (100%)", "1", self.actual_size)
        add("Save image as...", "Ctrl+S", self.save_as)
        add("Copy image", "Ctrl+C", self.copy)
        add("Fullscreen", "F11", self.toggle_fullscreen)
        add("Close", "Esc", self._escape)

        self.apply_colors(*colors)

    def apply_colors(self, bg: str, fg: str) -> None:
        self.view.setBackgroundBrush(QColor(bg))

    def show_image(self, name: str, data: bytes) -> bool:
        img = QImage.fromData(data)
        if img.isNull():
            return False
        self._img, self._data, self._name = img, data, name
        self.scene.clear()
        self._item = self.scene.addPixmap(QPixmap.fromImage(img))
        self.scene.setSceneRect(self._item.boundingRect())
        self.setWindowTitle(f"{Path(name).name} ({img.width()}x{img.height()})")
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.fit()
        self.raise_()
        self.activateWindow()
        return True

    # ---------- zoom ----------
    def fit(self):
        self._fit = True
        if self._item is None:
            return
        self.view.resetTransform()
        self.view.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)
        if self.view.transform().m11() > 1:  # don't enlarge small images
            self.view.resetTransform()

    def actual_size(self):
        self._fit = False
        self.view.resetTransform()

    def _manual_zoom(self):
        self._fit = False

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _escape(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.close()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit:
            self.fit()

    # ---------- actions ----------
    def save_as(self):
        suffix = Path(self._name).suffix or ".png"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save image", Path(self._name).name, f"Image (*{suffix});;All files (*)"
        )
        if path:
            try:
                Path(path).write_bytes(self._data)
            except OSError as e:
                QMessageBox.warning(self, "Save image", str(e))

    def copy(self):
        QApplication.clipboard().setImage(self._img)

    def closeEvent(self, event):
        self.closed.emit(self)
        super().closeEvent(event)
