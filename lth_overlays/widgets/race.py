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
    from ..flags import RACE_FLAG_STYLE as STYLE  # (fonas, tekstas)
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
        if "blue" in active and snap.session_type != "race" and not self.cfg.get("blue_outside_race"):
            del active["blue"]
        elif "blue" in active and self.cfg.get("blue_strict", False) and not self._blue_is_real(snap):
            del active["blue"]
        if "blue" not in active and self._blue_is_real(snap) and snap.session_type == "race" \
                and self.cfg.get("blue_early", True):
            active["blue"] = "BLUE FLAG"  # greitesnė mašina jau visai čia - prieš iRacing vėliavą
        # formuotės ratas - tik kol sesija tikrai „parade laps“ (PaceMode iRacing kartais lieka visą lenktynę)
        from lth_timing.frame import STATE_PARADE
        if snap.session_state == STATE_PARADE and not any(k in active for k in ("one_to_green", "caution",
                                                                                 "caution_waving", "red")):
            active["formation"] = "FORMATION LAP"
        if not self.cfg.get("show_green"):  # žalia / „one to green“ / formuotė - tik įjungus
            for k in ("green", "one_to_green", "formation"):
                active.pop(k, None)
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

    def _blue_is_real(self, snap) -> bool:
        """Mėlyna rodoma tik jei už manęs tikrai yra mašina, kuri lenkia ratu arba greitesnės klasės."""
        if snap.session_type != "race":
            return bool(self.cfg.get("blue_outside_race"))
        me = next((r for r in snap.cars if r.is_me), None)
        cls = snap.classes or {}
        my_lap = (cls.get(me.class_id, {}) or {}).get("est_lap") if me is not None else None
        if me is not None and not my_lap and me.best_lap > 0:
            my_lap = me.best_lap
        window = float(self.cfg.get("blue_window", 1.5))
        for r in snap.relative:
            if r.is_me or not (-window <= r.gap < 0) or r.car.status != "track":
                continue
            if r.lap_rel > 0:
                return True
            other = (cls.get(r.car.class_id, {}) or {}).get("est_lap") or (r.car.best_lap if r.car.best_lap > 0 else None)
            if me is not None and r.car.class_id != me.class_id and other and my_lap and other < my_lap * 0.99:
                return True
        return False

    @staticmethod
    def _rank(key):
        order = ("disqualify", "black", "repair", "red", "caution_waving", "caution", "yellow_waving", "yellow",
                 "debris", "blue", "white", "checkered", "one_to_green", "formation", "green")
        return order.index(key) if key in order else 99

    # filtras kopijoms: kokias vėliavas rodo šis valdiklis
    GROUPS = {"yellow": ("caution_waving", "caution", "yellow_waving", "yellow", "debris"), "blue": ("blue",),
              "black": ("disqualify", "black", "repair"), "red": ("red",), "white": ("white",),
              "checkered": ("checkered",), "start": ("one_to_green", "green", "formation")}

    def _allowed(self, key) -> bool:
        only = self.cfg.get("only") or {}
        for g, keys in self.GROUPS.items():
            if key in keys:
                return only.get(g, True) is not False
        return True

    def desired_height(self) -> int:
        st = self.cfg.get("style", "banner")
        if st in ("tile", "light", "wave", "led"):
            return int(self.width() * (1.0 if st != "light" else 0.82) +
                       (self.fonts.em_small * 1.7 if self.cfg.get("label", True) else 0))
        if st == "strip":
            return int(self.fonts.em_base * 0.9)
        return int(self.fonts.em_base * 2.8)

    def paint_content(self, p: QPainter):
        view = self._view
        if view is not None and not self._allowed(view[0]):
            view = None
        if view is None:
            if not self.editing:
                return
            view = ("yellow", "YELLOW")
        key, txt = view
        st = self.cfg.get("style", "banner")
        if st == "banner":
            self._paint_banner(p, key, txt)
            return
        r = QRectF(self.rect())
        rad = self.pal.radius
        self._drew_bg = True
        lab_h = self.fonts.em_small * 1.7 if self.cfg.get("label", True) and st != "strip" else 0.0
        if st == "strip":
            bg, _fg = self.STYLE.get(key, ((60, 60, 60), (255, 255, 255)))
            self._cloth(p, r, key, 0.0, rad)
            return
        # plytelė / lemputė / plazdanti vėliava: tamsus pagrindas, vėliava viduje, užrašas apačioje
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.pal.bg)
        p.drawRoundedRect(r, rad, rad)
        area = QRectF(r.x(), r.y(), r.width(), r.height() - lab_h)
        m = min(area.width(), area.height()) * 0.12
        inner = area.adjusted(m, m, -m, -m)
        if st == "tile":
            self._cloth(p, inner, key, 0.0, max(2.0, rad * 0.7))
        elif st == "led":
            side = min(area.width(), area.height()) * 0.94
            box = QRectF(area.center().x() - side / 2, area.center().y() - side / 2, side, side)
            p.drawPixmap(box.topLeft(), self._led_panel(key, side))
        elif st == "wave":
            pole = QRectF(inner.x(), inner.y(), max(2.0, inner.width() * 0.035), inner.height())
            p.setBrush(QColor(200, 200, 205))
            p.drawRoundedRect(pole, 1.5, 1.5)
            cloth = QRectF(pole.right() + 1, inner.y() + inner.height() * 0.04, inner.width() - pole.width() - 1,
                           inner.height() * 0.62)
            self._cloth(p, cloth, key, cloth.height() * 0.09, 0.0)
        else:  # light - kaip trasos šviesų panelis
            bg, _fg = self.STYLE.get(key, ((60, 60, 60), (255, 255, 255)))
            col = QColor(*bg) if key not in ("black", "disqualify") else QColor(240, 240, 240)
            if key == "repair":
                col = QColor(255, 120, 20)
            d = min(inner.width(), inner.height())
            c = inner.center()
            from PySide6.QtGui import QRadialGradient
            for k, a in ((1.0, 40), (0.82, 70)):
                g = QColor(col)
                g.setAlpha(a)
                p.setBrush(g)
                p.drawEllipse(c, d / 2 * k, d / 2 * k)
            rg = QRadialGradient(c, d * 0.36)
            rg.setColorAt(0.0, col.lighter(150))
            rg.setColorAt(0.75, col)
            rg.setColorAt(1.0, col.darker(130))
            p.setBrush(rg)
            p.drawEllipse(c, d * 0.34, d * 0.34)
            if key == "checkered":
                self._cloth(p, QRectF(c.x() - d * 0.24, c.y() - d * 0.24, d * 0.48, d * 0.48), key, 0.0, d * 0.24)
        if lab_h:
            p.setPen(self.pal.text)
            self.draw_text(p, QRectF(r.x() + 4, r.bottom() - lab_h - 2, r.width() - 8, lab_h), txt, "small", "c")

    def _led_panel(self, key, side: float):
        """Trasos LED skydas: taškų matrica (vėliavos raštas), užgesę taškai pilki. Paruošiama vieną kartą."""
        dpr = self.devicePixelRatioF()
        ck = (key, round(side, 1), dpr)
        cache = self.__dict__.setdefault("_led_cache", {})
        pm = cache.get(ck)
        if pm is not None:
            return pm
        from PySide6.QtGui import QImage, QPixmap
        n = 22
        img = QImage(n, n, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0))
        q = QPainter(img)
        self._cloth(q, QRectF(0, 0, n, n), key, 0.0, 0.0)
        q.end()
        pm = QPixmap(int(side * dpr), int(side * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(QColor(14, 14, 16))
        q.drawRoundedRect(QRectF(0, 0, side, side), side * 0.05, side * 0.05)
        m = side * 0.05
        step = (side - 2 * m) / n
        rad = step * 0.36
        dark = key in ("black", "disqualify")
        for j in range(n):
            for i in range(n):
                c = QColor(img.pixel(i, j))
                border = i in (0, n - 1) or j in (0, n - 1)
                if dark and border:
                    c = QColor(245, 245, 245)
                lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
                if lum < 40:
                    c = QColor(46, 46, 50)  # užgesęs taškas
                else:
                    c = c.lighter(115)
                cx, cy = m + (i + 0.5) * step, m + (j + 0.5) * step
                if lum >= 40:
                    glow = QColor(c)
                    glow.setAlpha(60)
                    q.setBrush(glow)
                    q.drawEllipse(QPointF(cx, cy), rad * 1.45, rad * 1.45)
                q.setBrush(c)
                q.drawEllipse(QPointF(cx, cy), rad, rad)
        q.end()
        if len(cache) > 40:
            cache.clear()
        cache[ck] = pm
        return pm

    def _cloth(self, p, r: QRectF, key, wave: float, rad: float):
        from ..flags import paint_race_flag
        paint_race_flag(p, r, key, wave, rad)

    def _paint_banner(self, p: QPainter, key, txt):
        bg, fg = self.STYLE.get(key, ((60, 60, 60), (255, 255, 255)))
        r = QRectF(self.rect())
        rad = self.pal.radius
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(*bg))
        p.drawRoundedRect(r, rad, rad)
        self._drew_bg = True
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
        if self.cfg.get("style", "radar") in ("bars", "arrows"):
            side = self.cfg.get("side", "both")
            busy = bool((left and side != "right") or (right and side != "left"))
        self._view = (tuple(sorted(cars)), left, right, rng) if (busy or self.cfg.get("always")) else None
        return (self._view, self.width(), self.height())

    def desired_height(self) -> int:
        st = self.cfg.get("style", "radar")
        if st == "bars":
            return int(self.width() * (0.9 if self.cfg.get("side", "both") == "both" else 3.0))
        if st == "arrows":
            return int(self.width() * (0.45 if self.cfg.get("side", "both") == "both" else 1.0))
        return int(self.width() * 1.3)

    def paint_content(self, p: QPainter):
        view = self._view
        if view is None:
            if not self.editing:
                return
            view = ((-6.0, 12.0), 1, 0, float(self.cfg.get("range", 20)))
        st = self.cfg.get("style", "radar")
        if st in ("bars", "arrows"):
            self._paint_blindspot(p, view, st)
            return
        cars, left, right, rng = view
        r = QRectF(self.rect())
        pal = self.pal
        p.setPen(Qt.PenStyle.NoPen)
        bg = QColor(pal.bg)
        p.setBrush(bg)
        p.drawRoundedRect(r, pal.radius * 2, pal.radius * 2)
        self._drew_bg = pal.radius * 2
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
        # šonų įspėjimai: mašina šone pastumta tiek, kiek ji išlindusi į priekį / atsilikusi (kaip spotteris)
        near = min(cars, key=abs) if cars else 0.0
        if abs(near) > CAR_LEN_M * 1.3:
            near = 0.0
        for side, n in ((-1, left), (1, right)):
            if n:
                col = QColor(pal.bad)
                col.setAlpha(170 if n == 1 else 230)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col)
                x = cx + side * lane - cw / 2
                for i in range(n):
                    p.drawRoundedRect(QRectF(x + side * i * lane, cy - near * k - ch / 2, cw, ch), 3, 3)
                if self.cfg.get("overlap_text", True) and abs(near) >= 0.5:
                    p.setPen(pal.text)
                    tx = x + side * lane * (n - 1) + (cw + 4 if side > 0 else -40)
                    self.draw_text(p, QRectF(tx, cy - near * k - 8, 36, 16),
                                   f"{abs(near):.1f}", "tiny", "l" if side > 0 else "r")
                    p.setPen(Qt.PenStyle.NoPen)
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


    def _paint_blindspot(self, p: QPainter, view, st):
        """Akla zona: šoninės juostos arba rodyklės. Juostoje mašinos blokas juda pagal tai, kiek ji priekyje / gale
        (iRacing duoda tik „kairėje / dešinėje“, o atstumą išilgai - artimiausia mašina iš relative)."""
        cars, left, right, _rng = view
        r = QRectF(self.rect())
        pal = self.pal
        self._drew_bg = True
        side = self.cfg.get("side", "both")
        sides = [s_ for s_ in (-1, 1) if (side == "both" or (side == "left") == (s_ < 0))]
        near = min(cars, key=abs) if cars else 0.0
        if abs(near) > CAR_LEN_M * 1.3:
            near = 0.0
        p.setPen(Qt.PenStyle.NoPen)
        for s_ in sides:
            n = left if s_ < 0 else right
            if len(sides) == 2:
                box = QRectF(r.x(), r.y(), r.width() * 0.34, r.height()) if s_ < 0 else \
                    QRectF(r.right() - r.width() * 0.34, r.y(), r.width() * 0.34, r.height())
            else:
                box = QRectF(r)
            col = QColor(pal.bad if n else pal.dim)
            if st == "bars":
                track = QColor(pal.bg)
                p.setBrush(track)
                rad = min(box.width(), box.height()) * 0.3
                p.drawRoundedRect(box, rad, rad)
                inner = box.adjusted(box.width() * 0.18, box.width() * 0.18, -box.width() * 0.18, -box.width() * 0.18)
                if n:
                    from PySide6.QtGui import QLinearGradient
                    g = QLinearGradient(inner.topLeft(), inner.bottomLeft())
                    c1, c2 = QColor(col), QColor(col)
                    c1.setAlpha(60)
                    c2.setAlpha(60)
                    mid = QColor(col)
                    mid.setAlpha(235 if n > 1 else 190)
                    g.setColorAt(0.0, c1)
                    g.setColorAt(0.5, mid)
                    g.setColorAt(1.0, c2)
                    p.setBrush(g)
                    p.drawRoundedRect(inner, rad * 0.6, rad * 0.6)
                    # mašinos blokas: kiek ji priekyje (+) / gale (-)
                    k = inner.height() / (CAR_LEN_M * 3)
                    ch = CAR_LEN_M * k
                    cy = inner.center().y() - near * k
                    p.setBrush(QColor(255, 255, 255, 230))
                    p.drawRoundedRect(QRectF(inner.x() + inner.width() * 0.15, cy - ch / 2, inner.width() * 0.7, ch),
                                      3, 3)
                else:
                    idle = QColor(pal.dim)
                    idle.setAlpha(45)
                    p.setBrush(idle)
                    p.drawRoundedRect(inner, rad * 0.6, rad * 0.6)
            else:  # arrows - rodyklės
                if not n:
                    col.setAlpha(60)
                cx, cy = box.center().x(), box.center().y()
                h = min(box.height(), box.width() * 1.4) * 0.8
                w = h * 0.55
                for i in range(2 if n > 1 else 1):
                    off = i * w * 0.7 * s_
                    poly = [QPointF(cx + off - s_ * w / 2, cy - h / 2), QPointF(cx + off + s_ * w / 2, cy),
                            QPointF(cx + off - s_ * w / 2, cy + h / 2)]
                    pen = QPen(col, max(3.0, h * 0.16), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                               Qt.PenJoinStyle.RoundJoin)
                    p.setPen(pen)
                    p.drawPolyline(poly)
                p.setPen(Qt.PenStyle.NoPen)


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

    def wants_visible(self, snap) -> bool:
        if not super().wants_visible(snap):
            return False
        if self.cfg.get("display", "always") != "popup" or self.editing or snap is None:
            return True
        p = snap.player
        return bool(p is not None and p.valid and p.inc_last_add > 0 and p.inc_age < float(self.cfg.get("popup", 5.0)))

    def content_key(self, snap):
        p = snap.player
        limit = int(self.cfg.get("limit", 0) or 0) or int(getattr(snap, "incident_limit", 0) or 0)
        if p is None or not p.valid:  # garaže / kol neprisijungęs - paskutinis žinomas skaičius
            last = getattr(self, "_last_inc", (0, None))
            self._view = (last[0], last[1], limit, 0)
            return (self._view, self.width())
        popup = float(self.cfg.get("popup", 5.0))
        fresh = p.inc_last_add if p.inc_age < popup and p.inc_last_add > 0 else 0
        team = p.inc_team if p.inc_team and p.inc_team != p.inc_my else None
        self._last_inc = (p.inc_my, team)
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
        self._drew_bg = True
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


# ---------------------------------------------------------------- Pit commands (mygtukai)
class PitCommandsWidget(PanelWidget):
    """Mygtukai pit servisui be black box: paspaudi pele, komanda nueina į iRacing."""

    NAME = "pit_commands"
    TITLE = "Pit commands"
    MIN_WIDTH = 220
    INTERACTIVE = True
    BUTTONS = (("tyres", "All tyres"), ("finish", "Fuel to finish"), ("full", "Full tank"), ("nofuel", "No fuel"),
               ("fr", "Fast repair"), ("ws", "Windscreen"), ("clear", "Clear all"))

    def __init__(self, ctx):
        self._hover = None
        self._flash = None  # (mygtukas, laikas) - trumpas patvirtinimas paspaudus
        self._state = {}
        super().__init__(ctx)
        self.setMouseTracking(True)

    def content_key(self, snap):
        p = snap.player
        flags = p.pit_flags if p is not None else 0
        need = None
        if p is not None and p.fuel_to_finish is not None and math.isfinite(p.fuel_l):
            margin = float(self.ctx.config.widget("fuel").get("margin", 0.5) or 0) * (p.fuel_per_lap or 0)
            need = max(0.0, p.fuel_to_finish + margin - p.fuel_l)
        self._state = {"flags": flags, "fuel": p.pit_fuel if p is not None else 0.0,
                       "max": p.fuel_max_l if p is not None else 0.0, "need": need,
                       "repairs": p.fast_repairs if p is not None else 0}
        active = {
            "tyres": flags & 0x0F == 0x0F, "finish": False, "full": False, "nofuel": not flags & 0x10,
            "fr": bool(flags & 0x40), "ws": bool(flags & 0x20), "clear": False,
        }
        sub = f"Fuel +{self._state['fuel']:.1f} l" if flags & 0x10 else "No fuel"
        if need is not None:
            sub += f"   ·   to finish {need:.1f} l"
        self._view = (tuple(sorted(active.items())), sub, self._hover, self._flash[0] if self._flash else None)
        return (self._view, self.width())

    def desired_height(self) -> int:
        rows = (len(self.BUTTONS) + 1) // 2
        return self.body_height(1.2 + rows * 1.55)

    def _rects(self):
        lh = self.lh()
        x0 = self.pad()
        y0 = self.header_h() + self.pad() * 0.4 + lh * 1.2
        w = (self.width() - 3 * x0) / 2
        out = {}
        for i, (key, _) in enumerate(self.BUTTONS):
            col, row = i % 2, i // 2
            out[key] = QRectF(x0 + col * (w + x0), y0 + row * lh * 1.55, w, lh * 1.3)
        return out

    def paint_content(self, p: QPainter):
        if self._view is None:
            return
        active, sub, hover, flash = self._view
        active = dict(active)
        y = self.card(p, "PIT COMMANDS", "click to set")
        p.setPen(self.pal.dim)
        self.text_line(p, y, sub, "dim", "small")
        for key, rect in self._rects().items():
            label = dict(self.BUTTONS)[key]
            on = active.get(key)
            bg = QColor(self.pal.accent) if on else QColor(self.pal.track)
            if key == flash:
                bg = QColor(self.pal.good)
            elif key == hover and not on:
                bg = QColor(self.pal.text)
                bg.setAlpha(60)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(rect, 5, 5)
            p.setPen(self.pal.ink if (on or key == flash) else self.pal.text)
            self.draw_text(p, rect, label, "small", "c")

    def _hit(self, pos):
        for key, rect in self._rects().items():
            if rect.contains(pos):
                return key
        return None

    def mouseMoveEvent(self, e):
        if self.editing:
            return super().mouseMoveEvent(e)
        h = self._hit(e.position())
        if h != self._hover:
            self._hover = h
            self.setCursor(Qt.CursorShape.PointingHandCursor if h else Qt.CursorShape.ArrowCursor)
            self._refresh()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        if self._hover is not None:
            self._hover = None
            self._refresh()

    def mousePressEvent(self, e):
        if self.editing:
            return super().mousePressEvent(e)
        if e.button() != Qt.MouseButton.LeftButton:
            return
        key = self._hit(e.position())
        if key is None:
            return
        self.send(key)
        self._flash = (key, 0)
        self._refresh()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(350, self._end_flash)

    def _end_flash(self):
        self._flash = None
        self._refresh()

    def _refresh(self):
        self._key = object()
        if self._snap is not None:
            self.push(self._snap, force=True)
        else:
            self.update()

    def send(self, key) -> list:
        """Komandų seka iRacing'ui. Grąžina [(mode, value)] (testams)."""
        from .. import win32 as w
        st = self._state
        flags = st.get("flags", 0)
        cmds = []
        if key == "tyres":
            if flags & 0x0F == 0x0F:
                cmds = [(w.PIT_CLEAR_TIRES, 0)]
            else:
                cmds = [(w.PIT_LF, 0), (w.PIT_RF, 0), (w.PIT_LR, 0), (w.PIT_RR, 0)]
        elif key == "finish" and st.get("need") is not None:
            cmds = [(w.PIT_FUEL, int(math.ceil(st["need"])))] if st["need"] > 0 else [(w.PIT_CLEAR_FUEL, 0)]
        elif key == "full":
            cmds = [(w.PIT_FUEL, int(math.ceil(st.get("max") or 999)))]
        elif key == "nofuel":
            cmds = [(w.PIT_CLEAR_FUEL, 0)]
        elif key == "fr":
            cmds = [(w.PIT_CLEAR_FR, 0)] if flags & 0x40 else [(w.PIT_FR, 0)]
        elif key == "ws":
            cmds = [(w.PIT_CLEAR_WS, 0)] if flags & 0x20 else [(w.PIT_WS, 0)]
        elif key == "clear":
            cmds = [(w.PIT_CLEAR, 0)]
        for mode, value in cmds:
            w.pit_command(mode, value)
        return cmds
