"""Bendra bazė „kortelės“ tipo valdikliams (kuras, sesija, boksai...).

Visi piešimo pagalbininkai naudoja tekstų talpyklą (draw_text) ir paletės
spalvas, todėl nauji valdikliai atrodo vienodai su Standings / Relative.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter

from ..window import OverlayWidget


def fmt_time(s, digits=3) -> str:
    if s is None or not math.isfinite(s) or s <= 0:
        return "–"
    m, sec = divmod(s, 60.0)
    if m >= 1:
        return f"{int(m)}:{sec:0{3 + digits}.{digits}f}"
    return f"{sec:.{digits}f}"


def fmt_clock(s) -> str:
    if s is None or not math.isfinite(s) or s < 0 or s > 1e6:
        return "–"
    s = int(s)
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def fmt_signed(v, digits=2) -> str:
    if v is None or not math.isfinite(v):
        return "–"
    return f"{v:+.{digits}f}"


class PanelWidget(OverlayWidget):
    """Kortelė: fonas + (nebūtina) antraštė + eilutės „pavadinimas ... reikšmė“."""

    MIN_WIDTH = 150
    HAS_HEADER = True

    def __init__(self, ctx):
        self._view = None
        super().__init__(ctx)

    # ---- matmenys ----
    def lh(self) -> float:
        return round(self.fonts.em_base * 1.42)

    def pad(self) -> float:
        return round(self.fonts.em_base * 0.55)

    def header_h(self) -> int:
        if not self.HAS_HEADER:
            return 0
        return super().header_h()

    def body_height(self, lines: float) -> int:
        return int(self.header_h() + lines * self.lh() + self.pad() * 1.4)

    # ---- piešimas ----
    def card(self, p: QPainter, title: str = "", right: str = "") -> float:
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.pal.bg)
        p.drawRoundedRect(r, self.pal.radius, self.pal.radius)
        if self.HAS_HEADER and self.cfg.get("show_header", True) and title:
            return self.paint_header(p, title, right) + self.pad() * 0.4
        return self.pad() * 0.7

    def kv(self, p: QPainter, y: float, label: str, value: str, color: str = "text", font: str = "base",
           label_color: str = "dim") -> float:
        lh = self.lh()
        x0 = self.pad() * 1.4
        w = self.width() - 2 * x0
        p.setPen(getattr(self.pal, label_color))
        self.draw_text(p, QRectF(x0, y, w * 0.55, lh), label, "small")
        p.setPen(getattr(self.pal, color))
        self.draw_text(p, QRectF(x0, y, w, lh), value, font, "r")
        return y + lh

    def text_line(self, p: QPainter, y: float, text: str, color: str = "text", font: str = "base",
                  align: str = "l") -> float:
        lh = self.lh()
        x0 = self.pad() * 1.4
        p.setPen(getattr(self.pal, color))
        self.draw_text(p, QRectF(x0, y, self.width() - 2 * x0, lh), text, font, align)
        return y + lh

    def bar(self, p: QPainter, rect: QRectF, frac: float, color: QColor, back: QColor | None = None):
        frac = 0.0 if not math.isfinite(frac) else max(0.0, min(1.0, frac))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(back if back is not None else self.pal.track)
        rad = min(rect.height() / 2, 3)
        p.drawRoundedRect(rect, rad, rad)
        if frac > 0:
            p.setBrush(color)
            p.drawRoundedRect(QRectF(rect.x(), rect.y(), rect.width() * frac, rect.height()), rad, rad)

    def chip(self, p: QPainter, rect: QRectF, text: str, bg: QColor, fg: QColor, font: str = "tiny"):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(rect, self.pal.radius * 0.8, self.pal.radius * 0.8)
        p.setPen(fg)
        self.draw_text(p, rect, text, font, "c")

    def empty_note(self, p: QPainter, y: float, text: str) -> float:
        return self.text_line(p, y, text, "dim", "small")
