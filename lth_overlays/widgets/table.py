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

from ..flags import draw_flag
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

    COLLAPSIBLE = ("status", "catch", "tire", "change", "flag", "irchange")  # tušti stulpeliai neužima vietos

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
                  "license": "LIC", "irating": "iR", "irchange": "+iR", "tire": "TYRE", "delta": "DELTA", "catch": "CATCH"}

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
                        draw_flag(p, rect.adjusted(1, rh * 0.24, -1, -rh * 0.24), text, 1.5)
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
        x = rect.right() - total if align == RIGHT else rect.x()
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
        self._paint_info(p, r.adjusted(10, 0, -10, 0), info, LEFT)

    def paint_flag_border(self, p: QPainter):
        col = getattr(self, "_border", None)
        if col is None:
            return
        wpx = float(self.cfg.get("flag_border", 2) or 0)
        p.setPen(QPen(QColor(*col), wpx))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(wpx / 2, wpx / 2, -wpx / 2, -wpx / 2),
                          self.pal.radius, self.pal.radius)
