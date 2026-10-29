"""Telemetry puslapis: sesijos ataskaita ir dviejų ratų palyginimas (savo ar draugo .lthlap)."""
from __future__ import annotations

import math
import os
import re

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from lth_timing import telemetry as T

from ..config import app_dir
from .components import Card, Combo, KpiTile, Segmented, SettingRow, Toggle, button, clear_layout, hbox, label
from .pages import Page, open_folder
from .style import qcolor, ui_font

COL_A = QColor("#ECBE58")
COL_B = QColor("#5AA9FF")


def laps_dir() -> str:
    return os.path.join(app_dir(), "laps")


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name or "x").strip("_")[:60] or "x"


def best_path(track_key: str, car: str) -> str:
    return os.path.join(laps_dir(), _safe(track_key), _safe(car) + "_best.lthlap")


# ====================================================================== grafikai
class LapTimesChart(QWidget):
    """Ratų laikai stulpeliais: violetinis - geriausias, pilki - boksų / negaliojantys."""

    def __init__(self):
        super().__init__()
        self.laps = []
        self.setMinimumHeight(150)

    def set_laps(self, laps):
        self.laps = laps
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(64, 8, -8, -22)
        laps = [x for x in self.laps if x.lap_time > 0]
        p.setFont(ui_font(10))
        if not laps:
            p.setPen(qcolor("faint"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Lap times appear here after your first lap")
            return
        valid = [x.lap_time for x in laps if x.valid] or [x.lap_time for x in laps]
        best = min(valid)
        lo = best - 0.3
        hi = max(min(max(x.lap_time for x in laps), best * 1.06), best + 1.0)
        n = len(laps)
        bw = r.width() / n
        p.setPen(QPen(qcolor("border"), 1))
        for k in range(4):
            y = r.bottom() - r.height() * k / 3
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.setPen(qcolor("faint"))
            p.drawText(QRectF(0, y - 8, 58, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       T.fmt(lo + (hi - lo) * k / 3)[:-2])
            p.setPen(QPen(qcolor("border"), 1))
        for i, lap in enumerate(laps):
            v = min(lap.lap_time, hi)
            h = max(2.0, (v - lo) / (hi - lo) * r.height())
            x = r.left() + i * bw + bw * 0.15
            col = QColor("#B48CFF") if lap.valid and lap.lap_time == best else (
                qcolor("accent") if lap.valid else qcolor("faint"))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(x, r.bottom() - h, bw * 0.7, h), 2, 2)
            if n <= 40 or i % max(1, n // 20) == 0:
                p.setPen(qcolor("faint"))
                p.drawText(QRectF(x - 6, r.bottom() + 4, bw * 0.7 + 12, 14), Qt.AlignmentFlag.AlignCenter,
                           str(lap.number))


class TraceView(QWidget):
    """Kanalai pagal atstumą: laiko skirtumas, greitis, dujos, stabdys, vairas, pavara. Ratukas - artinti.
    Kiekvienas ratas turi savo spalvą visuose grafikuose (A - auksinė, B - mėlyna)."""

    PANELS = (("delta", "Delta", 1.0), ("speed", "Speed", 1.6), ("throttle", "Throttle", 0.85),
              ("brake", "Brake", 0.85), ("abs", "ABS", 0.40), ("steer", "Steering", 0.8), ("gear", "Gear", 0.65))
    GAP = 24
    TOP = 26  # legenda

    hovered = Signal(float)  # rato dalis 0..1, -1 = pelė ne ant grafiko
    zoomed = Signal(float, float)  # rodoma rato dalis (nuo, iki)

    def __init__(self):
        super().__init__()
        self.a = self.b = None
        self.track_m = 0.0
        self.unit_kmh = True
        self.x0, self.x1 = 0.0, 1.0
        self._cache = None
        self._hover = None
        self._drag = None
        self.setMouseTracking(True)
        self.setMinimumHeight(700)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_laps(self, a, b, track_m):
        self.a, self.b, self.track_m = a, b, float(track_m or 0)
        self._cache = None
        self.update()

    def reset_zoom(self):
        self.set_range(0.0, 1.0)

    # ---- geometrija ----
    def _rects(self):
        r = QRectF(self.rect()).adjusted(70, self.TOP, -12, -24)
        total = sum(k for *_, k in self.PANELS)
        gap = self.GAP
        h_avail = r.height() - gap * (len(self.PANELS) - 1)
        out, y = [], r.top()
        for key, title, k in self.PANELS:
            h = h_avail * k / total
            out.append((key, title, QRectF(r.left(), y, r.width(), h)))
            y += h + gap
        return out

    def _x(self, g, rect):
        return rect.left() + (g - self.x0) / (self.x1 - self.x0) * rect.width()

    def _poly(self, grid, vals, rect, lo, hi):
        m = (grid >= self.x0 - 0.002) & (grid <= self.x1 + 0.002)
        g, v = grid[m], vals[m]
        if len(g) < 2:
            return QPolygonF()
        step = max(1, int(len(g) / max(200, rect.width() * 1.5)))
        g, v = g[::step], v[::step]
        xs = rect.left() + (g - self.x0) / (self.x1 - self.x0) * rect.width()
        ys = rect.bottom() - (np.clip(v, lo, hi) - lo) / (hi - lo or 1) * rect.height()
        return QPolygonF([QPointF(float(x), float(y)) for x, y in zip(xs, ys)])

    def _fill_runs(self, p, grid, mask, rect, color):
        """Užpildo stačiakampius ten, kur mask True (matomame rato intervale)."""
        from ..widgets.wheel import runs
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        span = self.x1 - self.x0
        for i0, i1 in runs(mask):
            g0, g1 = float(grid[max(0, i0)]), float(grid[min(len(grid) - 1, i1)])
            if g1 < self.x0 or g0 > self.x1:
                continue
            x0 = rect.left() + (max(g0, self.x0) - self.x0) / span * rect.width()
            x1 = rect.left() + (min(g1, self.x1) - self.x0) / span * rect.width()
            p.drawRect(QRectF(x0, rect.top(), max(1.5, x1 - x0), rect.height()))

    def set_range(self, x0, x1):
        span = min(1.0, max(0.002, x1 - x0))  # iki ~10 m - linijos „išsitempia“
        x0 = min(max(0.0, x0), 1.0 - span)
        self.x0, self.x1 = x0, x0 + span
        self._cache = None
        self.update()
        self.zoomed.emit(self.x0, self.x1)

    # ---- piešimas ----
    def _legend(self, p):
        x = 70.0
        p.setFont(ui_font(11, QFont.Weight.DemiBold))
        for lap, col, name in ((self.a, COL_A, "A"), (self.b, COL_B, "B")):
            if lap is None:
                continue
            p.setPen(QPen(col, 3))
            p.drawLine(QPointF(x, 12), QPointF(x + 22, 12))
            who = lap.meta.get("driver") if lap.meta.get("imported") else ("saved best" if lap.meta.get("saved_best")
                                                                          else f"lap {lap.number}")
            txt = f"{name}  {who}  {T.fmt(lap.lap_time)}"
            p.setPen(qcolor("text"))
            p.drawText(QRectF(x + 28, 2, 400, 20), Qt.AlignmentFlag.AlignVCenter, txt)
            x += 28 + p.fontMetrics().horizontalAdvance(txt) + 28
        p.setFont(ui_font(10))

    def _paint_base(self) -> QPixmap:
        dpr = self.devicePixelRatioF()
        pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        a, b = self.a, self.b
        self._legend(p)
        for key, title, rect in self._rects():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qcolor("bg"))
            p.drawRoundedRect(rect.adjusted(-4, -3, 4, 3), 6, 6)
            p.setPen(QPen(qcolor("border"), 1))
            for k in ((0.25, 0.5, 0.75) if key != "abs" else ()):  # tinklelis
                yy = rect.bottom() - rect.height() * k
                p.drawLine(QPointF(rect.left(), yy), QPointF(rect.right(), yy))
            p.setPen(qcolor("muted"))
            p.setFont(ui_font(10.5, QFont.Weight.DemiBold))
            p.drawText(QRectF(0, rect.top() - 2, 62, 16), Qt.AlignmentFlag.AlignRight, title)
            p.setFont(ui_font(10))
            if a is None:
                continue
            g = a.grid
            if key == "delta":
                if b is None:
                    p.setPen(qcolor("faint"))
                    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Pick a second lap to see where time is won or lost")
                    continue
                d = T.delta_trace(a, b)
                m = float(max(0.3, np.nanmax(np.abs(d)) * 1.1))
                p.setPen(QPen(qcolor("border2"), 1))
                ymid = rect.center().y()
                p.drawLine(QPointF(rect.left(), ymid), QPointF(rect.right(), ymid))
                p.setPen(qcolor("faint"))
                p.drawText(QRectF(0, rect.top() + 16, 62, 14), Qt.AlignmentFlag.AlignRight, f"B +{m:.1f}s")
                p.drawText(QRectF(0, rect.bottom() - 14, 62, 14), Qt.AlignmentFlag.AlignRight, f"B -{m:.1f}s")
                poly = self._poly(g, d, rect, -m, m)
                if len(poly) > 1:
                    path = QPainterPath()
                    path.moveTo(poly[0].x(), ymid)
                    for pt in poly:
                        path.lineTo(pt)
                    path.lineTo(poly[len(poly) - 1].x(), ymid)
                    path.closeSubpath()
                    p.save()
                    p.setClipRect(QRectF(rect.left(), rect.top(), rect.width(), ymid - rect.top()))
                    p.fillPath(path, QColor(255, 90, 90, 70))
                    p.restore()
                    p.save()
                    p.setClipRect(QRectF(rect.left(), ymid, rect.width(), rect.bottom() - ymid))
                    p.fillPath(path, QColor(60, 220, 140, 70))
                    p.restore()
                    p.setPen(QPen(qcolor("text"), 1.6))
                    p.drawPolyline(poly)
                continue
            if key == "abs":  # kur veikė ABS: atskira juosta kiekvienam ratui jo spalva
                laps = [(lap, col, nm) for lap, col, nm in ((a, COL_A, "A"), (b, COL_B, "B")) if lap is not None]
                rh = rect.height() / max(1, len(laps))
                for i, (lap, col, nm) in enumerate(laps):
                    yy = rect.top() + i * rh
                    v = T.channel_on(lap, g, "abs")
                    p.setPen(col)
                    p.drawText(QRectF(rect.left() + 4, yy, 14, rh), Qt.AlignmentFlag.AlignCenter, nm)
                    p.setPen(qcolor("faint"))
                    if v is None:
                        p.drawText(QRectF(rect.left() + 24, yy, rect.width(), rh), Qt.AlignmentFlag.AlignVCenter,
                                   "no ABS data (lap recorded before v0.6.2)")
                        continue
                    bar = QRectF(rect.left() + 22, yy + rh * 0.15, rect.width() - 22, rh * 0.70)
                    p.fillRect(bar, QColor(255, 255, 255, 10))
                    self._fill_runs(p, g, v > 0.5, QRectF(rect.left(), bar.top(), rect.width(), bar.height()), col)
                continue
            if key == "brake" and a is not None:  # oranžinis fonas ten, kur A rate veikė ABS
                v = T.channel_on(a, g, "abs")
                if v is not None:
                    self._fill_runs(p, g, v > 0.5, rect, QColor(255, 140, 30, 55))
            lo, hi = {"speed": (0.0, None), "throttle": (0.0, 1.0), "brake": (0.0, 1.0),
                      "steer": (None, None), "gear": (0.0, None)}[key]
            series = [(lap, T.channel_on(lap, g, key)) for lap in (a, b) if lap is not None]
            series = [(lap, v) for lap, v in series if v is not None]
            if not series:
                continue
            if lo is None or hi is None:
                allv = np.concatenate([v for _, v in series])
                if key == "steer":
                    m = float(max(0.2, np.nanmax(np.abs(allv))))
                    lo, hi = -m, m
                else:
                    hi = float(max(1.0, np.nanmax(allv) * 1.05))
            for lap, v in reversed(series):  # B apačioje, A viršuje
                col = QColor(COL_A if lap is a else COL_B)
                p.setPen(QPen(col, 2.0 if lap is a else 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                              Qt.PenJoinStyle.RoundJoin))
                p.drawPolyline(self._poly(g, v, QRectF(rect), lo, hi))
            p.setPen(qcolor("faint"))
            if key == "speed":
                k = 3.6 if self.unit_kmh else 2.236936
                p.drawText(QRectF(0, rect.top() + 16, 62, 14), Qt.AlignmentFlag.AlignRight, f"{hi * k:.0f}")
                p.drawText(QRectF(0, rect.bottom() - 14, 62, 14), Qt.AlignmentFlag.AlignRight, "0")
            elif key in ("throttle", "brake"):
                p.drawText(QRectF(0, rect.top() + 16, 62, 14), Qt.AlignmentFlag.AlignRight, "100%")
        # atstumo ašis
        rects = self._rects()
        bottom = rects[-1][2]
        p.setPen(qcolor("faint"))
        for i in range(6):
            gx = self.x0 + (self.x1 - self.x0) * i / 5
            x = self._x(gx, bottom)
            txt = f"{gx * self.track_m:.0f} m" if self.track_m else f"{gx * 100:.0f}%"
            al = Qt.AlignmentFlag.AlignLeft if i == 0 else (Qt.AlignmentFlag.AlignRight if i == 5 else
                                                             Qt.AlignmentFlag.AlignHCenter)
            rx = x if i == 0 else (x - 80 if i == 5 else x - 40)
            p.drawText(QRectF(rx, bottom.bottom() + 4, 80, 16), al | Qt.AlignmentFlag.AlignVCenter, txt)
        p.end()
        return pm

    def hover_pct(self):
        if self._hover is None or self.a is None:
            return None
        top = self._rects()[0][2]
        if not (top.left() <= self._hover <= top.right()):
            return None
        return self.x0 + (self._hover - top.left()) / top.width() * (self.x1 - self.x0)

    def paintEvent(self, e):
        key = (id(self.a), id(self.b), self.width(), self.height(), self.x0, self.x1, self.unit_kmh)
        if self._cache is None or self._cache[0] != key:
            self._cache = (key, self._paint_base())
        p = QPainter(self)
        p.drawPixmap(0, 0, self._cache[1])
        sel = getattr(self, "_sel", None)
        if sel is not None:  # pažymima vieta priartinimui
            top, bottom = self._rects()[0][2], self._rects()[-1][2]
            a_, b_ = sorted(sel)
            p.fillRect(QRectF(a_, top.top(), b_ - a_, bottom.bottom() - top.top()), QColor(236, 190, 88, 40))
            p.setPen(QPen(COL_A, 1))
            p.drawLine(QPointF(a_, top.top()), QPointF(a_, bottom.bottom()))
            p.drawLine(QPointF(b_, top.top()), QPointF(b_, bottom.bottom()))
        gx = self.hover_pct()
        if gx is None:
            return
        rects = self._rects()
        top, bottom = rects[0][2], rects[-1][2]
        x = self._hover
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(255, 255, 255, 120), 1))
        p.drawLine(QPointF(x, top.top()), QPointF(x, bottom.bottom()))
        lines = []
        dist = f"{gx * self.track_m:.0f} m" if self.track_m else f"{gx * 100:.1f}%"
        lines.append((dist, qcolor("text")))
        k = 3.6 if self.unit_kmh else 2.236936
        unit = "km/h" if self.unit_kmh else "mph"
        for lap, col, name in ((self.a, COL_A, "A"), (self.b, COL_B, "B")):
            if lap is None:
                continue
            sp = np.interp(gx, lap.grid, lap.data["speed"]) * k
            th = np.interp(gx, lap.grid, lap.data["throttle"]) * 100
            br = np.interp(gx, lap.grid, lap.data["brake"]) * 100
            ge = int(round(float(np.interp(gx, lap.grid, lap.data["gear"]))))
            lines.append((f"{name}  {sp:.0f} {unit}   T {th:.0f}%   B {br:.0f}%   G {ge}", col))
        if self.b is not None:
            d = float(np.interp(gx, self.b.grid, self.b.data["time"]) - np.interp(gx, self.a.grid, self.a.data["time"]))
            lines.append((f"Delta B - A  {d:+.3f}s", qcolor("bad") if d > 0 else qcolor("good")))
        p.setFont(ui_font(11))
        w = max(p.fontMetrics().horizontalAdvance(t) for t, _ in lines) + 20
        bx = x + 12 if x + 12 + w < self.width() else x - 12 - w
        box = QRectF(bx, top.top() + 4, w, 18 * len(lines) + 10)
        p.setPen(QPen(qcolor("border2"), 1))
        p.setBrush(QColor(15, 16, 20, 235))
        p.drawRoundedRect(box, 6, 6)
        for i, (t, c) in enumerate(lines):
            p.setPen(c)
            p.drawText(QRectF(box.left() + 10, box.top() + 5 + i * 18, w - 14, 18), Qt.AlignmentFlag.AlignVCenter, t)
        # taškai ant kreivių
        for key, _, rect in rects:
            if key not in ("speed",):
                continue
            for lap, col in ((self.b, COL_B), (self.a, COL_A)):
                if lap is None:
                    continue
                hi = float(max(1.0, max(np.nanmax(l.data["speed"]) for l in (self.a, self.b) if l is not None) * 1.05))
                v = float(np.interp(gx, lap.grid, lap.data["speed"]))
                y = rect.bottom() - min(1.0, v / hi) * rect.height()
                p.setPen(QPen(QColor(15, 16, 20), 1.5))
                p.setBrush(col)
                p.drawEllipse(QPointF(x, y), 4, 4)


class TrackMini(QWidget):
    """Trasos kontūras šalia grafikų: kur tiksliai trasoje yra pelė ir kur B laimi (žalia) / pralaimi (raudona)."""

    clicked = Signal(float)  # spustelėta trasos vieta (rato dalis)

    def __init__(self):
        super().__init__()
        self.points = None
        self.a = self.b = None
        self.pos = None
        self.range = (0.0, 1.0)
        self._cache = None
        self.setFixedSize(280, 280)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click a corner to zoom the graphs there")

    def set_range(self, x0, x1):
        self.range = (x0, x1)
        self.update()

    def mousePressEvent(self, e):
        xy = self._xy()
        d = (xy[:, 0] - e.position().x()) ** 2 + (xy[:, 1] - e.position().y()) ** 2
        i = int(np.argmin(d))
        if d[i] < 30 ** 2:
            self.clicked.emit(i / len(xy))

    def set_data(self, points, a, b):
        self.points = None if points is None else np.asarray(points, dtype=float)
        self.a, self.b = a, b
        self._cache = None
        self.update()

    def set_pos(self, gx):
        self.pos = gx if gx is not None and gx >= 0 else None
        self.update()

    def _xy(self):
        r = QRectF(self.rect()).adjusted(16, 16, -16, -16)
        pts = self.points
        if pts is None:  # nėra įrašyto žemėlapio - apskritimas
            a = np.linspace(0, 2 * np.pi, 400, endpoint=False)
            pts = np.stack([0.5 + 0.5 * np.sin(a), 0.5 - 0.5 * np.cos(a)], axis=1)
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        span = max(float((hi - lo).max()), 1e-6)
        k = min(r.width(), r.height()) / span
        mid = (lo + hi) / 2
        xs = r.center().x() + (pts[:, 0] - mid[0]) * k
        ys = r.center().y() + (pts[:, 1] - mid[1]) * k
        return np.stack([xs, ys], axis=1)

    def _at(self, xy, g):
        n = len(xy)
        x = (g % 1.0) * n
        i = int(x) % n
        j = (i + 1) % n
        f = x - int(x)
        return QPointF(xy[i, 0] * (1 - f) + xy[j, 0] * f, xy[i, 1] * (1 - f) + xy[j, 1] * f)

    def _base(self):
        dpr = self.devicePixelRatioF()
        pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qcolor("bg"))
        p.drawRoundedRect(QRectF(self.rect()), 10, 10)
        xy = self._xy()
        n = len(xy)
        p.setPen(QPen(QColor(0, 0, 0, 160), 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in xy] + [QPointF(*xy[0])]))
        # spalva pagal tai, kur B laimi / pralaimi prieš A
        cols = None
        if self.a is not None and self.b is not None:
            gs = (np.arange(n + 1) / n)
            ta = np.interp(gs, self.a.grid, self.a.data["time"])
            tb = np.interp(gs, self.b.grid, self.b.data["time"])
            dd = np.diff(tb - ta)  # + = B šioje atkarpoje lėtesnis
            thr = max(0.004, float(np.percentile(np.abs(dd), 60)))
            cols = dd / thr
        for i in range(n):
            j = (i + 1) % n
            if cols is None:
                c = QColor(220, 220, 225, 200)
            else:
                v = max(-1.0, min(1.0, float(cols[i])))
                if v > 0.15:
                    c = QColor(255, 80, 90, int(120 + 135 * v))
                elif v < -0.15:
                    c = QColor(60, 220, 140, int(120 - 135 * v))
                else:
                    c = QColor(200, 200, 205, 170)
            p.setPen(QPen(c, 4.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(*xy[i]), QPointF(*xy[j]))
        # starto linija
        s0, s1 = self._at(xy, 0.0), self._at(xy, 0.004)
        dx, dy = s1.x() - s0.x(), s1.y() - s0.y()
        ln = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / ln * 9, dx / ln * 9
        p.setPen(QPen(COL_A, 3))
        p.drawLine(QPointF(s0.x() - nx, s0.y() - ny), QPointF(s0.x() + nx, s0.y() + ny))
        p.setPen(qcolor("faint"))
        p.setFont(ui_font(10))
        note = "green: B faster   red: B slower" if cols is not None else ("" if self.points is not None
                                                                          else "track outline not recorded yet")
        p.drawText(QRectF(10, self.height() - 22, self.width() - 20, 16), Qt.AlignmentFlag.AlignCenter, note)
        p.end()
        return pm

    def paintEvent(self, e):
        key = (id(self.points), id(self.a), id(self.b), self.width(), self.height())
        if self._cache is None or self._cache[0] != key:
            self._cache = (key, self._base())
        p = QPainter(self)
        p.drawPixmap(0, 0, self._cache[1])
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        x0, x1 = self.range
        if x1 - x0 < 0.999:  # priartinta atkarpa - balta
            xy = self._xy()
            pts = [self._at(xy, g) for g in np.linspace(x0, x1, max(4, int((x1 - x0) * 400) + 2))]
            p.setPen(QPen(QColor(255, 255, 255, 230), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin))
            p.drawPolyline(QPolygonF(pts))
        if self.pos is None:
            return
        c = self._at(self._xy(), self.pos)
        p.setPen(QPen(QColor(15, 16, 20), 2))
        p.setBrush(COL_A)
        p.drawEllipse(c, 7, 7)
        p.setPen(QPen(QColor(255, 255, 255), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, 11, 11)


    # ---- pelė ----
    # Kaip Garage61: tempk per grafiką - priartina tą vietą; ratukas - artinti / tolinti;
    # dešinys pelės mygtukas arba Shift + tempimas - stumti; dvigubas spustelėjimas - visas ratas.
    def _gx_at(self, x):
        r = self._rects()[0][2]
        return self.x0 + (x - r.left()) / r.width() * (self.x1 - self.x0)

    def mouseMoveEvent(self, e):
        x = e.position().x()
        if self._drag is not None:
            r = self._rects()[0][2]
            dx = (self._drag[0] - x) / r.width() * (self._drag[2] - self._drag[1])
            span = self._drag[2] - self._drag[1]
            self.set_range(self._drag[1] + dx, self._drag[1] + dx + span)
        elif getattr(self, "_sel", None) is not None:
            r = self._rects()[0][2]
            self._sel = (self._sel[0], min(max(x, r.left()), r.right()))
        self._hover = x
        self.update()
        gx = self.hover_pct()
        self.hovered.emit(-1.0 if gx is None else float(gx))

    def mousePressEvent(self, e):
        x = e.position().x()
        pan = e.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton) or (
            e.button() == Qt.MouseButton.LeftButton and e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if pan:
            self._drag = (x, self.x0, self.x1)
        elif e.button() == Qt.MouseButton.LeftButton and self.a is not None:
            r = self._rects()[0][2]
            if r.left() <= x <= r.right():
                self._sel = (x, x)

    def mouseReleaseEvent(self, e):
        self._drag = None
        sel = getattr(self, "_sel", None)
        self._sel = None
        if sel is not None and abs(sel[1] - sel[0]) > 6:
            a_, b_ = sorted(sel)
            self.set_range(self._gx_at(a_), self._gx_at(b_))
        self.update()

    def mouseDoubleClickEvent(self, e):
        self._sel = None
        self.reset_zoom()

    def leaveEvent(self, e):
        self._hover = None
        self.update()
        self.hovered.emit(-1.0)

    def wheelEvent(self, e):
        gx = self._gx_at(e.position().x())
        k = 0.8 if e.angleDelta().y() > 0 else 1.25
        span = min(1.0, max(0.002, (self.x1 - self.x0) * k))
        x0 = gx - (gx - self.x0) * span / (self.x1 - self.x0)
        self.set_range(x0, x0 + span)
        gx = self.hover_pct()
        self.hovered.emit(-1.0 if gx is None else float(gx))


# ====================================================================== puslapis
class TelemetryPage(Page):
    TITLE = "Telemetry"
    SUBTITLE = "Your laps this session, and lap against lap: your own or a friend's"
    MAX_W = 1400

    def __init__(self, center):
        super().__init__(center)
        self.imported = []  # Lap
        self._ver = None
        d = self.ctx.config.data.setdefault("telemetry", {"record": True, "hz": 30, "auto_save_best": True})

        rec = Card("Recording", "Only your own car, only while you drive. Laps stay in memory; your best lap per "
                                "car and track is saved so you can compare later or send it to a friend.")
        t = Toggle(bool(d.get("record", True)))
        t.toggled.connect(lambda v: self._set("record", bool(v)))
        rec.add(SettingRow("Record my laps", t))
        seg = Segmented({"30": "30 Hz", "60": "60 Hz"}, str(int(d.get("hz", 30))))
        seg.changed.connect(lambda v: self._set("hz", int(v)))
        rec.add(SettingRow("Sample rate", seg, "60 Hz is more detailed in fast corners and costs a little more CPU."))
        t_ses = Toggle(bool(d.get("save_sessions", True)))
        t_ses.toggled.connect(lambda v: self._set("save_sessions", bool(v)))
        rec.add(SettingRow("Save every session", t_ses, "Practice, qualifying and race laps are kept on this PC "
                                                        "(last 50 sessions, about 2-3 MB per race)."))
        self.content.addWidget(rec)

        ses = Card("Session")
        srow = QHBoxLayout()
        srow.setSpacing(10)
        self.c_ses = Combo({"live": "Current session"}, "live", 460)
        self.c_ses.changed.connect(self._pick_session)
        srow.addWidget(self.c_ses)
        b_sdir = button("Open sessions folder", "ghost", "folder")
        b_sdir.clicked.connect(self._open_sessions)
        srow.addStretch(1)
        srow.addWidget(b_sdir)
        ses.add(srow)
        self.content.addWidget(ses)
        self.source = "live"
        self._past = {}  # aplankas -> ratai
        self._ses_list_key = None

        rep = Card("Session report")
        self.kpis = QHBoxLayout()
        self.kpis.setSpacing(12)
        rep.add(self.kpis)
        self.chart = LapTimesChart()
        rep.add(self.chart)
        self.table = QGridLayout()
        self.table.setHorizontalSpacing(18)
        self.table.setVerticalSpacing(2)
        rep.add(self.table)
        self.content.addWidget(rep)

        cmp_ = Card("Compare laps", "Drag across the graphs to zoom into that part of the lap (or click a corner on "
                                    "the map). Mouse wheel zooms, right-drag moves, double-click shows the whole lap.")
        row = QHBoxLayout()
        row.setSpacing(10)
        self.c_a = Combo({}, None, 300)
        self.c_b = Combo({}, None, 300)
        self.c_a.changed.connect(lambda _: self._compare())
        self.c_b.changed.connect(lambda _: self._compare())
        la, lb = label("A", "h3"), label("B", "h3")
        la.setStyleSheet(f"color: {COL_A.name()};")
        lb.setStyleSheet(f"color: {COL_B.name()};")
        row.addWidget(la)
        row.addWidget(self.c_a)
        row.addSpacing(8)
        row.addWidget(lb)
        row.addWidget(self.c_b)
        row.addStretch(1)
        cmp_.add(row)
        btns = QHBoxLayout()
        b_imp = button("Import lap...", None, "download")
        b_imp.clicked.connect(self._import)
        b_exp = button("Export lap A...", "ghost", "upload")
        b_exp.clicked.connect(self._export)
        b_csv = button("Export A as CSV", "ghost", "list")
        b_csv.clicked.connect(self._export_csv)
        b_dir = button("Open laps folder", "ghost", "folder")
        b_dir.clicked.connect(lambda: (os.makedirs(laps_dir(), exist_ok=True), open_folder(laps_dir())))
        for b in (b_imp, b_exp, b_csv):
            btns.addWidget(b)
        btns.addStretch(1)
        btns.addWidget(b_dir)
        cmp_.add(btns)
        self.trace = TraceView()
        self.mini = TrackMini()
        self.trace.hovered.connect(self.mini.set_pos)
        self.trace.zoomed.connect(self.mini.set_range)
        self.mini.clicked.connect(lambda g: self.trace.set_range(g - 0.03, g + 0.03))
        tr_row = QHBoxLayout()
        tr_row.setSpacing(14)
        side = QVBoxLayout()
        side.addWidget(self.mini, 0, Qt.AlignmentFlag.AlignHCenter)
        side.addStretch(1)
        tr_row.addLayout(side)
        tr_row.addWidget(self.trace, 1)
        self.tr_row = tr_row
        cmp_.add(tr_row)
        self.content.addWidget(cmp_)
        self.content.addStretch(1)

    # ---- duomenys ----
    def recorder(self):
        eng = getattr(self.ctx, "engine", None)
        return getattr(getattr(eng, "timing", None), "recorder", None)

    def _set(self, k, v):
        self.ctx.config.data.setdefault("telemetry", {})[k] = v
        self.ctx.save_config_soon()

    def _live_laps(self):
        r = self.recorder()
        return list(r.laps) if r is not None else []

    def _session_laps(self):
        if self.source != "live":
            if self.source not in self._past:
                from ..sessions import SessionStore
                self._past[self.source] = SessionStore.load(self.source)
            return self._past[self.source]
        return self._live_laps()

    def _store(self):
        return getattr(self.ctx, "sessions", None)

    def _open_sessions(self):
        st = self._store()
        if st is not None:
            os.makedirs(st.root, exist_ok=True)
            open_folder(st.root)

    def _fill_sessions(self):
        st = self._store()
        items = st.list() if st is not None else []
        key = tuple(f for f, _ in items)
        if key == self._ses_list_key:
            return
        self._ses_list_key = key
        cur = self.source
        self.c_ses.blockSignals(True)
        self.c_ses.clear()
        self.c_ses._keys = ["live"]
        self.c_ses.addItem("Current session", "live")
        for folder, m in items:
            n = len(m.get("laps") or {})
            best = T.fmt(m.get("best")) if m.get("best") else "–"
            kind = (m.get("type") or "session").capitalize()
            txt = f"{(m.get('started') or '')[:16]}   {m.get('track') or ''}   {kind}   {n} laps   best {best}"
            self.c_ses._keys.append(folder)
            self.c_ses.addItem(txt, folder)
        if cur in self.c_ses._keys:
            self.c_ses.setCurrentIndex(self.c_ses._keys.index(cur))
        self.c_ses.blockSignals(False)

    def _pick_session(self, key):
        self.source = key or "live"
        self.trace.reset_zoom()
        self._refresh(force=True)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        from PySide6.QtWidgets import QBoxLayout
        narrow = self.viewport().width() < 1150  # mažesniame ekrane žemėlapis virš grafikų
        d = QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight
        if self.tr_row.direction() != d:
            self.tr_row.setDirection(d)

    def _saved_best(self):
        r = self.recorder()
        meta = r.meta if r is not None else {}
        path = best_path(meta.get("track_key", ""), meta.get("car", "")) if meta.get("track_key") else None
        if path and os.path.isfile(path):
            try:
                lap = T.load_lap(path)
                lap.meta["imported"] = False
                lap.meta["saved_best"] = True
                return lap
            except (OSError, ValueError, KeyError):
                return None
        return None

    def _options(self):
        opts = []
        laps = self._session_laps()
        past = self.source != "live"
        best = min((x.lap_time for x in laps if x.valid), default=None)
        for x in reversed(laps):
            if not x.has_trace:
                continue
            tag = " · best" if x.valid and x.lap_time == best else ("" if x.valid else " · pit" if x.pit else " · invalid")
            opts.append((f"s{id(x)}", f"Lap {x.number}   {T.fmt(x.lap_time)}{tag}", x))
        if past:  # lyginimui su seną sesiją - ir dabartinės sesijos ratai
            for x in reversed(self._live_laps()):
                if x.has_trace:
                    opts.append((f"l{id(x)}", f"Now: lap {x.number}   {T.fmt(x.lap_time)}", x))
        sb = self._saved_best()
        if sb is not None:
            opts.append(("saved", f"My saved best   {T.fmt(sb.lap_time)}   ({sb.meta.get('date', '')[:10]})", sb))
        for i, x in enumerate(self.imported):
            who = x.meta.get("driver") or "imported"
            opts.append((f"i{i}", f"{who}   {T.fmt(x.lap_time)}   ({x.meta.get('track', '')})", x))
        return opts

    # ---- UI ----
    def on_show(self):
        self._refresh(force=True)

    def tick(self, snap):
        if self.isVisible():
            self._refresh()

    def _refresh(self, force=False):
        r = self.recorder()
        self._fill_sessions()
        ver = (r.version if r is not None else -1, len(self.imported), self.source)
        if ver == self._ver and not force:
            return
        self._ver = ver
        laps = self._session_laps()
        self._fill_report(laps)
        opts = self._options()
        self._lap_by_key = {k: lap for k, _, lap in opts}
        for combo, default in ((self.c_a, "best"), (self.c_b, "last")):
            cur = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo._keys = [k for k, _, _ in opts] + ["none"]
            for k, text, _ in opts:
                combo.addItem(text, k)
            combo.addItem("None", "none")
            if cur in combo._keys:
                combo.setCurrentIndex(combo._keys.index(cur))
            else:
                combo.setCurrentIndex(self._default_index(opts, default))
            combo.blockSignals(False)
        self._compare()

    def _default_index(self, opts, which):
        if not opts:
            return 0
        if which == "best":
            valid = [(i, lap) for i, (_, _, lap) in enumerate(opts) if lap.valid]
            return min(valid, key=lambda x: x[1].lap_time)[0] if valid else 0
        # B: naujausias ratas, kuris nėra A
        a = self.c_a.currentData()
        for i, (k, _, _) in enumerate(opts):
            if k != a:
                return i
        return len(opts)  # None

    def _fill_report(self, laps):
        clear_layout(self.kpis)
        timed = [x for x in laps if x.lap_time > 0]
        valid = [x.lap_time for x in timed if x.valid]
        best = min(valid) if valid else None
        avg = sum(valid) / len(valid) if valid else None
        cons = float(np.std(valid)) if len(valid) >= 3 else None
        fuel = [x.meta.get("fuel_used") for x in timed if x.valid and x.meta.get("fuel_used")]
        for title, val in (("Laps", str(len(timed))), ("Best", T.fmt(best)), ("Average", T.fmt(avg)),
                           ("Consistency", f"± {cons:.2f}s" if cons is not None else "–"),
                           ("Fuel / lap", f"{sum(fuel) / len(fuel):.2f} l" if fuel else "–")):
            self.kpis.addWidget(KpiTile(title, val))
        self.chart.set_laps(timed)
        clear_layout(self.table)
        heads = ("Lap", "Time", "To best", "Position", "Fuel", "")
        for c, h in enumerate(heads):
            self.table.addWidget(label(h, "faint"), 0, c)
        for r, x in enumerate(reversed(timed[-12:]), start=1):
            d = x.lap_time - best if best and x.valid else None
            self.table.addWidget(label(str(x.number)), r, 0)
            self.table.addWidget(label(T.fmt(x.lap_time), "h3" if x.lap_time == best else None), r, 1)
            self.table.addWidget(label(f"+{d:.3f}" if d else ("best" if d == 0 else "–"), "muted"), r, 2)
            pos = x.meta.get("position")
            self.table.addWidget(label(f"P{pos}" if pos else "–", "muted"), r, 3)
            fu = x.meta.get("fuel_used")
            self.table.addWidget(label(f"{fu:.2f} l" if fu else "–", "muted"), r, 4)
            self.table.addWidget(label("pit" if x.pit else ("" if x.valid else "invalid"), "faint"), r, 5)
        self.table.setColumnStretch(5, 1)

    def _lap(self, combo):
        return getattr(self, "_lap_by_key", {}).get(combo.currentData())

    def _compare(self):
        a, b = self._lap(self.c_a), self._lap(self.c_b)
        if a is None and b is not None:
            a, b = b, None
        r = self.recorder()
        tm = (a.meta.get("track_m") if a is not None else 0) or (r.track_m if r is not None else 0)
        units = (self.ctx.config.widget("inputs") or {}).get("unit", "kmh")
        self.trace.unit_kmh = units != "mph"
        self.trace.set_laps(a, b if b is not a else None, tm)
        self.mini.set_data(self._track_points(a), a, b if b is not a else None)

    def _track_points(self, lap):
        """Trasos kontūras: iš rato failo (draugo ratas) arba šios trasos įrašytas žemėlapis."""
        if lap is None:
            return None
        if lap.track_map is not None:
            return lap.track_map
        eng = getattr(self.ctx, "engine", None)
        tm = getattr(getattr(eng, "timing", None), "trackmap", None)
        key = lap.meta.get("track_key")
        if tm is not None and tm.points is not None and (not key or str(tm.key) == str(key)):
            return tm.points
        if key:  # išsaugotas žemėlapis diske
            path = os.path.join(app_dir(), "maps", f"{key}.json")
            try:
                import json
                with open(path, encoding="utf-8") as fh:
                    pts = np.asarray(json.load(fh)["pts"], dtype=float)
                if pts.ndim == 2 and pts.shape[1] == 2:
                    return pts
            except (OSError, ValueError, KeyError):
                pass
        return None

    # ---- failai ----
    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import lap", laps_dir(), "LTH lap (*.lthlap)")
        if not path:
            return
        try:
            lap = T.load_lap(path)
        except (OSError, ValueError, KeyError) as e:
            QMessageBox.warning(self, "Import lap", f"Could not read this file.\n\n{e}")
            return
        r = self.recorder()
        mine = r.meta.get("track_key") if r is not None else None
        if mine and lap.meta.get("track_key") and lap.meta.get("track_key") != mine:
            QMessageBox.information(self, "Import lap", f"This lap is from {lap.meta.get('track', 'another track')}. "
                                                        "It is compared by lap distance, so corners may not line up.")
        self.imported.append(lap)
        self._refresh(force=True)
        key = f"i{len(self.imported) - 1}"
        if key in self.c_b._keys:
            self.c_b.setCurrentIndex(self.c_b._keys.index(key))

    def _export(self):
        lap = self._lap(self.c_a)
        if lap is None:
            return
        name = f"{_safe(lap.meta.get('track', 'track'))}_{_safe(lap.meta.get('car_name') or lap.meta.get('car', 'car'))}" \
               f"_{T.fmt(lap.lap_time).replace(':', 'm').replace('.', 's')}.lthlap"
        os.makedirs(laps_dir(), exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Export lap", os.path.join(laps_dir(), name), "LTH lap (*.lthlap)")
        if path:
            try:
                T.save_lap(path, lap, self._track_points(lap))
            except OSError as e:
                QMessageBox.warning(self, "Export lap", str(e))

    def _export_csv(self):
        lap = self._lap(self.c_a)
        if lap is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", os.path.join(laps_dir(), "lap.csv"), "CSV (*.csv)")
        if path:
            try:
                T.save_csv(path, lap)
            except OSError as e:
                QMessageBox.warning(self, "Export CSV", str(e))


def autosave_best(recorder, state: dict, track_map=None) -> str | None:
    """Kviečiama UI gijoje ~1 Hz: išsaugo geriausią galiojantį ratą (jei geresnis nei diske)."""
    if recorder is None or recorder.version == state.get("ver"):
        return None
    state["ver"] = recorder.version
    best = recorder.best()
    meta = recorder.meta
    if best is None or not meta.get("track_key") or not meta.get("car"):
        return None
    path = best_path(meta["track_key"], meta["car"])
    key = (path, round(best.lap_time, 4))
    if state.get("saved") == key:
        return None
    old = state.get("disk", {}).get(path)
    if old is None and os.path.isfile(path):
        try:
            old = T.load_lap(path).lap_time
        except (OSError, ValueError, KeyError):
            old = None
        state.setdefault("disk", {})[path] = old
    if old is not None and best.lap_time >= old - 1e-4:
        return None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        T.save_lap(path, best, track_map)
    except OSError:
        return None
    state["saved"] = key
    state.setdefault("disk", {})[path] = best.lap_time
    return path
