"""Bendras lentelės piešimas Standings ir Relative valdikliams.

Eilutės aprašomos hashable tuple'ais (tekstas + spalvos žetonas), todėl jas
galima tiesiog palyginti su ankstesnėmis ir nepiešti, jei niekas nepasikeitė.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap, QPolygonF

from ..window import OverlayWidget

LEFT, RIGHT, CENTER = "l", "r", "c"
_LOGO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "logos")
_LOGOS = {}


def logo(short: str):
    if short not in _LOGOS:
        path = os.path.join(_LOGO_DIR, f"{short}.png")
        _LOGOS[short] = QPixmap(path) if os.path.exists(path) else None
    return _LOGOS[short]


class Cell(tuple):
    """(raktas, tekstas, fg, bg, lygiavimas, šriftas)"""
    __slots__ = ()

    def __new__(cls, key, text, fg="text", bg=None, align=LEFT, font="base"):
        return tuple.__new__(cls, (key, text, fg, bg, align, font))


class TableWidget(OverlayWidget):
    # stulpelio raktas -> plotis em vienetais (1 em = šrifto aukštis); None = lankstus
    WIDTHS = {}
    ALIGN = {}
    NAME_MIN_EM = 7.0  # vardo stulpelis ne siauresnis (≈ "J. SURNAME")

    def content_min_width(self) -> int:
        cols = getattr(self, "_cols", None) or []
        if not cols:
            return 0
        em = self.fonts.em_base
        pad = em * 0.45
        fixed = sum(self.WIDTHS[c] * em for c in cols if self.WIDTHS.get(c))
        n_flex = sum(1 for c in cols if not self.WIDTHS.get(c))
        return int(2 * pad + fixed + pad * 0.4 * len(cols) + n_flex * em * self.NAME_MIN_EM + 2)

    def _color(self, token):
        if token is None:
            return None
        if isinstance(token, tuple):
            kind, v = token
            return self.pal.class_color(v) if kind == "rgb" else self.pal.hex_color(v)
        return getattr(self.pal, token)

    def row_h(self) -> float:
        return round(self.fonts.em_base * self.pal.row_k)

    def layout(self, cols):
        """Stulpelių x pozicijos pagal plotį."""
        em = self.fonts.em_base
        pad = em * 0.45
        fixed = sum(self.WIDTHS[c] * em for c in cols if self.WIDTHS.get(c))
        flex_cols = [c for c in cols if not self.WIDTHS.get(c)]
        avail = self.width() - 2 * pad - fixed - pad * 0.4 * len(cols)
        flex = max(em * 4, avail / max(1, len(flex_cols)))
        x = pad
        out = {}
        for c in cols:
            w = self.WIDTHS.get(c) * em if self.WIDTHS.get(c) else flex
            out[c] = (x, w)
            x += w + pad * 0.4
        return out

    def paint_rows(self, p: QPainter, rows, cols, y0: float, me_flag="me"):
        rh = self.row_h()
        lay = self.layout(cols)
        y = y0
        for i, (kind, cells, flags) in enumerate(rows):
            if kind == "sep":
                p.setPen(self.pal.dim)
                self.draw_text(p, QRectF(0, y, self.width(), rh * 0.6), "· · ·", "tiny", CENTER)
                y += rh * 0.6
                continue
            if kind == "class":
                self._paint_class_header(p, cells, y, rh)
                y += rh * 0.9
                continue
            if me_flag in flags:
                p.fillRect(QRectF(0, y, self.width(), rh), self.pal.me_bg)
                if not self.pal.lumina:
                    p.fillRect(QRectF(0, y, 3, rh), self.pal.accent)
            elif i % 2:
                p.fillRect(QRectF(0, y, self.width(), rh), self.pal.row_alt)
            for cell in cells:
                key, text, fg, bg, align, font = cell
                if key not in lay:
                    continue
                x, w = lay[key]
                rect = QRectF(x, y, w, rh)
                if key == "classbar":
                    cc = self._color(bg)
                    if self.pal.lumina:  # klasės spalvos linija po eilute + siaura juostelė
                        line = QColor(cc)
                        line.setAlpha(170)
                        p.fillRect(QRectF(0, y + rh - 1, self.width(), 1), line)
                        p.fillRect(QRectF(0, y, 3, rh - 1), cc)
                    else:
                        p.fillRect(QRectF(0, y + 2, 3, rh - 4), cc)
                    continue
                if key == "brand" and text:
                    pm = logo(text)
                    if pm is not None and not pm.isNull():
                        s = rh * 0.7
                        p.drawPixmap(QRectF(x + (w - s) / 2, y + (rh - s) / 2, s, s).toRect(), pm)
                        continue
                if bg is not None:
                    bw = min(w, self.text_width(text, font) + rh * 0.45)
                    bx = x + (w - bw) / 2 if align == CENTER else (x + w - bw if align == RIGHT else x)
                    br = QRectF(bx, y + rh * 0.16, bw, rh * 0.68)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(self._color(bg))
                    p.drawRoundedRect(br, self.pal.radius * 0.7, self.pal.radius * 0.7)
                    rect = br
                    align = CENTER
                p.setPen(self._color(fg))
                if align == LEFT and key == "name":
                    text = self.elide(text, w, font)
                self.draw_text(p, rect, text, font, align)
            y += rh
        return y

    def _paint_class_header(self, p, cells, y, rh):
        name, color, count = cells
        c = self._color(color)
        if self.pal.lumina:  # klasės "kortelė": spalvotas pasviręs skirtukas su pavadinimu
            top, hgt = y + rh * 0.12, rh * 0.7
            tw = min(self.width() * 0.6, self.text_width(name.upper(), "tiny") + 26)
            p.fillRect(QRectF(0, top, self.width(), hgt), self.pal.header)
            poly = QPolygonF([QPointF(0, top), QPointF(tw, top), QPointF(tw - hgt * 0.35, top + hgt), QPointF(0, top + hgt)])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawPolygon(poly)
            p.setPen(self.pal.ink)
            self.draw_text(p, QRectF(10, top, tw - 14, hgt), name.upper(), "tiny")
            p.setPen(c)
            self.draw_text(p, QRectF(12, top, self.width() - 24, hgt), count, "tiny", RIGHT)
            return
        p.fillRect(QRectF(0, y + rh * 0.15, self.width(), rh * 0.7), self.pal.header)
        p.fillRect(QRectF(0, y + rh * 0.15, 4, rh * 0.7), c)
        p.setPen(c)
        self.draw_text(p, QRectF(12, y, self.width() - 24, rh * 0.9), name.upper(), "tiny")
        p.setPen(self.pal.dim)
        self.draw_text(p, QRectF(12, y, self.width() - 24, rh * 0.9), count, "tiny", RIGHT)

    def number_cell(self, key, r):
        """Mašinos numeris: modernioje temoje - klasės spalvos plytelė su juodu tekstu."""
        if self.pal.lumina:
            return Cell(key, r.number, fg="ink", bg=("rgb", r.class_color), align=CENTER, font="bold")
        return Cell(key, r.number, fg="text", bg="header", align=CENTER, font="bold")

    def paint_frame(self, p: QPainter, title: str, right: str = "") -> float:
        """Fonas ir antraštė. Grąžina y, nuo kurio prasideda eilutės."""
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.pal.bg)
        p.drawRoundedRect(r, self.pal.radius, self.pal.radius)
        if not self.cfg.get("show_header", True):
            return 4.0
        hh = self.paint_header(p, title, right)
        return hh + 2
