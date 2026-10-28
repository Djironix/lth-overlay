"""Standings: visas laukas pagal poziciją, su multiklase ir filtrais."""
from __future__ import annotations

from ..registry import STANDINGS_COLUMNS
from ..theme import fmt_gap, fmt_lap, short_name
from .table import CENTER, LEFT, RIGHT, Cell, TableWidget, ordered_columns

SESSION_NAMES = {"race": "RACE", "qualify": "QUALIFYING", "practice": "PRACTICE", "warmup": "WARMUP"}


def irating_text(ir: int) -> str:
    return f"{ir / 1000:.1f}k" if ir >= 1000 else str(ir or "")


class StandingsWidget(TableWidget):
    NAME = "standings"
    TITLE = "Standings"
    MIN_WIDTH = 220
    HEIGHT_MODE = "rows"
    WIDTHS = {"classbar": 0.01, "pos": 1.6, "change": 0.9, "number": 2.2, "flag": 1.45, "brand": 2.3, "name": None,
              "carname": 6.5, "gap": 3.4, "interval": 3.2, "last": 4.0, "best": 4.0, "start": 1.9, "irating": 2.3, "irchange": 2.2,
              "license": 2.0, "pit": 2.4, "tire": 1.2}

    def __init__(self, ctx):
        self._rows = []
        self._cols = []
        self._title = ("", ())
        self._footer = ()
        self._border = None
        self._friends = {}
        super().__init__(ctx)

    # ---------------- duomenys -> eilutės ----------------
    def content_key(self, snap):
        c = self.cfg
        cols = ordered_columns(c, STANDINGS_COLUMNS)
        self.WIDTHS = dict(type(self).WIDTHS, license=3.6 if c.get("license_style") == "full" else 2.0)
        self._cols = ["classbar"] + cols
        self._footer = self.footer_info(snap)
        self._friends = self.ctx.config.friends()
        rows = self._build_rows(snap, cols)
        self._rows = rows
        self._cols = ["classbar"] + self.collapse_empty(cols, rows)
        stype = SESSION_NAMES.get(snap.session_type, "")
        info = self.header_info(snap)
        self._title = (stype, info)
        self._border = self.session_border(snap)
        return (tuple(rows), tuple(cols), self._title, self._footer, self._border, self.width(),
                bool(self.cfg.get("column_header")))

    def _select(self, snap, rows):
        """Filtrai: visi / top N + aplink mane / tik aplink mane."""
        c = self.cfg
        mode = c.get("filter", "top_around")
        if mode == "all":
            return rows, set()
        me_i = next((i for i, r in enumerate(rows) if r.is_me), None)
        keep = set()
        n_top = int(c.get("top_n", 3))
        n_around = int(c.get("around_n", 5))
        if mode == "top_around":
            keep.update(range(min(n_top, len(rows))))
        if me_i is not None:
            keep.update(range(max(0, me_i - n_around), min(len(rows), me_i + n_around + 1)))
        elif mode != "top_around":
            keep.update(range(min(n_around * 2 + 1, len(rows))))
        idx = sorted(keep)
        return [rows[i] for i in idx], idx

    def _build_rows(self, snap, cols):
        c = self.cfg
        cars = list(snap.cars)
        me = next((r for r in cars if r.is_me), None)
        multiclass = snap.multiclass
        class_mode = c.get("class_mode", "grouped") if multiclass else "overall"
        out, meta = [], []  # meta: (rūšis, klasė, ar mano klasė, ar aš)
        if class_mode == "grouped":
            order = []
            for r in cars:
                if r.class_id not in order:
                    order.append(r.class_id)
            # mano klasė pirma
            if me and me.class_id in order:
                order.remove(me.class_id)
                order.insert(0, me.class_id)
            other_n = int(c.get("other_classes_n", 3))
            for cid in order:
                rows = [r for r in cars if r.class_id == cid]
                mine = me is not None and me.class_id == cid
                if mine:
                    sel, idx = self._select(snap, rows)  # mano klasė: pasirinktas filtras
                elif other_n <= 0:
                    continue  # kitos klasės paslėptos
                else:  # kitos klasės: tik top N
                    sel, idx = rows[:other_n], list(range(min(other_n, len(rows))))
                info = snap.classes.get(cid, {})
                sof = (snap.sof or {}).get(cid)
                count = f"{len(rows)} car{'s' if len(rows) != 1 else ''}"
                if sof:
                    count += f"  ·  SOF {sof / 1000:.1f}k" if sof >= 1000 else f"  ·  SOF {sof}"
                out.append(("class", (info.get("name") or rows[0].class_name, ("rgb", info.get("color", 0xFFFFFF)),
                                      count), ()))
                meta.append(("class", cid, mine, False))
                self._append(out, sel, idx, cols, snap, by_class=True, meta=meta, cid=cid, mine=mine)
        else:
            rows = [r for r in cars if me is None or class_mode == "overall" or r.class_id == me.class_id]
            sel, idx = self._select(snap, rows)
            self._append(out, sel, idx, cols, snap, by_class=multiclass and class_mode == "mine", meta=meta,
                         cid=None, mine=True)
        return self._fit(out, meta)

    @staticmethod
    def _cleanup(out, meta):
        """Pašalina tuščias klasių antraštes ir skirtukus kraštuose."""
        k = 0
        while k < len(meta):
            kind = meta[k][0]
            nxt = meta[k + 1][0] if k + 1 < len(meta) else None
            prv = meta[k - 1][0] if k > 0 else None
            if (kind == "class" and nxt in (None, "class")) or (kind == "sep" and (nxt in (None, "class", "sep") or prv in (None, "class"))):
                del out[k], meta[k]
                k = max(0, k - 1)
                continue
            k += 1

    def _row_units(self, kind) -> float:
        return 0.6 if kind == "sep" else 0.9 if kind == "class" else 1.0

    def _fit(self, out, meta):
        """Apriboja eilutes: pagal vartotojo nustatytą aukštį arba „Max rows“.
        Pirmiausia trumpinamos kitos klasės (nuo galo), mano eilutė lieka visada."""
        avail = self.avail_body_height()
        if avail is not None:
            budget = max(1.0, (avail - self.footer_h() - self.colhead_h()) / self.row_h())
        else:
            budget = int(self.cfg.get("max_rows", 26)) + sum(1 for m in meta if m[0] != "car") * 0.9
        out, meta = list(out), list(meta)

        def total():
            return sum(self._row_units(m[0]) for m in meta)

        # 1) kitų klasių eilutės nuo galo
        while total() > budget + 1e-6:
            k = next((k for k in range(len(meta) - 1, -1, -1) if not meta[k][2] and meta[k][0] != "class"), None)
            if k is None:
                break
            del out[k], meta[k]
            self._cleanup(out, meta)
        # 2) mano klasė: tolimiausios nuo manęs eilutės
        while total() > budget + 1e-6:
            me_i = next((k for k, m in enumerate(meta) if m[3]), None)
            cand = [k for k, m in enumerate(meta) if m[0] == "car" and not m[3]]
            if not cand:
                break
            k = max(cand, key=lambda k: (abs(k - me_i) if me_i is not None else k, k))
            del out[k], meta[k]
            self._cleanup(out, meta)
        self._meta = meta
        return out

    def _append(self, out, sel, idx, cols, snap, by_class, meta, cid, mine):
        prev = None
        for r, i in zip(sel, idx or range(len(sel))):
            if prev is not None and i != prev + 1:
                out.append(("sep", (), ()))
                meta.append(("sep", cid, mine, False))
            prev = i
            out.append(self._row(r, cols, snap, by_class))
            meta.append(("car", cid, mine, bool(r.is_me)))

    def _row(self, r, cols, snap, by_class):
        c = self.cfg
        race = snap.session_type == "race"
        dim = r.status in ("pit", "garage", "out")
        base = "dim" if dim else "text"
        cells = [Cell("classbar", "", bg=("rgb", r.class_color))]
        for k in cols:
            if k == "pos":
                cells.append(Cell(k, str(r.class_pos if by_class or snap.multiclass else r.pos), fg=base,
                                  align=RIGHT, font="bold"))
            elif k == "change":
                ch = r.pos_change_lap if race else 0
                cells.append(Cell(k, "▲" if ch > 0 else "▼" if ch < 0 else "",
                                  fg="good" if ch > 0 else "bad", align=CENTER, font="tiny"))
            elif k == "number":
                cells.append(self.number_cell(k, r))
            elif k == "flag":
                cells.append(self.flag_cell(k, r))
            elif k == "brand":
                cells.append(self.brand_cell(k, r))
            elif k == "carname":
                cells.append(self.carname_cell(k, r))
            elif k == "name":
                friend = self._friends.get(r.user_id) if r.user_id and not r.is_me else None
                cells.append(Cell(k, short_name(r, c.get("name_mode", "abbrev"), self.pal.upper_names),
                                  fg=("hex", friend) if friend else base, font="bold" if r.is_me else "base"))
            elif k == "gap":
                if race:
                    t = "" if r.gap is None and not r.gap_laps else fmt_gap(r.gap, r.gap_laps, r.stale or r.approx)
                    if r.gap is None and not r.gap_laps:
                        t = "Leader" if r.class_pos == 1 else ""
                else:
                    t = fmt_gap(r.gap) if r.gap is not None else ("" if r.best_lap <= 0 else "")
                cells.append(Cell(k, t, fg="dim" if (r.stale or r.approx) else base, align=RIGHT))
            elif k == "interval":
                t = fmt_gap(r.interval, r.interval_laps, r.stale or r.approx) if (r.interval is not None or r.interval_laps) else ""
                cells.append(Cell(k, t, fg="dim" if (r.stale or r.approx) else base, align=RIGHT))
            elif k == "last":
                fg = "purple" if r.last_is_fastest else "good" if r.last_is_pb else base
                cells.append(Cell(k, fmt_lap(r.last_lap), fg=fg, align=RIGHT))
            elif k == "best":
                cells.append(Cell(k, fmt_lap(r.best_lap), fg="purple" if r.best_is_fastest else base, align=RIGHT))
            elif k == "start":
                ch = r.pos_change_start if race else 0
                cells.append(Cell(k, f"{ch:+d}" if ch else "", fg="good" if ch > 0 else "bad", align=RIGHT, font="small"))
            elif k == "irating":
                cells.append(Cell(k, irating_text(r.irating), fg="dim", align=RIGHT, font="small"))
            elif k == "irchange":
                cells.append(self.irchange_cell(k, r, snap))
            elif k == "license":
                cells.append(self.license_cell(k, r))
            elif k == "pit":
                st = self.status_cell(k, r, race)
                if not st[1] and race and r.laps_since_pit is not None:
                    st = Cell(k, f"{r.laps_since_pit}", fg="dim", align=CENTER, font="small")
                cells.append(st)
            elif k == "tire":
                cells.append(Cell(k, "W" if r.tire == 1 else "", fg="blue", align=CENTER, font="tiny"))
        flags = ("me",) if r.is_me else (("friend",) if self._friends.get(r.user_id) else ())
        return ("car", tuple(cells), flags)

    # ---------------- piešimas ----------------
    def desired_height(self) -> int:
        rh = self.row_h()
        h = sum(rh * self._row_units(kind) for kind, _, _ in self._rows)
        return int(self.header_h() + self.colhead_h() + h + self.footer_h() + 6)

    def paint_content(self, p):
        if not self._rows and not self.editing:
            return
        y = self.paint_frame(p, *self._title)
        y = self.paint_colhead(p, self._rows, self._cols, y)
        y = self.paint_rows(p, self._rows, self._cols, y)
        self.paint_footer(p, y)
        self.paint_flag_border(p)
