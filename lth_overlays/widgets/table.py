"""Bendras lentelės piešimas Standings ir Relative valdikliams (v0.6 dizainas).

Eilutės aprašomos hashable tuple'ais (tekstas + spalvos žetonas), todėl jas
galima tiesiog palyginti su ankstesnėmis ir nepiešti, jei niekas nepasikeitė.

Naujovės: vėliavos, spalvoti licencijų ženkliukai, būsenos ženkliukai, eilučių
tankis ir stilius, antraštės / apatinės juostos informacija, vėliavos kontūras.
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF

from ..flags import draw_flag, draw_flag_styled
from ..theme import fmt_clock, fmt_lap
from ..window import OverlayWidget

LEFT, RIGHT, CENTER = "l", "r", "c"
DENSITY = {"roomy": 1.12, "normal": 1.0, "compact": 0.86, "ultra": 0.74}

# Sesijos vėliavos kontūrui (svarbumo tvarka): bitas -> spalva
_FLAG_BORDER = ((0x00000010, (230, 40, 40)), (0x00008000 | 0x00004000, (255, 205, 30)),
                (0x00000100 | 0x00000008, (255, 205, 30)), (0x00000002, (245, 245, 245)),
                (0x00000001, (245, 245, 245)))
_DRIVER_BLUE = 0x00000020
_DRIVER_BLACK = 0x00010000
_DRIVER_REPAIR = 0x00100000
_DRIVER_DQ = 0x00020000


# būsenos tekstas -> lenktynių vėliava (piešiama kaip mažas paveikslėlis vietoj BLK / REP ...)
FLAG_ICONS = {"BLK": "black", "REP": "repair", "DQ": "disqualify", "BLUE": "blue"}


class Cell(tuple):
    """(raktas, tekstas, fg, bg, lygiavimas, šriftas)"""
    __slots__ = ()

    def __new__(cls, key, text, fg="text", bg=None, align=LEFT, font="base"):
        return tuple.__new__(cls, (key, text, fg, bg, align, font))


def ordered_columns(cfg: dict, spec: dict, key="columns", order_key="order") -> list:
    """Įjungti stulpeliai vartotojo tvarka; nauji (atnaujinus programą) įterpiami ten, kur numatyta."""
    enabled = cfg.get(key) or {}
    order = [k for k in (cfg.get(order_key) or []) if k in spec]
    default = list(spec)
    for i, k in enumerate(default):
        if k in order:
            continue
        prev = next((default[j] for j in range(i - 1, -1, -1) if default[j] in order), None)
        order.insert(order.index(prev) + 1 if prev else 0, k)
    return [k for k in order if enabled.get(k, spec[k][1])]


def contrast(rgb: int) -> str:
    r, g, b = (rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255
    return "ink" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "white"


class TableWidget(OverlayWidget):
    # stulpelio raktas -> plotis em vienetais (1 em = šrifto aukštis); None = lankstus
    WIDTHS = {}
    NAME_MIN_EM = 6.5  # vardo stulpelis ne siauresnis (≈ "J. SURNAME")

    COLLAPSIBLE = ("status", "catch", "tire", "change", "flag", "irchange", "laps")  # tušti stulpeliai neužima vietos

    def collapse_empty(self, cols: list, rows) -> list:
        """Stulpeliai, kuriuose visose eilutėse tuščia (pvz. niekas neboksuose), paslepiami."""
        used = set()
        for kind, cells, _ in rows:
            if kind != "car":
                continue
            for cell in cells:
                if cell[1]:
                    used.add(cell[0])
        return [c for c in cols if c not in self.COLLAPSIBLE or c in used or self.editing]

    def content_min_width(self) -> int:
        cols = getattr(self, "_cols", None) or []
        if not cols:
            return 0
        em = self.fonts.em_base
        pad = em * 0.45
        fixed = sum(self.WIDTHS[c] * em for c in cols if self.WIDTHS.get(c))
        n_flex = sum(1 for c in cols if not self.WIDTHS.get(c))
        return int(2 * pad + fixed + pad * 0.35 * len(cols) + n_flex * em * self.NAME_MIN_EM + 2)

    def _color(self, token):
        if token is None:
            return None
        if isinstance(token, tuple):
            kind, v = token
            return self.pal.class_color(v) if kind == "rgb" else self.pal.hex_color(v)
        if token == "white":
            return QColor(255, 255, 255)
        return getattr(self.pal, token)

    def row_h(self) -> float:
        return round(self.fonts.em_base * self.pal.row_k * DENSITY.get(self.cfg.get("density", "normal"), 1.0))

    def layout(self, cols):
        """Stulpelių x pozicijos pagal plotį."""
        em = self.fonts.em_base
        pad = em * 0.45
        gap = pad * 0.35
        fixed = sum(self.WIDTHS[c] * em for c in cols if self.WIDTHS.get(c))
        flex_cols = [c for c in cols if not self.WIDTHS.get(c)]
        avail = self.width() - 2 * pad - fixed - gap * len(cols)
        flex = max(em * 4, avail / max(1, len(flex_cols)))
        x = pad
        out = {}
        for c in cols:
            w = self.WIDTHS.get(c) * em if self.WIDTHS.get(c) else flex
            out[c] = (x, w)
            x += w + gap
        return out

    # ---------------- ląstelės, kurias naudoja abu valdikliai ----------------
    def number_cell(self, key, r):
        """Mašinos numeris: klasės spalvos plytelė su kontrastingu tekstu."""
        return Cell(key, r.number, fg=contrast(r.class_color), bg=("rgb", r.class_color), align=CENTER, font="bold")

    def license_cell(self, key, r):
        if not r.license:
            return Cell(key, "", align=CENTER)
        letter = r.license.split(" ")[0]
        txt = r.license if self.cfg.get("license_style") == "full" else letter
        if txt.startswith("P"):  # Pro licencija
            txt = "PRO" if self.cfg.get("license_style") != "full" else txt
        if r.lic_color >= 0:
            return Cell(key, txt, fg=contrast(r.lic_color), bg=("rgb", r.lic_color), align=CENTER, font="tiny")
        return Cell(key, txt, fg="dim", align=CENTER, font="small")

    IR_TIERS = ((5000, (180, 120, 255)), (4000, (236, 190, 88)), (3000, (92, 214, 122)), (2000, (104, 172, 255)),
                (1500, (150, 160, 175)), (0, (110, 116, 128)))

    def irating_cell(self, key, r):
        """iRating: aiškus blokelis (spalva pagal lygį) arba paprastas tekstas."""
        from .standings import irating_text
        if not r.irating:
            return Cell(key, "", align=CENTER)
        txt = irating_text(r.irating)
        if self.cfg.get("irating_style", "badge") == "text":
            return Cell(key, txt, fg="dim", align=RIGHT, font="small")
        rgb = next(c for lim, c in self.IR_TIERS if r.irating >= lim)
        v = (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]
        return Cell(key, txt, fg=contrast(v), bg=("rgb", v), align=CENTER, font="tiny")

    def irchange_cell(self, key, r, snap):
        d = snap.ir_change.get(r.idx) if snap is not None else None
        if d is None:
            return Cell(key, "", align=RIGHT)
        return Cell(key, f"{d:+.0f}", fg="good" if d > 0.5 else ("bad" if d < -0.5 else "dim"), align=RIGHT,
                    font="small")

    def flag_cell(self, key, r):
        return Cell(key, r.country or "", align=CENTER)

    def brand_cell(self, key, r):
        return Cell(key, r.brand.get("short", ""), fg="white", bg=("hex", r.brand.get("color", "#555")),
                    align=CENTER, font="tiny")

    def carname_cell(self, key, r, fg="dim"):
        return Cell(key, r.car_short or r.brand.get("name", ""), fg=fg, font="small")

    def status_cell(self, key, r, race: bool):
        """PIT / OUT / OFF ir vairuotojo vėliavos (juoda, meatball, DQ, mėlyna)."""
        fb = r.flag_bits
        if fb & _DRIVER_DQ:
            return Cell(key, "DQ", fg="white", bg="red", align=CENTER, font="tiny")
        if fb & _DRIVER_BLACK:
            return Cell(key, "BLK", fg="white", bg=("hex", "#111111"), align=CENTER, font="tiny")
        if fb & _DRIVER_REPAIR:
            return Cell(key, "REP", fg="ink", bg=("hex", "#ff8a1e"), align=CENTER, font="tiny")
        if r.status == "pit":
            return Cell(key, "PIT", fg="white", bg="pit", align=CENTER, font="tiny")
        if r.status == "off":
            return Cell(key, "OFF", fg="ink", bg="yellow", align=CENTER, font="tiny")
        if r.status in ("garage", "out"):
            return Cell(key, "OUT", fg="dim", align=CENTER, font="tiny")
        if race and fb & _DRIVER_BLUE:
            return Cell(key, "BLUE", fg="white", bg="blue", align=CENTER, font="tiny")
        return Cell(key, "", align=CENTER)

    @staticmethod
    def delta_cell(rr, key="delta"):
        """Gap'o pokytis per ratą (artėjam / tolstam) - tas pats Relative ir Standings."""
        if rr is None or rr.is_me or rr.delta is None:
            return Cell(key, "", align=RIGHT)
        d = rr.delta
        pre = "" if rr.delta_exact else "~"
        ahead = rr.gap > 0  # priekyje: gap mažėja = tu greitesnis (gerai); už tavęs: mažėja = vejasi (blogai)
        if d < -0.05:
            return Cell(key, f"▼{pre}{-d:.1f}", fg="good" if ahead else "bad", align=RIGHT, font="small")
        if d > 0.05:
            return Cell(key, f"▲{pre}{d:.1f}", fg="bad" if ahead else "good", align=RIGHT, font="small")
        return Cell(key, "= 0.0", fg="dim", align=RIGHT, font="small")

    def pit_width(self) -> float:
        return {"since": 2.4, "stop": 5.4, "both": 6.6}.get(self.cfg.get("pit_style", "stop"), 5.4)

    def pit_cell(self, key, r, race: bool):
        """Boksai: būsenos ženkliukas, o kai trasoje - paskutinis sustojimas (ratas ir trukmė) ar ratai nuo jo."""
        st = self.status_cell(key, r, race)
        if st[1] and st[1] != "PIT":
            return st
        if r.status == "pit":
            live = f"PIT {r.pit_live:.0f}s" if r.pit_live >= 1 else "PIT"
            return Cell(key, live, fg="white", bg="pit", align=CENTER, font="tiny")
        mode = self.cfg.get("pit_style", "stop")
        ls = r.last_stop
        since = f"{r.laps_since_pit}" if (race and r.laps_since_pit is not None) else ""
        if mode == "since" or ls is None:
            return Cell(key, since, fg="dim", align=CENTER, font="small")
        stop = f"L{ls[0]} {ls[1]:.0f}s"
        txt = stop if mode == "stop" else f"{stop} +{since}" if since else stop
        return Cell(key, txt, fg="dim", align=CENTER, font="small")

    # ---------------- paskutiniai ratai (Last 5 / 10 laps) ----------------
    LAPS_EM = {"squares": 0.95, "delta": 2.3, "times": 3.4}

    def laps_width(self) -> float:
        n = int(self.cfg.get("laps_n", 5) or 5)
        return n * self.LAPS_EM.get(self.cfg.get("laps_style", "delta"), 2.3)

    def laps_ref(self, snap, r) -> float | None:
        """Su kuo lyginam: mano tempas (5 švarių ratų mediana), mano paskutinis, jo geriausias ar jo vidurkis."""
        mode = self.cfg.get("laps_ref", "my_pace")
        p = snap.player if snap is not None else None
        if mode == "my_last":
            return p.last_lap if p is not None and p.last_lap > 0 else None
        if mode == "their_best":
            return r.best_lap if r.best_lap > 0 else None
        if mode == "their_avg":
            clean = sorted(t for t, pit in r.recent if not pit and t > 0)
            return clean[len(clean) // 2] if clean else None
        if p is None:
            return None
        if p.pace_lap:
            return p.pace_lap
        return p.best_lap if p.best_lap > 0 else None

    def laps_cell(self, key, r, snap):
        """Ląstelė su N paskutinių ratų: ((tekstas, spalva, ryškumas 0..1), ...), seniausias kairėje.
        Žalia - greitesnis už palyginimą, raudona - lėtesnis, pilka - boksų ratas ar ±0.1 s."""
        n = int(self.cfg.get("laps_n", 5) or 5)
        style = self.cfg.get("laps_style", "delta")
        ref = self.laps_ref(snap, r)
        laps = list(r.recent[-n:])
        out = []
        for t, pit in laps:
            d = (t - ref) if ref else None
            if pit:
                col, k = "pit", 0.5
            elif d is None or abs(d) < 0.1:
                col, k = "dim", 0.35
            else:
                col, k = ("good" if d < 0 else "bad"), min(1.0, 0.35 + abs(d) / 1.5 * 0.65)
            if style == "times":
                m, sec = divmod(t, 60.0)
                txt = f"{int(m)}:{sec:04.1f}" if m else f"{sec:.1f}"
            elif style == "delta":
                txt = "PIT" if pit else ("–" if d is None else f"{d:+.1f}")
            else:
                txt = ""
            out.append((txt, col, round(k, 2)))
        out = [("", None, 0.0)] * (n - len(out)) + out  # trūkstami ratai - tuščios vietos kairėje
        return Cell(key, tuple(out) if laps else "", align=RIGHT, font="tiny")

    def _paint_laps(self, p, rect, segs, rh):
        n = len(segs)
        if not n:
            return
        sw = rect.width() / n
        squares = self.cfg.get("laps_style", "delta") == "squares"
        for i, (txt, col, k) in enumerate(segs):
            if col is None:
                continue
            c = QColor(self._color(col))
            cell = QRectF(rect.x() + i * sw, rect.y(), sw, rh)
            if squares:
                c.setAlphaF(k)
                sq = min(sw - 2, rh * 0.5)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(c)
                p.drawRoundedRect(QRectF(cell.center().x() - sq / 2, cell.center().y() - sq / 2, sq, sq), 2, 2)
            else:
                p.setPen(c)
                self.draw_text(p, cell.adjusted(1, 0, -1, 0), txt, "tiny", CENTER)

    # ---------------- informacijos juostos ----------------
    def info_values(self, snap, keys) -> tuple:
        """[(pavadinimas, reikšmė)] - antraštei ir apatinei juostai."""
        if not keys or snap is None:
            return ()
        me = next((r for r in snap.cars if r.is_me), None)
        p = snap.player
        w = snap.weather
        race = snap.session_type == "race"
        out = []
        for k in keys:
            v = None
            label = ""
            if k == "session":
                if race and 0 < snap.laps_remain < 30000:
                    v = f"{snap.laps_remain} laps left"
                elif 0 < snap.time_remain < 1e5:
                    v = f"{fmt_clock(snap.time_remain)} left"
            elif k == "position" and me is not None:
                n_class = sum(1 for r in snap.cars if r.class_id == me.class_id)
                v = f"P{me.class_pos}/{n_class}" if me.class_pos else None
            elif k == "sof" and snap.sof:
                cid = me.class_id if me is not None and snap.multiclass else 0
                sof = snap.sof.get(cid) or snap.sof.get(0)
                if sof:
                    label, v = "SOF", f"{sof / 1000:.1f}k" if sof >= 1000 else str(sof)
            elif k == "lap" and me is not None:
                label, v = "Lap", str(me.laps + 1)
                left = getattr(p, "race_laps_left", None) if (p is not None and race) else None
                if left is not None and math.isfinite(left):
                    total = me.laps + float(getattr(p, "lap_pct", 0.0) or 0.0) + float(left)
                    tt = f"{round(total)}" if abs(total - round(total)) < 0.05 else f"{total:.1f}"
                    v = f"{me.laps + 1}/{tt}"  # pvz. 12/23.4 - kiek ratų iki finišo (laiko lenktynėse - įvertis)
            elif k == "track_temp" and w is not None and w.valid and math.isfinite(w.track_temp):
                label, v = "Track", f"{w.track_temp:.0f}°"
            elif k == "air_temp" and w is not None and w.valid and math.isfinite(w.air_temp):
                label, v = "Air", f"{w.air_temp:.0f}°"
            elif k == "wetness" and w is not None and w.valid:
                v = w.wetness_text
            elif k == "precip" and w is not None and w.valid:
                label, v = "Rain", f"{w.precipitation * 100:.0f}%"
            elif k == "clock" and w is not None and w.valid:
                sec = int(w.time_of_day) % 86400
                v = f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}"
            elif k == "local":
                v = time.strftime("%H:%M")
            elif k == "incidents" and p is not None and p.valid:
                lim = int(self.ctx.config.widget("incidents").get("limit", 0) or 0) or snap.incident_limit
                v = f"{p.inc_my}x" + (f"/{lim}" if lim else "")
            elif k == "fuel" and p is not None and math.isfinite(p.fuel_l):
                label, v = "Fuel", f"{p.fuel_l:.1f} l" + (f" · {p.fuel_laps_left:.1f} laps" if p.fuel_laps_left else "")
            elif k == "bias" and p is not None and p.brake_bias is not None:
                label, v = "BB", f"{p.brake_bias:.1f}"
            elif k == "last" and p is not None and p.last_lap > 0:
                label, v = "Last", fmt_lap(p.last_lap)
            elif k == "best" and p is not None and p.best_lap > 0:
                label, v = "Best", fmt_lap(p.best_lap)
            elif k == "delta" and p is not None and p.deltas.get("best") is not None:
                label, v = "Δ", f"{p.deltas['best']:+.2f}"
            elif k == "ir_proj" and me is not None and me.idx in snap.ir_change:
                label, v = "iR", f"{snap.ir_change[me.idx]:+.0f}"
            elif k == "track" and snap.track_name:
                v = snap.track_name
            if v:
                out.append((label, v))
        return tuple(out)

    def header_info(self, snap) -> tuple:
        from ..registry import INFO_ITEMS
        keys = ordered_columns(self.cfg, INFO_ITEMS, "header_items", "header_items_order")
        return self.info_values(snap, keys)

    def footer_info(self, snap) -> tuple:
        from ..registry import FOOTER_ITEMS
        keys = ordered_columns(self.cfg, FOOTER_ITEMS, "footer_items", "footer_items_order")
        return self.info_values(snap, keys)

    COL_LABELS = {"pos": "P", "change": "+/-", "number": "#", "name": "DRIVER", "brand": "CAR", "carname": "CAR",
                  "pit": "PIT", "gap": "GAP", "interval": "INT", "last": "LAST", "best": "BEST", "start": "ST",
                  "license": "LIC", "irating": "iR", "irchange": "+iR", "tire": "TYRE", "delta": "DELTA", "catch": "CATCH",
                  "laps": "LAST LAPS", "status": "", "pitstops": "STOPS", "lapsdone": "LAPS", "classpos": "CL"}

    def colhead_h(self) -> int:
        return round(self.fonts.em_small * 1.25) if self.cfg.get("column_header") else 0

    def paint_colhead(self, p: QPainter, rows, cols, y: float) -> float:
        """Plona stulpelių pavadinimų eilutė (lygiuota kaip pirmos mašinos eilutės ląstelės)."""
        h = self.colhead_h()
        if not h:
            return y
        lay = self.layout(cols)
        aligns = {}
        for kind, cells, _ in rows:
            if kind == "car":
                aligns = {c[0]: c[4] for c in cells}
                break
        p.setPen(self.pal.dim)
        for key in cols:
            label = self.COL_LABELS.get(key)
            if not label or key not in lay:
                continue
            x, w = lay[key]
            al = aligns.get(key, LEFT)
            self.draw_text(p, QRectF(x, y, w, h), label if self.text_width(label, "tiny") <= w + 2 else label[:1],
                           "tiny", al)
        line = QColor(self.pal.dim)
        line.setAlpha(60)
        p.fillRect(QRectF(0, y + h - 1, self.width(), 1), line)
        return y + h

    def footer_h(self) -> int:
        return round(self.fonts.em_small * 1.8) if getattr(self, "_footer", ()) else 0

    def session_border(self, snap) -> tuple | None:
        """Vėliavos kontūro spalva (sesijos vėliava arba mėlyna man)."""
        if not int(self.cfg.get("flag_border", 2) or 0) or snap is None:
            return None
        p = snap.player
        bits = p.flag_bits if p is not None else 0
        if bits & _DRIVER_BLUE and snap.session_type == "race":
            return (40, 120, 235)
        for bit, col in _FLAG_BORDER:
            if bits & bit:
                return col
        return None

    # ---------------- piešimas ----------------
    def paint_rows(self, p: QPainter, rows, cols, y0: float, me_flag="me"):
        rh = self.row_h()
        lay = self.layout(cols)
        style = self.cfg.get("row_style", "alternate")
        y = y0
        car_i = 0
        for kind, cells, flags in rows:
            if kind == "sep":
                p.setPen(self.pal.dim)
                self.draw_text(p, QRectF(0, y, self.width(), rh * 0.6), "· · ·", "tiny", CENTER)
                y += rh * 0.6
                continue
            if kind == "class":
                self._paint_class_header(p, cells, y, rh)
                y += rh * 0.9
                car_i = 0
                continue
            row = QRectF(0, y, self.width(), rh)
            if me_flag in flags:
                p.fillRect(row, self.pal.me_bg)
                p.fillRect(QRectF(0, y, 3, rh), self.pal.accent)
            elif style == "alternate" and car_i % 2:
                p.fillRect(row, self.pal.row_alt)
            if "friend" in flags:
                fc = QColor(self.pal.accent)
                fc.setAlpha(36)
                p.fillRect(row, fc)
            if "blue" in flags:  # mėlyna vėliava: ryški mėlyna eilutė su juosta kairėje
                bc = QColor(30, 110, 255, 95)
                p.fillRect(row, bc)
                p.fillRect(QRectF(0, y, 4, rh), QColor(60, 140, 255))
            car_i += 1
            for cell in cells:
                key, text, fg, bg, align, font = cell
                if key not in lay:
                    continue
                x, w = lay[key]
                rect = QRectF(x, y, w, rh)
                if key == "classbar":
                    cc = self._color(bg)
                    if me_flag not in flags:
                        p.fillRect(QRectF(0, y + 2, 3, rh - 4), cc)
                    if style == "class":
                        line = QColor(cc)
                        line.setAlpha(150)
                        p.fillRect(QRectF(0, y + rh - 1, self.width(), 1), line)
                    elif style == "lines":
                        p.fillRect(QRectF(0, y + rh - 1, self.width(), 1), self.pal.row_alt)
                    continue
                if key == "flag":
                    if text:
                        st, fr = self.cfg.get("flag_style", "3d"), self.cfg.get("flag_frame", "none")
                        draw_flag_styled(p, rect.adjusted(1, rh * 0.22, -1, -rh * 0.22), text, st, fr,
                                         self.pal.accent, 1.5, self.devicePixelRatioF())
                    continue
                if key == "laps":
                    if text:
                        self._paint_laps(p, rect, text, rh)
                    continue
                if key in ("status", "pit") and text in FLAG_ICONS and self.cfg.get("status_icons", True):
                    from ..flags import paint_race_flag
                    fh = rh * 0.56
                    fw = min(w - 2, fh * 1.4)
                    fr = QRectF(x + (w - fw) / 2, y + (rh - fh) / 2, fw, fh)
                    paint_race_flag(p, fr, FLAG_ICONS[text], fh * 0.08, 1.5)
                    continue
                if key == "brand" and text and self.cfg.get("brand_style", "badge") == "logo":
                    from ..logos import STORE
                    pm = STORE.pixmap(text, w - 2, rh * 0.68, self.devicePixelRatioF())
                    if pm is not None:
                        pw, ph = pm.width() / pm.devicePixelRatio(), pm.height() / pm.devicePixelRatio()
                        p.drawPixmap(QPointF(x + (w - pw) / 2, y + (rh - ph) / 2), pm)
                        continue
                if bg is not None and text:
                    bw = min(w, self.text_width(text, font) + rh * 0.42)
                    bx = x + (w - bw) / 2 if align == CENTER else (x + w - bw if align == RIGHT else x)
                    br = QRectF(bx, y + rh * 0.17, bw, rh * 0.66)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(self._color(bg))
                    p.drawRoundedRect(br, min(4.0, self.pal.radius * 0.8), min(4.0, self.pal.radius * 0.8))
                    rect = br
                    align = CENTER
                elif not text:
                    continue
                p.setPen(self._color(fg))
                if align == LEFT and key in ("name", "carname"):
                    text = self.elide(text, w, font)
                self.draw_text(p, rect, text, font, align)
            y += rh
        return y

    def _paint_class_header(self, p, cells, y, rh):
        name, color, count = cells[:3]
        c = self._color(color)
        top, hgt = y + rh * 0.12, rh * 0.7
        tw = min(self.width() * 0.6, self.text_width(name.upper(), "tiny") + 26)
        p.fillRect(QRectF(0, top, self.width(), hgt), self.pal.header)
        poly = QPolygonF([QPointF(0, top), QPointF(tw, top), QPointF(tw - hgt * 0.35, top + hgt), QPointF(0, top + hgt)])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawPolygon(poly)
        p.setPen(self._color(contrast(self._rgb(color))))
        self.draw_text(p, QRectF(10, top, tw - 14, hgt), name.upper(), "tiny")
        p.setPen(self.pal.dim)
        self.draw_text(p, QRectF(12, top, self.width() - 24, hgt), count, "tiny", RIGHT)

    @staticmethod
    def _rgb(token) -> int:
        if isinstance(token, tuple) and token[0] == "rgb":
            return int(token[1])
        return 0xFFFFFF

    def paint_frame(self, p: QPainter, title: str, info=()) -> float:
        """Fonas ir antraštė su informacija dešinėje. Grąžina y, nuo kurio prasideda eilutės."""
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.pal.bg)
        p.drawRoundedRect(r, self.pal.radius, self.pal.radius)
        self._drew_bg = True
        if not self.cfg.get("show_header", True):
            return 4.0
        hh = self.paint_header(p, title, "")
        if info:
            al = self.cfg.get("header_align", "right")
            tw = self.text_width(title, "tiny") + self.fonts.em_small * 2.2
            if al == "left":
                self._paint_info(p, QRectF(tw, 0, r.width() - tw - 10, hh), info, LEFT)
            elif al == "center":
                self._paint_info(p, QRectF(tw, 0, r.width() - 2 * tw, hh), info, CENTER)
            else:
                self._paint_info(p, QRectF(r.width() * 0.25, 0, r.width() * 0.75 - 10, hh), info, RIGHT)
        return hh + 2

    def _paint_info(self, p, rect: QRectF, info, align=RIGHT):
        """„SOF 2.4k   Track 28°   33:20 left“ - pavadinimai pilki, reikšmės baltos."""
        parts = []
        for label, value in info:
            parts.append((label, value))
        gap = self.fonts.em_small * 0.9
        widths = [(self.text_width(l + " ", "tiny") if l else 0) + self.text_width(v, "small") for l, v in parts]
        total = sum(widths) + gap * (len(parts) - 1)
        while parts and total > rect.width():  # netelpa - numetam paskutinius
            parts.pop()
            widths.pop()
            total = sum(widths) + gap * max(0, len(parts) - 1)
        x = rect.right() - total if align == RIGHT else (rect.center().x() - total / 2 if align == CENTER else rect.x())
        for (label, value), wv in zip(parts, widths):
            if label:
                p.setPen(self.pal.dim)
                self.draw_text(p, QRectF(x, rect.y(), wv, rect.height()), label, "tiny")
                lw = self.text_width(label + " ", "tiny")
            else:
                lw = 0
            p.setPen(self.pal.text)
            self.draw_text(p, QRectF(x + lw, rect.y(), wv - lw, rect.height()), value, "small")
            x += wv + gap

    def paint_footer(self, p: QPainter, y: float):
        info = getattr(self, "_footer", ())
        if not info:
            return
        fh = self.footer_h()
        r = QRectF(0, y + 2, self.width(), fh)
        p.fillRect(r, self.pal.header)
        al = {"left": LEFT, "center": CENTER, "right": RIGHT}.get(self.cfg.get("footer_align", "left"), LEFT)
        self._paint_info(p, r.adjusted(10, 0, -10, 0), info, al)

    def paint_flag_border(self, p: QPainter):
        col = getattr(self, "_border", None)
        if col is None:
            return
        wpx = float(self.cfg.get("flag_border", 2) or 0)
        p.setPen(QPen(QColor(*col), wpx))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(wpx / 2, wpx / 2, -wpx / 2, -wpx / 2),
                          self.pal.radius, self.pal.radius)
