"""Telemetry puslapis: sesijos ataskaita ir dviejų ratų palyginimas (savo ar draugo .lthlap)."""
from __future__ import annotations

import math
import os
import re

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QMessageBox, QWidget

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
    """Kanalai pagal atstumą: laiko skirtumas, greitis, pedalai, vairas, pavara. Ratukas - artinti."""

    PANELS = (("delta", "Delta", 0.9), ("speed", "Speed", 1.6), ("pedals", "Throttle / brake", 1.1),
              ("steer", "Steering", 0.9), ("gear", "Gear", 0.7))

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
        self.setMinimumHeight(520)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_laps(self, a, b, track_m):
        self.a, self.b, self.track_m = a, b, float(track_m or 0)
        self._cache = None
        self.update()

    def reset_zoom(self):
        self.x0, self.x1 = 0.0, 1.0
        self._cache = None
        self.update()

    # ---- geometrija ----
    def _rects(self):
        r = QRectF(self.rect()).adjusted(64, 6, -12, -24)
        total = sum(k for *_, k in self.PANELS)
        gap = 10
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

    # ---- piešimas ----
    def _paint_base(self) -> QPixmap:
        dpr = self.devicePixelRatioF()
        pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(ui_font(10))
        a, b = self.a, self.b
        for key, title, rect in self._rects():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qcolor("bg"))
            p.drawRoundedRect(rect.adjusted(-4, -2, 4, 2), 6, 6)
            p.setPen(qcolor("faint"))
            p.drawText(QRectF(0, rect.top(), 58, 16), Qt.AlignmentFlag.AlignRight, title.split(" /")[0])
            if a is None:
                continue
            g = a.grid
            if key == "delta":
                if b is None:
                    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Pick a second lap to see where time is won or lost")
                    continue
                d = T.delta_trace(a, b)
                m = float(max(0.3, np.nanmax(np.abs(d)) * 1.1))
                p.setPen(QPen(qcolor("border2"), 1))
                ymid = rect.center().y()
                p.drawLine(QPointF(rect.left(), ymid), QPointF(rect.right(), ymid))
                p.setPen(qcolor("faint"))
                p.drawText(QRectF(0, rect.top() + 14, 58, 14), Qt.AlignmentFlag.AlignRight, f"+{m:.1f}s")
                p.drawText(QRectF(0, rect.bottom() - 14, 58, 14), Qt.AlignmentFlag.AlignRight, f"-{m:.1f}s")
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
                    p.setPen(QPen(qcolor("text"), 1.4))
                    p.drawPolyline(poly)
                continue
            chans = {"speed": [("speed", 0, None)], "pedals": [("throttle", 0, 1), ("brake", 0, 1)],
                     "steer": [("steer", None, None)], "gear": [("gear", 0, None)]}[key]
            for ch, lo, hi in chans:
                series = [(lap, T.channel_on(lap, g, ch)) for lap in (a, b) if lap is not None]
                series = [(lap, v) for lap, v in series if v is not None]
                if not series:
                    continue
                if lo is None or hi is None:
                    allv = np.concatenate([v for _, v in series])
                    if ch == "steer":
                        m = float(max(0.2, np.nanmax(np.abs(allv))))
                        lo, hi = -m, m
                    else:
                        hi = float(max(1.0, np.nanmax(allv) * 1.05))
                for lap, v in reversed(series):
                    col = QColor(COL_A if lap is a else COL_B)
                    if key == "pedals":
                        col = QColor("#3DDC97") if ch == "throttle" else QColor("#FF4D5E")
                        if lap is b:
                            col.setAlpha(150)
                    pen = QPen(col, 1.6 if lap is a else 1.4)
                    if lap is b and key == "pedals":
                        pen.setStyle(Qt.PenStyle.DashLine)
                    p.setPen(pen)
                    p.drawPolyline(self._poly(g, v, QRectF(rect), lo, hi))
                if key == "speed":
                    k = 3.6 if self.unit_kmh else 2.236936
                    p.setPen(qcolor("faint"))
                    p.drawText(QRectF(0, rect.top() + 14, 58, 14), Qt.AlignmentFlag.AlignRight,
                               f"{hi * k:.0f}")
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

    def paintEvent(self, e):
        key = (id(self.a), id(self.b), self.width(), self.height(), self.x0, self.x1, self.unit_kmh)
        if self._cache is None or self._cache[0] != key:
            self._cache = (key, self._paint_base())
        p = QPainter(self)
        p.drawPixmap(0, 0, self._cache[1])
        if self._hover is None or self.a is None:
            return
        rects = self._rects()
        top, bottom = rects[0][2], rects[-1][2]
        x = self._hover
        if not (top.left() <= x <= top.right()):
            return
        gx = self.x0 + (x - top.left()) / top.width() * (self.x1 - self.x0)
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

    # ---- pelė ----
    def mouseMoveEvent(self, e):
        x = e.position().x()
        if self._drag is not None:
            r = self._rects()[0][2]
            dx = (self._drag[0] - x) / r.width() * (self._drag[2] - self._drag[1])
            span = self._drag[2] - self._drag[1]
            x0 = min(max(0.0, self._drag[1] + dx), 1.0 - span)
            self.x0, self.x1 = x0, x0 + span
            self._cache = None
        self._hover = x
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = (e.position().x(), self.x0, self.x1)

    def mouseReleaseEvent(self, e):
        self._drag = None

    def mouseDoubleClickEvent(self, e):
        self.reset_zoom()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def wheelEvent(self, e):
        r = self._rects()[0][2]
        gx = self.x0 + (e.position().x() - r.left()) / r.width() * (self.x1 - self.x0)
        k = 0.8 if e.angleDelta().y() > 0 else 1.25
        span = min(1.0, max(0.01, (self.x1 - self.x0) * k))
        x0 = gx - (gx - self.x0) * span / (self.x1 - self.x0)
        x0 = min(max(0.0, x0), 1.0 - span)
        self.x0, self.x1 = x0, x0 + span
        self._cache = None
        self.update()


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
        self.content.addWidget(rec)

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

        cmp_ = Card("Compare laps", "Wheel to zoom, drag to move, double-click to see the whole lap.")
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
        cmp_.add(self.trace)
        self.content.addWidget(cmp_)
        self.content.addStretch(1)

    # ---- duomenys ----
    def recorder(self):
        eng = getattr(self.ctx, "engine", None)
        return getattr(getattr(eng, "timing", None), "recorder", None)

    def _set(self, k, v):
        self.ctx.config.data.setdefault("telemetry", {})[k] = v
        self.ctx.save_config_soon()

    def _session_laps(self):
        r = self.recorder()
        return list(r.laps) if r is not None else []

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
        best = min((x.lap_time for x in laps if x.valid), default=None)
        for x in reversed(laps):
            if not x.has_trace:
                continue
            tag = " · best" if x.valid and x.lap_time == best else ("" if x.valid else " · pit" if x.pit else " · invalid")
            opts.append((f"s{id(x)}", f"Lap {x.number}   {T.fmt(x.lap_time)}{tag}", x))
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
        ver = (r.version if r is not None else -1, len(self.imported))
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
                T.save_lap(path, lap)
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


def autosave_best(recorder, state: dict) -> str | None:
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
        T.save_lap(path, best)
    except OSError:
        return None
    state["saved"] = key
    state.setdefault("disk", {})[path] = best.lap_time
    return path
