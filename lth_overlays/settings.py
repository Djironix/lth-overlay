"""Valdiklio nustatymų langas. Pakeitimai taikomi iškart ir išsaugomi."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSlider,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from .config import RELATIVE_COLUMNS, STANDINGS_COLUMNS, WEATHER_FIELDS
from .theme import FONT_CHOICES, THEMES

ENGINEER_TYPES = {"ahead": "Car ahead (once per lap)", "behind": "Car behind closing", "slow_car": "Slow car ahead",
                  "weather": "Track getting wetter / drying", "best_lap": "Personal best lap",
                  "time": "5 minutes / last lap", "faster_class": "Faster class from behind"}


class SettingsDialog(QDialog):
    def __init__(self, ctx, name: str):
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self.ctx = ctx
        self.name = name
        w = ctx.widgets[name]
        self.setWindowTitle(f"LTH Overlays - {w.TITLE}")
        self.setMinimumWidth(420)
        tabs = QTabWidget()
        tabs.addTab(self._widget_tab(), w.TITLE)
        tabs.addTab(self._global_tab(), "General")
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        lay.addWidget(close)

    @property
    def cfg(self):
        return self.ctx.config.widget(self.name)

    def _changed(self):
        self.ctx.widget_changed(self.name)

    # ---------------- valdikliai ----------------
    def _check(self, form, label, key, cfg=None):
        cfg = cfg if cfg is not None else self.cfg
        cb = QCheckBox(label)
        cb.setChecked(bool(cfg.get(key)))

        def on(v):
            cfg[key] = bool(v)
            self._changed()
        cb.toggled.connect(on)
        form.addRow(cb)
        return cb

    def _spin(self, form, label, key, lo, hi):
        sb = QSpinBox()
        sb.setRange(lo, hi)
        sb.setValue(int(self.cfg.get(key, lo)))

        def on(v):
            self.cfg[key] = int(v)
            self._changed()
        sb.valueChanged.connect(on)
        form.addRow(label, sb)

    def _combo(self, form, label, key, options: dict):
        cb = QComboBox()
        for k, v in options.items():
            cb.addItem(v, k)
        i = cb.findData(self.cfg.get(key))
        cb.setCurrentIndex(max(0, i))

        def on(_):
            self.cfg[key] = cb.currentData()
            self._changed()
        cb.currentIndexChanged.connect(on)
        form.addRow(label, cb)

    def _slider(self, form, label, key, lo, hi, scale=100):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(int(round(self.cfg.get(key, 1.0) * scale)))
        val = QLabel(f"{s.value()} %")

        def on(v):
            self.cfg[key] = v / scale
            val.setText(f"{v} %")
            self._changed()
        s.valueChanged.connect(on)
        row = QHBoxLayout()
        row.addWidget(s)
        row.addWidget(val)
        form.addRow(label, row)

    def _columns(self, form, spec, cols_key, order_key=None):
        """Stulpeliai: pažymėti = rodomi, tempiant keičiama tvarka."""
        lst = QListWidget()
        lst.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        order = self.cfg.get(order_key) if order_key else list(spec)
        order = [k for k in order if k in spec] + [k for k in spec if k not in (order or [])]
        for k in order:
            it = QListWidgetItem(spec[k][0])
            it.setData(Qt.ItemDataRole.UserRole, k)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled)
            it.setCheckState(Qt.CheckState.Checked if self.cfg[cols_key].get(k) else Qt.CheckState.Unchecked)
            lst.addItem(it)
        lst.setMinimumHeight(min(320, 24 * len(order)))

        def sync(*_):
            keys = []
            for i in range(lst.count()):
                it = lst.item(i)
                k = it.data(Qt.ItemDataRole.UserRole)
                keys.append(k)
                self.cfg[cols_key][k] = it.checkState() == Qt.CheckState.Checked
            if order_key:
                self.cfg[order_key] = keys
            self._changed()
        lst.itemChanged.connect(sync)
        lst.model().rowsMoved.connect(sync)
        form.addRow(QLabel("Columns (tick to show, drag to reorder):" if order_key else "Fields:"))
        form.addRow(lst)

    def _widget_tab(self):
        page = QWidget()
        form = QFormLayout(page)
        self._check(form, "Show", "visible")
        self._slider(form, "Size", "scale", 60, 250)
        self._slider(form, "Opacity", "opacity", 30, 100)
        names = {"abbrev": "J. Smith", "full": "John Smith", "last": "Smith", "three": "SMI"}
        if self.name == "standings":
            self._combo(form, "Filter", "filter", {"top_around": "Top N + around me", "around": "Around me only",
                                                    "all": "Everyone"})
            self._spin(form, "Top N", "top_n", 0, 20)
            self._spin(form, "Around me ±", "around_n", 1, 20)
            self._spin(form, "Max rows", "max_rows", 5, 64)
            self._combo(form, "Multiclass", "class_mode", {"grouped": "Grouped by class", "overall": "Overall",
                                                           "mine": "My class only"})
            self._combo(form, "Names", "name_mode", names)
            self._check(form, "LTH league drivers only (by iRacing ID)", "lth_only")
            self._check(form, "Header", "show_header")
            self._columns(form, STANDINGS_COLUMNS, "columns", "order")
        elif self.name == "relative":
            self._spin(form, "Cars ahead", "ahead", 1, 8)
            self._spin(form, "Cars behind", "behind", 1, 8)
            self._combo(form, "Names", "name_mode", names)
            self._check(form, "Header", "show_header")
            self._columns(form, RELATIVE_COLUMNS, "columns", "order")
        elif self.name == "weather":
            self._combo(form, "Mode", "mode", {"expanded": "Expanded", "compact": "Compact"})
            self._check(form, "Only show when the track is not dry", "only_when_wet")
            self._columns(form, WEATHER_FIELDS, "fields")
        elif self.name == "engineer":
            form.addRow(QLabel("Messages show only on straights, at most once every 20 s."))
            for k, label in ENGINEER_TYPES.items():
                self._check(form, label, k, cfg=self.cfg["types"])
        return page

    def _global_tab(self):
        page = QWidget()
        form = QFormLayout(page)
        data = self.ctx.config.data
        theme = QComboBox()
        for k, t in THEMES.items():
            theme.addItem(t["name"], k)
        theme.setCurrentIndex(max(0, theme.findData(data.get("theme", "lth"))))

        def on_theme(_):
            data["theme"] = theme.currentData()
            self.ctx.theme_changed()
        theme.currentIndexChanged.connect(on_theme)
        form.addRow("Theme", theme)
        font = QComboBox()
        for k, (_fam, label) in FONT_CHOICES.items():
            font.addItem(label, k)
        font.setCurrentIndex(max(0, font.findData(data.get("font", "montserrat"))))

        def on_font(_):
            data["font"] = font.currentData()
            self.ctx.theme_changed()
        font.currentIndexChanged.connect(on_font)
        form.addRow("Font", font)
        for key, label in (("auto_profile", "Switch profile by session (race / qualifying / practice)"),):
            cb = QCheckBox(label)
            cb.setChecked(bool(data.get(key)))
            cb.toggled.connect(lambda v, k=key: (data.__setitem__(k, bool(v)), self.ctx.save_config()))
            form.addRow(cb)
        ids = QPlainTextEdit(", ".join(str(x) for x in data.get("lth_member_ids", [])))
        ids.setPlaceholderText("iRacing IDs of LTH league drivers, comma separated")
        ids.setMaximumHeight(70)

        def on_ids():
            vals = []
            for part in ids.toPlainText().replace("\n", ",").split(","):
                part = part.strip()
                if part.isdigit():
                    vals.append(int(part))
            data["lth_member_ids"] = vals
            self.ctx.save_config()
        ids.textChanged.connect(on_ids)
        form.addRow("LTH drivers", ids)
        row = QHBoxLayout()
        exp = QPushButton("Export profile")
        imp = QPushButton("Import profile")
        exp.clicked.connect(self._export)
        imp.clicked.connect(self._import)
        row.addWidget(exp)
        row.addWidget(imp)
        form.addRow(row)
        return page

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export profile", "lth_profile.json", "JSON (*.json)")
        if path:
            self.ctx.config.export_profile(self.ctx.config.profile_key, path)

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import profile", "", "JSON (*.json)")
        if not path:
            return
        try:
            self.ctx.config.import_profile(self.ctx.config.profile_key, path)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "LTH Overlays", f"Import failed: {e}")
            return
        self.ctx.save_config()
        self.ctx.theme_changed()
