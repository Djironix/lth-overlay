"""Overview (Dashboard): sveikinimas, trasos kontūras, statistika iš išsaugotų sesijų."""
from __future__ import annotations

import json
import math
import os

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from lth_timing import telemetry as T

from ..config import app_dir
from ..registry import WIDGETS
from .components import Card, button, clear_layout, label
from .pages import Page
from .style import T as TH, icon_pixmap, qcolor, ui_font

SESSION_NAMES = {"race": "Race", "qualify": "Qualifying", "practice": "Practice", "warmup": "Warmup"}


def _track_points(track_key: str):
    if not track_key:
        return None
    try:
        with open(os.path.join(app_dir(), "maps", f"{track_key}.json"), encoding="utf-8") as fh:
            pts = np.asarray(json.load(fh)["pts"], dtype=float)
        return pts if pts.ndim == 2 and pts.shape[1] == 2 else None
    except (OSError, ValueError, KeyError):
        return None


def _default_shape():
    a = np.linspace(0, 2 * math.pi, 240, endpoint=False)
    r = 1 + 0.28 * np.sin(3 * a + 0.4) + 0.12 * np.cos(5 * a)
    return np.stack([0.5 + 0.42 * r * np.cos(a), 0.5 + 0.36 * r * np.sin(a)], axis=1)


def _fit(pts, rect: QRectF):
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    span = max(float((hi - lo).max()), 1e-6)
    k = min(rect.width(), rect.height()) / span
    mid = (lo + hi) / 2
    return [QPointF(rect.center().x() + (x - mid[0]) * k, rect.center().y() + (y - mid[1]) * k) for x, y in pts]


class TrackGlow(QWidget):
    """Didelis švytintis trasos kontūras (paskutinė trasa arba abstrakti forma)."""

    def __init__(self, thin=False):
        super().__init__()
        self.pts = None
        self.thin = thin
        self.setMinimumHeight(120)

    def set_points(self, pts):
        self.pts = pts
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pts = self.pts if self.pts is not None else _default_shape()
        poly = QPolygonF(_fit(pts, QRectF(self.rect()).adjusted(14, 14, -14, -14)))
        poly.append(poly[0])
        acc = qcolor("accent")
        if self.thin:
            p.setPen(QPen(QColor(200, 204, 210), 1.6))
            p.drawPolyline(poly)
            return
        for w, a in ((16, 18), (9, 40), (5, 90)):  # švytėjimas
            c = QColor(acc)
            c.setAlpha(a)
            p.setPen(QPen(c, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPolyline(poly)
        p.setPen(QPen(acc, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPolyline(poly)
        c0 = poly[int(len(poly) * 0.12)]
        p.setBrush(acc)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(c0, 5, 5)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(acc, 1.2))
        p.drawEllipse(c0, 10, 10)


class Donut(QWidget):
    def __init__(self):
        super().__init__()
        self.frac = 0.0
        self.setMinimumSize(160, 160)

    def set(self, frac, empty=False):
        self.frac = max(0.0, min(1.0, frac))
        self.empty = empty
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = min(self.width(), self.height()) - 24
        r = QRectF((self.width() - s) / 2, (self.height() - s) / 2, s, s)
        p.setPen(QPen(QColor(255, 255, 255, 22), 16))
        p.drawEllipse(r)
        p.setPen(QPen(qcolor("accent"), 16, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(r, 90 * 16, int(-self.frac * 360 * 16))
        p.setPen(qcolor("text"))
        p.setFont(ui_font(24, QFont.Weight.Bold))
        empty = getattr(self, "empty", True)
        p.drawText(r.adjusted(0, -10, 0, -10), Qt.AlignmentFlag.AlignCenter, "–" if empty else f"{self.frac * 100:.0f}%")
        p.setPen(qcolor("faint"))
        p.setFont(ui_font(11))
        p.drawText(r.adjusted(0, 30, 0, 30), Qt.AlignmentFlag.AlignCenter, "no laps yet" if empty else "of laps")


class WeekBars(QWidget):
    DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

    def __init__(self):
        super().__init__()
        self.vals = [0] * 7
        self.setMinimumHeight(130)

    def set(self, vals):
        self.vals = list(vals)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n = 7
        gap = 12
        w = (self.width() - gap * (n - 1)) / n
        top, bot = 4, self.height() - 22
        mx = max(self.vals) or 1
        best = self.vals.index(max(self.vals)) if any(self.vals) else -1
        for i, v in enumerate(self.vals):
            x = i * (w + gap)
            h = max(6.0, (bot - top) * v / mx) if v else 6.0
            r = QRectF(x, bot - h, w, h)
            if i == best:
                g = QLinearGradient(0, r.top(), 0, r.bottom())
                g.setColorAt(0, QColor("#F3D27E"))
                g.setColorAt(1, qcolor("accent"))
                p.setBrush(g)
            else:
                p.setBrush(QColor(255, 255, 255, 18))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(r, 8, 8)
            p.setPen(qcolor("faint"))
            p.setFont(ui_font(11))
            p.drawText(QRectF(x, bot + 4, w, 16), Qt.AlignmentFlag.AlignCenter, self.DAYS[i])
            if v:
                p.setPen(qcolor("muted"))
                p.drawText(QRectF(x, r.top() - 16, w, 14), Qt.AlignmentFlag.AlignCenter, str(v))


class StatTile(QWidget):
    """Kortelė su apskritimo ikona: „Laps this month 412“."""

    def __init__(self, title, icon_name):
        super().__init__()
        self.setObjectName("StatTile")
        self.setStyleSheet(f"QWidget#StatTile {{ background: {TH['surface']}; border: 1px solid {TH['border']};"
                           f" border-radius: 18px; }}")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        h = QHBoxLayout(self)
        h.setContentsMargins(18, 16, 18, 16)
        h.setSpacing(14)
        self.icon_name = icon_name
        ic = QWidget()
        ic.setFixedSize(46, 46)
        ic.paintEvent = lambda e, w=ic: self._paint_icon(w)
        h.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(label(title, "faint"))
        self.value = label("–", "kpi")
        col.addWidget(self.value)
        h.addLayout(col, 1)

    def _paint_icon(self, w):
        p = QPainter(w)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        acc = qcolor("accent")
        c = QColor(acc)
        c.setAlpha(40)
        p.setBrush(c)
        c2 = QColor(acc)
        c2.setAlpha(110)
        p.setPen(QPen(c2, 1))
        p.drawEllipse(QRectF(1, 1, 44, 44))
        p.drawPixmap(13, 13, icon_pixmap(self.icon_name, TH["accent"], 20))


class OverviewPage(Page):
    TITLE = "Overview"
    SUBTITLE = "Everything at a glance"
    MAX_W = 1500

    def __init__(self, center):
        super().__init__(center)
        self.widget().layout().setContentsMargins(32, 18, 32, 12)  # telpa į 900 px aukščio langą be slinkties
        main = QHBoxLayout()
        main.setSpacing(24)
        # ---- kairė: sveikinimas ir trasa ----
        left = QVBoxLayout()
        left.setSpacing(4)
        self.hello = label("Welcome back,", "muted")
        left.addWidget(self.hello)
        rr = label("Ready to race?")
        rr.setStyleSheet(f"font-size: 24px; font-weight: 700; color: {TH['text']};")
        left.addWidget(rr)
        left.addSpacing(18)
        t = label("LTH Overlays")
        t.setStyleSheet(f"font-size: 52px; font-weight: 800; color: {TH['text']};")
        left.addWidget(t)
        self.status = label("Waiting for iRacing", "muted", wrap=True)
        left.addWidget(self.status)
        left.addSpacing(10)
        b_edit = button("Edit layout on screen", "primary", "move")
        b_edit.clicked.connect(lambda: self.ctx.toggle_edit())
        b_tel = button("Open telemetry", None, "delta")
        b_tel.clicked.connect(lambda: center.go("telemetry"))
        row = QHBoxLayout()
        row.addWidget(b_edit)
        row.addWidget(b_tel)
        row.addStretch(1)
        left.addLayout(row)
        self.glow = TrackGlow()
        self.glow.setMinimumHeight(250)
        left.addWidget(self.glow, 1)
        self.on_screen = label("", "faint", wrap=True)
        left.addWidget(self.on_screen)
        main.addLayout(left, 5)
        # ---- dešinė: statistika ----
        grid = QGridLayout()
        grid.setSpacing(16)
        self.t_laps = StatTile("Laps this month", "flag")
        self.t_time = StatTile("Time on track", "clock")
        grid.addWidget(self.t_laps, 0, 0)
        grid.addWidget(self.t_time, 0, 1)
        self.c_last = Card("Latest session")
        box = QWidget()
        box.setObjectName("LastBox")
        box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        box.setStyleSheet(f"QWidget#LastBox {{ background: {TH['surface2']}; border-radius: 12px; }}")
        bh = QHBoxLayout(box)
        bh.setContentsMargins(12, 10, 12, 10)
        bh.setSpacing(10)
        self.last_badge = QLabel("")
        self.last_badge.setStyleSheet(f"background: {TH['accent']}; color: {TH['accent_text']}; font-size: 10px;"
                                      f" font-weight: 800; border-radius: 5px; padding: 2px 6px;")
        self.last_badge.hide()
        bh.addWidget(self.last_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        bc = QVBoxLayout()
        bc.setSpacing(2)
        self.last_head = label("No sessions yet", "h3", wrap=True)
        self.last_sub = label("Drive some laps - every session is saved.", "faint", wrap=True)
        bc.addWidget(self.last_head)
        bc.addWidget(self.last_sub)
        bh.addLayout(bc, 1)
        self.c_last.add(box)
        self.last_track = TrackGlow(thin=True)
        self.last_track.setFixedHeight(120)
        self.c_last.add(self.last_track)
        self.last_kv = QGridLayout()
        self.last_kv.setVerticalSpacing(6)
        self.c_last.add(self.last_kv)
        grid.addWidget(self.c_last, 1, 0)
        self.c_car = Card("Most driven car")
        self.donut = Donut()
        from PySide6.QtWidgets import QSizePolicy
        self.donut.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.c_car.add(self.donut)
        self.car_lbl = label("–", "muted", wrap=True)
        self.c_car.add(self.car_lbl)
        grid.addWidget(self.c_car, 1, 1)
        self.c_week = Card("This week", "Laps per day")
        self.week = WeekBars()
        self.c_week.add(self.week)
        grid.addWidget(self.c_week, 2, 0, 1, 2)
        wrap = QWidget()
        wrap.setLayout(grid)
        wrap.setMinimumWidth(560)
        main.addWidget(wrap, 4)
        self.content.addLayout(main)
        self.content.addStretch(1)
        self._key = None
        self._list_t = 0.0
        self._st = []

    def on_show(self):
        self._key = None
        self.tick(self.ctx.engine.latest)

    def _kv(self, rows):
        clear_layout(self.last_kv)
        for r, (k, v, col) in enumerate(rows):
            self.last_kv.addWidget(label(k, "faint"), r, 0)
            lv = label(v)
            if col:
                lv.setStyleSheet(f"color: {TH[col]};")
            self.last_kv.addWidget(lv, r, 1, Qt.AlignmentFlag.AlignRight)

    def _hello(self):
        snap = self.ctx.engine.latest
        me = next((r for r in snap.cars if r.is_me), None) if snap.connected else None
        name = (me.name if me is not None and me.name else self.ctx.config.data.get("driver_name")) or ""
        first = name.split()[0] if name.split() else ""
        self.hello.setText(f"Welcome back, {first}" if first else "Welcome back,")

    def tick(self, snap):
        from ..sessions import stats
        import time as _t
        now = _t.monotonic()
        if self._key is None or now - self._list_t > 5.0:  # disko skaitymas ne dažniau kaip kas 5 s
            self._list_t = now
            self._st = self.ctx.sessions.list() if getattr(self.ctx, "sessions", None) else []
            self._hello()
        st = self._st
        key = (tuple(f for f, _ in st), tuple(m.get("updated") for _, m in st[:1]))
        on = [s.title for s in WIDGETS if self.ctx.config.widget(s.name).get("visible")]
        self.on_screen.setText("On screen: " + (", ".join(on) if on else "nothing - open Widgets to add some"))
        if snap.connected:
            kind = SESSION_NAMES.get(snap.session_type, "Session")
            self.status.setText(f"iRacing is running · {kind} · {snap.track_name or ''} · {len(on)} widgets on")
            pts = getattr(getattr(self.ctx.engine.timing, "trackmap", None), "points", None)
            if pts is not None and self.glow.pts is not pts:
                self.glow.set_points(pts)
        else:
            self.status.setText(f"Waiting for iRacing · overlays appear when you join a session · {len(on)} widgets on")
        if key == self._key:
            return
        self._key = key
        s = stats(st)
        self.t_laps.value.setText(str(s["laps_month"]))
        mins = int(s["time_month_s"] // 60)
        self.t_time.value.setText(f"{mins // 60}h {mins % 60:02d}m")
        last = s["latest"]
        if last:
            kind = SESSION_NAMES.get(last.get("type") or "", "Session")
            self.last_badge.setText(kind.upper())
            self.last_badge.show()
            self.last_head.setText(last.get("car_name") or last.get("car") or "")
            self.last_sub.setText(f"{last.get('track') or ''}  ·  {(last.get('started') or '')[:16]}")
            pts = _track_points(last.get("track_key"))
            self.last_track.set_points(pts)
            if not snap.connected and pts is not None:
                self.glow.set_points(pts)
            rows = [("Best lap", T.fmt(last.get("best")), None), ("Laps", str(len(last.get("laps") or {})), None)]
            if last.get("position"):
                rows.append(("Position", f"P{last['position']}", None))
            self._kv(rows)
        top = s["top_car"]
        if top and top[1]:
            self.donut.set(top[2])
            self.car_lbl.setText(f"{top[0]}  ·  {top[1]} laps")
        else:
            self.donut.set(0.0, empty=True)
            self.car_lbl.setText("")
        self.week.set(s["week"])
