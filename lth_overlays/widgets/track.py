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
    FAST_CAPABLE = True  # mašinos juda sklandžiai (iki 60 fps), trasa piešiama vieną kartą

    def __init__(self, ctx):
        self._pts_id = None
        self._path = None  # (raktas, QPainterPath, transformuoti taškai)
        self._static = None  # (raktas, QPixmap) - fonas, antraštė, trasa
        self._meta = ()
        super().__init__(ctx)

    def fast_tick(self, timing) -> bool:
        if self._view is None or not self._meta:
            return False
        live = timing.frame.CarIdxLapDistPct
        if live is None:
            return False
        n = len(live)
        old = {c[0]: c[1] for c in self._view[1]}
        cars = []
        for idx, color, number, me, in_pit, leader in self._meta:
            pct = float(live[idx]) if idx < n else -1.0
            if not (0.0 <= pct <= 1.0):
                pct = old.get(idx, -1.0)
                if pct < 0:
                    continue
            cars.append((idx, round(pct, 5), color, number, me, in_pit, leader))
        cars = tuple(cars)
        if cars == self._view[1]:
            return False
        self._view = (self._view[0], cars, self._view[2], self._view[3])
        return True

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
        # mėlyna vėliava (lenkiamas) ir draugų spalvos (Drivers puslapis)
        race = snap.session_type == "race"
        friends = self.ctx.config.friends() if hasattr(self.ctx.config, "friends") else {}
        extra = {}
        if self.cfg.get("blue_flags", True) or friends:
            for r in snap.cars:
                blue = bool(race and self.cfg.get("blue_flags", True) and r.flag_bits & 0x20 and not r.is_me)
                fc = friends.get(r.user_id) if r.user_id and not r.is_me else None
                if blue or fc:
                    extra[r.idx] = (blue, fc)
        self._extra = extra
        ex_key = tuple(sorted(extra.items()))
        rec = None if pts is not None else (bool(tm.get("recording")), round(float(tm.get("progress", 0.0)), 2))
        self._meta = tuple((c[0], c[2], c[3], c[4], c[5], c[6]) for c in cars)
        if self.fast_active() and self._view is not None:  # padėtis atnaujina fast_tick
            self._view = (pts, self._view[1] if self._view[1] else tuple(cars), rec, tuple(snap.sectors or ()))
            return (id(pts) if pts is not None else None, self._meta, rec, self.width(), self.height(),
                    self.cfg.get("mirror"), self.cfg.get("rotate"), self.cfg.get("numbers"), self.cfg.get("dot"), ex_key)
        self._view = (pts, tuple(cars), rec, tuple(snap.sectors or ()))
        return (id(pts) if pts is not None else None, self._view[1], rec, self.width(), self.height(),
                self.cfg.get("mirror"), self.cfg.get("rotate"), self.cfg.get("numbers"), self.cfg.get("dot"), ex_key)

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
        y0 = float(self.header_h()) if self.cfg.get("show_header", True) else 0.0
        m = self.pad() * 1.6
        area = QRectF(m, y0 + m, r.width() - 2 * m, r.height() - y0 - 2 * m)
        sc = self._scale()
        # nejudanti dalis (fonas, antraštė, trasa) - į talpyklą; kas kadrą piešiam tik taškus
        dpr = self.devicePixelRatioF()
        skey = (id(pts) if pts is not None else None, rec, tuple(sectors), self.width(), self.height(), id(pal),
                self.cfg.get("mirror"), self.cfg.get("rotate"), self.cfg.get("show_header", True), dpr)
        if self._static is None or self._static[0] != skey:
            from PySide6.QtGui import QPixmap
            pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._paint_static(q, pts, rec, sectors, r, area, sc)
            q.end()
            self._static = (skey, pm)
        p.drawPixmap(0, 0, self._static[1])
        self._drew_bg = True
        if area.width() < 20 or area.height() < 20:
            return
        path, xy = self._geometry(pts, area)
        self._paint_cars(p, xy, cars, sc)

    def _paint_static(self, p, pts, rec, sectors, r, area, sc):
        pal = self.pal
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.bg)
        p.drawRoundedRect(r, pal.radius, pal.radius)
        if self.cfg.get("show_header", True):
            self.paint_header(p, "TRACK MAP", "" if rec is None else
                              (f"recording {rec[1] * 100:.0f}%" if rec[0] else "drive a clean lap to record"))
        if area.width() < 20 or area.height() < 20:
            return
        path, xy = self._geometry(pts, area)
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

    def _sprite(self, fill: QColor, rad: float, ring: str, sc: float):
        """Mašinos taškas kaip paruoštas paveikslėlis: antialiasintas apskritimas kainuoja daug daugiau
        nei paveikslėlio kopija, o žemėlapis piešiamas 30-60 kartų per sekundę."""
        dpr = self.devicePixelRatioF()
        key = (fill.rgba(), round(rad, 2), ring, round(sc, 3), dpr)
        cache = self.__dict__.setdefault("_sprites", {})
        pm = cache.get(key)
        if pm is None:
            from PySide6.QtGui import QPixmap
            outer = rad + (2.5 * sc + 1.6 * sc if ring == "me" else 1.8 * sc + 1.2 * sc if ring else 1.2) + 1
            size = int((outer * 2 + 2) * dpr) + 1
            pm = QPixmap(size, size)
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            c = QPointF(size / dpr / 2, size / dpr / 2)
            q.setPen(QPen(QColor(0, 0, 0, 200), 1.2))
            q.setBrush(fill)
            q.drawEllipse(c, rad, rad)
            q.setBrush(Qt.BrushStyle.NoBrush)
            if ring == "me":
                q.setPen(QPen(QColor(255, 255, 255), 1.6 * sc))
                q.drawEllipse(c, rad + 2.5 * sc, rad + 2.5 * sc)
            elif ring == "leader":
                q.setPen(QPen(QColor(255, 255, 255, 200), 1.2 * sc))
                q.drawEllipse(c, rad + 1.8 * sc, rad + 1.8 * sc)
            elif ring == "blue":
                q.setPen(QPen(QColor(40, 130, 255), 2.2 * sc))
                q.drawEllipse(c, rad + 2.0 * sc, rad + 2.0 * sc)
            elif ring == "friend":
                q.setPen(QPen(fill.lighter(150), 1.4 * sc))
                q.drawEllipse(c, rad + 1.8 * sc, rad + 1.8 * sc)
            q.end()
            if len(cache) > 300:
                cache.clear()
            cache[key] = pm
        return pm

    def _paint_cars(self, p, xy, cars, sc):
        pal = self.pal
        dot = 4.2 * sc * float(self.cfg.get("dot", 1.0) or 1.0)
        numbers = self.cfg.get("numbers")
        dpr = self.devicePixelRatioF()
        extra = getattr(self, "_extra", {})
        for idx, prog, color, number, me, in_pit, leader in cars:
            c = self._at(xy, prog)
            ex = extra.get(idx)
            col = QColor(ex[1]) if ex and ex[1] else (QColor(pal.class_color(color)) if color else QColor(pal.text))
            if in_pit:
                col.setAlpha(110)
            rad = dot * (1.6 if me else 1.0)
            ring = "me" if me else ("blue" if ex and ex[0] else ("leader" if leader else ("friend" if ex and ex[1] else "")))
            pm = self._sprite(pal.accent if me else col, rad, ring, sc)
            half = pm.width() / dpr / 2
            p.drawPixmap(QPointF(c.x() - half, c.y() - half), pm)
            if numbers and not in_pit:
                p.setPen(pal.text)
                self.draw_text(p, QRectF(c.x() + rad + 2, c.y() - 7, 40, 14), number, "tiny")


class FlatMapWidget(TrackMapWidget):
    """Trasa kaip tiesi linija: visas ratas nuo starto iki finišo (arba aš per vidurį)."""
    NAME = "flat_map"
    TITLE = "Flat track map"
    HEIGHT_MODE = "auto"
    MIN_WIDTH = 240
    MIN_HEIGHT = 30

    def desired_height(self) -> int:
        return int(self.fonts.em_base * (3.4 if self.cfg.get("numbers") else 2.4))

    def paint_content(self, p: QPainter):
        if self._view is None:
            return
        _pts, cars, _rec, sectors = self._view
        r = QRectF(self.rect())
        pal = self.pal
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.bg)
        p.drawRoundedRect(r, pal.radius, pal.radius)
        self._drew_bg = True
        sc = self._scale()
        pad = self.pad() * 1.4
        x0, x1 = pad, r.width() - pad
        yl = r.height() * (0.42 if self.cfg.get("numbers") else 0.5)
        centered = self.cfg.get("center_me", False)
        me_pct = next((c[1] for c in cars if c[4]), None)

        def xpos(pct):
            if centered and me_pct is not None:
                pct = (pct - me_pct + 0.5) % 1.0
            return x0 + (pct % 1.0) * (x1 - x0)

        p.setPen(QPen(QColor(220, 220, 225, 120), 3 * sc, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(x0, yl), QPointF(x1, yl))
        for i, s in enumerate(sectors or (0.0,)):
            x = xpos(s)
            p.setPen(QPen(pal.accent if i == 0 else QColor(255, 255, 255, 110), 2.5 * sc if i == 0 else 1.2 * sc))
            p.drawLine(QPointF(x, yl - 6 * sc), QPointF(x, yl + 6 * sc))
        dot = 4.2 * sc * float(self.cfg.get("dot", 1.0) or 1.0)
        numbers = self.cfg.get("numbers")
        dpr = self.devicePixelRatioF()
        extra = getattr(self, "_extra", {})
        for idx, prog, color, number, me, in_pit, leader in cars:
            x = xpos(prog)
            ex = extra.get(idx)
            col = QColor(ex[1]) if ex and ex[1] else (QColor(pal.class_color(color)) if color else QColor(pal.text))
            if in_pit:
                col.setAlpha(110)
            rad = dot * (1.5 if me else 1.0)
            ring = "me" if me else ("blue" if ex and ex[0] else ("friend" if ex and ex[1] else ""))
            pm = self._sprite(pal.accent if me else col, rad, ring, sc)
            half = pm.width() / dpr / 2
            p.drawPixmap(QPointF(x - half, yl - half), pm)
            if numbers and not in_pit:
                p.setPen(pal.accent if me else pal.dim)
                self.draw_text(p, QRectF(x - 20, yl + rad + 2, 40, self.fonts.em_small * 1.2), number, "tiny", "c")
