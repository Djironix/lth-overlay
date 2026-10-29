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


_SPA = None


def spa_track():
    """Spa-Francorchamps kontūras (pagal laikrodžio rodyklę, nuo boksų tiesiosios) ir tipinio GT3 rato
    laiko profilis (t: 0..1 kiekviename taške) - taškas lėtėja La Source, lekia Kemmel tiesiąja."""
    global _SPA
    if _SPA is None:
        try:
            with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "tracks", "spa.json"),
                      encoding="utf-8") as fh:
                d = json.load(fh)
            _SPA = (np.asarray(d["pts"], dtype=float), np.asarray(d["t"], dtype=float))
        except (OSError, ValueError, KeyError):
            a = np.linspace(0, 2 * math.pi, 240, endpoint=False)
            _SPA = (np.stack([0.5 + 0.4 * np.cos(a), 0.5 + 0.4 * np.sin(a)], axis=1), a / (2 * math.pi))
    return _SPA


def _fit(pts, rect: QRectF):
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    span = max(float((hi - lo).max()), 1e-6)
    k = min(rect.width(), rect.height()) / span
    mid = (lo + hi) / 2
    return [QPointF(rect.center().x() + (x - mid[0]) * k, rect.center().y() + (y - mid[1]) * k) for x, y in pts]


def _best_lap(folder, last):
    """Geriausias ratas paskutinei trasai: visų laikų rekordas šiai mašinai arba geriausias sesijos ratas."""
    from .telemetry_page import best_path
    cands = []
    if last.get("track_key") and last.get("car"):
        cands.append(best_path(last["track_key"], last["car"]))
    laps = last.get("laps") or {}
    valid = [(v[0], k) for k, v in laps.items() if v and v[1] and v[0] > 0]
    if folder and valid:
        cands.append(os.path.join(folder, f"lap_{int(min(valid)[1]):03d}.lthlap"))
    for path in cands:
        if os.path.isfile(path):
            try:
                return T.load_lap(path)
            except (OSError, ValueError, KeyError):
                continue
    return None


def _lap_profile(lap):
    """(rato dalis, laikas 0..1, rato laikas s) iš tikro rato telemetrijos."""
    try:
        g = np.asarray(lap.grid, dtype=float)
        t = np.maximum.accumulate(np.asarray(lap.data["time"], dtype=float))
        T_ = float(lap.lap_time)
        if len(g) < 20 or T_ <= 0 or not np.all(np.isfinite(t)):
            return None
        tn = np.clip(t / T_, 0.0, 1.0)
        if g[0] > 0:
            g, tn = np.insert(g, 0, 0.0), np.insert(tn, 0, 0.0)
        return g, tn, T_
    except (KeyError, TypeError, ValueError):
        return None


class TrackGlow(QWidget):
    """Švytintis trasos kontūras su važiuojančiu tašku.

    Taškas juda pagal rato laiko profilį: Spa - tipinis GT3 ratas, kita trasa - tavo geriausias ratas
    (iš telemetrijos), o kai važiuoji - tikra tavo vieta trasoje. Kontūras nupieštas vieną kartą į
    paveikslėlį, kas kadrą perpiešiamas tik mažas plotas aplink tašką (30 kadrų/s, tik kai matosi)."""

    FPS = 30
    TRAIL = 0.035  # uodegos ilgis (rato dalis)

    def __init__(self, thin=False):
        super().__init__()
        self.pts = None
        self.thin = thin
        self.setMinimumHeight(120)
        self._cache = None
        self._poly = None
        self._prof = None  # (pct, t 0..1, rato laikas s)
        self._live = None  # funkcija -> rato dalis arba None
        self._t0 = 0.0
        self._pct = 0.0
        self._dirty = QRectF()
        self._timer = None
        if not thin:
            self._timer = QTimer(self)
            self._timer.setInterval(int(1000 / self.FPS))
            self._timer.timeout.connect(self._step)

    # ---- duomenys ----
    def set_points(self, pts, profile=None):
        """pts - (N, 2) taškai rato tvarka nuo starto linijos. profile - (pct, t_norm, lap_s)."""
        if pts is self.pts and profile is None and self._prof is not None:
            return
        self.pts = pts
        if profile is None:
            if pts is None:
                sp, st = spa_track()
                profile = (np.linspace(0, 1, len(sp), endpoint=False), st, 137.0)
            else:
                n = len(pts)
                profile = (np.linspace(0, 1, n, endpoint=False), np.linspace(0, 1, n, endpoint=False), 120.0)
        self._prof = profile
        self._cache = None
        self.update()

    def set_live(self, fn):
        self._live = fn

    # ---- animacija ----
    def showEvent(self, e):
        super().showEvent(e)
        if self._timer is not None:
            import time as _t
            self._t0 = self._t0 or _t.monotonic()
            self._timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        if self._timer is not None:
            self._timer.stop()

    def _pct_now(self) -> float:
        if self._live is not None:
            v = self._live()
            if v is not None:
                return v % 1.0
        import time as _t
        pct, tn, lap_s = self._prof
        tau = ((_t.monotonic() - self._t0) / max(lap_s, 1.0)) % 1.0
        return float(np.interp(tau, np.append(tn, 1.0), np.append(pct, 1.0)))

    def _step(self):
        w = self.window()
        if w is not None and w.isMinimized():
            return
        if self._poly is None or self._prof is None:
            self.update()
            return
        self._pct = self._pct_now()
        r = self._dot_rect()
        self.update((r.united(self._dirty)).toAlignedRect())
        self._dirty = r

    def _at(self, pct):
        poly = self._poly
        n = len(poly)
        f = (pct % 1.0) * n
        i = int(f)
        k = f - i
        a, b = poly[i % n], poly[(i + 1) % n]
        return QPointF(a.x() + (b.x() - a.x()) * k, a.y() + (b.y() - a.y()) * k)

    def _trail(self):
        return [self._at(self._pct - self.TRAIL * j / 14) for j in range(15)]

    def _dot_rect(self):
        pts = self._trail()
        xs = [p.x() for p in pts]
        ys = [p.y() for p in pts]
        return QRectF(min(xs) - 16, min(ys) - 16, max(xs) - min(xs) + 32, max(ys) - min(ys) + 32)

    # ---- piešimas ----
    def _build(self):
        from PySide6.QtGui import QPixmap
        if self._prof is None:
            self.set_points(self.pts)
        pts = self.pts if self.pts is not None else spa_track()[0]
        dpr = self.devicePixelRatioF()
        pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        self._poly = _fit(pts, QRectF(self.rect()).adjusted(18, 18, -18, -18))
        poly = QPolygonF(self._poly)
        poly.append(poly[0])
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        acc = qcolor("accent")
        if self.thin:
            p.setPen(QPen(QColor(200, 204, 210), 1.6))
            p.drawPolyline(poly)
        else:
            for w, a in ((16, 16), (9, 36), (5, 80)):  # švytėjimas
                c = QColor(acc)
                c.setAlpha(a)
                p.setPen(QPen(c, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                p.drawPolyline(poly)
            p.setPen(QPen(acc, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPolyline(poly)
            # starto / finišo linija
            a0, a1 = self._poly[0], self._poly[1]
            dx, dy = a1.x() - a0.x(), a1.y() - a0.y()
            ln = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / ln * 9, dx / ln * 9
            p.setPen(QPen(QColor(255, 255, 255, 200), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            p.drawLine(QPointF(a0.x() - nx, a0.y() - ny), QPointF(a0.x() + nx, a0.y() + ny))
        p.end()
        self._cache = pm

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._cache = None

    def paintEvent(self, e):
        if self._cache is None or self._cache.size() != self.size() * self.devicePixelRatioF():
            self._build()
        p = QPainter(self)
        p.drawPixmap(0, 0, self._cache)
        if self.thin or self._poly is None:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        acc = qcolor("accent")
        tr = self._trail()
        for j in range(len(tr) - 1):  # uodega
            c = QColor("#FFF4D6")
            c.setAlpha(int(200 * (1 - j / (len(tr) - 1))))
            p.setPen(QPen(c, 3.2 - 2.4 * j / len(tr), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(tr[j], tr[j + 1])
        c0 = tr[0]
        halo = QColor(acc)
        halo.setAlpha(70)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(halo)
        p.drawEllipse(c0, 11, 11)
        p.setBrush(QColor("#FFF4D6"))
        p.drawEllipse(c0, 5, 5)


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
        self.track_cap = QLabel()
        self.track_cap.setTextFormat(Qt.TextFormat.RichText)
        self.track_cap.setWordWrap(True)
        self.track_cap.setStyleSheet(f"color: {TH['muted']}; font-size: 13px; background: transparent;")
        left.addWidget(self.track_cap)
        left.addSpacing(6)
        self.on_screen = label("", "faint", wrap=True)
        left.addWidget(self.on_screen)
        self._hero_key = None
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
        self.last_track.hide()
        self.c_last.add(self.last_track)
        self.last_kv = QGridLayout()
        self.last_kv.setVerticalSpacing(6)
        self.c_last.add(self.last_kv)
        self.c_last.body.addStretch(1)
        grid.addWidget(self.c_last, 1, 0)
        self.c_car = Card("Most driven car")
        self.donut = Donut()
        from PySide6.QtWidgets import QSizePolicy
        self.donut.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.donut.setMaximumHeight(210)
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
        self.content.addLayout(main, 1)  # užpildo visą aukštį - trasa didėja kartu su langu
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

    def _hero(self, snap, folder, last):
        """Didysis kontūras: važiuojant - dabartinė trasa ir tavo tikra vieta; kitaip - paskutinė važiuota trasa,
        taškas važiuoja tavo geriausio rato tempu; jei dar nieko nevažiavai - Spa."""
        tm = getattr(self.ctx.engine.timing, "trackmap", None)
        live_pts = getattr(tm, "points", None) if snap.connected else None
        if live_pts is not None:
            key = ("live", id(live_pts))
            if key != self._hero_key:
                self._hero_key = key
                self.glow.set_points(live_pts)
                eng = self.ctx.engine

                def live():
                    sn = eng.latest
                    pl = sn.player
                    return pl.lap_pct if sn.connected and sn.on_track and pl is not None else None
                self.glow.set_live(live)
                self.track_cap.setText(f"<b style='color:{TH['text']}'>{snap.track_name or 'Current track'}</b>"
                                       f"&nbsp;&nbsp;·&nbsp;&nbsp;live - the dot is you")
            return
        pts = _track_points(last.get("track_key")) if last else None
        key = ("last", folder, last.get("best") if last else None, pts is not None)
        if key == self._hero_key:
            return
        self._hero_key = key
        self.glow.set_live(None)
        if pts is None:
            self.glow.set_points(None)  # Spa
            hint = (f"{last.get('track') or 'your last track'} shows up here once its map is recorded (one clean lap)"
                    if last else "drive a session and your last track shows up here")
            self.track_cap.setText(f"<b style='color:{TH['text']}'>Spa-Francorchamps</b>&nbsp;&nbsp;·&nbsp;&nbsp;{hint}")
            return
        lap = _best_lap(folder, last)
        prof = _lap_profile(lap) if lap is not None else None
        if prof is None:  # rato telemetrijos nėra - tolygiu tempu pagal geriausią sesijos ratą
            n = len(pts)
            u = np.linspace(0, 1, n, endpoint=False)
            prof = (u, u, float(last.get("best") or 120.0))
            lap = None
        self.glow.set_points(pts, prof)
        name = last.get("track") or last.get("track_key") or "Last track"
        if lap is not None:
            how = f"the dot runs your best lap {T.fmt(lap.lap_time)}"
        else:
            how = "last driven"
        self.track_cap.setText(f"<b style='color:{TH['text']}'>{name}</b>&nbsp;&nbsp;·&nbsp;&nbsp;{how}")

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
        else:
            self.status.setText(f"Waiting for iRacing · overlays appear when you join a session · {len(on)} widgets on")
        self._hero(snap, st[0][0] if st else None, st[0][1] if st else None)
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
            self.last_track.setVisible(pts is not None)
            if pts is not None:
                self.last_track.set_points(pts)
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
