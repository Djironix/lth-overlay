"""LTH prekės ženklas: logotipas ir programos ikona (tray, langai)."""
from __future__ import annotations

import os

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

BRAND_DIR = os.path.join(os.path.dirname(__file__), "data", "brand")
LOGO_PATH = os.path.join(BRAND_DIR, "lth-logo.png")

# Spalvos iš logotipo gradiento
GOLD_LIGHT = "#FBD069"
GOLD = "#ECBE58"
GOLD_DARK = "#D1A03A"

_logo = None
_icon = None


def logo() -> QPixmap:
    global _logo
    if _logo is None:
        _logo = QPixmap(LOGO_PATH) if os.path.exists(LOGO_PATH) else QPixmap()
    return _logo


def logo_pixmap(height: int, dpr: float = 2.0) -> QPixmap:
    src = logo()
    if src.isNull():
        return QPixmap()
    h = int(round(height * dpr))
    pm = src.scaledToHeight(h, Qt.TransformationMode.SmoothTransformation)
    pm.setDevicePixelRatio(dpr)
    return pm


def _tile(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(16, 16, 20))
    r = max(2.0, size / 5)
    p.drawRoundedRect(QRectF(0, 0, size, size), r, r)
    src = logo()
    if not src.isNull():
        pad = max(1.0, size * 0.1)
        w = size - 2 * pad
        h = w * src.height() / src.width()
        p.drawPixmap(QRectF(pad, (size - h) / 2, w, h), src, QRectF(src.rect()))
    else:
        from PySide6.QtGui import QFont
        f = QFont()
        f.setPixelSize(int(size * 0.62))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(GOLD))
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "L")
    p.end()
    return pm


def app_icon() -> QIcon:
    global _icon
    if _icon is None:
        _icon = QIcon()
        for s in (16, 20, 24, 32, 40, 48, 64, 128, 256):
            _icon.addPixmap(_tile(s))
    return _icon
