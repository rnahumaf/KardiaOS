from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QImage, QPainter
from PySide6.QtCore import Qt
from PIL import Image
root = Path(__file__).resolve().parents[1]
app = QApplication([])
image = QImage(256, 256, QImage.Format.Format_ARGB32)
image.fill(Qt.GlobalColor.transparent)
painter = QPainter(image)
QSvgRenderer(str(root / 'src/kardiaos/assets/app.svg')).render(painter)
painter.end()
(root / 'build').mkdir(exist_ok=True)
image.save(str(root / 'build/app.png'))
Image.open(root / 'build/app.png').save(root / 'build/app.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
