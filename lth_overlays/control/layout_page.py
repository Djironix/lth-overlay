"""Layout: visas ekranas sumažintas, valdiklius galima tempti ir keisti dydį pele.

Keičiami tie patys nustatymai kaip tempiant tikrą overlay'ų langą, todėl
abu būdai visada sutampa. Rodyklės - pastumti 1 px (Shift - 10 px).
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ..registry import BY_NAME, WIDGETS
from .components import (Card, NumberField, SettingRow, SliderField, Toggle, button, clear_layout, hbox, label,
                         vbox)
from .style import T, icon_pixmap, qcolor, ui_font

GRID = 8
SNAP = 10
HANDLE = 9


class LayoutCanvas(QWidget):
    selected = Signal(str)
    geometry_edited = Signal(str)

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.ctx = page.ctx
        self.sel = None
        self.show_hidden = False
        self.view_index = None  # None = visi monitoriai
        self._drag = None
        self._hover = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(360)

    # ---- geometrija ----
    def screen(self) -> QRect:
        """Rodoma sritis: visas darbalaukis arba pasirinktas monitorius."""
        screens = self.ctx.screens()
        if self.view_index is not None and 0 <= self.view_index < len(screens):
            return screens[self.view_index][1]
        return self.ctx.desktop_rect()

    def _xf(self):
        scr = self.screen()
        avail = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        k = min(avail.width() / max(scr.width(), 1), avail.height() / max(scr.height(), 1))
        w, h = scr.width() * k, scr.height() * k
        ox = avail.x() + (avail.width() - w) / 2
        oy = avail.y()
        return k, ox, oy, scr

    def heightForWidth(self, w):
        scr = self.screen()
        return int((w - 24) * scr.height() / max(scr.width(), 1)) + 24

    def hasHeightForWidth(self):
        return True

    def items(self):
        out = []
        for spec in WIDGETS:
            on = bool(self.ctx.config.widget(spec.name).get("visible"))
            if not on and not self.show_hidden:
                continue
            w = self.ctx.widgets[spec.name]
            out.append((spec.name, QRect(w.x(), w.y(), w.width(), max(w.height(), 24)), on))
        return out

    def to_view(self, r: QRect) -> QRectF:
        k, ox, oy, scr = self._xf()
        return QRectF(ox + (r.x() - scr.x()) * k, oy + (r.y() - scr.y()) * k, r.width() * k, r.height() * k)

    def hit(self, pos):
        for name, r, on in reversed(self.items()):
            v = self.to_view(r)
            if v.adjusted(-4, -4, 4, 4).contains(pos):
                corner = QRectF(v.right() - HANDLE, v.bottom() - HANDLE, HANDLE * 2, HANDLE * 2)
                if name == self.sel and corner.contains(pos):
                    return name, "resize"
                if name == self.sel and abs(pos.x() - v.right()) < 6 and v.top() < pos.y() < v.bottom():
                    return name, "width"
                if name == self.sel and abs(pos.y() - v.bottom()) < 6 and v.left() < pos.x() < v.right():
                    return name, "height"
                if v.contains(pos):
                    return name, "move"
        return None, None

    # ---- pelė ----
    def mousePressEvent(self, e):
        self.setFocus()
        name, zone = self.hit(e.position())
        if name != self.sel:
            self.sel = name
            self.selected.emit(name or "")
            if zone in ("resize", "width", "height"):
                zone = "move"
        if name is None:
            self.update()
            return
        if e.button() == Qt.MouseButton.RightButton:
            self.page.center.open_widget(name)
            return
        w = self.ctx.widgets[name]
        self._drag = (name, zone, e.position(), w.geometry(), float(w.cfg.get("scale", 1.0) or 1.0))
        self.update()

    def mouseDoubleClickEvent(self, e):
        name, _ = self.hit(e.position())
        if name:
            self.page.center.open_widget(name)

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._drag is None:
            name, zone = self.hit(pos)
            cur = {"move": Qt.CursorShape.SizeAllCursor, "resize": Qt.CursorShape.SizeFDiagCursor,
                   "width": Qt.CursorShape.SizeHorCursor, "height": Qt.CursorShape.SizeVerCursor}
            self.setCursor(cur.get(zone, Qt.CursorShape.ArrowCursor))
            if name != self._hover:
                self._hover = name
                self.update()
            return
        name, zone, start, geo, scale0 = self._drag
        k = self._xf()[0]
        dx = (pos.x() - start.x()) / k
        dy = (pos.y() - start.y()) / k
        w = self.ctx.widgets[name]
        c = w.cfg
        if zone == "move":
            x, y = self._snap(name, geo.x() + dx, geo.y() + dy, geo.width(), geo.height())
            w.move(int(x), int(y))
            c["x"], c["y"], c["pos_v"] = int(x), int(y), 2
        elif zone in ("width", "resize"):
            nw = max(w.min_width(), round((geo.width() + dx) / GRID) * GRID)
            c["x"], c["y"], c["pos_v"] = geo.x(), geo.y(), 2
            c["width"] = int(round(nw / scale0))
            if zone == "resize":
                self._set_height(w, geo.height() + dy, scale0)
            w.apply_settings()
        elif zone == "height":
            c["x"], c["y"], c["pos_v"] = geo.x(), geo.y(), 2
            self._set_height(w, geo.height() + dy, scale0)
            w.apply_settings()
        self.geometry_edited.emit(name)
        self.update()

    def _set_height(self, w, nh, scale0):
        c = w.cfg
        if w.HEIGHT_MODE == "auto":  # aukštis pagal turinį: keičiam mastelį
            geo = self._drag[3]
            f = max(0.2, nh / max(geo.height(), 1))
            c["scale"] = round(min(3.0, max(0.5, scale0 * f)), 2)
        else:
            nh = max(w.min_height(), round(nh / GRID) * GRID)
            c["height"] = int(round(nh / scale0))

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            name = self._drag[0]
            self._drag = None
            self._commit(name)

    def _commit(self, name):
        w = self.ctx.widgets[name]
        w.apply_settings()
        if w._snap is not None:
            w.push(w._snap, force=True)
        self.ctx.save_config_soon()
        self.page.center.preview.invalidate(name)
        self.geometry_edited.emit(name)
        self.update()

    def keyPressEvent(self, e):
        if not self.sel:
            return super().keyPressEvent(e)
        step = 10 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        d = {Qt.Key.Key_Left: (-step, 0), Qt.Key.Key_Right: (step, 0), Qt.Key.Key_Up: (0, -step),
             Qt.Key.Key_Down: (0, step)}.get(e.key())
        if d:
            w = self.ctx.widgets[self.sel]
            w.cfg["x"], w.cfg["y"], w.cfg["pos_v"] = w.x() + d[0], w.y() + d[1], 2
            w.move(w.cfg["x"], w.cfg["y"])
            self._commit(self.sel)
            return
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.ctx.set_widget_visible(self.sel, False)
            self.page.refresh_list()
            self.update()
            return
        super().keyPressEvent(e)

    def _snap(self, name, x, y, w, h):
        if not self.ctx.config.data.get("snap", True):
            return round(x), round(y)
        xs, ys, centers = [], [], set()
        for _, sr in self.ctx.screens():
            xs += [sr.left(), sr.right() + 1, sr.center().x()]
            ys += [sr.top(), sr.bottom() + 1]
            centers.add(sr.center().x())
        for n, r, on in self.items():
            if n == name or not on:
                continue
            xs += [r.left(), r.right() + 1]
            ys += [r.top(), r.bottom() + 1]
        self._guides = []

        def snap(v, size, edges, axis):
            best, bd = None, SNAP + 1
            for edge in edges:
                for cand in (edge, edge - size, edge - size / 2):
                    if cand == edge - size / 2 and edge not in centers:
                        continue
                    dist = abs(v - cand)
                    if dist < bd:
                        best, bd, line = cand, dist, edge
            if best is not None and bd <= SNAP:
                self._guides.append((axis, line))
                return best
            return round(v / GRID) * GRID

        return snap(x, w, xs, "x"), snap(y, h, ys, "y")

    # ---- piešimas ----
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        k, ox, oy, scr = self._xf()
        view = QRectF(ox, oy, scr.width() * k, scr.height() * k)
        if self.view_index is not None:
            p.setClipRect(view.adjusted(-2, -24, 2, 2))
        screens = self.ctx.screens()
        for i, (sname, sr) in enumerate(screens):
            sv = self.to_view(sr)
            g = QLinearGradient(0, sv.top(), 0, sv.bottom())
            g.setColorAt(0.0, QColor(74, 92, 116))
            g.setColorAt(0.55, QColor(52, 58, 66))
            g.setColorAt(0.56, QColor(36, 38, 42))
            g.setColorAt(1.0, QColor(22, 22, 25))
            p.setPen(QPen(qcolor("border2"), 1.5))
            p.setBrush(g)
            p.drawRoundedRect(sv.adjusted(1, 1, -1, -1), 6, 6)
            p.save()
            p.setClipRect(sv)
            p.setPen(QPen(QColor(255, 255, 255, 14), 1))
            step = 80 * k
            x = sv.left() + step
            while x < sv.right():
                p.drawLine(QPointF(x, sv.top()), QPointF(x, sv.bottom()))
                x += step
            y = sv.top() + step
            while y < sv.bottom():
                p.drawLine(QPointF(sv.left(), y), QPointF(sv.right(), y))
                y += step
            p.setPen(QPen(QColor(255, 255, 255, 30), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(sv.center().x(), sv.top()), QPointF(sv.center().x(), sv.bottom()))
            p.restore()
            p.setPen(QColor(255, 255, 255, 70))
            p.setFont(ui_font(12, QFont.Weight.DemiBold))
            label_txt = f"Display {i + 1}{'  (main)' if i == 0 and len(screens) > 1 else ''}"
            p.drawText(sv.adjusted(0, 0, 0, -18), Qt.AlignmentFlag.AlignCenter, label_txt)
            p.setFont(ui_font(11))
            p.setPen(QColor(255, 255, 255, 50))
            p.drawText(sv.adjusted(0, 18, 0, 0), Qt.AlignmentFlag.AlignCenter, f"{sr.width()} × {sr.height()}")
        # valdikliai
        prev = self.page.center.preview
        for name, r, on in self.items():
            v = self.to_view(r)
            pm = self.page.thumbs.get(name)
            p.setOpacity(1.0 if on else 0.35)
            if pm is not None:
                p.drawPixmap(v, pm, QRectF(0, 0, pm.width(), pm.height()))
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(15, 15, 18, 200))
                p.drawRoundedRect(v, 4, 4)
            p.setOpacity(1.0)
            sel = name == self.sel
            hov = name == self._hover
            if sel or hov or not on:
                p.setPen(QPen(qcolor("accent") if sel else QColor(255, 255, 255, 120), 1.6 if sel else 1,
                              Qt.PenStyle.SolidLine if sel else Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(v.adjusted(-1, -1, 1, 1), 4, 4)
            if sel or hov or pm is None:
                title = BY_NAME[name].title
                p.setFont(ui_font(11, QFont.Weight.DemiBold))
                tw = p.fontMetrics().horizontalAdvance(title) + 14
                chip = QRectF(v.x(), max(view.top(), v.y() - 20), tw, 18)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(qcolor("accent") if sel else QColor(20, 20, 24, 230))
                p.drawRoundedRect(chip, 4, 4)
                p.setPen(QColor(T["accent_text"]) if sel else qcolor("text"))
                p.drawText(chip, Qt.AlignmentFlag.AlignCenter, title)
            if sel:
                p.setPen(QPen(QColor(0, 0, 0, 160), 1))
                p.setBrush(qcolor("accent"))
                p.drawRoundedRect(QRectF(v.right() - 5, v.bottom() - 5, 10, 10), 2, 2)
                p.setBrush(QColor(255, 255, 255))
                p.drawRoundedRect(QRectF(v.right() - 4, v.center().y() - 4, 8, 8), 2, 2)
                p.drawRoundedRect(QRectF(v.center().x() - 4, v.bottom() - 4, 8, 8), 2, 2)
        # prilipimo linijos
        if self._drag is not None and self._drag[1] == "move":
            p.setPen(QPen(qcolor("accent"), 1, Qt.PenStyle.DashLine))
            for axis, line in getattr(self, "_guides", []):
                if axis == "x":
                    xx = ox + (line - scr.x()) * k
                    p.drawLine(QPointF(xx, view.top()), QPointF(xx, view.bottom()))
                else:
                    yy = oy + (line - scr.y()) * k
                    p.drawLine(QPointF(view.left(), yy), QPointF(view.right(), yy))
        del prev


class LayoutPage(QWidget):
    TITLE = "Layout"
    SUBTITLE = "Drag widgets to place them. Drag the corner or edges to resize. Double-click to configure."

    def __init__(self, center):
        super().__init__()
        self.setObjectName("Page")
        self.center = center
        self.ctx = center.ctx
        self.thumbs = {}
        root = QHBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(12)
        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.b_edit = button("Edit on screen", "primary", "move", "Show the real widgets with handles in iRacing")
        self.b_edit.clicked.connect(lambda: self.ctx.toggle_edit())
        bar.addWidget(self.b_edit)
        self.b_presets = button("Presets", None, "layout", "Ready layouts: Simple, Single monitor, Triple monitor")
        self.b_presets.clicked.connect(self._presets)
        bar.addWidget(self.b_presets)
        self.t_snap = Toggle(bool(self.ctx.config.data.get("snap", True)))
        self.t_snap.toggled.connect(self._snap)
        bar.addSpacing(8)
        bar.addWidget(self.t_snap)
        bar.addWidget(label("Snap", "muted"))
        bar.addSpacing(8)
        self.t_hidden = Toggle(False)
        self.t_hidden.toggled.connect(self._hidden)
        bar.addWidget(self.t_hidden)
        bar.addWidget(label("Show hidden widgets", "muted"))
        bar.addStretch(1)
        self.view_box = QHBoxLayout()
        self.view_box.setSpacing(6)
        bar.addLayout(self.view_box)
        left.addLayout(bar)
        self.canvas = LayoutCanvas(self)
        self.canvas.selected.connect(self._select)
        self.canvas.geometry_edited.connect(self._geo_edited)
        left.addWidget(self.canvas, 1)
        left.addWidget(label("Drag to move · corner and edges resize · double-click opens settings · "
                             "arrow keys nudge 1 px (Shift 10 px) · Delete hides", "faint"))
        root.addLayout(left, 1)
        # inspektorius
        side = QWidget()
        side.setFixedWidth(320)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(14)
        self.insp = Card("Selected widget")
        self.insp_body = QVBoxLayout()
        self.insp_body.setSpacing(10)
        self.insp.add(self.insp_body)
        sl.addWidget(self.insp)
        lst = Card("Widgets on screen")
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        inner = QWidget()
        self.list_lay = QVBoxLayout(inner)
        self.list_lay.setContentsMargins(0, 0, 4, 0)
        self.list_lay.setSpacing(2)
        sc.setWidget(inner)
        lst.add(sc)
        sl.addWidget(lst, 1)
        root.addWidget(side)
        self._fields = None
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh_thumbs)

    # ---- API centrui ----
    def _fill_views(self):
        from .components import Segmented, clear_layout as _clear
        _clear(self.view_box)
        screens = self.ctx.screens()
        if len(screens) < 2:
            self.canvas.view_index = None
            return
        opts = {"all": "All screens"}
        opts.update({str(i): f"Display {i + 1}" for i in range(len(screens))})
        cur = "all" if self.canvas.view_index is None else str(self.canvas.view_index)
        seg = Segmented(opts, cur if cur in opts else "all")
        seg.changed.connect(self._set_view)
        self.view_box.addWidget(label("View", "muted"))
        self.view_box.addWidget(seg)

    def _set_view(self, v):
        self.canvas.view_index = None if v == "all" else int(v)
        self.canvas.update()

    def on_show(self, select=None):
        self._fill_views()
        self.t_snap.set_silent(bool(self.ctx.config.data.get("snap", True)))
        self.editing_changed(self.ctx.editing)
        self.center.ensure_sizes()
        if select:
            self.canvas.sel = select
        self._select(self.canvas.sel or "")
        self.refresh_list()
        self._refresh_thumbs()
        self._timer.start()
        self.canvas.setFocus()

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)

    def tick(self, snap):
        pass

    def editing_changed(self, on):
        self.b_edit.setText("Done editing on screen" if on else "Edit on screen")

    def geometry_changed(self, name):
        self.thumbs.pop(name, None)
        self.canvas.update()
        if name == self.canvas.sel:
            self._update_fields()

    def _presets(self):
        from .dialogs import PresetDialog
        if PresetDialog(self.center).exec():
            self.center.ensure_sizes()
            self.thumbs.clear()
            self.refresh_list()
            self._refresh_thumbs()

    # ---- vidus ----
    def _snap(self, v):
        self.ctx.config.data["snap"] = bool(v)
        self.ctx.save_config_soon()

    def _hidden(self, v):
        self.canvas.show_hidden = bool(v)
        self.center.ensure_sizes(everything=bool(v))
        self._refresh_thumbs()
        self.canvas.update()

    def _refresh_thumbs(self):
        if not self.isVisible():
            return
        snap = self.center.preview.snapshot()
        for name, r, on in self.canvas.items():
            try:
                self.thumbs[name] = self.center.preview.render(name, snap)
            except Exception:  # noqa: BLE001
                import traceback
                self.center.log_error(traceback.format_exc())
        self.canvas.update()

    def refresh_list(self):
        clear_layout(self.list_lay)
        for spec in WIDGETS:
            on = bool(self.ctx.config.widget(spec.name).get("visible"))
            if not on:
                continue
            row = QHBoxLayout()
            row.setContentsMargins(4, 3, 4, 3)
            row.setSpacing(10)
            ic = QLabel()
            ic.setPixmap(icon_pixmap(spec.icon, T["accent"] if spec.name == self.canvas.sel else T["muted"], 16))
            row.addWidget(ic)
            b = button(spec.title, "ghost")
            b.setStyleSheet("text-align: left; padding: 4px 6px;")
            b.clicked.connect(lambda _=False, n=spec.name: self._select(n))
            row.addWidget(b, 1)
            t = Toggle(True)
            t.toggled.connect(lambda v, n=spec.name: self._toggle(n, v))
            row.addWidget(t)
            w = QWidget()
            w.setLayout(row)
            self.list_lay.addWidget(w)
        add = button("Add widgets", "ghost", "plus")
        add.clicked.connect(lambda: self.center.go("widgets"))
        self.list_lay.addWidget(add)
        self.list_lay.addStretch(1)

    def _toggle(self, name, v):
        self.ctx.set_widget_visible(name, v)
        QTimer.singleShot(200, self.refresh_list)
        self.canvas.update()

    def _select(self, name):
        name = name or None
        self.canvas.sel = name
        self.canvas.update()
        clear_layout(self.insp_body)
        self._fields = None
        if not name:
            self.insp_body.addWidget(label("Click a widget on the canvas to move it, resize it or change its size.", "muted", wrap=True))
            return
        spec = BY_NAME[name]
        w = self.ctx.widgets[name]
        self.insp_body.addWidget(label(spec.title, "h2"))
        fx, fy = NumberField(w.x(), width=120, suffix=" px"), NumberField(w.y(), width=120, suffix=" px")
        fw, fh = NumberField(w.width(), 40, 4000, width=120, suffix=" px"), NumberField(w.height(), 20, 3000,
                                                                                      width=120, suffix=" px")
        grid = QVBoxLayout()
        grid.setSpacing(8)
        for a, b in ((("X", fx), ("Y", fy)), (("Width", fw), ("Height", fh))):
            grid.addLayout(hbox(vbox(label(a[0], "faint"), a[1], spacing=3), vbox(label(b[0], "faint"), b[1],
                                                                               spacing=3), None))
        self.insp_body.addLayout(grid)
        fh.setEnabled(w.HEIGHT_MODE != "auto")
        if w.HEIGHT_MODE == "auto":
            fh.setToolTip("Height follows the content")
        sc = SliderField(float(w.cfg.get("scale", 1.0) or 1.0), 0.5, 3.0, 0.05, percent=True, width=280)
        self.insp_body.addWidget(label("Size", "faint"))
        self.insp_body.addWidget(sc)
        fx.valueChanged.connect(lambda v: self._set(name, "x", v))
        fy.valueChanged.connect(lambda v: self._set(name, "y", v))
        fw.valueChanged.connect(lambda v: self._set(name, "w", v))
        fh.valueChanged.connect(lambda v: self._set(name, "h", v))
        sc.changed.connect(lambda v: self._set(name, "scale", v))
        b1 = button("Settings", None, "sliders")
        b1.clicked.connect(lambda: self.center.open_widget(name))
        b2 = button("Center", "ghost", "align_center")
        b2.clicked.connect(lambda: self._center(name))
        b3 = button("", "danger", "eye_off", "Hide this widget")
        b3.setFixedWidth(36)
        b3.clicked.connect(lambda: (self._toggle(name, False), self._select("")))
        self.insp_body.addLayout(hbox(b1, b2, None, b3))
        self._fields = (name, fx, fy, fw, fh, sc)
        self.refresh_list()

    def _set(self, name, what, v):
        w = self.ctx.widgets[name]
        c = w.cfg
        s = float(c.get("scale", 1.0) or 1.0)
        c["x"], c["y"], c["pos_v"] = w.x(), w.y(), 2
        if what == "x":
            c["x"] = int(v)
        elif what == "y":
            c["y"] = int(v)
        elif what == "w":
            c["width"] = int(round(v / s))
        elif what == "h":
            c["height"] = int(round(v / s))
        elif what == "scale":
            c["scale"] = round(float(v), 2)
        self.ctx.widget_changed(name)
        self.canvas._commit(name)
        if what == "scale":
            QTimer.singleShot(0, self._update_fields)

    def _center(self, name):
        w = self.ctx.widgets[name]
        w.center_on_screen()
        self.canvas._commit(name)
        self._update_fields()

    def _geo_edited(self, name):
        if self._fields and self._fields[0] == name:
            self._update_fields()

    def _update_fields(self):
        if not self._fields:
            return
        name, fx, fy, fw, fh, sc = self._fields
        w = self.ctx.widgets[name]
        fx.set_silent(w.x())
        fy.set_silent(w.y())
        fw.set_silent(w.width())
        fh.set_silent(w.height())
        sc.set_value(float(w.cfg.get("scale", 1.0) or 1.0))


__all__ = ["LayoutPage", "SettingRow"]
