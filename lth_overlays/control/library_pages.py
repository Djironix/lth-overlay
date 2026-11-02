"""Records (asmeniniai rekordai) puslapis."""
from __future__ import annotations

import os

from PySide6.QtWidgets import QGridLayout, QMessageBox

from lth_timing import telemetry as T

from .components import Card, button, clear_layout, label
from .pages import Page


class RecordsPage(Page):
    TITLE = "Records"
    SUBTITLE = "Your all-time best laps per car and track"

    def __init__(self, center):
        super().__init__(center)
        self.card = Card("Personal bests", "Saved automatically when you beat your best (valid laps only). "
                                           "Open one to compare it in Telemetry.")
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(6)
        self.card.add(self.grid)
        self.content.addWidget(self.card)
        self.content.addStretch(1)
        self._key = None

    def on_show(self):
        recs = self.ctx.pbs.records()
        key = tuple((a, b, v.get("lap")) for a, b, v in recs)
        if key == self._key:
            return
        self._key = key
        clear_layout(self.grid)
        if not recs:
            self.grid.addWidget(label("No records yet - drive a valid lap.", "faint"), 0, 0)
            return
        for c, h in enumerate(("Track", "Car", "Best lap", "Date", "")):
            self.grid.addWidget(label(h, "faint"), 0, c)
        from .telemetry_page import best_path
        for r, (tk, ck, v) in enumerate(recs, start=1):
            self.grid.addWidget(label(v.get("track") or tk, "h3"), r, 0)
            self.grid.addWidget(label(v.get("car") or ck), r, 1)
            self.grid.addWidget(label(T.fmt(v.get("lap")), "h3"), r, 2)
            self.grid.addWidget(label(v.get("date", ""), "muted"), r, 3)
            path = best_path(tk, ck)
            if os.path.isfile(path):
                b = button("Open in Telemetry", "ghost", "delta")
                b.clicked.connect(lambda _=False, pth=path: self._open(pth))
                self.grid.addWidget(b, r, 4)
        self.grid.setColumnStretch(4, 1)

    def _open(self, path):
        try:
            lap = T.load_lap(path)
        except (OSError, ValueError, KeyError) as e:
            QMessageBox.warning(self, "Records", str(e))
            return
        lap.meta["imported"] = True
        lap.meta.setdefault("driver", "My record")
        self.center.go("telemetry")
        tp = self.center._pages.get("telemetry")
        if tp is not None:
            tp.imported.append(lap)
            tp._refresh(force=True)
            key = f"i{len(tp.imported) - 1}"
            if key in tp.c_a._keys:
                tp.c_a.setCurrentIndex(tp.c_a._keys.index(key))
