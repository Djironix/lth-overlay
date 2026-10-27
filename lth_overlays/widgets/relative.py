"""Relative: arčiausios mašinos trasoje su delta (artėjam / tolstam)."""
from __future__ import annotations

from ..theme import fmt_rel, short_name
from .standings import irating_text
from .table import CENTER, RIGHT, Cell, TableWidget


class RelativeWidget(TableWidget):
    NAME = "relative"
    TITLE = "Relative"
    MIN_WIDTH = 220
    HEIGHT_MODE = "rows"
    WIDTHS = {"classbar": 0.01, "pos": 1.8, "number": 2.4, "name": None, "irating": 2.8, "license": 3.0,
              "delta": 3.6, "catch": 3.0, "gap": 3.4}

    def __init__(self, ctx):
        self._rows = []
        self._cols = []
        self._title = ("RELATIVE", "")
        super().__init__(ctx)

    def content_key(self, snap):
        c = self.cfg
        cols = [k for k in c["order"] if c["columns"].get(k)]
        self._cols = ["classbar"] + cols
        rel = snap.relative
        me_i = next((i for i, r in enumerate(rel) if r.is_me), None)
        if me_i is not None:
            a, b = int(c.get("ahead", 3)), int(c.get("behind", 3))
            avail = self.avail_body_height()
            if avail is not None:  # aukštis nustatytas tempiant: tiek eilučių, kiek telpa
                n = max(1, int(avail // self.row_h()))
                a = (n - 1) // 2
                b = n - 1 - a
            rel = rel[max(0, me_i - a): me_i + b + 1]
        race = snap.session_type == "race"
        rows = [self._row(r, cols, snap, race) for r in rel]
        self._rows = rows
        me = next((r for r in snap.cars if r.is_me), None)
        right = ""
        if me is not None:
            n_class = sum(1 for r in snap.cars if r.class_id == me.class_id)
            right = f"P{me.class_pos}/{n_class}" if race else f"P{me.class_pos}"
        self._title = ("RELATIVE", right)
        return (tuple(rows), tuple(cols), self._title, self.width())

    def _row(self, rr, cols, snap, race):
        r = rr.car
        if rr.is_me:
            fg = "text"
        elif r.status in ("pit", "garage", "out"):
            fg = "pit"
        elif r.status == "off":
            fg = "yellow"
        elif race and rr.lap_rel > 0:
            fg = "red"  # ratu priekyje (lenkia tave)
        elif race and rr.lap_rel < 0:
            fg = "blue"  # ratu atsilikęs (tu jį lenki)
        else:
            fg = "text"
        cells = [Cell("classbar", "", bg=("rgb", r.class_color))]
        for k in cols:
            if k == "pos":
                cells.append(Cell(k, str(r.class_pos if snap.multiclass else r.pos), fg=fg, align=RIGHT, font="bold"))
            elif k == "number":
                cells.append(self.number_cell(k, r))
            elif k == "name":
                cells.append(Cell(k, short_name(r, self.cfg.get("name_mode", "abbrev"), self.pal.upper_names), fg=fg,
                                  font="bold" if rr.is_me else "base"))
            elif k == "irating":
                cells.append(Cell(k, irating_text(r.irating), fg="dim", align=RIGHT, font="small"))
            elif k == "license":
                cells.append(Cell(k, r.license.split(" ")[0] if r.license else "", fg="dim", align=CENTER, font="small"))
            elif k == "delta":
                cells.append(self._delta_cell(rr))
            elif k == "catch":
                t = ""
                if not rr.is_me and rr.gap > 0 and rr.laps_to_catch is not None and rr.lap_rel == 0:
                    t = f"{rr.laps_to_catch:.0f} laps" if rr.catchable is not False else "no catch"
                    t = t if rr.laps_to_catch < 99 else ""
                cells.append(Cell(k, t, fg="dim", align=RIGHT, font="small"))
            elif k == "gap":
                t = "" if rr.is_me else fmt_rel(rr.gap, rr.stale or rr.approx)
                cells.append(Cell(k, t, fg="dim" if (rr.stale or rr.approx) else fg, align=RIGHT, font="bold"))
        return ("car", tuple(cells), ("me",) if rr.is_me else ())

    @staticmethod
    def _delta_cell(rr):
        if rr.is_me or rr.delta is None:
            return Cell("delta", "", align=RIGHT)
        d = rr.delta
        pre = "" if rr.delta_exact else "~"
        # Priekyje: gap'as mažėja = tu greitesnis (gerai). Už tavęs: mažėja = tave vejasi (blogai).
        ahead = rr.gap > 0
        if d < -0.05:
            return Cell("delta", f"▼{pre}{-d:.1f}", fg="good" if ahead else "bad", align=RIGHT, font="small")
        if d > 0.05:
            return Cell("delta", f"▲{pre}{d:.1f}", fg="bad" if ahead else "good", align=RIGHT, font="small")
        return Cell("delta", "= 0.0", fg="dim", align=RIGHT, font="small")

    def desired_height(self) -> int:
        n = max(1, len(self._rows))
        return int(self.header_h() + self.row_h() * n + 6)

    def paint_content(self, p):
        if not self._rows and not self.editing:
            return
        y = self.paint_frame(p, *self._title)
        self.paint_rows(p, self._rows, self._cols, y)
