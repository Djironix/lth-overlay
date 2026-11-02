"""Mašinos valdikliai: Fuel, Dash, Inputs, G-force, Tyres, Car settings, Engine warnings."""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPainterPath, QPen, QPolygonF

from .wheel import GT3Wheel, ImageWheel, decimate, runs
from .panel import PanelWidget

L_TO_GAL = 0.264172


class FuelWidget(PanelWidget):
    NAME = "fuel"
    TITLE = "Fuel"
    MIN_WIDTH = 190

    def content_key(self, snap):
        p = snap.player
        if p is None or not p.valid or not math.isfinite(p.fuel_l):
            self._view = None
            return None
        gal = self.cfg.get("unit", "l") == "gal"
        k, u = (L_TO_GAL, " gal") if gal else (1.0, " l")
        margin = float(self.cfg.get("margin", 0.5) or 0.0)
        lines = []
        if p.fuel_per_lap:
            last = f"   (last {p.fuel_last_lap * k:.2f})" if p.fuel_last_lap else ""
            lines.append(("Per lap", f"{p.fuel_per_lap * k:.2f}{u}{last}", "text"))
            lines.append(("Laps of fuel", f"{p.fuel_laps_left:.1f}", "text"))
            if p.fuel_to_finish is not None:
                need = p.fuel_to_finish + margin * p.fuel_per_lap
                add = need - p.fuel_l
                lines.append(("To finish", f"{need * k:.1f}{u}   ({p.race_laps_left:.1f} laps)", "text"))
                if add <= 0:
                    lines.append(("Add at stop", "Enough to finish", "good"))
                else:
                    stops = ""
                    if p.fuel_max_l and add > p.fuel_max_l:
                        stops = f"   ({math.ceil(add / p.fuel_max_l)} stops)"
                    lines.append(("Add at stop", f"+{add * k:.1f}{u}{stops}", "yellow"))
        else:
            lines.append(("Per lap", "measuring - drive a clean lap", "dim"))
        pct = p.fuel_pct if math.isfinite(p.fuel_pct) else (p.fuel_l / p.fuel_max_l if p.fuel_max_l else math.nan)
        self._view = (f"{p.fuel_l * k:.1f}{u}", round(pct, 3) if math.isfinite(pct) else None, tuple(lines))
        return (self._view, self.width())

    def desired_height(self) -> int:
        n = len(self._view[2]) if self._view else 1
        return self.body_height(n + 1.5)

    def paint_content(self, p: QPainter):
        if self._view is None:
            if self.editing:
                self.card(p, "FUEL")
            return
        level, pct, lines = self._view
        y = self.card(p, "FUEL")
        x0 = self.pad() * 1.4
        w = self.width() - 2 * x0
        lh = self.lh()
        p.setPen(self.pal.text)
        self.draw_text(p, QRectF(x0, y, w * 0.45, lh * 1.2), level, "mid")
        if pct is not None:
            col = self.pal.bad if pct < 0.1 else self.pal.yellow if pct < 0.25 else self.pal.good
            self.bar(p, QRectF(x0 + w * 0.5, y + lh * 0.45, w * 0.5, lh * 0.3), pct, col)
        y += lh * 1.5
        for label, value, col in lines:
            y = self.kv(p, y, label, value, col)


def fuel_plan(fuel_l, fpl, laps_left, tank, margin_laps, lap_no, lap_pct, max_save=0.12):
    """Kuro strategija. Grąžina dict arba None, jei trūksta duomenų.

    laps_left - kiek ratų (su dalimi) dar nuvažiuosiu; margin_laps - atsarga ratais."""
    if not (fpl and fpl > 0) or laps_left is None or not math.isfinite(fuel_l):
        return None
    laps_fuel = fuel_l / fpl  # kiek ratų užteks nuo dabar
    need = (laps_left + margin_laps) * fpl
    deficit = need - fuel_l
    out = {"laps_fuel": laps_fuel, "laps_left": laps_left, "need": need, "deficit": deficit, "fpl": fpl}
    to_line = 1.0 - (lap_pct % 1.0)  # iki artimiausio linijos kirtimo
    if deficit <= 0:
        out.update(stops=0, spare=laps_fuel - laps_left, allowed=fuel_l / (laps_left + margin_laps))
        return out
    stops = math.ceil(deficit / tank - 1e-9) if tank and tank > 0 else 1
    out["stops"] = stops
    # vėliausias ratas sustoti: kiek linijos kirtimų dar pasieksiu su atsarga
    usable = laps_fuel - margin_laps
    k_last = math.floor(usable - to_line + 1e-9) + 1 if usable >= to_line else 0
    out["latest_lap"] = lap_no + k_last - 1 if k_last >= 1 else None  # sustoti šio rato pabaigoje
    if stops == 1 and tank and tank > 0:
        # anksčiausias: po sustojimo likęs atstumas turi tilpti į pilną baką
        d_min = laps_left + margin_laps - tank / fpl
        j = max(1, math.ceil(d_min - to_line + 1e-9) + 1)
        out["earliest_lap"] = lap_no + j - 1
    # taupymas: kiek reikėtų mažiau per ratą, kad užtektų vienu sustojimu mažiau
    budget = fuel_l + (stops - 1) * (tank or 0.0)
    target = budget / (laps_left + margin_laps)
    save = 1.0 - target / fpl
    out["save_target"] = target
    out["save_pct"] = save
    out["save_ok"] = 0 < save <= max_save
    return out


class FuelStrategyWidget(PanelWidget):
    """Kada sustoti, kiek pilti ir kiek reikia taupyti, kad užtektų vienu sustojimu mažiau."""
    NAME = "fuel_strategy"
    TITLE = "Fuel strategy"
    MIN_WIDTH = 220

    def content_key(self, snap):
        p = snap.player
        if p is None or not p.valid or not math.isfinite(p.fuel_l):
            self._view = None
            return None
        gal = self.cfg.get("unit", "l") == "gal"
        k, u = (L_TO_GAL, " gal") if gal else (1.0, " l")
        race = snap.session_type == "race"
        margin = float(self.cfg.get("margin", 0.5) or 0.0)
        max_save = float(self.cfg.get("max_save", 0.12) or 0.12)
        lines, status = [], ("", "dim")
        plan = fuel_plan(p.fuel_l, p.fuel_per_lap, p.race_laps_left if race else None, p.fuel_max_l, margin,
                         p.lap_no, p.lap_pct, max_save)
        if not p.fuel_per_lap:
            status = ("MEASURING", "dim")
            lines.append(("Per lap", "drive a clean lap", "dim"))
        elif plan is None:
            status = ("RACE ONLY", "dim")
            lines.append(("Per lap", f"{p.fuel_per_lap * k:.2f}{u}", "text"))
            lines.append(("Laps of fuel", f"{p.fuel_l / p.fuel_per_lap:.1f}", "text"))
        else:
            lines.append(("Laps to go", f"{plan['laps_left']:.1f}", "text"))
            lines.append(("Laps of fuel", f"{plan['laps_fuel']:.1f}   ({p.fuel_per_lap * k:.2f}{u}/lap)", "text"))
            if plan["stops"] == 0:
                status = ("NO STOP NEEDED", "good")
                lines.append(("Spare", f"{plan['spare']:.1f} laps", "good"))
                lines.append(("You can use", f"{plan['allowed'] * k:.2f}{u}/lap", "text"))
            else:
                n = plan["stops"]
                status = (f"{n} STOP{'S' if n > 1 else ''}", "yellow")
                lines.append(("Fuel to add", f"+{plan['deficit'] * k:.1f}{u}" + (" in total" if n > 1 else ""),
                              "yellow"))
                lo, hi = plan.get("earliest_lap"), plan.get("latest_lap")
                if hi is None:
                    lines.append(("Pit", "this lap!", "bad"))
                elif lo is not None and lo > hi:
                    lines.append(("Pit window", "closed - one more stop", "bad"))
                elif lo is not None:
                    lines.append(("Pit window", f"lap {lo} - {hi}" if lo < hi else f"lap {hi}", "text"))
                else:
                    lines.append(("Pit by", f"end of lap {hi}", "text"))
                if plan["save_ok"]:
                    fewer = "no stop" if n == 1 else f"{n - 1} stop{'s' if n > 2 else ''}"
                    lines.append((f"For {fewer}", f"{plan['save_target'] * k:.2f}{u}/lap  (save "
                                  f"{plan['save_pct'] * 100:.0f}%)", "purple"))
                elif plan["save_pct"] > 0:
                    lines.append(("Saving", f"would need {plan['save_pct'] * 100:.0f}% - not realistic", "dim"))
        self._view = (status, tuple(lines))
        return (self._view, self.width())

    def desired_height(self) -> int:
        n = len(self._view[1]) if self._view else 1
        return self.body_height(n + 1.4)

    def paint_content(self, p: QPainter):
        if self._view is None:
            if self.editing:
                self.card(p, "FUEL STRATEGY")
            return
        (status, scol), lines = self._view
        y = self.card(p, "FUEL STRATEGY")
        x0 = self.pad() * 1.4
        w = self.width() - 2 * x0
        lh = self.lh()
        p.setPen(getattr(self.pal, scol))
        self.draw_text(p, QRectF(x0, y, w, lh * 1.2), status, "mid")
        y += lh * 1.4
        for label, value, col in lines:
            y = self.kv(p, y, label, value, col)


class DashWidget(PanelWidget):
    NAME = "dash"
    TITLE = "Dash"
    HAS_HEADER = False
    MIN_WIDTH = 180
    FAST_CAPABLE = True

    def __init__(self, ctx):
        self._rpm_max = 0.0
        super().__init__(ctx)

    def _make_view(self, rpm, speed, gear, limiter):
        self._rpm_max = max(self._rpm_max * 0.9995, rpm, 6000.0)
        mph = self.cfg.get("unit", "kmh") == "mph"
        spd = speed * (2.23694 if mph else 3.6)
        frac = rpm / self._rpm_max if self._rpm_max else 0.0
        shift = frac >= float(self.cfg.get("shift_pct", 0.94))
        g = "R" if gear < 0 else "N" if gear == 0 else str(gear)
        return (g, f"{spd:.0f}", "mph" if mph else "km/h", round(frac, 3), shift, limiter)

    def content_key(self, snap):
        if self.fast_active():
            return ("fast", self.width())
        p = snap.player
        if p is None or not p.valid:
            self._view = None
            return None
        self._view = self._make_view(p.rpm, p.speed, p.gear, p.limiter)
        return (self._view, self.width())

    def fast_tick(self, timing) -> bool:
        f = timing.frame
        rpm = float(f.get("RPM", 0.0) or 0.0)
        view = self._make_view(rpm, float(f.get("Speed", 0.0) or 0.0), int(f.get("Gear", 0) or 0),
                               bool(int(f.get("EngineWarnings", 0) or 0) & 0x10))
        if view == self._view:
            return False
        self._view = view
        return True

    def desired_height(self) -> int:
        return int(self.fonts.em_base * 4.6)

    def paint_content(self, p: QPainter):
        if self._view is None:
            return
        gear, spd, unit, frac, shift, limiter = self._view
        r = QRectF(self.rect())
        pal = self.pal
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.bg)
        if shift:
            c = QColor(pal.red)
            c.setAlpha(150)
            p.setBrush(c)
        p.drawRoundedRect(r, pal.radius, pal.radius)
        self._drew_bg = True
        pad = self.pad()
        bar_h = max(6.0, r.height() * 0.16)
        top = QRectF(pad, pad * 0.3, r.width() - 2 * pad, r.height() - bar_h - pad * 1.6)
        p.setPen(pal.text)
        self.draw_text(p, QRectF(top.x(), top.y(), top.width() * 0.35, top.height()), gear, "huge", "c")
        self.draw_text(p, QRectF(top.x() + top.width() * 0.35, top.y(), top.width() * 0.45, top.height()), spd, "big", "r")
        p.setPen(pal.dim)
        self.draw_text(p, QRectF(top.x() + top.width() * 0.82, top.y(), top.width() * 0.18, top.height()), unit, "tiny")
        bar = QRectF(pad, r.height() - pad - bar_h, r.width() - 2 * pad, bar_h)
        col = pal.bad if frac > 0.94 else pal.yellow if frac > 0.85 else pal.good
        self.bar(p, bar, frac, col)
        if limiter:
            self.chip(p, QRectF(pad, pad * 0.5, self.text_width("LIMITER", "tiny") + 14, bar_h * 1.6), "LIMITER",
                      pal.blue, pal.text)


class InputsWidget(PanelWidget):
    NAME = "inputs"
    TITLE = "Inputs"
    HAS_HEADER = False
    HEIGHT_MODE = "free"
    MIN_WIDTH = 160
    MIN_HEIGHT = 40
    FAST_CAPABLE = True
    # stovint nelėtinam: pedalų spaudimas (pvz. boksuose) turi matytis iškart; kai niekas nejuda,
    # fast_tick vis tiek nepiešia (kreivės nepasikeitė), tad CPU beveik neauga
    IDLE_THROTTLE = False
    KEYS = ("throttle", "brake", "clutch", "steer", "abs")

    def __init__(self, ctx):
        self._seq = -1
        self._wheel = None
        self._fcache = {}
        super().__init__(ctx)

    def content_key(self, snap):
        if self.fast_active():  # gyvai piešia fast_tick (60 Hz), momentinė būsena nereikalinga
            return ("fast", self.width(), self.height())
        p = snap.player
        if p is None or not p.valid:
            self._view = None
            return None
        n = int(float(self.cfg.get("seconds", 4.0)) * 60)
        tr = {k: v[-n:] for k, v in (p.inputs or {}).items()}
        self._view = (tr, round(p.throttle, 2), round(p.brake, 2), round(p.clutch, 2), p.abs_active,
                      p.speed, p.gear, p.steer, int(p.t * 60))
        return (len(tr.get("throttle", ())), p.t, self.width(), self.height())

    def fast_tick(self, timing) -> bool:
        pl = timing.player
        if pl.inp_seq == self._seq:
            return False  # naujo mėginio nėra (pauzė) - neperpiešiam
        self._seq = pl.inp_seq
        n = int(float(self.cfg.get("seconds", 4.0)) * 60)
        arr = pl.input_trace(n)
        if arr is None:
            return False
        f = timing.frame
        speed, gear = round(float(f.get("Speed", 0.0) or 0.0), 1), int(f.get("Gear", 0) or 0)
        last = getattr(self, "_last_arr", None)
        if (last is not None and last[0].shape == arr.shape and last[1] == (speed, gear)
                and np.array_equal(last[0], arr)):
            return False  # stovint niekas nesikeičia - nepiešiam iš naujo
        self._last_arr = (arr.copy(), (speed, gear))
        tr = dict(zip(self.KEYS, arr))
        self._view = (tr, float(arr[0, -1]), float(arr[1, -1]), float(arr[2, -1]), bool(arr[4, -1] > 0.5),
                      speed, gear, float(arr[3, -1]), int(pl.inp_seq))
        return True

    def desired_height(self) -> int:
        return int(self.fonts.em_base * 6)

    def _font(self, px: float):
        px = max(6, int(round(px)))
        f = self._fcache.get(px)
        if f is None:
            from PySide6.QtGui import QFont
            f = self._fcache[px] = self.fonts._font(px, QFont.Weight.Bold)
        return f

    def parts(self) -> list:
        """Įjungtos dalys vartotojo tvarka (graph, bars, abs, wheel)."""
        from ..registry import INPUT_PARTS
        from .table import ordered_columns
        return ordered_columns(self.cfg, INPUT_PARTS, "parts", "parts_order")

    def _layout(self, r: QRectF):
        """Visų dalių vietos pagal valdiklio dydį ir tvarką (veikia bet kokiam monitoriui / masteliui)."""
        c = self.cfg
        pad = self.pad()
        parts = self.parts()
        bars = "bars" in parts
        pct = bars and c.get("show_percent", True)
        wheel = "wheel" in parts
        speed = wheel and c.get("show_speed", True)
        show_abs = "abs" in parts
        nbars = 3 if c.get("show_clutch") else 2
        inner_h = r.height() - 2 * pad
        bw = inner_h * 0.13 if bars else 0
        if pct:
            bw = max(bw, self.text_width("100", "tiny") + 2)
        asz = max(self.text_width("ABS", "tiny") + 8, inner_h * 0.42) if show_abs else 0
        wsz = inner_h * (0.60 if speed else 1.0) if wheel else 0  # 60 % vairas, 40 % greitis po juo
        sp_px = inner_h * 0.40 * 0.86
        sp_w = QFontMetricsF(self._font(sp_px)).horizontalAdvance("888") + 4 if speed else 0
        col_w = max(wsz, sp_w) if wheel else 0
        widths = {"bars": bw * nbars + pad * (nbars - 1), "abs": asz, "wheel": col_w}
        fixed = sum(widths[k] for k in parts if k != "graph") + pad * max(0, len(parts) - 1)
        gw = max(10.0, r.width() - 2 * pad - fixed) if "graph" in parts else 0.0
        x = pad if "graph" in parts else max(pad, (r.width() - fixed) / 2)
        rects = {}
        for k in parts:
            w = gw if k == "graph" else widths[k]
            rects[k] = QRectF(x, pad, w, inner_h)
            x += w + pad
        graph = rects.get("graph", QRectF(pad, pad, 0, inner_h))
        return dict(pad=pad, bars=bars, pct=pct, wheel=wheel, speed=speed, show_abs=show_abs, nbars=nbars, bw=bw,
                    asz=asz, wsz=wsz, sp_px=sp_px, col_w=col_w, graph=graph, rects=rects, has_graph="graph" in parts,
                    lab_h=self.lh() * 0.75 if pct else 0)

    def paint_content(self, p: QPainter):
        if self._view is None:
            return
        tr, thr, brk, clu, abs_on, speed, gear, steer, seq = self._view
        r = QRectF(self.rect())
        pal = self.pal
        lkey = (self.width(), self.height(), id(self.fonts), tuple(sorted((k, repr(v)) for k, v in self.cfg.items()
                                                                          if k.startswith(("show", "parts")))))
        if getattr(self, "_lay", (None,))[0] != lkey:
            self._lay = (lkey, self._layout(r))
        L = self._lay[1]
        pad, graph, bw, nbars, rects = L["pad"], L["graph"], L["bw"], L["nbars"], L["rects"]
        bar_top = graph.top() + L["lab_h"]
        # fonas, tinklelis ir juostų pagrindai nesikeičia - paruošiami vieną kartą
        bkey = (lkey, id(pal), self.devicePixelRatioF())
        if getattr(self, "_bg_key", None) != bkey:
            from PySide6.QtGui import QPixmap
            dpr = self.devicePixelRatioF()
            pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(pal.bg)
            q.drawRoundedRect(r, pal.radius, pal.radius)
            if L["has_graph"]:
                q.setPen(QPen(pal.row_alt, 1))
                for k in (0.25, 0.5, 0.75):
                    yy = graph.bottom() - graph.height() * k
                    q.drawLine(QPointF(graph.left(), yy), QPointF(graph.right(), yy))
            if L["bars"]:
                x = rects["bars"].left()
                q.setPen(Qt.PenStyle.NoPen)
                q.setBrush(pal.track)
                for _ in range(nbars):
                    q.drawRoundedRect(QRectF(x, bar_top, bw, graph.bottom() - bar_top), 2, 2)
                    x += bw + pad
            q.end()
            self._bg_pm, self._bg_key = pm, bkey
        p.drawPixmap(0, 0, self._bg_pm)
        self._drew_bg = True

        if L["has_graph"]:
            self._paint_traces(p, tr, graph, seq)
        if L["bars"]:
            x = rects["bars"].left()
            vals = [(thr, pal.good), (brk, pal.yellow if abs_on else pal.bad)]
            if nbars == 3:
                vals.append((clu, pal.blue))
            p.setPen(Qt.PenStyle.NoPen)
            bh = graph.bottom() - bar_top
            for v, col in vals:
                h = bh * max(0.0, min(1.0, v))
                if h > 0.5:
                    p.fillRect(QRectF(x, graph.bottom() - h, bw, h), col)
                if L["pct"]:
                    p.setPen(col)
                    self.draw_text(p, QRectF(x - 4, graph.top(), bw + 8, L["lab_h"]), f"{v * 100:.0f}", "tiny", "c")
                    p.setPen(Qt.PenStyle.NoPen)
                x += bw + pad
        if L["show_abs"]:  # ABS lemputė: dega, kol ABS mažina stabdymo jėgą (BrakeABSactive)
            asz = L["asz"]
            ra = rects["abs"]
            ar = QRectF(ra.left(), ra.center().y() - asz / 2, asz, asz)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(pal.yellow if abs_on else pal.track)
            p.drawRoundedRect(ar, 3, 3)
            p.setPen(QColor(20, 20, 20) if abs_on else pal.dim)
            self.draw_text(p, ar, "ABS", "tiny", "c")
        if L["wheel"]:
            self._paint_wheel(p, rects["wheel"], L, steer, gear, speed)

    def _paint_traces(self, p: QPainter, tr: dict, graph: QRectF, seq: int):
        pal = self.pal
        pen_w = max(1.5, self._scale() * 1.8)
        buckets = max(8, int(graph.width() / 5))  # grupė ~5 px (min + max): pikai lieka, piešti pigu

        def to_poly(idx, v, n, center, scale):
            v = np.clip(v * scale, -1, 1) if center else np.clip(v, 0, 1)
            xs = graph.left() + idx * (graph.width() / max(1, n - 1))
            ys = graph.center().y() - v * graph.height() / 2 if center else graph.bottom() - v * graph.height()
            return QPolygonF(list(map(QPointF, xs.tolist(), ys.tolist())))

        def trace(vals, color, center=False, scale=1.0, aa=True, width=None):
            if vals is None or len(vals) < 2:
                return
            idx, v = decimate(np.asarray(vals), seq, buckets)
            p.setPen(QPen(color, width or pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap,
                          Qt.PenJoinStyle.BevelJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            if not aa:
                p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            p.drawPolyline(to_poly(idx, v, len(vals), center, scale))
            if not aa:
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self.cfg.get("show_steering", True):
            trace(tr.get("steer"), QColor(200, 200, 210, 150), center=True, scale=1 / 2.5, aa=False)
        if self.cfg.get("show_clutch"):
            trace(tr.get("clutch"), pal.blue)
        brake = tr.get("brake")
        trace(brake, pal.bad)
        absv = tr.get("abs")
        if brake is not None and absv is not None and len(absv) == len(brake):
            # ABS: ta stabdžio kreivės dalis, kur ABS veikė, lieka geltona ir slenka kartu su ja
            n = len(brake)
            col = QColor(pal.yellow)
            p.setPen(QPen(col, pen_w * 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            for a, b in runs(np.asarray(absv) > 0.5):
                lo, hi = max(0, a - 1), min(n - 1, b + 1)
                idx = np.arange(lo, hi + 1)
                p.drawPolyline(to_poly(idx, np.asarray(brake)[idx], n, False, 1.0))
        trace(tr.get("throttle"), pal.good)

    def _paint_wheel(self, p: QPainter, col: QRectF, L: dict, steer: float, gear: int, speed: float):
        """GT3 D formos vairas (sukasi kartu su tavo vairu), pavara centre, greitis po vairu."""
        img = self.cfg.get("wheel_image") or ""
        if self._wheel is None or getattr(self._wheel, "path", "") != img:
            self._wheel = ImageWheel(img) if img else GT3Wheel()
        wsz = L["wsz"]
        c = QPointF(col.center().x(), col.top() + wsz / 2)
        self._wheel.draw(p, c, wsz, steer, self.devicePixelRatioF())
        g = "R" if gear < 0 else "N" if gear == 0 else str(gear)
        p.setPen(self.pal.text)
        p.setFont(self._font(wsz * 0.30))
        p.drawText(QRectF(c.x() - wsz / 2, c.y() - wsz * 0.24, wsz, wsz * 0.36), Qt.AlignmentFlag.AlignCenter, g)
        if L["speed"]:
            mph = self.cfg.get("unit", "kmh") == "mph"
            spd = f"{speed * (2.23694 if mph else 3.6):.0f}"
            p.setFont(self._font(L["sp_px"]))
            p.setPen(self.pal.text)
            p.drawText(QRectF(col.left() - 4, col.top() + wsz, col.width() + 8, col.height() - wsz),
                       Qt.AlignmentFlag.AlignCenter, spd)


class GForceWidget(PanelWidget):
    NAME = "gforce"
    TITLE = "G-force"
    HAS_HEADER = False
    HEIGHT_MODE = "free"
    MIN_WIDTH = 80
    MIN_HEIGHT = 80

    def content_key(self, snap):
        p = snap.player
        if p is None or not p.valid:
            self._view = None
            return None
        trail = tuple(p.g_trail) if self.cfg.get("trail", True) else ()
        self._view = (round(p.lat_g, 2), round(p.long_g, 2), trail)
        return (self._view[:2], len(trail), p.t, self.width(), self.height())

    def desired_height(self) -> int:
        return self.width()

    def paint_content(self, p: QPainter):
        if self._view is None:
            return
        lat, lon, trail = self._view
        r = QRectF(self.rect())
        pal = self.pal
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.bg)
        p.drawRoundedRect(r, pal.radius, pal.radius)
        self._drew_bg = True
        c = r.center()
        rad = min(r.width(), r.height()) / 2 - self.pad()
        mg = float(self.cfg.get("max_g", 3.0) or 3.0)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for g in range(1, int(mg) + 1):
            p.setPen(QPen(pal.row_alt if g < mg else pal.dim, 1))
            rr = rad * g / mg
            p.drawEllipse(c, rr, rr)
        p.setPen(QPen(pal.row_alt, 1))
        p.drawLine(QPointF(c.x() - rad, c.y()), QPointF(c.x() + rad, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - rad), QPointF(c.x(), c.y() + rad))

        def pt(la, lo):
            k = rad / mg
            return QPointF(c.x() + max(-mg, min(mg, la)) * k, c.y() - max(-mg, min(mg, lo)) * k)

        p.setPen(Qt.PenStyle.NoPen)
        n = len(trail)
        for i, (la, lo) in enumerate(trail):
            col = QColor(pal.accent)
            col.setAlpha(int(30 + 120 * i / max(1, n)))
            p.setBrush(col)
            p.drawEllipse(pt(la, lo), 2.5, 2.5)
        p.setBrush(pal.accent)
        p.drawEllipse(pt(lat, lon), max(4.0, rad * 0.08), max(4.0, rad * 0.08))
        p.setPen(pal.text)
        tot = math.hypot(lat, lon)
        self.draw_text(p, QRectF(self.pad(), self.pad() * 0.5, r.width(), self.lh()), f"{tot:.1f} g", "small")


def _temp_color(pal, t):
    if not math.isfinite(t):
        return pal.track
    if t < 65:
        return pal.blue
    if t < 80:
        return QColor(90, 200, 230)
    if t <= 100:
        return pal.good
    if t <= 110:
        return pal.yellow
    return pal.bad


class TyresWidget(PanelWidget):
    NAME = "tyres"
    TITLE = "Tyres"
    MIN_WIDTH = 200

    def content_key(self, snap):
        p = snap.player
        if p is None or not p.tyres:
            self._view = None
            return None
        data = []
        for w in ("LF", "RF", "LR", "RR"):
            temps, wear, press = p.tyres.get(w, ((math.nan,) * 3, (math.nan,) * 3, math.nan))
            data.append((w, tuple(round(t, 0) if math.isfinite(t) else math.nan for t in temps),
                         tuple(round(x * 100) if math.isfinite(x) else -1 for x in wear),
                         round(press, 0) if math.isfinite(press) else -1))
        self._view = tuple(data)
        return (self._view, self.width(), self.cfg.get("show_wear"), self.cfg.get("show_pressure"))

    def desired_height(self) -> int:
        extra = (1 if self.cfg.get("show_wear", True) else 0) + (1 if self.cfg.get("show_pressure") else 0)
        return self.body_height(2 * (1.8 + extra * 0.9) + 0.9)

    def paint_content(self, p: QPainter):
        if self._view is None:
            if self.editing:
                self.card(p, "TYRES")
            return
        y0 = self.card(p, "TYRES", "updated in pits")
        pad = self.pad()
        lh = self.lh()
        extra = (1 if self.cfg.get("show_wear", True) else 0) + (1 if self.cfg.get("show_pressure") else 0)
        cell_h = lh * (1.8 + extra * 0.9)
        cw = (self.width() - pad * 3) / 2
        for i, (w, temps, wear, press) in enumerate(self._view):
            col, row = i % 2, i // 2
            x = pad + col * (cw + pad)
            y = y0 + row * (cell_h + pad * 0.6)
            p.setPen(self.pal.dim)
            self.draw_text(p, QRectF(x, y, cw, lh * 0.8), w, "tiny")
            sw = cw / 3
            for k, t in enumerate(temps):
                rect = QRectF(x + k * sw + 1, y + lh * 0.8, sw - 2, lh)
                bg = QColor(_temp_color(self.pal, t))
                bg.setAlpha(170)
                self.chip(p, rect, "–" if not math.isfinite(t) else f"{t:.0f}°", bg, self.pal.text, "small")
            yy = y + lh * 1.85
            if self.cfg.get("show_wear", True):
                p.setPen(self.pal.dim)
                txt = "  ".join("–" if x < 0 else f"{x}%" for x in wear)
                self.draw_text(p, QRectF(x, yy, cw, lh * 0.8), txt, "tiny", "c")
                yy += lh * 0.9
            if self.cfg.get("show_pressure"):
                p.setPen(self.pal.dim)
                self.draw_text(p, QRectF(x, yy, cw, lh * 0.8), "–" if press < 0 else f"{press:.0f} kPa", "tiny", "c")


class CarSettingsWidget(PanelWidget):
    NAME = "car_settings"
    TITLE = "Car setting changes"
    HAS_HEADER = False

    def content_key(self, snap):
        p = snap.player
        hold = float(self.cfg.get("hold", 3.0))
        ev = [] if p is None else [e for e in p.dc_events if e[3] < hold]
        # vienas įrašas kiekvienam nustatymui (paskutinis)
        last = {}
        for name, old, new, age in ev:
            first_old = last[name][0] if name in last else old
            last[name] = (first_old, new)
        self._view = tuple((k, v[0], v[1]) for k, v in last.items())[-3:]
        return (self._view, self.width())

    def desired_height(self) -> int:
        return self.body_height(max(1, len(self._view or ())) * 1.2)

    def paint_content(self, p: QPainter):
        rows = self._view or ()
        if not rows:
            if not self.editing:
                return
            rows = (("Brake bias", "54.2", "53.8"),)
        self.card(p)
        lh = self.lh() * 1.2
        y = self.pad() * 0.7
        x0 = self.pad() * 1.4
        w = self.width() - 2 * x0
        for name, old, new in rows:
            p.setPen(self.pal.dim)
            self.draw_text(p, QRectF(x0, y, w * 0.5, lh), name.upper(), "tiny")
            p.setPen(self.pal.dim)
            self.draw_text(p, QRectF(x0, y, w * 0.72, lh), f"{old}  →", "small", "r")
            p.setPen(self.pal.accent)
            self.draw_text(p, QRectF(x0, y, w, lh), new, "mid", "r")
            y += lh


class EngineWarningsWidget(PanelWidget):
    NAME = "engine_warn"
    TITLE = "Engine warnings"
    HAS_HEADER = False

    def content_key(self, snap):
        p = snap.player
        if p is None or not p.valid:
            self._view = None
            return None
        temps = ""
        if self.cfg.get("always"):
            parts = []
            if math.isfinite(p.water_temp):
                parts.append(f"Water {p.water_temp:.0f}°")
            if math.isfinite(p.oil_temp):
                parts.append(f"Oil {p.oil_temp:.0f}°")
            if math.isfinite(p.oil_press):
                parts.append(f"Oil {p.oil_press:.1f} bar")
            temps = "   ".join(parts)
        self._view = (tuple(p.warnings), temps)
        return (self._view, self.width())

    def desired_height(self) -> int:
        n = len(self._view[0]) if self._view else 0
        return self.body_height(max(1, n + (1 if self._view and self._view[1] else 0)) * 1.1)

    def paint_content(self, p: QPainter):
        warns, temps = self._view if self._view else ((), "")
        if not warns and not temps:
            if not self.editing:
                return
            temps = "Shows only when something is wrong"
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        if warns:
            c = QColor(self.pal.bad)
            c.setAlpha(210)
            p.setBrush(c)
        else:
            p.setBrush(self.pal.bg)
        p.drawRoundedRect(r, self.pal.radius, self.pal.radius)
        self._drew_bg = True
        y = self.pad() * 0.7
        lh = self.lh() * 1.1
        for wtxt in warns:
            y = self.text_line(p, y, "⚠  " + wtxt.upper(), "text", "bold")
        if temps:
            self.text_line(p, y, temps, "text" if warns else "dim", "small")
