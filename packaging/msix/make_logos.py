"""Writes the PNG logos MSIX needs from the LTH logo (lth_overlays/data/brand/lth-icon-256.png)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

out = sys.argv[1]
src_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "lth_overlays", "data", "brand", "lth-icon-256.png")
app = QApplication([])
src = QImage(src_path)
if src.isNull():
    raise SystemExit(f"logo not found: {src_path}")
for name, size in (("StoreLogo.png", 50), ("Square150x150Logo.png", 150), ("Square44x44Logo.png", 44),
                   ("Square44x44Logo.targetsize-256_altform-unplated.png", 256)):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    m = 0 if size <= 50 or "targetsize" in name else int(size * 0.12)
    p.drawImage(QRect(m, m, size - 2 * m, size - 2 * m), src)
    p.end()
    img.save(os.path.join(out, name))
print("logos ->", out)
