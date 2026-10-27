"""Writes the PNG logos MSIX needs (gold L on black)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

out = sys.argv[1]
app = QApplication([])
for name, size in (("StoreLogo.png", 50), ("Square150x150Logo.png", 150), ("Square44x44Logo.png", 44)):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = size / 64
    p.setBrush(QColor(14, 14, 16))
    p.setPen(QColor(226, 177, 60))
    p.drawRoundedRect(int(2 * r), int(2 * r), int(60 * r), int(60 * r), 12 * r, 12 * r)
    f = QFont()
    f.setPixelSize(int(40 * r))
    f.setBold(True)
    p.setFont(f)
    p.drawText(img.rect(), Qt.AlignmentFlag.AlignCenter, "L")
    p.end()
    img.save(os.path.join(out, name))
