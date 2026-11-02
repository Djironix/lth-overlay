"""Relative: arčiausios mašinos trasoje su delta (artėjam / tolstam)."""
from __future__ import annotations

from ..registry import RELATIVE_COLUMNS
from ..theme import fmt_gap, fmt_lap, fmt_rel, short_name
from .standings import irating_text
from .table import CENTER, RIGHT, Cell, TableWidget, ordered_columns


class RelativeWidget(TableWidget):
    NAME = "relative"
    TITLE = "Relative"
    MIN_WIDTH = 220
    HEIGHT_MODE = "rows"
    WIDTHS = {"classbar": 0.01, "pos": 1.6, "number": 2.2, "flag": 1.45, "name": None, "brand": 2.3,
              "carname": 6.5, "status": 2.4, "irating": 2.8, "irchange": 2.2, "last": 3.9, "best": 3.9, "license": 2.0, "delta": 2.9, "catch": 3.0, "gap": 3.0,
              "change": 0.9, "start": 1.9, "leadergap": 3.4, "interval": 3.2, "tire": 1.2, "pitstops": 1.6,
              "lapsdone": 2.0, "laps": 11.5}

    def __init__(self, ctx):
        self._rows = []
        self._cols = []
        self._title = ("RELATIVE", ())
        self._footer = ()
        self._border = None
        super().__init__(ctx)

    def content_key(self, snap):
        c = self.cfg
        cols = ordered_columns(c, RELATIVE_COLUMNS)
        self.WIDTHS = dict(type(self).WIDTHS, license=3.6 if c.get("license_style") == "full" else 2.0,
                           laps=self.laps_width(), brand=2.9 if c.get("brand_style", "logo") == "logo" else 2.3,
                           status=self.pit_width() if c.get("pit_style", "stop") != "badge" else 2.4)
        self._cols = ["classbar"] + cols
        rel = snap.relative
        me_i = next((i for i, r in enumerate(rel) if r.is_me), None)
        self._footer = self.footer_info(snap)
        if me_i is not None:
            a, b = int(c.get("ahead", 3)), int(c.get("behind", 3))
            avail = self.avail_body_height()
            if avail is not None:  # aukštis nustatytas tempiant: tiek eilučių, kiek telpa
                n = max(1, int((avail - self.footer_h() - self.colhead_h()) // self.row_h()))
                a = (n - 1) // 2
                b = n - 1 - a
            rel = rel[max(0, me_i - a): me_i + b + 1]
        race = snap.session_type == "race"
        friends = self.ctx.config.friends() if hasattr(self.ctx.config, "friends") else {}
        rows = [self._row(r, cols, snap, race, friends) for r in rel]
        self._rows = rows
        self._cols = ["classbar"] + self.collapse_empty(cols, rows)
        self._title = ("RELATIVE", self.header_info(snap))
        self._border = self.session_border(snap)
        return (tuple(rows), tuple(cols), self._title, self._footer, self._border, self.width(),
                bool(c.get("column_header")))

    def _row(self, rr, cols, snap, race, friends):
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
        friend = friends.get(r.user_id) if r.user_id else None
        cells = [Cell("classbar", "", bg=("rgb", r.class_color))]
        for k in cols:
            if k == "pos":
                cells.append(Cell(k, str(r.class_pos if snap.multiclass else r.pos) if r.pos else "", fg=fg,
                                  align=RIGHT, font="bold"))
            elif k == "number":
                cells.append(self.number_cell(k, r))
            elif k == "flag":
                cells.append(self.flag_cell(k, r))
            elif k == "name":
                nm = short_name(r, self.cfg.get("name_mode", "abbrev"), self.pal.upper_names)
                cells.append(Cell(k, nm, fg=("hex", friend) if friend and not rr.is_me else fg,
                                  font="bold" if rr.is_me else "base"))
            elif k == "brand":
                cells.append(self.brand_cell(k, r))
            elif k == "carname":
                cells.append(self.carname_cell(k, r))
            elif k == "status":
                cells.append(self.pit_cell(k, r, race) if self.cfg.get("pit_style", "stop") != "badge"
                             else self.status_cell(k, r, race))
            elif k == "irating":
                cells.append(self.irating_cell(k, r))
            elif k == "irchange":
                cells.append(self.irchange_cell(k, r, snap))
            elif k == "last":
                lf = "purple" if r.last_is_fastest else "good" if r.last_is_pb else "dim"
                cells.append(Cell(k, fmt_lap(r.last_lap), fg=lf, align=RIGHT, font="small"))
            elif k == "best":
                cells.append(Cell(k, fmt_lap(r.best_lap), fg="purple" if r.best_is_fastest else "dim", align=RIGHT,
                                  font="small"))
            elif k == "license":
                cells.append(self.license_cell(k, r))
            elif k == "delta":
                cells.append(self.delta_cell(rr))
            elif k == "catch":
                t = ""
                if not rr.is_me and rr.gap > 0 and rr.laps_to_catch is not None and rr.lap_rel == 0:
                    t = f"{rr.laps_to_catch:.0f} laps" if rr.catchable is not False else "no catch"
                    t = t if rr.laps_to_catch < 99 else ""
                cells.append(Cell(k, t, fg="dim", align=RIGHT, font="small"))
            elif k == "change":
                ch = r.pos_change_lap if race else 0
                cells.append(Cell(k, "▲" if ch > 0 else "▼" if ch < 0 else "", fg="good" if ch > 0 else "bad",
                                  align=CENTER, font="tiny"))
            elif k == "start":
                ch = r.pos_change_start if race else 0
                cells.append(Cell(k, f"{ch:+d}" if ch else "", fg="good" if ch > 0 else "bad", align=RIGHT, font="small"))
            elif k == "leadergap":
                if r.gap is None and not r.gap_laps:
                    t = "Leader" if race and r.class_pos == 1 else ""
                else:
                    t = fmt_gap(r.gap, r.gap_laps if race else 0, r.stale or r.approx)
                cells.append(Cell(k, t, fg="dim", align=RIGHT, font="small"))
            elif k == "interval":
                t = fmt_gap(r.interval, r.interval_laps, r.stale or r.approx) \
                    if (r.interval is not None or r.interval_laps) else ""
                cells.append(Cell(k, t, fg="dim", align=RIGHT, font="small"))
            elif k == "tire":
                cells.append(Cell(k, "W" if r.tire == 1 else "", fg="blue", align=CENTER, font="tiny"))
            elif k == "pitstops":
                cells.append(Cell(k, str(r.pit_stops) if r.pit_stops else "", fg="dim", align=CENTER, font="small"))
            elif k == "lapsdone":
                cells.append(Cell(k, str(r.laps) if r.laps else "", fg="dim", align=RIGHT, font="small"))
            elif k == "laps":
                cells.append(self.laps_cell(k, r, snap))
            elif k == "gap":
                t = "" if rr.is_me else fmt_rel(rr.gap, rr.stale or rr.approx)
                cells.append(Cell(k, t, fg="dim" if (rr.stale or rr.approx) else fg, align=RIGHT, font="bold"))
        flags = ("me",) if rr.is_me else (("friend",) if friend else ())
        if race and r.flag_bits & 0x20 and self.cfg.get("blue_rows", True):
            flags = flags + ("blue",)
        return ("car", tuple(cells), flags)

    def desired_height(self) -> int:
        n = max(1, len(self._rows))
        return int(self.header_h() + self.colhead_h() + self.row_h() * n + self.footer_h() + 6)

    def paint_content(self, p):
        if not self._rows and not self.editing:
            return
        y = self.paint_frame(p, *self._title)
        y = self.paint_colhead(p, self._rows, self._cols, y)
        y = self.paint_rows(p, self._rows, self._cols, y)
        self.paint_footer(p, y)
        self.paint_flag_border(p)
