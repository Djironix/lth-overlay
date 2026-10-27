"""Standings: visas laukas pagal poziciją, su multiklase ir filtrais."""
from __future__ import annotations

from ..theme import fmt_clock, fmt_gap, fmt_lap, short_name
from .table import CENTER, LEFT, RIGHT, Cell, TableWidget

SESSION_NAMES = {"race": "RACE", "qualify": "QUALIFYING", "practice": "PRACTICE", "warmup": "WARMUP"}


def irating_text(ir: int) -> str:
    return f"{ir / 1000:.1f}k" if ir >= 1000 else str(ir or "")


class StandingsWidget(TableWidget):
    NAME = "standings"
    TITLE = "Standings"
    MIN_WIDTH = 220
    HEIGHT_MODE = "rows"
    WIDTHS = {"classbar": 0.01, "pos": 1.7, "change": 1.0, "number": 2.4, "brand": 2.5, "name": None,
              "gap": 3.6, "interval": 3.6, "last": 4.2, "best": 4.2, "start": 2.0, "irating": 2.8,
              "license": 3.0, "pit": 2.6, "tire": 1.3}

    def __init__(self, ctx):
        self._rows = []
        self._cols = []
        self._title = ("", "")
        super().__init__(ctx)

    # ---------------- duomenys -> eilutės ----------------
    def content_key(self, snap):
        c = self.cfg
        cols = [k for k in c["order"] if c["columns"].get(k)]
        self._cols = ["classbar"] + cols
        rows = self._build_rows(snap, cols)
        self._rows = rows
        stype = SESSION_NAMES.get(snap.session_type, "")
        if snap.session_type == "race":
            if 0 < snap.laps_remain < 30000:
                right = f"{snap.laps_remain} laps left"
            else:
                right = f"{fmt_clock(snap.time_remain)} left" if snap.time_remain > 0 else ""
        else:
            right = f"{fmt_clock(snap.time_remain)} left" if 0 < snap.time_remain < 1e5 else ""
        self._title = (stype, right)
        return (tuple(rows), tuple(cols), self._title, self.width())

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
                out.append(("class", (info.get("name") or rows[0].class_name, ("rgb", info.get("color", 0xFFFFFF)),
                                      f"{len(rows)} car{'s' if len(rows) != 1 else ''}"), ()))
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
            budget = avail / self.row_h()
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
            elif k == "brand":
                cells.append(Cell(k, r.brand.get("short", ""), fg="text", bg=("hex", r.brand.get("color", "#555")),
                                  align=CENTER, font="tiny"))
            elif k == "name":
                cells.append(Cell(k, short_name(r, c.get("name_mode", "abbrev"), self.pal.upper_names), fg=base, font="bold" if r.is_me else "base"))
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
            elif k == "license":
                cells.append(Cell(k, r.license.split(" ")[0] if r.license else "", fg="dim", align=CENTER, font="small"))
            elif k == "pit":
                if r.status == "pit":
                    cells.append(Cell(k, "PIT", fg="text", bg="pit", align=CENTER, font="tiny"))
                elif r.status == "off":
                    cells.append(Cell(k, "OFF", fg="text", bg="yellow", align=CENTER, font="tiny"))
                elif r.status in ("garage", "out"):
                    cells.append(Cell(k, "OUT", fg="dim", align=CENTER, font="tiny"))
                elif race and r.laps_since_pit is not None:
                    cells.append(Cell(k, f"{r.laps_since_pit}", fg="dim", align=CENTER, font="small"))
                else:
                    cells.append(Cell(k, "", align=CENTER))
            elif k == "tire":
                cells.append(Cell(k, "W" if r.tire == 1 else "", fg="blue", align=CENTER, font="tiny"))
        flags = ("me",) if r.is_me else ()
        return ("car", tuple(cells), flags)

    # ---------------- piešimas ----------------
    def desired_height(self) -> int:
        rh = self.row_h()
        h = sum(rh * self._row_units(kind) for kind, _, _ in self._rows)
        return int(self.header_h() + h + 6)

    def paint_content(self, p):
        if not self._rows and not self.editing:
            return
        y = self.paint_frame(p, *self._title) if self._rows or self.editing else 0
        self.paint_rows(p, self._rows, self._cols, y)
