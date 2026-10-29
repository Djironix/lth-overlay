"""Setups (LTH setupų paketai ir automatinis įdiegimas) ir Records (asmeniniai rekordai) puslapiai."""
from __future__ import annotations

import os

from PySide6.QtWidgets import QFileDialog, QGridLayout, QMessageBox

from lth_timing import telemetry as T

from .components import Card, SettingRow, Toggle, button, clear_layout, hbox, label
from .pages import Page, open_folder


class SetupsPage(Page):
    TITLE = "Setups"
    SUBTITLE = "Install LTH setup packs into iRacing automatically"

    def __init__(self, center):
        super().__init__(center)
        lib = self.ctx.setups
        st = self.ctx.config.data.setdefault("setups", {"auto": False})
        c = Card("Auto install", "When you join a session, setups for that car are copied to "
                                 "Documents\\iRacing\\setups\\<car>\\LTH. Your own setups are never touched.")
        t = Toggle(bool(st.get("auto", False)))
        t.toggled.connect(self._auto)
        c.add(SettingRow("Install automatically", t, "Only new or changed files are copied."))
        from ..setups import iracing_setups_dir
        d = iracing_setups_dir()
        self.dest = label(d or "iRacing setups folder not found (start iRacing once).", "faint", wrap=True)
        c.add(self.dest)
        self.content.addWidget(c)

        lc = Card("Library", "Import a setup pack (.zip from Discord) or single .sto files. In a pack, each car has "
                             "its own folder named like iRacing's (e.g. bmwm4gt3). Single files go to the car "
                             "you are driving now.")
        b_imp = button("Import setups...", None, "download")
        b_imp.clicked.connect(self._import)
        b_dir = button("Open library folder", "ghost", "folder")
        b_dir.clicked.connect(lambda: (os.makedirs(lib.root, exist_ok=True), open_folder(lib.root)))
        lc.add(hbox(b_imp, None, b_dir))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(6)
        lc.add(self.grid)
        self.content.addWidget(lc)
        self.content.addStretch(1)
        self._fill()

    def _auto(self, on):
        self.ctx.config.data.setdefault("setups", {})["auto"] = bool(on)
        self.ctx._setups_car = None  # įjungus - įdiegti iš karto
        self.ctx.save_config_soon()

    def _current_car(self) -> str:
        snap = self.ctx.engine.latest
        return snap.car_key if snap.connected else ""

    def _import(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Import setups", "", "Setups (*.zip *.sto)")
        if not paths:
            return
        try:
            res = self.ctx.setups.import_files(paths, self._current_car())
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Import setups", f"Could not read the file.\n\n{e}")
            return
        if not res:
            QMessageBox.information(self, "Import setups", "No setups found. In a pack each car needs its own folder "
                                                           "(like iRacing's), or join a session to import single files "
                                                           "for the car you are driving.")
        else:
            self.ctx.notify("Imported " + ", ".join(f"{n} for {car}" for car, n in res.items()))
            self.ctx._setups_car = None
        self._fill()

    def _install(self, car):
        n = self.ctx.setups.install(car)
        self.ctx.notify(f"{n} setups installed for {car}" if n else f"Setups for {car} are already up to date")

    def _remove(self, car):
        if QMessageBox.question(self, "Remove", f"Remove {car} setups from the library? "
                                                "Files already in iRacing stay.") == QMessageBox.StandardButton.Yes:
            self.ctx.setups.remove(car)
            self._fill()

    def _fill(self):
        clear_layout(self.grid)
        cars = self.ctx.setups.cars()
        if not cars:
            self.grid.addWidget(label("The library is empty.", "faint"), 0, 0)
            return
        cur = self._current_car()
        for r, (car, n) in enumerate(sorted(cars.items())):
            self.grid.addWidget(label(car + ("   (driving now)" if car == cur else ""), "h3"), r, 0)
            self.grid.addWidget(label(f"{n} setup{'s' if n != 1 else ''}", "faint"), r, 1)
            b = button("Install now", "ghost", "download")
            b.clicked.connect(lambda _=False, c=car: self._install(c))
            rm = button("", "ghost", "trash", "Remove from library")
            rm.clicked.connect(lambda _=False, c=car: self._remove(c))
            self.grid.addWidget(b, r, 2)
            self.grid.addWidget(rm, r, 3)
        self.grid.setColumnStretch(1, 1)

    def on_show(self):
        self._fill()


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
