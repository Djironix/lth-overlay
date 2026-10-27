"""Laiko valdikliai: Delta bar, Lap history, Session, Battle analysis."""
from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter

from .panel import PanelWidget, fmt_clock, fmt_signed, fmt_time

SESSION_NAMES = {"race": "RACE", "qualify": "QUALIFYING", "practice": "PRACTICE", "warmup": "WARMUP"}


class DeltaBarWidget(PanelWidget):
    NAME = "delta_bar"
    TITLE = "Delta bar"
    HAS_HEADER = False
    HEIGHT_MODE = "free"
    MIN_WIDTH = 160
    MIN_HEIGHT = 28
    FAST_CAPABLE = True
    REF_LABEL = {"best": "BEST", "optimal": "OPTIMAL", "session_best": "SESSION BEST", "session_last": "LAST"}
    REF_VAR = {"best": "LapDeltaToBestLap", "optimal": "LapDeltaToOptimalLap",
               "session_best": "LapDeltaToSessionBestLap", "session_last": "LapDeltaToSessionLastlLap"}

    def fast_tick(self, timing) -> bool:
        f = timing.frame
        ref = self.cfg.get("reference", "best")
        name = self.REF_VAR.get(ref, "LapDeltaToBestLap")
        v, ok = f.values.get(name), f.values.get(name + "_OK")
        d = round(float(v), 2) if v is not None and ok else None
        cur = float(f.get("LapCurrentLapTime", 0.0) or 0.0)
        view = (d, ref, fmt_time(cur, 1) if self.cfg.get("show_lap_time", True) and cur > 0 else "")
        if view == self._view:
            return False
        self._view = view
        return True

    def content_key(self, snap):
        if self.fast_active():
            return ("fast", self.width(), self.height())
        p = snap.player
        ref = self.cfg.get("reference", "best")
        d = p.deltas.get(ref) if p is not None else None
        cur = p.current_lap_time if p is not None else 0.0
        self._view = (None if d is None else round(d, 2), ref,
                      fmt_time(cur, 1) if self.cfg.get("show_lap_time", True) and cur > 0 else "")
        return (self._view, self.width(), self.height())

    def desired_height(self) -> int:
        return int(self.fonts.em_base * 3.6)

    def paint_content(self, p: QPainter):
        if self._view is None:
            return
        d, ref, cur = self._view
        r = QRectF(self.rect())
        pal = self.pal
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.bg)
        p.drawRoundedRect(r, pal.radius, pal.radius)
        pad = self.pad()
        bar_h = max(6.0, r.height() * 0.22)
        bar = QRectF(pad, r.height() - pad - bar_h, r.width() - 2 * pad, bar_h)
        p.setBrush(pal.track)
        p.drawRoundedRect(bar, bar_h / 2, bar_h / 2)
        mid = bar.center().x()
        if d is not None:
            rng = float(self.cfg.get("range", 2.0) or 2.0)
            k = max(-1.0, min(1.0, d / rng))
            col = pal.good if d < 0 else pal.bad
            w = abs(k) * bar.width() / 2
            p.setBrush(col)
            p.drawRoundedRect(QRectF(mid - w if d < 0 else mid, bar.y(), w, bar_h), bar_h / 2, bar_h / 2)
        p.fillRect(QRectF(mid - 1, bar.y() - 2, 2, bar_h + 4), pal.text)
        top = QRectF(pad, 0, r.width() - 2 * pad, bar.y())
        p.setPen(pal.dim)
        self.draw_text(p, top, self.REF_LABEL.get(ref, ""), "tiny")
        if cur:
            self.draw_text(p, top, cur, "small", "r")
        p.setPen(pal.dim if d is None else (pal.good if d < 0 else pal.bad))
        self.draw_text(p, top, "–.––" if d is None else fmt_signed(d), "mid", "c")


class LapHistoryWidget(PanelWidget):
    NAME = "lap_history"
    TITLE = "Lap history"
    HEIGHT_MODE = "rows"
    MIN_WIDTH = 200

    def content_key(self, snap):
        p = snap.player
        laps = list(p.laps) if p is not None else []
        n = int(self.cfg.get("rows", 8))
        avail = self.avail_body_height()
        if avail is not None:
            n = max(1, int((avail - self.lh() * 1.2) // self.lh()))
        laps = laps[-n:][::-1]
        best = min((x.time for x in laps if x.time > 0 and not x.pit), default=0.0)
        if p is not None and p.best_lap > 0:
            best = p.best_lap
        show_fuel = self.cfg.get("show_fuel", True)
        rows = []
        for x in laps:
            diff = x.time - best if best > 0 and x.time > 0 else None
            col = "purple" if best > 0 and abs(x.time - best) < 1e-3 else ("dim" if x.pit else "text")
            fuel = f"{x.fuel:.2f} l" if show_fuel and x.fuel else ""
            rows.append((str(x.lap), fmt_time(x.time), "" if diff is None or diff < 1e-3 else f"+{diff:.3f}",
                         "PIT" if x.pit else fuel, col))
        foot = ""
        if p is not None and p.stint_avg:
            foot = f"Stint avg {fmt_time(p.stint_avg)}"
            if p.consistency is not None:
                foot += f"   ±{p.consistency:.2f}"
        self._view = (tuple(rows), fmt_time(best) if best > 0 else "", foot)
        return (self._view, self.width())

    def desired_height(self) -> int:
        n = len(self._view[0]) if self._view else 1
        return self.body_height(max(1, n) + 1.2)

    def paint_content(self, p: QPainter):
        if self._view is None:
            return
        rows, best, foot = self._view
        y = self.card(p, "LAP HISTORY", f"best {best}" if best else "")
        if not rows:
            self.empty_note(p, y, "Laps appear after your first full lap")
            return
        lh = self.lh()
        x0 = self.pad() * 1.4
        w = self.width() - 2 * x0
        for i, (lap, t, diff, extra, col) in enumerate(rows):
            if i % 2:
                p.fillRect(QRectF(0, y, self.width(), lh), self.pal.row_alt)
            p.setPen(self.pal.dim)
            self.draw_text(p, QRectF(x0, y, w * 0.14, lh), lap, "small", "r")
            p.setPen(getattr(self.pal, col))
            self.draw_text(p, QRectF(x0 + w * 0.18, y, w * 0.34, lh), t, "bold")
            p.setPen(self.pal.bad)
            self.draw_text(p, QRectF(x0 + w * 0.5, y, w * 0.26, lh), diff, "small", "r")
            p.setPen(self.pal.dim)
            self.draw_text(p, QRectF(x0, y, w, lh), extra, "small", "r")
            y += lh
        if foot:
            p.setPen(self.pal.dim)
            self.draw_text(p, QRectF(x0, y + lh * 0.1, w, lh), foot, "small")


class SessionWidget(PanelWidget):
    NAME = "session"
    TITLE = "Session"

    def content_key(self, snap):
        c = self.cfg
        lines = []
        race = snap.session_type == "race"
        if c.get("show_track", True) and snap.track_name:
            lines.append(("Track", snap.track_name, "text"))
        if race and 0 <= snap.laps_remain < 30000:
            lines.append(("Laps left", str(snap.laps_remain), "text"))
        elif 0 < snap.time_remain < 1e6:
            lines.append(("Time left", fmt_clock(snap.time_remain), "text"))
        me = next((r for r in snap.cars if r.is_me), None)
        if c.get("show_position", True) and me is not None:
            n_class = sum(1 for r in snap.cars if r.class_id == me.class_id)
            pos = f"P{me.class_pos} / {n_class}"
            if snap.multiclass:
                pos += f"   (P{me.pos} overall)"
            lines.append(("Position", pos, "text"))
            if me.laps:
                lines.append(("Laps done", str(me.laps), "text"))
        if c.get("show_sof", True) and snap.sof:
            cid = me.class_id if me is not None and snap.multiclass else 0
            sof = snap.sof.get(cid) or snap.sof.get(0)
            if sof:
                lines.append(("Strength of field", f"{sof:,}".replace(",", " "), "text"))
        w = snap.weather
        if c.get("show_clock", True) and w is not None and w.valid:
            sec = int(w.time_of_day) % 86400
            lines.append(("Time of day", f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}", "text"))
        self._view = (SESSION_NAMES.get(snap.session_type, "SESSION"), tuple(lines))
        return (self._view, self.width())

    def desired_height(self) -> int:
        return self.body_height(len(self._view[1]) if self._view else 1)

    def paint_content(self, p: QPainter):
        if self._view is None:
            return
        title, lines = self._view
        y = self.card(p, title)
        for label, value, col in lines:
            y = self.kv(p, y, label, self.elide(value, self.width() * 0.6), col)


class BattleWidget(PanelWidget):
    NAME = "battle"
    TITLE = "Battle analysis"
    MIN_WIDTH = 240

    def content_key(self, snap):
        c = self.cfg
        entries = []
        for b in snap.battle or []:
            if (b["side"] == "ahead" and not c.get("show_ahead", True)) or \
                    (b["side"] == "behind" and not c.get("show_behind", True)):
                continue
            diff = tuple(None if d is None else round(d, 2) for d in b["diff"])
            mine = tuple(None if x is None else round(x, 2) for x in b["mine"])
            total = sum(d for d in diff if d is not None) if all(d is not None for d in diff) else None
            entries.append((b["side"], b["number"], b["abbrev"] or b["name"], round(b["gap"], 1), diff, mine,
                            None if total is None else round(total, 2)))
        self._view = (tuple(entries), len(snap.sectors or [0, 0, 0]), bool(c.get("show_times")))
        return (self._view, self.width())

    def desired_height(self) -> int:
        if not self._view or not self._view[0]:
            return self.body_height(1)
        per = 2 + (1 if self._view[2] else 0)
        return self.body_height(len(self._view[0]) * per + 0.6 * (len(self._view[0]) - 1))

    def paint_content(self, p: QPainter):
        if self._view is None:
            return
        entries, n_sec, show_times = self._view
        y = self.card(p, "BATTLE", "last lap, by sector")
        if not entries:
            self.empty_note(p, y, "No car of your class close on the same lap")
            return
        lh = self.lh()
        x0 = self.pad() * 1.4
        w = self.width() - 2 * x0
        for k, (side, num, name, gap, diff, mine, total) in enumerate(entries):
            if k:
                y += lh * 0.6
            p.setPen(self.pal.dim)
            self.draw_text(p, QRectF(x0, y, w, lh), "AHEAD" if side == "ahead" else "BEHIND", "tiny")
            p.setPen(self.pal.text)
            self.draw_text(p, QRectF(x0 + w * 0.2, y, w * 0.6, lh), self.elide(f"#{num}  {name}", w * 0.58), "bold")
            self.draw_text(p, QRectF(x0, y, w, lh), f"{gap:+.1f} s", "base", "r")
            y += lh
            cells = n_sec + 1
            cw = w / cells
            for i in range(cells):
                rect = QRectF(x0 + i * cw + 1, y + lh * 0.1, cw - 2, lh * 0.8)
                if i < n_sec:
                    d = diff[i] if i < len(diff) else None
                    label = f"S{i + 1} " + ("–" if d is None else f"{d:+.2f}")
                else:
                    d = total
                    label = "LAP " + ("–" if d is None else f"{d:+.2f}")
                if d is None:
                    bg, fg = self.pal.track, self.pal.dim
                else:  # mano laikas - jo laikas: < 0 = aš greitesnis
                    bg = QColor(self.pal.good if d < 0 else self.pal.bad)
                    bg.setAlpha(60 if abs(d) < 0.05 else 150)
                    fg = self.pal.text
                self.chip(p, rect, label, bg, fg, "tiny")
            y += lh
            if show_times:
                p.setPen(self.pal.dim)
                for i in range(n_sec):
                    t = mine[i] if i < len(mine) else None
                    self.draw_text(p, QRectF(x0 + i * cw, y, cw, lh), "–" if t is None else f"{t:.2f}", "small", "c")
                y += lh
