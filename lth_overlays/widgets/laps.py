"""Lap timer (su asmeniniu rekordu) ir sektorių delta."""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter

from .panel import PanelWidget, fmt_time


def _ok(v) -> bool:
    return v is not None and math.isfinite(v) and v > 0


class LapTimerWidget(PanelWidget):
    NAME = "lap_timer"
    TITLE = "Lap timer"
    MIN_WIDTH = 170
    FAST_CAPABLE = True  # einamasis laikas tiesiai iš kadro

    def __init__(self, ctx):
        self._static = None
        super().__init__(ctx)

    def _live(self, cur, delta, best):
        pred = best + delta if _ok(best) and delta is not None else None
        return (fmt_time(cur, 1) if cur > 0 else "–", None if delta is None else round(delta, 2),
                fmt_time(pred, 3) if _ok(pred) else "–", pred)

    def fast_tick(self, timing) -> bool:
        if self._static is None:
            return False
        f = timing.frame
        cur = float(f.get("LapCurrentLapTime", 0.0) or 0.0)
        v, ok = f.values.get("LapDeltaToBestLap"), f.values.get("LapDeltaToBestLap_OK")
        live = self._live(cur, float(v) if v is not None and ok else None, self._static[1])
        if self._view is not None and live == self._view[0]:
            return False
        self._view = (live,) + self._static
        return True

    def content_key(self, snap):
        p = snap.player
        if p is None or not p.valid:
            self._view = self._static = None
            return None
        pbs = getattr(self.ctx, "pbs", None)
        pb = pbs.get(snap.track_key, snap.car_key) if pbs is not None else None
        new_pb = bool(pbs is not None and pbs.new_pb_t and time.monotonic() - pbs.new_pb_t < 8.0)
        self._static = (p.last_lap if _ok(p.last_lap) else None, p.best_lap if _ok(p.best_lap) else None, pb, new_pb)
        if self.fast_active() and self._view is not None:
            self._view = (self._view[0],) + self._static
            return ("fast", self._static, self.width())
        self._view = (self._live(p.current_lap_time, p.deltas.get("best"), self._static[1]),) + self._static
        return (self._view, self.width())

    def desired_height(self) -> int:
        rows = sum(1 for k in ("show_last", "show_best", "show_pb", "show_pred") if self.cfg.get(k, True))
        return int(self.header_h() + self.fonts.em_base * 2.6 + ((rows + 1) // 2) * self.fonts.em_base * 2.3
                   + self.pad() * 1.6)

    def paint_content(self, p: QPainter):
        if self._view is None:
            return
        (cur, delta, pred_s, pred), last, best, pb, new_pb = self._view
        c = self.cfg
        y = self.card(p, "LAP TIMER", "NEW PB" if new_pb else "")
        pad = self.pad() * 1.4
        w = self.width() - 2 * pad
        big_h = self.fonts.em_base * 2.4
        p.setPen(self.pal.text)
        self.draw_text(p, QRectF(pad, y, w * 0.62, big_h), cur, "big")
        if delta is not None:
            p.setPen(self.pal.good if delta < 0 else self.pal.bad if delta > 0 else self.pal.dim)
            self.draw_text(p, QRectF(pad, y, w, big_h), f"{delta:+.2f}", "mid", "r")
        y += big_h + self.fonts.em_base * 0.2
        items = []
        if c.get("show_last", True):
            items.append(("LAST", fmt_time(last) if last else "–", "text"))
        if c.get("show_best", True):
            items.append(("BEST", fmt_time(best) if best else "–", "good" if best else "dim"))
        if c.get("show_pb", True):
            col = "purple" if new_pb else ("text" if pb else "dim")
            items.append(("PB", fmt_time(pb) if pb else "–", col))
        if c.get("show_pred", True):
            col = "dim"
            if pred is not None and pb:
                col = "purple" if pred < pb else "text"
            items.append(("PREDICTED", pred_s, col))
        cell_w = w / 2
        ch = self.fonts.em_base * 2.3
        for i, (lab, val, col) in enumerate(items):
            x = pad + (i % 2) * cell_w
            yy = y + (i // 2) * ch
            p.setPen(self.pal.dim)
            self.draw_text(p, QRectF(x, yy, cell_w, ch * 0.42), lab, "tiny")
            p.setPen(getattr(self.pal, col))
            self.draw_text(p, QRectF(x, yy + ch * 0.36, cell_w - 4, ch * 0.6), val, "bold")


class SectorsWidget(PanelWidget):
    NAME = "sectors"
    TITLE = "Sectors"
    MIN_WIDTH = 200
    SHOW_LAST_S = 4.0  # tiek sekundžių po rato rodom ką tik baigto rato sektorius

    def content_key(self, snap):
        s = getattr(snap, "my_sectors", None)
        if s is None or not s.bounds:
            self._view = None
            return None
        n = len(s.bounds)
        just_done = s.lap_done_age < self.SHOW_LAST_S and any(v is not None for v in s.last)
        cells = []
        for i in range(n):
            best = s.best[i] if i < len(s.best) else None
            if just_done:
                cells.append(self._cell(s.last[i], best, s.last_improved[i] if i < len(s.last_improved) else False))
            elif i < s.index or (s.current[i] is not None and i != s.index):
                cells.append(self._cell(s.current[i], best, s.improved[i]))
            elif i == s.index:
                cells.append(("run", fmt_time(s.elapsed, 1) if s.elapsed > 0 else "–", "", "text"))
            else:
                v = s.last[i] if i < len(s.last) else None
                cells.append(("old", fmt_time(v) if v else "–", "", "dim"))
        opt = s.optimal
        right = f"OPTIMAL {fmt_time(opt)}" if opt and self.cfg.get("show_optimal", True) else ""
        self._view = (tuple(cells), right)
        return (self._view, self.width())

    @staticmethod
    def _cell(v, best, improved):
        if v is None:
            return ("old", "–", "", "dim")
        if improved:
            return ("done", fmt_time(v), "BEST", "purple")
        d = v - best if best else 0.0
        col = "good" if d <= 0.05 else ("yellow" if d <= 0.5 else "bad")
        return ("done", fmt_time(v), f"+{d:.3f}" if d >= 0.0005 else "=", col)

    def desired_height(self) -> int:
        return int(self.header_h() + self.fonts.em_base * 3.0 + self.pad() * 1.2)

    def paint_content(self, p: QPainter):
        if self._view is None:
            return
        cells, right = self._view
        y = self.card(p, "SECTORS", right)
        pad = self.pad()
        n = max(1, len(cells))
        gap = pad * 0.5
        w = (self.width() - 2 * pad - gap * (n - 1)) / n
        h = self.fonts.em_base * 2.7
        for i, (kind, val, sub, col) in enumerate(cells):
            x = pad + i * (w + gap)
            r = QRectF(x, y, w, h)
            colr = QColor(getattr(self.pal, col))
            bg = QColor(colr)
            bg.setAlpha(46 if kind == "done" else 0)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg if kind == "done" else self.pal.track)
            p.drawRoundedRect(r, self.pal.radius * 0.8, self.pal.radius * 0.8)
            if kind == "done":
                p.setBrush(colr)
                p.drawRoundedRect(QRectF(x, y, w, 3), 1.5, 1.5)
            p.setPen(self.pal.dim)
            self.draw_text(p, QRectF(x + 6, y + 2, w - 12, h * 0.36), f"S{i + 1}", "tiny")
            if sub:
                p.setPen(colr)
                self.draw_text(p, QRectF(x + 6, y + 2, w - 12, h * 0.36), sub, "tiny", "r")
            p.setPen(colr if kind != "old" else self.pal.dim)
            self.draw_text(p, QRectF(x + 6, y + h * 0.36, w - 12, h * 0.58), val, "bold", "c")
