"""Orų langelis: šlapumas, temperatūros, vėjas santykinai su mašina, tendencija."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPen, QPolygonF

from ..window import OverlayWidget


RUBBER = {"clean": ("Clean", 0), "low usage": ("Low", 1), "moderately low usage": ("Moderately low", 2),
          "moderate usage": ("Moderate", 3), "moderately high usage": ("Moderately high", 4),
          "high usage": ("High", 5)}
CARDINAL = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def track_usage_text(raw: str) -> str:
    """iRacing SessionTrackRubberState -> „Moderately low (2/5)“. iRacing procentų neduoda - tik lygį
    sesijos pradžioje, todėl rodom lygį iš 5."""
    r = (raw or "").strip().lower()
    if not r:
        return ""
    if r in RUBBER:
        name, lvl = RUBBER[r]
        return f"{name} ({lvl}/5)"
    if "carry" in r:
        return "Carried over"
    return r.capitalize()


def cardinal(rad: float) -> str:
    deg = math.degrees(rad) % 360
    return CARDINAL[int((deg + 22.5) // 45) % 8]


def _clock(sec: float) -> str:
    sec = int(sec) % 86400
    return f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}"


class WeatherWidget(OverlayWidget):
    NAME = "weather"
    TITLE = "Weather"
    MIN_WIDTH = 180

    def __init__(self, ctx):
        self._items = []
        self._compass = None
        self._w = None
        super().__init__(ctx)

    # ---- Rain Master call juostelė virš valdiklio ----
    def push(self, snap, force=False):
        super().push(snap, force)
        self._sync_strip(snap)

    def _sync_strip(self, snap):
        call = None
        if self.cfg.get("rain_calls", True) and self.isVisible():
            call = getattr(snap, "rain_call", None)
            if call is None and self.editing:
                from lth_timing.rain_tips import CALLS, RainCall
                t, k, d = CALLS["hidden_water"]
                call = RainCall("hidden_water", t, k, d)
        strip = getattr(self, "_strip", None)
        if call is None:
            if strip is not None and strip.isVisible():
                strip.hide()
            return
        if strip is None:
            from .rain import CallStrip
            strip = self._strip = CallStrip(self)
        if strip.call is None or strip.call.key != call.key or not strip.isVisible():
            strip.set_call(call)
            strip.show()
        else:
            strip.follow()

    def moveEvent(self, e):
        super().moveEvent(e)
        strip = getattr(self, "_strip", None)
        if strip is not None and strip.isVisible():
            strip.follow()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        strip = getattr(self, "_strip", None)
        if strip is not None and strip.isVisible():
            strip.follow()

    def hideEvent(self, e):
        super().hideEvent(e)
        strip = getattr(self, "_strip", None)
        if strip is not None:
            strip.hide()

    def keep_on_top(self):
        super().keep_on_top()
        strip = getattr(self, "_strip", None)
        if strip is not None and strip.isVisible():
            from .. import win32
            win32.keep_on_top(strip)

    def wants_visible(self, snap) -> bool:
        c = self.cfg
        if not super().wants_visible(snap):
            return False
        if c.get("only_when_wet") and snap.weather is not None and snap.weather.wetness <= 1 and not self.editing:
            return False
        return True

    def content_key(self, snap):
        w = snap.weather
        self._w = w
        if w is None or not w.valid:
            self._items = []
            return ("none",)
        f = self.cfg["fields"]
        items = []
        if f.get("track_temp"):
            ch = w.track_temp_change
            tail = f"  {ch:+.1f}" if abs(ch) >= 0.3 and w.window_s >= 120 else ""
            items.append(("Track", f"{w.track_temp:.1f} °C{tail}", "text"))
        if f.get("air_temp"):
            items.append(("Air", f"{w.air_temp:.1f} °C", "text"))
        if f.get("precip"):
            items.append(("Rain", f"{w.precipitation * 100:.0f} %", "blue" if w.precipitation > 0.01 else "dim"))
        if f.get("skies"):
            items.append(("Sky", w.skies_text, "text"))
        compass = f.get("wind") and self.cfg.get("compass", "compass") == "compass" and w.heading is not None
        if f.get("wind") and not compass:
            items.append(("Wind", f"{w.wind_speed * 3.6:.0f} km/h {self._wind_word(w)}", "text"))
        if f.get("humidity"):
            items.append(("Humidity", f"{w.humidity * 100:.0f} %", "text"))
        if f.get("track_usage"):
            tu = track_usage_text(getattr(snap, "track_usage", ""))
            if tu:
                items.append(("Track usage", tu, "text"))
        if f.get("fog"):
            items.append(("Fog", f"{w.fog * 100:.0f} %", "text"))
        if f.get("time"):
            items.append(("Time", _clock(w.time_of_day), "text"))
        self._items = items
        self._compass = (round(w.wind_speed * 3.6), round(math.degrees(w.wind_dir) / 5) * 5,
                         round(math.degrees(w.heading) / 5) * 5, self._wind_word(w)) if compass else None
        wind = round(math.degrees(w.wind_rel) / 10) if w.wind_rel is not None else None
        return (tuple(items), w.wetness, w.declared_wet, w.trend, wind, self._compass, self.cfg.get("mode"),
                self.width())

    @staticmethod
    def _wind_word(w) -> str:
        if w.wind_rel is None:
            return ""
        a = abs(math.degrees(w.wind_rel))
        if a < 45:
            return "headwind"
        if a > 135:
            return "tailwind"
        return "crosswind"

    # ---------------- piešimas ----------------
    def desired_height(self) -> int:
        lh = self.fonts.em_base * 1.45
        compact = self.cfg.get("mode") == "compact"
        head = self.fonts.em_small * 1.9
        bar = lh * 2.1
        n = 0 if compact else len(self._items)
        comp = self._compass_size() + lh * 0.3 if (not compact and getattr(self, "_compass", None)) else 0
        return int(head + bar + lh * n + comp + 10)

    def _compass_size(self) -> float:
        return min(self.width() * 0.46, self.fonts.em_base * 6.2)

    def paint_content(self, p: QPainter):
        w = self._w
        if (w is None or not w.valid) and not self.editing:
            return
        pal, fonts = self.pal, self.fonts
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.bg)
        p.drawRoundedRect(r, pal.radius, pal.radius)
        self._drew_bg = True
        hh = self.paint_header(p, "WEATHER")
        if w is None or not w.valid:
            return
        if w.declared_wet:
            tw = self.text_width("WET", "tiny") + 10
            br = QRectF(r.width() - tw - 10, hh * 0.2, tw, hh * 0.6)
            p.setBrush(pal.blue)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(br, 3, 3)
            p.setPen(pal.text)
            self.draw_text(p, br, "WET", "tiny", "c")
        lh = fonts.em_base * 1.45
        y = hh + 6
        # Šlapumo juosta: 7 segmentai
        p.setPen(pal.text)
        self.draw_text(p, QRectF(10, y, r.width() - 20, lh), w.wetness_text, "bold")
        trend = {"wetter": ("▲ wetter", pal.blue), "drying": ("▼ drying", pal.yellow), "stable": ("= stable", pal.dim)}
        if self.cfg["fields"].get("trend"):
            txt, col = trend.get(w.trend, ("", pal.dim))
            p.setPen(col)
            self.draw_text(p, QRectF(10, y, r.width() - 20, lh), txt, "small", "r")
        y += lh
        seg_w = (r.width() - 20 - 6 * 3) / 7
        for i in range(7):
            on = i < max(0, w.wetness)
            col = pal.blue if (on and w.wetness > 1) else (pal.good if on else pal.row_alt)
            if not on:
                col = pal.track
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(10 + i * (seg_w + 3), y + lh * 0.25, seg_w, lh * 0.4), 2, 2)
        y += lh * 1.1 - 4
        if self.cfg.get("mode") == "compact":
            return
        for label, value, color in self._items:
            p.setPen(pal.dim)
            self.draw_text(p, QRectF(10, y, r.width() * 0.4, lh), label, "small")
            p.setPen(getattr(pal, color))
            right_pad = 10
            if label == "Wind" and w.wind_rel is not None:
                self._arrow(p, QPointF(r.width() - 10 - lh * 0.4, y + lh / 2), lh * 0.38, w.wind_rel)
                right_pad = 10 + lh
                p.setPen(getattr(pal, color))
            self.draw_text(p, QRectF(r.width() * 0.35, y, r.width() * 0.65 - right_pad, lh), value, "base", "r")
            y += lh
        if getattr(self, "_compass", None):
            self._paint_compass(p, y + lh * 0.15, r)

    def _paint_compass(self, p: QPainter, y: float, r: QRectF):
        """Klasikinis kompasas (šiaurė viršuje): mėlyna rodyklė - kur pučia vėjas, auksinis trikampis - kur
        važiuoji. Dešinėje - greitis, iš kur pučia ir ar tai priešinis / šoninis / pavėjinis."""
        kmh, wdir, head, word = self._compass
        pal = self.pal
        size = self._compass_size()
        c = QPointF(10 + size / 2, y + size / 2)
        rad = size / 2 - 2
        p.setPen(QPen(pal.track, max(1.5, rad * 0.05)))
        p.setBrush(pal.header)
        p.drawEllipse(c, rad, rad)
        for k in range(36):  # padalos kas 10°, ilgesnės kas 90°
            a = math.radians(k * 10)
            ln = rad * (0.16 if k % 9 == 0 else 0.08)
            p.setPen(QPen(pal.text if k % 9 == 0 else pal.dim, 1.4 if k % 9 == 0 else 1.0))
            p.drawLine(QPointF(c.x() + math.sin(a) * (rad - ln), c.y() - math.cos(a) * (rad - ln)),
                       QPointF(c.x() + math.sin(a) * rad, c.y() - math.cos(a) * rad))
        for txt, ang in (("N", 0), ("E", 90), ("S", 180), ("W", 270)):
            a = math.radians(ang)
            pt = QPointF(c.x() + math.sin(a) * rad * 0.66, c.y() - math.cos(a) * rad * 0.66)
            p.setPen(pal.bad if txt == "N" else pal.dim)
            self.draw_text(p, QRectF(pt.x() - rad * 0.3, pt.y() - rad * 0.2, rad * 0.6, rad * 0.4), txt, "small", "c")
        # vėjo rodyklė: pučia IŠ wdir, todėl rodo į wdir + 180°
        a = math.radians(wdir + 180)
        dx, dy = math.sin(a), -math.cos(a)
        tip = QPointF(c.x() + dx * rad * 0.62, c.y() + dy * rad * 0.62)
        tail = QPointF(c.x() - dx * rad * 0.62, c.y() - dy * rad * 0.62)
        p.setPen(QPen(pal.blue, max(2.0, rad * 0.09), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(tail, QPointF(tip.x() - dx * rad * 0.2, tip.y() - dy * rad * 0.2))
        nx, ny = -dy, dx
        hl, hw = rad * 0.30, rad * 0.20
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.blue)
        p.drawPolygon(QPolygonF([tip, QPointF(tip.x() - dx * hl + nx * hw, tip.y() - dy * hl + ny * hw),
                                 QPointF(tip.x() - dx * hl - nx * hw, tip.y() - dy * hl - ny * hw)]))
        # mašinos kryptis: auksinis trikampis ant krašto
        a = math.radians(head)
        dx, dy = math.sin(a), -math.cos(a)
        nx, ny = -dy, dx
        t0 = QPointF(c.x() + dx * rad * 0.98, c.y() + dy * rad * 0.98)
        p.setBrush(pal.accent)
        p.drawPolygon(QPolygonF([t0, QPointF(t0.x() - dx * rad * 0.24 + nx * rad * 0.13, t0.y() - dy * rad * 0.24 + ny * rad * 0.13),
                                 QPointF(t0.x() - dx * rad * 0.24 - nx * rad * 0.13, t0.y() - dy * rad * 0.24 - ny * rad * 0.13)]))
        # tekstas dešinėje
        x = c.x() + rad + 14
        w = r.width() - x - 10
        lh = self.fonts.em_base * 1.45
        ty = c.y() - lh * 1.5
        p.setPen(pal.text)
        self.draw_text(p, QRectF(x, ty, w, lh * 1.2), f"{kmh} km/h", "mid")
        p.setPen(pal.dim)
        self.draw_text(p, QRectF(x, ty + lh * 1.2, w, lh), f"from {cardinal(math.radians(wdir))}", "small")
        col = {"headwind": pal.bad, "tailwind": pal.good}.get(word, pal.yellow)
        p.setPen(col)
        self.draw_text(p, QRectF(x, ty + lh * 2.1, w, lh), word.capitalize(), "base")
        p.setPen(pal.accent)

    def _arrow(self, p: QPainter, c: QPointF, rad: float, angle: float):
        """Rodyklė rodo, į kurią pusę pučia vėjas mašinos atžvilgiu (viršus = į priekį)."""
        a = angle + math.pi  # vėjas pučia IŠ angle, rodyklė rodo kryptį, KUR pučia
        dx, dy = math.sin(a), -math.cos(a)
        tip = QPointF(c.x() + dx * rad, c.y() + dy * rad)
        tail = QPointF(c.x() - dx * rad, c.y() - dy * rad)
        p.setPen(QPen(self.pal.accent, max(1.5, rad * 0.22)))
        p.drawLine(tail, tip)
        nx, ny = -dy, dx
        head = QPolygonF([tip, QPointF(tip.x() - dx * rad * 0.7 + nx * rad * 0.45, tip.y() - dy * rad * 0.7 + ny * rad * 0.45),
                          QPointF(tip.x() - dx * rad * 0.7 - nx * rad * 0.45, tip.y() - dy * rad * 0.7 - ny * rad * 0.45)])
        p.setBrush(self.pal.accent)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(head)
