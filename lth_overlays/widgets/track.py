"""Trasos žemėlapis su visomis mašinomis.

Kol žemėlapis neįrašytas, mašinos rodomos ant apskritimo (pagal rato dalį) -
valdiklis naudingas jau nuo pirmos minutės.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from .panel import PanelWidget

BINS = 400


class TrackMapWidget(PanelWidget):
    NAME = "track_map"
    TITLE = "Track map"
    HEIGHT_MODE = "free"
    MIN_WIDTH = 120
    MIN_HEIGHT = 120

    def __init__(self, ctx):
        self._pts_id = None
        self._path = None  # (raktas, QPainterPath, transformuoti taškai)
        super().__init__(ctx)

    def content_key(self, snap):
        tm = snap.track_map or {}
        pts = tm.get("points")
        cars = []
        live = snap.car_pct  # šio kadro padėtys (standings atsinaujina tik ~2 Hz)
        n_live = len(live) if live is not None else 0
        for r in snap.cars:
            if r.status in ("out", "garage") or not math.isfinite(r.progress):
                continue
            pct = float(live[r.idx]) if 0 <= r.idx < n_live else -1.0
            if not (0.0 <= pct <= 1.0) or r.stale:
                pct = r.progress % 1.0
            cars.append((r.idx, round(pct, 4), r.class_color, r.number, r.is_me, r.status == "pit",
                         r.class_pos == 1))
        cars.sort(key=lambda c: c[4])  # aš - paskutinis (viršuje)
        rec = None if pts is not None else (bool(tm.get("recording")), round(float(tm.get("progress", 0.0)), 2))
        self._view = (pts, tuple(cars), rec, tuple(snap.sectors or ()))
        return (id(pts) if pts is not None else None, self._view[1], rec, self.width(), self.height(),
                self.cfg.get("mirror"), self.cfg.get("rotate"), self.cfg.get("numbers"), self.cfg.get("dot"))

    def desired_height(self) -> int:
        return self.width()

    # ---- geometrija ----
    def _transform(self, pts: np.ndarray, rect: QRectF) -> np.ndarray:
        xy = pts.copy()
        xy -= 0.5
        if self.cfg.get("mirror"):
            xy[:, 0] = -xy[:, 0]
        rot = int(self.cfg.get("rotate", "0") or 0) % 360
        if rot:
            a = math.radians(rot)
            c, s = math.cos(a), math.sin(a)
            xy = xy @ np.array([[c, s], [-s, c]])
        lo, hi = xy.min(axis=0), xy.max(axis=0)
        span = max(float((hi - lo).max()), 1e-6)
        size = min(rect.width(), rect.height())
        k = size / span
        mid = (lo + hi) / 2
        out = np.empty_like(xy)
        out[:, 0] = rect.center().x() + (xy[:, 0] - mid[0]) * k
        out[:, 1] = rect.center().y() + (xy[:, 1] - mid[1]) * k
        return out

    def _geometry(self, pts, rect: QRectF):
        key = (id(pts), rect.width(), rect.height(), self.cfg.get("mirror"), self.cfg.get("rotate"))
        if self._path is not None and self._path[0] == key:
            return self._path[1], self._path[2]
        if pts is None:
            n = BINS
            a = np.arange(n) / n * 2 * math.pi
            base = np.stack([0.5 + 0.5 * np.sin(a), 0.5 - 0.5 * np.cos(a)], axis=1)
            xy = self._transform(base, rect)
        else:
            xy = self._transform(np.asarray(pts, dtype=float), rect)
        path = QPainterPath(QPointF(*xy[0]))
        for x, y in xy[1:]:
            path.lineTo(x, y)
        path.closeSubpath()
        self._path = (key, path, xy)
        return path, xy

    @staticmethod
    def _at(xy: np.ndarray, pct: float) -> QPointF:
        x = (pct % 1.0) * len(xy)
        i = int(x) % len(xy)
        j = (i + 1) % len(xy)
        k = x - int(x)
        return QPointF(xy[i, 0] * (1 - k) + xy[j, 0] * k, xy[i, 1] * (1 - k) + xy[j, 1] * k)

    # ---- piešimas ----
    def paint_content(self, p: QPainter):
        if self._view is None:
            return
        pts, cars, rec, sectors = self._view
        r = QRectF(self.rect())
        pal = self.pal
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.bg)
        p.drawRoundedRect(r, pal.radius, pal.radius)
        y0 = 0.0
        if self.cfg.get("show_header", True):
            y0 = self.paint_header(p, "TRACK MAP", "" if rec is None else
                                   (f"recording {rec[1] * 100:.0f}%" if rec[0] else "drive a clean lap to record"))
        m = self.pad() * 1.6
        area = QRectF(m, y0 + m, r.width() - 2 * m, r.height() - y0 - 2 * m)
        if area.width() < 20 or area.height() < 20:
            return
        path, xy = self._geometry(pts, area)
        sc = self._scale()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 150), 7 * sc, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)
        p.setPen(QPen(QColor(220, 220, 225, 210 if pts is not None else 90), 3.2 * sc, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)
        # starto / finišo linija ir sektoriai
        for i, s in enumerate(sectors or (0.0,)):
            a = self._at(xy, s)
            b = self._at(xy, s + 0.004)
            dx, dy = b.x() - a.x(), b.y() - a.y()
            n = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / n * 7 * sc, dx / n * 7 * sc
            p.setPen(QPen(pal.accent if i == 0 else QColor(255, 255, 255, 120), 2.5 * sc if i == 0 else 1.5 * sc))
            p.drawLine(QPointF(a.x() - nx, a.y() - ny), QPointF(a.x() + nx, a.y() + ny))
        # mašinos
        dot = 4.2 * sc * float(self.cfg.get("dot", 1.0) or 1.0)
        numbers = self.cfg.get("numbers")
        for idx, prog, color, number, me, in_pit, leader in cars:
            c = self._at(xy, prog)
            col = QColor(pal.class_color(color)) if color else QColor(pal.text)
            if in_pit:
                col.setAlpha(110)
            rad = dot * (1.6 if me else 1.0)
            p.setPen(QPen(QColor(0, 0, 0, 200), 1.2))
            p.setBrush(pal.accent if me else col)
            p.drawEllipse(c, rad, rad)
            if me:
                p.setPen(QPen(QColor(255, 255, 255), 1.6 * sc))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(c, rad + 2.5 * sc, rad + 2.5 * sc)
            elif leader:
                p.setPen(QPen(QColor(255, 255, 255, 200), 1.2 * sc))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(c, rad + 1.8 * sc, rad + 1.8 * sc)
            if numbers and not in_pit:
                p.setPen(pal.text)
                self.draw_text(p, QRectF(c.x() + rad + 2, c.y() - 7, 40, 14), number, "tiny")
