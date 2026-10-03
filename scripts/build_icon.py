"""Render the source vector icon for the Windows executable and installer."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PIL import Image


def build_icon(root):
    root = Path(root)
    output = root / 'build' / 'icons'
    output.mkdir(parents=True, exist_ok=True)
    renderer = QSvgRenderer(str(root / 'thsr_ticket/desktop/assets/app.svg'))
    image = QImage(256, 256, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    image.save(str(output / 'app.png'))
    with Image.open(output / 'app.png') as raster:
        raster.save(output / 'app.ico', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return str(output / 'app.ico')


if __name__ == '__main__':
    build_icon(Path(__file__).resolve().parents[1])
