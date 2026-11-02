"""Valdiklio nustatymų forma, sugeneruota iš registry Field aprašų."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from ..registry import BY_NAME, fields_for
from .components import (Card, ColumnList, Combo, NumberField, Segmented, SettingRow, SliderField, Toggle, button,
                         label)

GROUP_ORDER = ("Visibility", "Position & size", "Look", "Content", "Columns", "Header & footer")
GROUP_SUB = {
    "Visibility": "When this widget is on screen.",
    "Position & size": "Exact pixels on your main screen. You can also drag it on screen or on the Layout page.",
    "Look": "Size, background and header.",
    "Content": "What the widget shows.",
    "Columns": "Turn columns on or off. Drag the handle to change the order.",
    "Header & footer": "Extra information next to the title and in a bar under the table. Drag to reorder.",
}


class WidgetForm(QWidget):
    def __init__(self, ctx, name: str):
        super().__init__()
        self.ctx = ctx
        self.name = name
        self.spec = BY_NAME[name]
        self._controls = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        groups = {}
        for f in fields_for(self.spec):
            groups.setdefault(f.group, []).append(f)
        for g in GROUP_ORDER + tuple(k for k in groups if k not in GROUP_ORDER):
            if g == "Position & size":
                lay.addWidget(self._geometry_card())
                continue
            if g not in groups:
                continue
            card = Card(g, GROUP_SUB.get(g))
            for f in groups[g]:
                card.add(self._control(f))
            lay.addWidget(card)
        lay.addStretch(1)

    @property
    def cfg(self):
        return self.ctx.config.widget(self.name)

    # ---------------------------------------------------------------- laukai
    def _set(self, key, value):
        self.cfg[key] = value
        self.ctx.widget_changed(self.name)

    def _control(self, f):
        c = self.cfg
        val = c.get(f.key, f.default)
        if f.kind == "bool":
            t = Toggle(bool(val))
            t.toggled.connect(lambda v, k=f.key: self._set(k, bool(v)))
            self._controls[f.key] = t
            return SettingRow(f.label, t, f.help)
        if f.kind in ("int", "float", "percent"):
            step = f.step or (1 if f.kind == "int" else 0.1)
            s = SliderField(val if val is not None else f.default, f.min, f.max, step, f.suffix,
                            percent=f.kind == "percent")
            if f.kind == "int":
                s.changed.connect(lambda v, k=f.key: self._set(k, int(round(v))))
            else:
                s.changed.connect(lambda v, k=f.key: self._set(k, float(v)))
            self._controls[f.key] = s
            return SettingRow(f.label, s, f.help)
        if f.kind == "choice":
            short = len(f.options) <= 4 and sum(len(t) for t in f.options.values()) <= 34
            w = Segmented(f.options, val) if short else Combo(f.options, val)
            w.changed.connect(lambda v, k=f.key: self._set(k, v))
            self._controls[f.key] = w
            return SettingRow(f.label, w, f.help)
        if f.kind in ("columns", "checks", "items"):
            enabled = c.get("columns" if f.kind == "columns" else f.key) or {}
            order = c.get("order") if f.kind == "columns" else (c.get(f.key + "_order") if f.kind == "items" else None)
            cl = ColumnList(f.spec, enabled, order, reorder=f.kind in ("columns", "items"))

            def changed(en, order, kind=f.kind, key=f.key):
                if kind == "columns":
                    self.cfg["columns"] = en
                    self.cfg["order"] = order
                elif kind == "items":
                    self.cfg[key] = en
                    self.cfg[key + "_order"] = order
                else:
                    self.cfg[key] = en
                self.ctx.widget_changed(self.name)
            cl.changed.connect(changed)
            box = QWidget()
            v = QVBoxLayout(box)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(6)
            if f.kind in ("checks", "items"):
                v.addWidget(label(f.label, "h3"))
                if f.help:
                    v.addWidget(label(f.help, "faint", wrap=True))
            v.addWidget(cl)
            return box
        if f.kind == "color":
            from .components import ColorButton
            b = ColorButton(str(val or f.default or "#ffffff"))
            b.changed.connect(lambda v, k=f.key: self._set(k, v))
            self._controls[f.key] = b
            return SettingRow(f.label, b, f.help)
        if f.kind == "image":
            return self._image_control(f, val)
        # text
        e = QLineEdit(str(val or ""))
        e.setMinimumWidth(240)
        e.editingFinished.connect(lambda k=f.key, e=e: self._set(k, e.text()))
        return SettingRow(f.label, e, f.help)

    def _image_control(self, f, val):
        """Paveikslėlis (pvz. savo vairo PNG): nukopijuojamas į programos aplanką, kad neprapultų."""
        import os
        import shutil
        from PySide6.QtWidgets import QFileDialog
        from ..config import app_dir
        name = label(os.path.basename(val) if val else "Built-in", "muted")
        pick = button("Choose image...", "ghost", "image")
        clear = button("", "ghost", "reset", "Back to the built-in one")
        clear.setFixedWidth(34)

        def choose():
            path, _ = QFileDialog.getOpenFileName(self, f.label, "", "Images (*.png *.webp *.jpg *.jpeg)")
            if not path:
                return
            folder = os.path.join(app_dir(), "images")
            os.makedirs(folder, exist_ok=True)
            dst = os.path.join(folder, f"{self.name}_{f.key}{os.path.splitext(path)[1].lower()}")
            try:
                shutil.copyfile(path, dst)
            except OSError:
                return
            name.setText(os.path.basename(path))
            self._set(f.key, dst)

        def reset():
            name.setText("Built-in")
            self._set(f.key, "")
        pick.clicked.connect(choose)
        clear.clicked.connect(reset)
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        h.addWidget(name)
        h.addWidget(pick)
        h.addWidget(clear)
        return SettingRow(f.label, box, f.help)

    # ---------------------------------------------------------------- vieta ir dydis
    def _ensure_size(self):
        """Paslėptas langas dar neturi tikro aukščio - paskaičiuojam iš dabartinių / demo duomenų."""
        w = self.ctx.widgets[self.name]
        if not w.isVisible():
            snap = self.ctx.engine.latest
            w.push(snap if snap.connected else self.ctx.preview_snapshot(), force=True)
        return w

    def _geometry_card(self):
        card = Card("Position & size", GROUP_SUB["Position & size"])
        w = self._ensure_size()
        self.fx = NumberField(w.x(), suffix=" px")
        self.fy = NumberField(w.y(), suffix=" px")
        self.fw = NumberField(w.width(), 40, 4000, suffix=" px")
        self.fh = NumberField(w.height(), 20, 3000, suffix=" px")
        row = QHBoxLayout()
        row.setSpacing(10)
        for t, fld in (("X", self.fx), ("Y", self.fy), ("Width", self.fw), ("Height", self.fh)):
            col = QVBoxLayout()
            col.setSpacing(4)
            col.addWidget(label(t, "faint"))
            col.addWidget(fld)
            row.addLayout(col)
        row.addStretch(1)
        card.add(row)
        mode = w.HEIGHT_MODE
        if mode == "auto":
            self.fh.setEnabled(False)
            self.fh.setToolTip("Height follows the content. Use Size to make the whole widget bigger.")
            self.auto_h = None
            card.add(label("Height follows the content. Drag a corner or change Size to scale the whole widget.",
                           "faint", wrap=True))
        else:
            self.auto_h = Toggle(not self.cfg.get("height"))
            txt = ("Automatic height (fit the rows)" if mode == "rows" else "Automatic height")
            card.add(SettingRow(txt, self.auto_h, "Off: drag the bottom edge or type a height to show more or "
                                                  "fewer rows." if mode == "rows" else ""))
            self.auto_h.toggled.connect(self._auto_height)
            self.fh.setEnabled(bool(self.cfg.get("height")))
        btns = QHBoxLayout()
        b1 = button("Center horizontally", "ghost", "align_center")
        b1.clicked.connect(self._center)
        btns.addWidget(b1)
        btns.addStretch(1)
        card.add(btns)
        self.fx.valueChanged.connect(lambda v: self._geo("x", v))
        self.fy.valueChanged.connect(lambda v: self._geo("y", v))
        self.fw.valueChanged.connect(lambda v: self._geo("w", v))
        self.fh.valueChanged.connect(lambda v: self._geo("h", v))
        return card

    def _scale(self):
        return float(self.cfg.get("scale", 1.0) or 1.0)

    def _geo(self, what, v):
        c = self.cfg
        w = self.ctx.widgets[self.name]
        c["x"], c["y"], c["pos_v"] = w.x(), w.y(), 2
        if what == "x":
            c["x"] = int(v)
        elif what == "y":
            c["y"] = int(v)
        elif what == "w":
            c["width"] = int(round(v / self._scale()))
        elif what == "h":
            c["height"] = int(round(v / self._scale()))
        self.ctx.widget_changed(self.name)
        QTimer.singleShot(0, self.refresh_geometry)

    def _auto_height(self, on):
        w = self.ctx.widgets[self.name]
        self.cfg["height"] = None if on else int(round(max(w.height(), 60) / self._scale()))
        self.fh.setEnabled(not on)
        self.ctx.widget_changed(self.name)
        QTimer.singleShot(0, self.refresh_geometry)

    def _center(self):
        self.ctx.widgets[self.name].center_on_screen()
        self.ctx.widget_changed(self.name)
        QTimer.singleShot(0, self.refresh_geometry)

    def refresh_geometry(self):
        w = self._ensure_size()
        self.fx.set_silent(w.x())
        self.fy.set_silent(w.y())
        self.fw.set_silent(w.width())
        self.fh.set_silent(w.height())
        if self.auto_h is not None:
            self.auto_h.set_silent(not self.cfg.get("height"))
            self.fh.setEnabled(bool(self.cfg.get("height")))
        sc = self._controls.get("scale")
        if sc is not None:
            sc.set_value(self._scale())
        vis = self._controls.get("visible")
        if vis is not None:
            vis.set_silent(bool(self.cfg.get("visible")))
