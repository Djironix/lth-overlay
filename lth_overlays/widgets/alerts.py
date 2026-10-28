"""Įspėjimai: greitesnė klasė iš už nugaros (Overtake alert) ir grįžimas į trasą (Rejoin)."""
from __future__ import annotations

import time

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from ..theme import short_name
from .panel import PanelWidget


def _class_lap(snap, cid) -> float:
    c = (snap.classes or {}).get(cid) or {}
    return float(c.get("est_lap") or 0.0)


class OvertakeAlertWidget(PanelWidget):
    """Multiclass: greitesnės klasės mašina artėja iš už nugaros / lėtesnė klasė priekyje."""
    NAME = "overtake_alert"
    TITLE = "Overtake alert"
    HAS_HEADER = False
    MIN_WIDTH = 200

    def content_key(self, snap):
        c = self.cfg
        items = []
        me = next((r for r in snap.relative if r.is_me), None)
        if me is not None and (snap.multiclass or c.get("same_class_lapping", False)):
            my_lap = _class_lap(snap, me.car.class_id)
            rng_b = float(c.get("range_behind", 3.0) or 3.0)
            rng_a = float(c.get("range_ahead", 2.0) or 0.0)
            for r in snap.relative:
                if r.is_me or r.car.status in ("pit", "garage", "out") or r.stale:
                    continue
                lap = _class_lap(snap, r.car.class_id)
                faster = r.car.class_id != me.car.class_id and my_lap and lap and lap < my_lap * 0.995
                slower = r.car.class_id != me.car.class_id and my_lap and lap and lap > my_lap * 1.005
                if r.gap < 0 and -r.gap <= rng_b and (faster or (c.get("same_class_lapping") and r.lap_rel > 0)):
                    items.append(("behind", -r.gap, r))
                elif 0 < r.gap <= rng_a and slower and c.get("slower_ahead", True):
                    items.append(("ahead", r.gap, r))
        if not items and self.editing:
            items = [("behind", 1.6, None)]
        items.sort(key=lambda x: (x[0] != "behind", x[1]))
        items = items[:int(c.get("max_cars", 2) or 2)]
        view = []
        for kind, gap, r in items:
            if r is None:
                view.append((kind, round(gap, 1), "LMP2", 0x33CEFF, "31", "M. PAULAUSKAS", None))
                continue
            car = r.car
            view.append((kind, round(gap, 1), car.class_name or "", car.class_color, car.number,
                         short_name(car, "abbrev", self.pal.upper_names),
                         None if r.delta is None else round(r.delta, 1)))
        self._view = tuple(view)
        return (self._view, self.width())

    def desired_height(self) -> int:
        n = max(1, len(self._view or ()))
        return int(self.fonts.em_base * 2.1 * n + self.pad())

    def paint_content(self, p: QPainter):
        if not self._view:
            return
        pad = self.pad() * 0.5
        rh = self.fonts.em_base * 2.1
        y = pad
        for kind, gap, cls, color, number, name, delta in self._view:
            r = QRectF(0, y, self.width(), rh - 3)
            cc = self.pal.class_color(color)
            p.setPen(QPen(cc, 2))
            p.setBrush(self.pal.bg)
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), self.pal.radius, self.pal.radius)
            tag_w = self.text_width(cls, "tiny") + 14
            tag = QRectF(8, y + rh * 0.22, tag_w, rh * 0.5)
            self.chip(p, tag, cls, cc, QColor(15, 15, 18))
            x = tag.right() + 8
            p.setPen(self.pal.yellow if kind == "behind" else self.pal.dim)
            label = "FASTER CLASS BEHIND" if kind == "behind" else "SLOWER CAR AHEAD"
            self.draw_text(p, QRectF(x, y + 2, self.width() - x - 60, rh * 0.45), label, "tiny")
            p.setPen(self.pal.text)
            self.draw_text(p, QRectF(x, y + rh * 0.4, self.width() - x - 60, rh * 0.52), f"#{number}  {name}", "small")
            p.setPen(self.pal.bad if kind == "behind" and gap < 1.0 else self.pal.text)
            self.draw_text(p, QRectF(0, y, self.width() - 10, rh - 3), f"{gap:.1f}s", "bold", "r")
            y += rh


class RejoinWidget(PanelWidget):
    """Kai išvažiuoji iš trasos ar sustoji - kas atvažiuoja iš už nugaros ir ar saugu grįžti."""
    NAME = "rejoin"
    TITLE = "Rejoin indicator"
    HAS_HEADER = False
    MIN_WIDTH = 200
    HOLD_S = 2.5

    def __init__(self, ctx):
        self._until = 0.0
        super().__init__(ctx)

    def content_key(self, snap):
        c = self.cfg
        p = snap.player
        me = next((r for r in snap.cars if r.is_me), None)
        now = time.monotonic()
        active = False
        if me is not None and p is not None and p.valid and snap.on_track and not snap.watching \
                and not p.on_pit_road:
            slow = p.speed < float(c.get("slow_kmh", 40.0) or 40.0) / 3.6
            if me.status == "off" or (slow and snap.session_state == 4):
                active = True
        if active:
            self._until = now + self.HOLD_S
        show = active or now < self._until or self.editing
        if not show:
            self._view = None
            return None
        cars = []
        for r in snap.relative:
            if r.is_me or r.gap >= 0 or r.car.status in ("pit", "garage", "out"):
                continue
            cars.append((round(-r.gap, 1), r.car.number, short_name(r.car, "abbrev", self.pal.upper_names),
                         r.car.class_color))
        cars.sort()
        if not cars and self.editing:
            cars = [(1.4, "46", "J. SAVICKAS", 0xFF5888), (5.2, "73", "E. ŠIMKUS", 0xFF5888)]
        wait, clear = float(c.get("wait_s", 2.0)), float(c.get("clear_s", 4.0))
        near = cars[0][0] if cars else 99.0
        state = "WAIT" if near < wait else ("CAUTION" if near < clear else "CLEAR")
        self._view = (state, tuple(cars[:2]))
        return (self._view, self.width())

    def desired_height(self) -> int:
        return int(self.fonts.em_base * (2.6 + 1.5 * 2) + self.pad())

    def paint_content(self, p: QPainter):
        if self._view is None:
            return
        state, cars = self._view
        col = {"WAIT": self.pal.bad, "CAUTION": self.pal.yellow, "CLEAR": self.pal.good}[state]
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.pal.bg)
        p.drawRoundedRect(r, self.pal.radius, self.pal.radius)
        self._drew_bg = True
        top = QRectF(0, 0, r.width(), self.fonts.em_base * 2.4)
        p.setBrush(col)
        p.drawRoundedRect(top, self.pal.radius, self.pal.radius)
        p.fillRect(QRectF(0, top.height() - self.pal.radius, r.width(), self.pal.radius), col)
        p.setPen(QColor(15, 15, 18))
        txt = {"WAIT": "WAIT - CAR COMING", "CAUTION": "CAUTION", "CLEAR": "CLEAR TO REJOIN"}[state]
        self.draw_text(p, top, txt, "bold", "c")
        y = top.bottom() + self.pad() * 0.4
        lh = self.fonts.em_base * 1.5
        x0 = self.pad() * 1.2
        if not cars:
            p.setPen(self.pal.dim)
            self.draw_text(p, QRectF(x0, y, r.width() - 2 * x0, lh), "No cars behind", "small")
        for gap, number, name, color in cars:
            p.fillRect(QRectF(x0, y + lh * 0.2, 3, lh * 0.6), self.pal.class_color(color))
            p.setPen(self.pal.text)
            self.draw_text(p, QRectF(x0 + 8, y, r.width() - 2 * x0 - 60, lh), f"#{number}  {name}", "small")
            p.setPen(self.pal.bad if gap < 2.0 else self.pal.yellow if gap < 4.0 else self.pal.text)
            self.draw_text(p, QRectF(x0, y, r.width() - 2 * x0, lh), f"{gap:.1f}s", "bold", "r")
            y += lh
