"""Lenktynių valdikliai: Flags, Radar, Pit helper, Pit window, Incidents, Stint, Formation, Radio, Connection."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from lth_timing.player import PIT_SV

from .panel import PanelWidget, fmt_clock

CAR_LEN_M = 4.8


# ---------------------------------------------------------------- Flags
class FlagsWidget(PanelWidget):
    NAME = "flags"
    TITLE = "Flags"
    HAS_HEADER = False
    MIN_WIDTH = 160
    # (fonas, tekstas) - None = paletės spalva
    STYLE = {
        "disqualify": ((10, 10, 10), (255, 255, 255)), "black": ((10, 10, 10), (255, 255, 255)),
        "repair": ((10, 10, 10), (255, 150, 40)), "red": ((215, 30, 40), (255, 255, 255)),
        "caution_waving": ((250, 205, 20), (20, 20, 20)), "caution": ((250, 205, 20), (20, 20, 20)),
        "yellow_waving": ((250, 205, 20), (20, 20, 20)), "yellow": ((250, 205, 20), (20, 20, 20)),
        "debris": ((250, 205, 20), (180, 30, 30)), "blue": ((30, 110, 230), (255, 255, 255)),
        "white": ((245, 245, 245), (20, 20, 20)), "checkered": ((245, 245, 245), (10, 10, 10)),
        "one_to_green": ((40, 170, 80), (255, 255, 255)), "green": ((40, 170, 80), (255, 255, 255)),
    }
    # vėliavos, kurios trumpos (mirksi) - jas laikome bent `hold` sekundžių
    SHORT = {"blue", "yellow", "yellow_waving", "debris", "black", "repair"}

    def __init__(self, ctx):
        self._seen = {}  # key -> (pirmą kartą, paskutinį kartą, tekstas)
        super().__init__(ctx)

    def content_key(self, snap):
        p = snap.player
        t = snap.t
        hold = float(self.cfg.get("hold", 4.0))
        active = {k: txt for k, txt in (p.flags if p is not None else ())}
        for k, txt in active.items():
            first = self._seen.get(k, (t, t, txt))[0]
            self._seen[k] = (first, t, txt)
        show = None
        for k, (first, last, txt) in sorted(self._seen.items(), key=lambda kv: self._rank(kv[0])):
            on = k in active or (k in self.SHORT and t - last < hold)
            if not on:
                continue
            if k == "green" and (not self.cfg.get("show_green") or t - first > hold):
                continue
            show = (k, txt)
            break
        # pamirštam senas
        self._seen = {k: v for k, v in self._seen.items() if k in active or t - v[1] < hold}
        self._view = show
        return (show, self.width())

    @staticmethod
    def _rank(key):
        order = ("disqualify", "black", "repair", "red", "caution_waving", "caution", "yellow_waving", "yellow",
                 "debris", "blue", "white", "checkered", "one_to_green", "green")
        return order.index(key) if key in order else 99

    def desired_height(self) -> int:
        return int(self.fonts.em_base * 2.8)

    def paint_content(self, p: QPainter):
        view = self._view
        if view is None:
            if not self.editing:
                return
            view = ("yellow", "YELLOW")
        key, txt = view
        bg, fg = self.STYLE.get(key, ((60, 60, 60), (255, 255, 255)))
        r = QRectF(self.rect())
        rad = self.pal.radius
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(*bg))
        p.drawRoundedRect(r, rad, rad)
        if key == "checkered":
            s = r.height() / 3
            for i in range(int(r.width() / s) + 1):
                for j in range(3):
                    if (i + j) % 2:
                        p.fillRect(QRectF(i * s, j * s, s, s), QColor(15, 15, 15))
            p.setBrush(QColor(245, 245, 245, 235))
            tw = self.text_width(txt, "mid") + 30
            p.drawRoundedRect(QRectF((r.width() - tw) / 2, r.height() * 0.18, tw, r.height() * 0.64), rad, rad)
        elif key == "repair":
            d = r.height() * 0.5
            p.setBrush(QColor(255, 120, 20))
            p.drawEllipse(QRectF(r.height() * 0.25, (r.height() - d) / 2, d, d))
        elif key == "debris":
            w = r.height() / 2
            for i in range(0, int(r.width() / w) + 2, 2):
                p.fillRect(QRectF(i * w, 0, w, r.height() * 0.12), QColor(200, 30, 30))
                p.fillRect(QRectF(i * w, r.height() * 0.88, w, r.height() * 0.12), QColor(200, 30, 30))
        p.setPen(QColor(*fg))
        self.draw_text(p, r, txt, "mid", "c")


# ---------------------------------------------------------------- Radar
class RadarWidget(PanelWidget):
    NAME = "radar"
    TITLE = "Radar"
    HAS_HEADER = False
    HEIGHT_MODE = "free"
    MIN_WIDTH = 70
    MIN_HEIGHT = 80
    SIDES = {2: (1, 0), 3: (0, 1), 4: (1, 1), 5: (2, 0), 6: (0, 2)}  # (kairėje, dešinėje)

    def content_key(self, snap):
        rng = float(self.cfg.get("range", 20))
        L = snap.track_length_m or 0.0
        cars = []
        if L > 0:
            for r in snap.relative:
                if r.is_me or r.car.status != "track":
                    continue
                d = r.distance * L
                if abs(d) <= rng + CAR_LEN_M:
                    cars.append(round(d, 1))
        p = snap.player
        lr = p.car_left_right if p is not None else 0
        left, right = self.SIDES.get(lr, (0, 0))
        busy = bool(cars) or left or right
        self._view = (tuple(sorted(cars)), left, right, rng) if (busy or self.cfg.get("always")) else None
        return (self._view, self.width(), self.height())

    def desired_height(self) -> int:
        return int(self.width() * 1.3)

    def paint_content(self, p: QPainter):
        view = self._view
        if view is None:
            if not self.editing:
                return
            view = ((-6.0, 12.0), 1, 0, float(self.cfg.get("range", 20)))
        cars, left, right, rng = view
        r = QRectF(self.rect())
        pal = self.pal
        p.setPen(Qt.PenStyle.NoPen)
        bg = QColor(pal.bg)
        p.setBrush(bg)
        p.drawRoundedRect(r, pal.radius * 2, pal.radius * 2)
        cx, cy = r.center().x(), r.center().y()
        k = (r.height() / 2 - 6) / (rng + CAR_LEN_M / 2)  # px per metrą
        cw = max(8.0, min(r.width() * 0.16, 2.0 * k))
        ch = max(14.0, CAR_LEN_M * k)
        lane = cw * 1.5
        # atstumo linijos
        p.setPen(QPen(pal.row_alt, 1, Qt.PenStyle.DotLine))
        for m in (5, 10, 20, 40):
            if m <= rng:
                for s in (-1, 1):
                    y = cy - s * m * k
                    p.drawLine(QPointF(r.left() + 6, y), QPointF(r.right() - 6, y))
        # šonų įspėjimai
        for side, n in ((-1, left), (1, right)):
            if n:
                col = QColor(pal.bad)
                col.setAlpha(170 if n == 1 else 230)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col)
                x = cx + side * lane - cw / 2
                for i in range(n):
                    p.drawRoundedRect(QRectF(x + side * i * lane, cy - ch / 2, cw, ch), 3, 3)
        # kitos mašinos (pagal atstumą; šoninės padėties iRacing neduoda)
        for d in cars:
            near = abs(d) < CAR_LEN_M
            if near and (left or right):
                continue  # jau nupiešta šone
            col = QColor(pal.yellow if abs(d) < 10 else pal.text)
            col.setAlpha(230)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(cx - cw / 2, cy - d * k - ch / 2, cw, ch), 3, 3)
        # aš
        p.setBrush(pal.accent)
        p.drawRoundedRect(QRectF(cx - cw / 2, cy - ch / 2, cw, ch), 3, 3)
        if cars:
            closest = min(cars, key=abs)
            if abs(closest) >= CAR_LEN_M:
                p.setPen(pal.dim)
                self.draw_text(p, QRectF(4, r.height() - self.lh(), r.width() - 8, self.lh()),
                               f"{abs(closest):.0f} m {'ahead' if closest > 0 else 'behind'}", "tiny", "c")


# ---------------------------------------------------------------- Pit helper
class PitHelperWidget(PanelWidget):
    NAME = "pit_helper"
    TITLE = "Pit helper"
    MIN_WIDTH = 220

    def content_key(self, snap):
        p = snap.player
        if p is None or not p.valid or not (p.on_pit_road or p.in_stall or self.cfg.get("always") or self.editing):
            self._view = None
            return (None, self.editing)
        services = tuple(name for bit, name in PIT_SV if p.pit_flags & bit)
        tyres = tuple(s for s in services if s in ("LF", "RF", "LR", "RR"))
        lines = []
        tyre_txt = "All four" if len(tyres) == 4 else ", ".join(tyres) if tyres else "No change"
        lines.append(("Tyres", tyre_txt, "text" if tyres else "dim"))
        if "Fuel" in services:
            lines.append(("Fuel", f"+{p.pit_fuel:.1f} l", "text"))
        else:
            lines.append(("Fuel", "No fuel", "dim"))
        if "Tear-off" in services:
            lines.append(("Windscreen", "Tear-off", "text"))
        if "Fast repair" in services:
            lines.append(("Fast repair", f"Yes ({p.fast_repairs} left)", "yellow"))
        elif p.fast_repairs:
            lines.append(("Fast repairs left", str(p.fast_repairs), "dim"))
        if p.repair_left > 0:
            lines.append(("Required repair", f"{p.repair_left:.0f} s", "bad"))
        if p.opt_repair_left > 0:
            lines.append(("Optional repair", f"{p.opt_repair_left:.0f} s", "yellow"))
        if p.tow_time > 0:
            lines.append(("Tow", fmt_clock(p.tow_time), "bad"))
        warn = ""
        if p.on_pit_road and not p.limiter and p.speed > 3:
            warn = "PIT LIMITER OFF"
        elif p.in_stall:
            warn = "IN PIT BOX"
        self._view = (tuple(lines), warn, p.limiter and p.on_pit_road)
        return (self._view, self.width())

    def desired_height(self) -> int:
        if not self._view:
            return self.body_height(1)
        return self.body_height(len(self._view[0]) + (1.5 if self._view[1] else 0))

    def paint_content(self, p: QPainter):
        if self._view is None:
            return
        lines, warn, lim = self._view
        y = self.card(p, "PIT", "LIMITER ON" if lim else "")
        if warn:
            col = QColor(self.pal.bad if "OFF" in warn else self.pal.good)
            col.setAlpha(200)
            x0 = self.pad()
            self.chip(p, QRectF(x0, y, self.width() - 2 * x0, self.lh() * 1.3), warn, col, self.pal.text, "bold")
            y += self.lh() * 1.5
        for label, value, col in lines:
            y = self.kv(p, y, label, value, col)


# ---------------------------------------------------------------- Pit window
class PitStrategyWidget(PanelWidget):
    NAME = "pit_strategy"
    TITLE = "Pit window"
    MIN_WIDTH = 220

    def content_key(self, snap):
        pit = snap.pit or {}
        service = float(self.cfg.get("service", 30.0))
        lane = pit.get("lane_loss")
        stop = pit.get("stop_loss")
        n = pit.get("samples", 0)
        lines = []
        if lane is not None:
            lines.append(("Pit lane loss", f"{lane:.1f} s", "text"))
            loss = lane + service
        elif stop is not None:
            loss = stop
        else:
            loss = None
        if stop is not None:
            lines.append(("Typical stop", f"{stop:.1f} s", "text"))
        lines.append(("Measured stops", str(n), "dim"))
        me = next((r for r in snap.cars if r.is_me), None)
        pred = None
        if loss is not None and me is not None and snap.session_type == "race" and (me.gap is not None or me.class_pos == 1):
            ref = me.last_lap or me.best_lap or 0.0
            mine = (me.gap or 0.0) + loss
            others = []
            for r in snap.cars:
                if r.is_me or r.class_id != me.class_id or r.status in ("out", "garage"):
                    continue
                if r.gap is not None:
                    g = r.gap
                elif r.class_pos == 1:
                    g = 0.0
                elif r.gap_laps and ref:
                    g = r.gap_laps * ref
                else:
                    continue
                others.append((g, r))
            others.sort(key=lambda x: x[0])
            pos = 1 + sum(1 for g, _ in others if g < mine)
            ahead = next(((mine - g, r) for g, r in reversed(others) if g < mine), None)
            behind = next(((g - mine, r) for g, r in others if g >= mine), None)
            pred = (pos, me.class_pos, ahead, behind)
        if pred is not None:
            pos, now, ahead, behind = pred
            col = "good" if pos <= now else "yellow" if pos - now <= 2 else "bad"
            lines.append(("Rejoin if you pit now", f"P{pos}  (now P{now})", col))
            if ahead:
                lines.append(("Behind", self._who(ahead), "text"))
            if behind:
                lines.append(("Ahead of", self._who(behind), "text" if behind[0] > 2 else "bad"))
        elif loss is None:
            lines.append(("Rejoin prediction", "after the first pit stop", "dim"))
        self._view = (tuple(lines), f"service {service:.0f} s")
        return (self._view, self.width())

    @staticmethod
    def _who(item):
        gap, r = item
        return f"#{r.number} {r.abbrev or r.name}  {gap:.1f} s"

    def desired_height(self) -> int:
        return self.body_height(len(self._view[0]) if self._view else 3)

    def paint_content(self, p: QPainter):
        if self._view is None:
            return
        lines, right = self._view
        y = self.card(p, "PIT WINDOW", right)
        for label, value, col in lines:
            y = self.kv(p, y, label, self.elide(value, self.width() * 0.55), col)


# ---------------------------------------------------------------- Incidents
class IncidentsWidget(PanelWidget):
    NAME = "incidents"
    TITLE = "Incidents"
    MIN_WIDTH = 140

    def content_key(self, snap):
        p = snap.player
        if p is None or not p.valid:
            self._view = None
            return None
        limit = int(self.cfg.get("limit", 0) or 0)
        popup = float(self.cfg.get("popup", 5.0))
        fresh = p.inc_last_add if p.inc_age < popup and p.inc_last_add > 0 else 0
        team = p.inc_team if p.inc_team and p.inc_team != p.inc_my else None
        self._view = (p.inc_my, team, limit, fresh)
        return (self._view, self.width())

    def desired_height(self) -> int:
        return self.body_height(1.7 + (1 if self._view and self._view[1] is not None else 0))

    def paint_content(self, p: QPainter):
        if self._view is None:
            return
        mine, team, limit, fresh = self._view
        r = QRectF(self.rect())
        y = self.card(p, "INCIDENTS")
        if fresh:
            c = QColor(self.pal.bad)
            c.setAlpha(110)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(r, self.pal.radius, self.pal.radius)
        x0 = self.pad() * 1.4
        w = r.width() - 2 * x0
        lh = self.lh()
        frac = mine / limit if limit else 0
        col = self.pal.bad if limit and frac >= 0.8 else self.pal.yellow if limit and frac >= 0.5 else self.pal.text
        p.setPen(col)
        self.draw_text(p, QRectF(x0, y, w, lh * 1.5), f"{mine}x" + (f" / {limit}" if limit else ""), "mid")
        if fresh:
            p.setPen(self.pal.text)
            self.draw_text(p, QRectF(x0, y, w, lh * 1.5), f"+{fresh}x", "mid", "r")
        y += lh * 1.6
        if limit:
            self.bar(p, QRectF(x0, y - lh * 0.15, w, 3), frac, col)
        if team is not None:
            self.kv(p, y, "Team", f"{team}x")


# ---------------------------------------------------------------- Stint
class StintWidget(PanelWidget):
    NAME = "stint"
    TITLE = "Stint"

    def content_key(self, snap):
        p = snap.player
        if p is None or not p.valid:
            self._view = None
            return None
        lines = [("Time", fmt_clock(p.stint_time), "text"), ("Laps", str(p.stint_laps), "text")]
        if p.stint_avg:
            m, s = divmod(p.stint_avg, 60)
            lines.append(("Average lap", f"{int(m)}:{s:06.3f}" if m else f"{s:.3f}", "text"))
        if self.cfg.get("show_drivers", True) and p.drivers_so_far > 1:
            lines.append(("Drivers so far", str(p.drivers_so_far), "dim"))
        self._view = tuple(lines)
        return (self._view, self.width())

    def desired_height(self) -> int:
        return self.body_height(len(self._view) if self._view else 2)

    def paint_content(self, p: QPainter):
        if self._view is None:
            return
        y = self.card(p, "STINT")
        for label, value, col in self._view:
            y = self.kv(p, y, label, value, col)


# ---------------------------------------------------------------- Formation
class FormationWidget(PanelWidget):
    NAME = "formation"
    TITLE = "Formation"
    MODES = {0: "Single file start", 1: "Double file start", 2: "Single file restart", 3: "Double file restart"}

    def content_key(self, snap):
        p = snap.player
        if p is None or p.pace_mode not in self.MODES or p.pace_row < 0:
            self._view = None
            return (None, self.editing)
        double = p.pace_mode in (1, 3)
        line = f"Line {p.pace_line + 1}" if double and p.pace_line >= 0 else "Single file"
        self._view = (self.MODES[p.pace_mode], f"Row {p.pace_row + 1}", line)
        return (self._view, self.width())

    def desired_height(self) -> int:
        return self.body_height(2.2)

    def paint_content(self, p: QPainter):
        view = self._view
        if view is None:
            if not self.editing:
                return
            view = ("Double file start", "Row 3", "Line 1")
        mode, row, line = view
        y = self.card(p, "FORMATION", mode)
        x0 = self.pad() * 1.4
        w = self.width() - 2 * x0
        p.setPen(self.pal.text)
        self.draw_text(p, QRectF(x0, y, w, self.lh() * 1.6), row, "mid")
        p.setPen(self.pal.accent)
        self.draw_text(p, QRectF(x0, y, w, self.lh() * 1.6), line, "bold", "r")


# ---------------------------------------------------------------- Radio
class RadioWidget(PanelWidget):
    NAME = "radio"
    TITLE = "Radio"
    HAS_HEADER = False

    def content_key(self, snap):
        p = snap.player
        idx = p.radio_idx if p is not None else -1
        car = next((r for r in snap.cars if r.idx == idx), None) if idx >= 0 else None
        self._view = None if car is None else (car.number, car.name, car.class_color, car.is_me)
        return (self._view, self.width(), self.editing)

    def desired_height(self) -> int:
        return self.body_height(1.2)

    def paint_content(self, p: QPainter):
        view = self._view
        if view is None:
            if not self.editing:
                return
            view = ("7", "Driver Name", 0xFFDA59, False)
        num, name, color, me = view
        self.card(p)
        lh = self.lh() * 1.2
        y = self.pad() * 0.7
        x0 = self.pad() * 1.2
        # mikrofono ženklas: pulsuojantis taškas
        d = lh * 0.42
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.pal.good if not me else self.pal.accent)
        p.drawEllipse(QRectF(x0, y + (lh - d) / 2, d, d))
        x = x0 + d + self.pad()
        tag = f"#{num}"
        tw = self.text_width(tag, "bold") + 12
        self.chip(p, QRectF(x, y + lh * 0.12, tw, lh * 0.76), tag, self.pal.class_color(color) if color else
                  self.pal.header, self.pal.ink if color else self.pal.text, "bold")
        p.setPen(self.pal.text)
        rest = QRectF(x + tw + self.pad(), y, self.width() - x - tw - 2 * self.pad(), lh)
        self.draw_text(p, rest, self.elide(name, rest.width()), "bold")


# ---------------------------------------------------------------- Connection
class ConnectionWidget(PanelWidget):
    NAME = "connection"
    TITLE = "Connection"
    HAS_HEADER = False

    def content_key(self, snap):
        p = snap.player
        if p is None or p.chan_quality is None:
            self._view = None
            return (None, self.editing)
        q = p.chan_quality
        bad = q < float(self.cfg.get("threshold", 0.9))
        if not bad and not self.cfg.get("always"):
            self._view = None
            return (None, self.editing)

        def ms(v):
            if v is None:
                return "–"
            return f"{v * 1000:.0f} ms" if v < 5 else f"{v:.0f} ms"

        partner = p.chan_partner
        self._view = (round(q, 2), None if partner is None else round(partner, 2), ms(p.latency), bad)
        return (self._view, self.width())

    def desired_height(self) -> int:
        return self.body_height(1.2)

    def paint_content(self, p: QPainter):
        view = self._view
        if view is None:
            if not self.editing:
                return
            view = (0.82, 0.95, "48 ms", True)
        q, partner, lat, bad = view
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        if bad:
            c = QColor(self.pal.bad)
            c.setAlpha(200)
            p.setBrush(c)
        else:
            p.setBrush(self.pal.bg)
        p.drawRoundedRect(r, self.pal.radius, self.pal.radius)
        lh = self.lh() * 1.2
        x0 = self.pad() * 1.2
        w = r.width() - 2 * x0
        y = self.pad() * 0.7
        # signalo stulpeliai
        bw = lh * 0.16
        for i in range(4):
            h = lh * (0.3 + 0.17 * i)
            on = q >= (0.5, 0.75, 0.9, 0.97)[i]
            p.setBrush(self.pal.text if on else QColor(255, 255, 255, 60))
            p.drawRect(QRectF(x0 + i * bw * 1.6, y + lh * 0.85 - h, bw, h))
        tx = x0 + bw * 7
        p.setPen(self.pal.text)
        lat_w = self.text_width(lat, "small") + self.pad()
        txt = f"BAD CONNECTION {q * 100:.0f}%" if bad else f"Connection {q * 100:.0f}%"
        if self.text_width(txt, "bold") > w - tx - lat_w:
            txt = f"{q * 100:.0f}%"
        self.draw_text(p, QRectF(tx, y, w - tx, lh), txt, "bold")
        p.setPen(self.pal.text if bad else self.pal.dim)
        self.draw_text(p, QRectF(x0, y, w, lh), lat, "small", "r")
