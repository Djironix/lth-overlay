"""Orų langelis: šlapumas, temperatūros, vėjas santykinai su mašina, tendencija."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPen, QPolygonF

from ..window import OverlayWidget


def _clock(sec: float) -> str:
    sec = int(sec) % 86400
    return f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}"


class WeatherWidget(OverlayWidget):
    NAME = "weather"
    TITLE = "Weather"
    MIN_WIDTH = 180

    def __init__(self, ctx):
        self._items = []
        self._w = None
        super().__init__(ctx)

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
        if f.get("wind"):
            items.append(("Wind", f"{w.wind_speed * 3.6:.0f} km/h {self._wind_word(w)}", "text"))
        if f.get("humidity"):
            items.append(("Humidity", f"{w.humidity * 100:.0f} %", "text"))
        if f.get("fog"):
            items.append(("Fog", f"{w.fog * 100:.0f} %", "text"))
        if f.get("time"):
            items.append(("Time", _clock(w.time_of_day), "text"))
        self._items = items
        wind = round(math.degrees(w.wind_rel) / 10) if w.wind_rel is not None else None
        return (tuple(items), w.wetness, w.declared_wet, w.trend, wind, self.cfg.get("mode"), self.width())

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
        return int(head + bar + lh * n + 10)

    def paint_content(self, p: QPainter):
        w = self._w
        if (w is None or not w.valid) and not self.editing:
            return
        pal, fonts = self.pal, self.fonts
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.bg)
        p.drawRoundedRect(r, pal.radius, pal.radius)
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
                col = pal.header
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
