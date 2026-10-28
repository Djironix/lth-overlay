"""Šalių vėliavos (flag-icons, MIT) iš vieno sprite failo."""
from __future__ import annotations

import json
import os

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

_DIR = os.path.join(os.path.dirname(__file__), "data", "flags")
_sprite = None
_index = None
_cache = {}


def _load():
    global _sprite, _index
    if _index is None:
        try:
            with open(os.path.join(_DIR, "flags.json"), encoding="utf-8") as fh:
                _index = json.load(fh)
            _sprite = QPixmap(os.path.join(_DIR, "flags.png"))
        except (OSError, ValueError):
            _index, _sprite = {"codes": {}}, QPixmap()


def flag_pixmap(code: str) -> QPixmap | None:
    """Vėliava 48×36 px (arba None, jei šalies nėra)."""
    if not code:
        return None
    pm = _cache.get(code)
    if pm is None and code not in _cache:
        _load()
        i = _index.get("codes", {}).get(code)
        if i is None or _sprite.isNull():
            _cache[code] = None
            return None
        w, h, cols = _index["w"], _index["h"], _index["cols"]
        pm = _sprite.copy((i % cols) * w, (i // cols) * h, w, h)
        _cache[code] = pm
    return pm


def draw_flag(p: QPainter, rect: QRectF, code: str, radius: float = 2.0) -> bool:
    """Vėliava per rect vidurį (4:3), su ploniu kontūru - kad balta vėliava matytųsi ant šviesaus fono."""
    pm = flag_pixmap(code)
    if pm is None:
        return False
    h = min(rect.height(), rect.width() * 0.75)
    w = h * 4 / 3
    r = QRectF(rect.x() + (rect.width() - w) / 2, rect.y() + (rect.height() - h) / 2, w, h)
    p.save()
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    from PySide6.QtGui import QPainterPath
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    p.setClipPath(path)
    p.drawPixmap(r, pm, QRectF(pm.rect()))
    p.setClipping(False)
    p.setPen(QPen(QColor(0, 0, 0, 90), 0.8))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(r, radius, radius)
    p.restore()
    return True
