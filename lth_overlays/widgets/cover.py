"""Garage cover: uždengia ekrano dalį (pvz. setup'ą), kai esi garaže - streameriams."""
from __future__ import annotations

import os

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap

from ..window import OverlayWidget


class GarageCoverWidget(OverlayWidget):
    NAME = "garage_cover"
    TITLE = "Garage cover"
    HEIGHT_MODE = "free"
    MIN_WIDTH = 120
    MIN_HEIGHT = 80

    def __init__(self, ctx):
        self._img = (None, None)  # (kelias, QPixmap)
        self._view = None
        super().__init__(ctx)

    def wants_visible(self, snap) -> bool:
        if not super().wants_visible(snap):
            return False
        if self.editing or snap is None:
            return True
        return bool(snap.in_garage and not snap.watching)

    def content_key(self, snap):
        c = self.cfg
        self._view = (c.get("color", "#0B0C10"), c.get("image", ""), c.get("text", ""), bool(c.get("logo", True)))
        return (self._view, self.width(), self.height())

    def desired_height(self) -> int:
        return 400

    def _image(self, path):
        if self._img[0] != path:
            pm = QPixmap(path) if path and os.path.isfile(path) else None
            self._img = (path, pm if pm is not None and not pm.isNull() else None)
        return self._img[1]

    def paint_content(self, p: QPainter):
        if self._view is None:
            return
        color, image, text, show_logo = self._view
        r = QRectF(self.rect())
        bg = QColor(color)
        if not bg.isValid():
            bg = QColor(11, 12, 16)
        bg.setAlpha(255)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, self.pal.radius, self.pal.radius)
        self._drew_bg = True
        pm = self._image(image)
        if pm is not None:  # vartotojo paveikslėlis: užpildo visą plotą (crop)
            k = max(r.width() / pm.width(), r.height() / pm.height())
            w, h = pm.width() * k, pm.height() * k
            p.save()
            p.setClipRect(r)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawPixmap(QRectF((r.width() - w) / 2, (r.height() - h) / 2, w, h), pm, QRectF(pm.rect()))
            p.restore()
        elif show_logo:
            from ..brand import logo_pixmap
            lh = int(min(r.height() * 0.28, r.width() * 0.14))
            lp = logo_pixmap(max(16, lh))
            lw = lp.width() / lp.devicePixelRatio()
            lhh = lp.height() / lp.devicePixelRatio()
            p.drawPixmap(int((r.width() - lw) / 2), int((r.height() - lhh) / 2 - (lhh * 0.35 if text else 0)), lp)
        if text:
            p.setPen(self.pal.text)
            self.draw_text(p, QRectF(0, r.height() * 0.62, r.width(), self.fonts.em_base * 2.4), text, "big", "c")
