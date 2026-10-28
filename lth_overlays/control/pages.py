"""Control Center puslapiai."""
from __future__ import annotations

import os
import re
import sys

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QFileDialog, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QKeySequenceEdit,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QScrollArea, QVBoxLayout, QWidget)

from lth_timing import VERSION

from ..config import app_dir
from ..registry import BY_NAME, CATEGORIES, WIDGETS
from ..theme import FONT_CHOICES, THEMES, Fonts
from .components import (Badge, Card, ColorButton, Combo, FlowGrid, IconTile, KpiTile, LineChart, Pill,
                         Segmented, SettingRow, Toggle, button, clear_layout, divider, hbox, label, vbox)
from .forms import WidgetForm
from .style import T, icon, icon_pixmap, qcolor, ui_font

SESSION_NAMES = {"race": "Race", "qualify": "Qualifying", "practice": "Practice", "warmup": "Warmup"}


def open_folder(path: str):
    os.makedirs(path, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


class Page(QScrollArea):
    """Puslapis su slinktimi. Turinys - self.content (QVBoxLayout)."""

    TITLE = ""
    SUBTITLE = ""
    MAX_W = 1180

    def __init__(self, center):
        super().__init__()
        self.center = center
        self.ctx = center.ctx
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner.setObjectName("Page")
        outer = QHBoxLayout(inner)
        outer.setContentsMargins(32, 26, 32, 40)
        col = QWidget()
        col.setMaximumWidth(self.MAX_W)
        self.content = QVBoxLayout(col)
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(16)
        outer.addWidget(col, 1)
        self.setWidget(inner)

    def on_show(self):
        pass

    def tick(self, snap):
        pass


# ====================================================================== Overview
class OverviewPage(Page):
    TITLE = "Overview"
    SUBTITLE = "Everything at a glance"

    def __init__(self, center):
        super().__init__(center)
        # hero
        hero = Card(padding=22)
        top = QHBoxLayout()
        top.setSpacing(16)
        self.hero_icon = IconTile("power", 48, T["faint"])
        top.addWidget(self.hero_icon)
        col = QVBoxLayout()
        col.setSpacing(3)
        self.hero_title = label("Waiting for iRacing", "h1")
        self.hero_sub = label("Overlays appear automatically when you join a session.", "muted", wrap=True)
        col.addWidget(self.hero_title)
        col.addWidget(self.hero_sub)
        top.addLayout(col, 1)
        b_edit = button("Edit layout on screen", "primary", "move")
        b_edit.clicked.connect(lambda: self.ctx.toggle_edit())
        b_canvas = button("Layout editor", None, "layout")
        b_canvas.clicked.connect(lambda: center.go("layout"))
        top.addWidget(b_canvas, 0, Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(b_edit, 0, Qt.AlignmentFlag.AlignVCenter)
        hero.add(top)
        self.content.addWidget(hero)
        # KPI
        grid = QGridLayout()
        grid.setSpacing(14)
        self.k_widgets = KpiTile("Active widgets", "–", "of 26", "widgets")
        self.k_cpu = KpiTile("CPU", "–", "LTH Overlays process", "cpu")
        self.k_ram = KpiTile("Memory", "–", "working set", "activity")
        self.k_fps = KpiTile("iRacing FPS", "–", "from telemetry", "gauge")
        for i, k in enumerate((self.k_widgets, self.k_cpu, self.k_ram, self.k_fps)):
            grid.addWidget(k, 0, i)
        self.content.addLayout(grid)
        # aktyvūs valdikliai + patarimai
        row = QHBoxLayout()
        row.setSpacing(16)
        manage = button("Manage widgets", "ghost", "chevron_right")
        manage.clicked.connect(lambda: center.go("widgets"))
        self.active_card = Card("Active widgets", "Turn widgets on and off for the current profile.", manage)
        self.active_list = QVBoxLayout()
        self.active_list.setSpacing(2)
        self.active_card.add(self.active_list)
        row.addWidget(self.active_card, 3)
        tips = Card("Quick start")
        hk = self.ctx.config.data.get("hotkeys") or {}
        for n, (t, s) in enumerate((
                ("Pick your widgets", "Widgets page: switch on what you want to see."),
                ("Place them", f"Press {hk.get('edit', 'Ctrl+Shift+E')} in iRacing, drag widgets, drag edges "
                               "and corners to resize. Or use the Layout editor here."),
                ("Fine-tune", "In edit mode every widget has a Settings button. Click it to open its settings."),
                ("Hide everything", f"{hk.get('toggle_all', 'Ctrl+Shift+H')} hides all overlays, e.g. for a "
                                    "screenshot.")), 1):
            r = QHBoxLayout()
            r.setSpacing(12)
            num = QLabel(str(n))
            num.setFixedSize(24, 24)
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num.setStyleSheet(f"background: {T['surface3']}; border-radius: 12px; color: {T['accent']};"
                              f" font-weight: 600; font-size: 12px;")
            r.addWidget(num, 0, Qt.AlignmentFlag.AlignTop)
            r.addLayout(vbox(label(t, "h3"), label(s, "muted", wrap=True), spacing=2), 1)
            tips.add(r)
        row.addWidget(tips, 2)
        self.content.addLayout(row)
        self.content.addStretch(1)
        self._active_key = None

    def on_show(self):
        self._active_key = None
        self.tick(self.ctx.engine.latest)

    def _fill_active(self):
        on = [s for s in WIDGETS if self.ctx.config.widget(s.name).get("visible")]
        key = tuple(s.name for s in on)
        if key == self._active_key:
            return
        self._active_key = key
        clear_layout(self.active_list)
        if not on:
            self.active_list.addWidget(label("No widgets are on. Open Widgets to add some.", "muted"))
        for s in on:
            r = QHBoxLayout()
            r.setSpacing(12)
            ic = QLabel()
            ic.setPixmap(icon_pixmap(s.icon, T["muted"], 18))
            r.addWidget(ic)
            r.addWidget(label(s.title), 1)
            r.addWidget(label(s.category, "faint"))
            cfg = button("", "ghost", "sliders", "Settings")
            cfg.setFixedWidth(36)
            cfg.clicked.connect(lambda _=False, n=s.name: self.center.open_widget(n))
            r.addWidget(cfg)
            t = Toggle(True)
            t.toggled.connect(lambda v, n=s.name: (self.ctx.set_widget_visible(n, v),
                                                   QTimer.singleShot(250, self._fill_active)))
            r.addWidget(t)
            w = QWidget()
            w.setLayout(r)
            r.setContentsMargins(4, 4, 4, 4)
            self.active_list.addWidget(w)

    def tick(self, snap):
        self._fill_active()
        perf = self.ctx.perf
        n_on = sum(1 for s in WIDGETS if self.ctx.config.widget(s.name).get("visible"))
        self.k_widgets.set(str(n_on), f"of {len(WIDGETS)} in profile “{self.center.profile_name()}”")
        cpu, ram, fps = perf.get("cpu"), perf.get("ram"), perf.get("fps")
        self.k_cpu.set("–" if cpu is None else f"{cpu:.1f}%")
        self.k_ram.set("–" if ram is None else f"{ram:.0f} MB")
        self.k_fps.set("–" if not fps else f"{fps:.0f}")
        if snap.connected:
            self.hero_icon.name, self.hero_icon.color = "check", T["good"]
            self.hero_title.setText(f"{SESSION_NAMES.get(snap.session_type, 'Session')} · {snap.track_name or 'iRacing'}")
            classes = len(snap.classes) if snap.classes else 1
            self.hero_sub.setText(f"Connected to iRacing · {len(snap.cars)} cars · "
                                  f"{classes} class{'es' if classes != 1 else ''}"
                                  + (" · spectating" if snap.watching else ""))
        else:
            self.hero_icon.name, self.hero_icon.color = "power", T["faint"]
            self.hero_title.setText("Waiting for iRacing")
            self.hero_sub.setText("Overlays appear automatically when you join a session. "
                                  "LTH Overlays uses almost no CPU while it waits.")
        self.hero_icon.update()


# ====================================================================== Widgets (katalogas)
class Thumb(QWidget):
    """Valdiklio miniatiūra ant tamsios „trasos“ fono."""

    def __init__(self, height=110):
        super().__init__()
        self.pm = None
        self.setFixedHeight(height)

    def set_pixmap(self, pm):
        self.pm = pm
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        from PySide6.QtGui import QLinearGradient
        g = QLinearGradient(0, 0, 0, r.height())
        g.setColorAt(0, QColor(52, 60, 72))
        g.setColorAt(1, QColor(26, 28, 33))
        p.setPen(QPen(qcolor("border"), 1))
        p.setBrush(g)
        p.drawRoundedRect(r, 9, 9)
        if self.pm is None or self.pm.isNull():
            p.setPen(qcolor("faint"))
            p.setFont(ui_font(12))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "Preparing preview…")
            return
        dpr = self.pm.devicePixelRatio() or 1.0
        pw, ph = self.pm.width() / dpr, self.pm.height() / dpr
        k = min(1.0, (r.width() - 16) / max(pw, 1), (r.height() - 16) / max(ph, 1))
        w, h = pw * k, ph * k
        target = QRectF(r.center().x() - w / 2, r.center().y() - h / 2, w, h)
        p.drawPixmap(target, self.pm, QRectF(0, 0, self.pm.width(), self.pm.height()))


class WidgetCard(QFrame):
    clicked = Signal(str)

    def __init__(self, ctx, spec):
        super().__init__()
        self.ctx, self.spec = ctx, spec
        self.setObjectName("WCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._style(False)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)
        self.thumb = Thumb(104)
        lay.addWidget(self.thumb)
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(IconTile(spec.icon, 32))
        col = QVBoxLayout()
        col.setSpacing(1)
        col.addWidget(label(spec.title, "h3"))
        col.addWidget(label(spec.category, "faint"))
        head.addLayout(col, 1)
        self.toggle = Toggle(bool(ctx.config.widget(spec.name).get("visible")))
        self.toggle.toggled.connect(lambda v: ctx.set_widget_visible(spec.name, v))
        head.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(head)
        d = label(spec.description, "muted", wrap=True)
        d.setMinimumHeight(36)
        d.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(d, 1)

    def _style(self, hover):
        self.setStyleSheet(f"QFrame#WCard {{ background: {T['surface']}; border: 1px solid "
                           f"{T['border2'] if hover else T['border']}; border-radius: 12px; }}")

    def enterEvent(self, e):
        self._style(True)

    def leaveEvent(self, e):
        self._style(False)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit(self.spec.name)

    def sync(self):
        self.toggle.set_silent(bool(self.ctx.config.widget(self.spec.name).get("visible")))


class WidgetsPage(Page):
    TITLE = "Widgets"
    SUBTITLE = "Choose what you see on track. Click a widget to configure it."

    def __init__(self, center):
        super().__init__(center)
        bar = QHBoxLayout()
        bar.setSpacing(12)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search widgets…")
        self.search.addAction(icon("search", T["faint"], 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(280)
        self.search.textChanged.connect(self._filter)
        bar.addWidget(self.search)
        self.cat = Segmented({"all": "All", **{c.lower(): c for c in CATEGORIES}}, "all")
        self.cat.changed.connect(lambda _: self._filter())
        bar.addWidget(self.cat)
        bar.addStretch(1)
        self.show_mode = Segmented({"all": "All", "on": "On"}, "all")
        self.show_mode.changed.connect(lambda _: self._filter())
        bar.addWidget(self.show_mode)
        self.content.addLayout(bar)
        self.grid = FlowGrid(290, 14)
        self.cards = {}
        for spec in WIDGETS:
            c = WidgetCard(self.ctx, spec)
            c.clicked.connect(center.open_widget)
            self.cards[spec.name] = c
        self.grid.set_items(list(self.cards.values()))
        self.content.addWidget(self.grid)
        self.empty = label("No widgets match.", "muted")
        self.empty.hide()
        self.content.addWidget(self.empty)
        self.content.addStretch(1)
        self._thumb_queue = []
        self._timer = QTimer(self)
        self._timer.setInterval(15)
        self._timer.timeout.connect(self._next_thumb)

    def _filter(self, *_):
        q = self.search.text().strip().lower()
        cat = self.cat.value
        only_on = self.show_mode.value == "on"
        items = []
        for name, c in self.cards.items():
            s = c.spec
            ok = (cat == "all" or s.category.lower() == cat) and \
                 (not q or q in s.title.lower() or q in s.description.lower() or q in s.category.lower())
            if only_on and not self.ctx.config.widget(name).get("visible"):
                ok = False
            if ok:
                items.append(c)
        self.grid.set_items(items)
        self.empty.setVisible(not items)

    def on_show(self):
        for c in self.cards.values():
            c.sync()
        self._filter()
        self._thumb_queue = list(self.cards)
        self._timer.start()

    def _next_thumb(self):
        if not self._thumb_queue or not self.isVisible():
            self._timer.stop()
            return
        name = self._thumb_queue.pop(0)
        try:
            self.cards[name].thumb.set_pixmap(self.center.preview.render(name))
        except Exception:  # noqa: BLE001 - peržiūra neturi sugadinti viso lango
            import traceback
            self.center.log_error(traceback.format_exc())

    def tick(self, snap):
        for c in self.cards.values():
            c.sync()
        # peržiūros: kai demo duomenys paruošti, o su iRacing - kas 5 s
        import time
        pv = self.center.preview.snapshot()
        now = time.monotonic()
        if id(pv) != getattr(self, "_pv_id", None) and (not pv.connected or now - getattr(self, "_pv_t", 0) > 5):
            self._pv_id, self._pv_t = id(pv), now
            if not self._thumb_queue:
                self._thumb_queue = list(self.cards)
                self._timer.start()


# ====================================================================== Widget detail
class PreviewStage(QWidget):
    def __init__(self):
        super().__init__()
        self.pm = None
        self.setMinimumHeight(220)

    def set_pixmap(self, pm):
        self.pm = pm
        if pm is not None:
            dpr = pm.devicePixelRatio() or 1.0
            self.setMinimumHeight(int(min(560, max(220, pm.height() / dpr + 48))))
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        from PySide6.QtGui import QLinearGradient
        g = QLinearGradient(0, 0, 0, r.height())
        g.setColorAt(0.0, QColor(84, 104, 128))
        g.setColorAt(0.55, QColor(58, 64, 72))
        g.setColorAt(0.56, QColor(40, 42, 46))
        g.setColorAt(1.0, QColor(24, 24, 27))
        p.setPen(QPen(qcolor("border"), 1))
        p.setBrush(g)
        p.drawRoundedRect(r, 10, 10)
        if self.pm is None:
            return
        dpr = self.pm.devicePixelRatio() or 1.0
        pw, ph = self.pm.width() / dpr, self.pm.height() / dpr
        k = min(1.0, (r.width() - 32) / max(pw, 1), (r.height() - 32) / max(ph, 1))
        w, h = pw * k, ph * k
        p.drawPixmap(QRectF(r.center().x() - w / 2, r.center().y() - h / 2, w, h), self.pm,
                     QRectF(0, 0, self.pm.width(), self.pm.height()))


class WidgetDetailPage(Page):
    MAX_W = 1280

    def __init__(self, center, name):
        self.name = name
        self.spec = BY_NAME[name]
        super().__init__(center)
        self.TITLE = self.spec.title
        self.SUBTITLE = f"Widgets / {self.spec.category}"
        back = button("All widgets", "ghost", "chevron_left")
        back.clicked.connect(lambda: center.go("widgets"))
        self.content.addLayout(hbox(back, None))
        head = QHBoxLayout()
        head.setSpacing(16)
        head.addWidget(IconTile(self.spec.icon, 52, T["accent"]))
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(label(self.spec.title, "h1"))
        col.addWidget(label(self.spec.description, "muted", wrap=True))
        head.addLayout(col, 1)
        self.vis = Toggle(bool(self.cfg.get("visible")))
        self.vis.toggled.connect(lambda v: (self.ctx.set_widget_visible(name, v), self.form.refresh_geometry()))
        head.addLayout(vbox(label("Show", "faint"), self.vis, spacing=4))
        reset = button("Reset", "danger", "reset", "Restore this widget's default settings")
        reset.clicked.connect(self._reset)
        head.addWidget(reset, 0, Qt.AlignmentFlag.AlignVCenter)
        self.content.addLayout(head)
        self.body = QHBoxLayout()
        self.body.setSpacing(18)
        self.form = WidgetForm(self.ctx, name)
        self.body.addWidget(self.form, 3)
        right = QVBoxLayout()
        right.setSpacing(14)
        self.data_badge = Badge("Demo data", "info")
        pv = Card("Live preview", "Updates as you change settings.", self.data_badge)
        self.stage = PreviewStage()
        pv.add(self.stage)
        b_show = button("Edit on screen", None, "move", "Turn on edit mode and move this widget in iRacing")
        b_show.clicked.connect(self._edit_on_screen)
        b_layout = button("Layout editor", "ghost", "layout")
        b_layout.clicked.connect(lambda: center.go("layout", select=name))
        pv.add(hbox(b_show, b_layout, None))
        right.addWidget(pv)
        hint = Card("Tips")
        tips = ["Drag the widget on screen in edit mode. Corners scale it, edges change width or height.",
                "Ctrl + mouse wheel over a widget changes its size.",
                "In edit mode, the Settings button on the widget (or a right-click) jumps back here."]
        if self.ctx.widgets[name].HEIGHT_MODE == "rows":
            tips.insert(1, "Drag the bottom edge to show more or fewer rows. Double-click to go back to automatic.")
        for t in tips:
            hint.add(label("•  " + t, "muted", wrap=True))
        right.addWidget(hint)
        right.addStretch(1)
        self.body.addLayout(right, 2)
        self.content.addLayout(self.body)
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._refresh_preview)

    @property
    def cfg(self):
        return self.ctx.config.widget(self.name)

    def _edit_on_screen(self):
        if not self.cfg.get("visible"):
            self.ctx.set_widget_visible(self.name, True)
            self.vis.set_silent(True)
        if not self.ctx.editing:
            self.ctx.toggle_edit()

    def _reset(self):
        if QMessageBox.question(self, "Reset widget", f"Restore default settings for {self.spec.title}?") \
                != QMessageBox.StandardButton.Yes:
            return
        vis = self.cfg.get("visible")
        self.ctx.config.reset_widget(self.name)
        self.cfg["visible"] = vis
        self.ctx.widget_changed(self.name)
        self.center.rebuild_widget_page(self.name)

    def on_show(self):
        self.vis.set_silent(bool(self.cfg.get("visible")))
        self.form.refresh_geometry()
        self._refresh_preview()
        self._timer.start()

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)

    def _refresh_preview(self):
        if not self.isVisible():
            return
        snap = self.center.preview.snapshot()
        self.data_badge.setText("Live data" if snap.connected else "Demo data")
        try:
            self.stage.set_pixmap(self.center.preview.render(self.name, snap))
        except Exception:  # noqa: BLE001
            import traceback
            self.center.log_error(traceback.format_exc())
            self._timer.stop()

    def geometry_changed(self):
        self.form.refresh_geometry()


# ====================================================================== Profiles
class ProfilesPage(Page):
    TITLE = "Profiles"
    SUBTITLE = "Separate layouts for race, qualifying, practice or anything else"

    def __init__(self, center):
        super().__init__(center)
        auto = Toggle(bool(self.ctx.config.data.get("auto_profile", True)))
        auto.toggled.connect(self._auto)
        self.auto = auto
        c = Card("Switch automatically", "Race, Qualifying and Practice profiles follow the iRacing session type.")
        c.add(SettingRow("Automatic profile switching", auto,
                         "Choosing a profile by hand turns this off until you turn it on again."))
        self.content.addWidget(c)
        b_new = button("New profile", "primary", "plus")
        b_new.clicked.connect(self._new)
        b_imp = button("Import layout", None, "upload", "Paste a share code or open a .lthlayout file")
        b_imp.clicked.connect(self._import)
        self.list_card = Card("Your profiles", None, None)
        self.list_card.body.insertLayout(0, hbox(None, b_imp, b_new))
        self.rows = QVBoxLayout()
        self.rows.setSpacing(8)
        self.list_card.add(self.rows)
        self.content.addWidget(self.list_card)
        # temos lygoms / serijoms
        b_add = button("Add rule", None, "plus")
        b_add.clicked.connect(self._add_rule)
        self.rules_card = Card("Theme per series",
                               "Use a different look automatically for an iRacing series or a private league session.",
                               b_add)
        self.rules = QVBoxLayout()
        self.rules.setSpacing(8)
        self.rules_card.add(self.rules)
        self.content.addWidget(self.rules_card)
        self.content.addStretch(1)

    def on_show(self):
        self.auto.set_silent(bool(self.ctx.config.data.get("auto_profile", True)))
        self._fill()
        self._fill_rules()

    def _auto(self, v):
        self.ctx.config.data["auto_profile"] = bool(v)
        self.ctx.save_config_soon()

    def _fill(self):
        clear_layout(self.rows)
        cfg = self.ctx.config
        for key, p in cfg.data["profiles"].items():
            active = key == cfg.profile_key
            row = QFrame()
            row.setObjectName("PRow")
            row.setStyleSheet(f"QFrame#PRow {{ background: {T['surface2'] if active else T['bg']}; border: 1px solid "
                              f"{T['accent'] if active else T['border']}; border-radius: 10px; }}")
            lay = QHBoxLayout(row)
            lay.setContentsMargins(14, 10, 10, 10)
            lay.setSpacing(10)
            lay.addWidget(IconTile("layers", 34, T["accent"] if active else T["muted"]))
            n_on = sum(1 for w in p.get("widgets", {}).values() if w.get("visible"))
            auto_txt = {"race": " · used in races", "qualify": " · used in qualifying",
                        "practice": " · used in practice"}.get(key, "")
            lay.addLayout(vbox(label(p.get("name", key), "h3"), label(f"{n_on} widgets on{auto_txt}", "faint"),
                               spacing=1), 1)
            if active:
                lay.addWidget(Badge("Active", "accent"))
            else:
                b = button("Activate", None)
                b.clicked.connect(lambda _=False, k=key: self._activate(k))
                lay.addWidget(b)
            sh = button("Share", None, "upload", "Share code for Discord or a .lthlayout file")
            sh.clicked.connect(lambda _=False, k=key: self._export(k))
            lay.addWidget(sh)
            for ic, tip, fn in (("edit", "Rename", self._rename), ("copy", "Duplicate", self._dup)):
                b = button("", "ghost", ic, tip)
                b.setFixedWidth(36)
                b.clicked.connect(lambda _=False, k=key, f=fn: f(k))
                lay.addWidget(b)
            if key not in ("race", "qualify", "practice"):
                b = button("", "danger", "trash", "Delete")
                b.setFixedWidth(36)
                b.clicked.connect(lambda _=False, k=key: self._delete(k))
                lay.addWidget(b)
            self.rows.addWidget(row)

    def _unique_key(self, name):
        base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "profile"
        key, i = base, 2
        while key in self.ctx.config.data["profiles"]:
            key, i = f"{base}_{i}", i + 1
        return key

    def _activate(self, key):
        self.ctx.set_profile(key)
        self.auto.set_silent(bool(self.ctx.config.data.get("auto_profile")))
        self._fill()

    def _new(self):
        name, ok = QInputDialog.getText(self, "New profile", "Name (copies the current layout):")
        if ok and name.strip():
            self.ctx.config.add_profile(self._unique_key(name), name.strip())
            self.ctx.save_config()
            self._fill()

    def _rename(self, key):
        p = self.ctx.config.data["profiles"][key]
        name, ok = QInputDialog.getText(self, "Rename profile", "Name:", text=p.get("name", key))
        if ok and name.strip():
            p["name"] = name.strip()
            self.ctx.save_config()
            self._fill()
            self.center.profile_changed()

    def _dup(self, key):
        p = self.ctx.config.data["profiles"][key]
        name = f"{p.get('name', key)} copy"
        self.ctx.config.add_profile(self._unique_key(name), name, copy_from=key)
        self.ctx.save_config()
        self._fill()

    def _export(self, key):
        from .dialogs import ShareDialog
        ShareDialog(self.center, key).exec()

    def _import(self):
        from .dialogs import ImportDialog
        ImportDialog(self.center).exec()
        self._fill()

    def _delete(self, key):
        name = self.ctx.config.data["profiles"][key].get("name", key)
        if QMessageBox.question(self, "Delete profile", f"Delete “{name}”? This cannot be undone.") \
                != QMessageBox.StandardButton.Yes:
            return
        was_active = key == self.ctx.config.profile_key
        self.ctx.config.delete_profile(key)
        if was_active:
            self.ctx.set_profile(self.ctx.config.profile_key, manual=False)
        self.ctx.save_config()
        self._fill()
        self.center.profile_changed()

    # ---- temų taisyklės ----
    def _fill_rules(self):
        clear_layout(self.rules)
        st = self.ctx.config.data.setdefault("series_themes", {})
        if not st:
            self.rules.addWidget(label("No rules. The theme from Appearance is used everywhere.", "muted"))
        themes = {k: v["name"] for k, v in THEMES.items()}
        for rule, theme in list(st.items()):
            kind, _, ident = rule.partition(":")
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(label("League session" if kind == "league" else "Series", "muted"))
            row.addWidget(label(f"ID {ident}", "h3"))
            row.addStretch(1)
            row.addWidget(label("uses", "faint"))
            cb = Combo(themes, theme, 220)
            cb.changed.connect(lambda v, r=rule: self._set_rule(r, v))
            row.addWidget(cb)
            b = button("", "danger", "trash", "Remove")
            b.setFixedWidth(36)
            b.clicked.connect(lambda _=False, r=rule: self._del_rule(r))
            row.addWidget(b)
            self.rules.addLayout(row)

    def _add_rule(self):
        kinds = ["Series", "League session"]
        kind, ok = QInputDialog.getItem(self, "Theme rule", "Apply to:", kinds, 0, False)
        if not ok:
            return
        ident, ok = QInputDialog.getInt(self, "Theme rule", "iRacing series ID:" if kind == "Series" else "iRacing league ID:", 0, 1, 99999999)
        if not ok:
            return
        key = "league" if kind.startswith("League") else "series"
        self.ctx.config.data.setdefault("series_themes", {})[f"{key}:{ident}"] = self.ctx.config.data.get("theme", "lth")
        self.ctx.save_config()
        self._fill_rules()

    def _set_rule(self, rule, theme):
        self.ctx.config.data["series_themes"][rule] = theme
        self.ctx.save_config()

    def _del_rule(self, rule):
        self.ctx.config.data["series_themes"].pop(rule, None)
        self.ctx.save_config()
        self._fill_rules()


# ====================================================================== Appearance
class ThemeCard(QWidget):
    clicked = Signal(str)

    def __init__(self, key, selected=False):
        super().__init__()
        self.key = key
        self.selected = selected
        self.setFixedHeight(166)
        self.setMinimumWidth(180)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        self.clicked.emit(self.key)

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()

    def paintEvent(self, e):
        t = THEMES[self.key]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        border = qcolor("accent") if self.selected else (qcolor("border2") if self.underMouse() else qcolor("border"))
        p.setPen(QPen(border, 2 if self.selected else 1))
        p.setBrush(qcolor("surface"))
        p.drawRoundedRect(r, 12, 12)
        # mini scena
        from PySide6.QtGui import QLinearGradient
        stage = QRectF(r.x() + 10, r.y() + 10, r.width() - 20, 96)
        g = QLinearGradient(0, stage.top(), 0, stage.bottom())
        g.setColorAt(0, QColor(80, 98, 120))
        g.setColorAt(1, QColor(34, 36, 40))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(stage, 8, 8)
        box = stage.adjusted(14, 12, -14, -10)
        bg = QColor(*t["bg"], int(255 * t["bg_alpha"]))
        rad = float(t.get("radius", 6))
        p.setBrush(bg)
        p.drawRoundedRect(box, rad, rad)
        hh = 14
        style = t.get("header_style", "marker" if t.get("lumina") else "line")
        hc = QColor(*t["header"])
        if t.get("header_alpha") is not None:
            hc.setAlpha(int(255 * t["header_alpha"]))
        p.setBrush(hc)
        p.drawRoundedRect(QRectF(box.x(), box.y(), box.width(), hh), rad, rad)
        acc = QColor(*t["accent"])
        if style == "line":
            p.fillRect(QRectF(box.x(), box.y() + hh - 2, box.width(), 2), acc)
        elif style == "gold":
            gg = QLinearGradient(box.x(), 0, box.right(), 0)
            gg.setColorAt(0, QColor(251, 208, 105))
            gg.setColorAt(1, QColor(209, 160, 58))
            p.fillRect(QRectF(box.x(), box.y() + hh - 2, box.width(), 2), gg)
            p.fillRect(QRectF(box.x(), box.y() + 3, 2, hh - 6), gg)
        elif style == "marker":
            p.fillRect(QRectF(box.x(), box.y() + 3, 2, hh - 6), acc)
        p.setBrush(QColor(*t["text"]) if style != "line" and style != "gold" else acc)
        p.drawRoundedRect(QRectF(box.x() + 7, box.y() + hh * 0.38, box.width() * 0.22, hh * 0.24), 1, 1)
        rows = 4
        rh = (box.height() - hh - 4) / rows
        for i in range(rows):
            y = box.y() + hh + 2 + i * rh
            if i == 1:
                p.fillRect(QRectF(box.x(), y, box.width(), rh), QColor(*t["me_bg"]))
            elif i % 2:
                p.fillRect(QRectF(box.x(), y, box.width(), rh), QColor(*t["row_alt"]))
            p.setBrush(QColor(255, 88, 136) if i < 2 else QColor(92, 170, 255))
            p.drawRoundedRect(QRectF(box.x() + 5, y + rh * 0.25, 12, rh * 0.5), 2, 2)
            p.setBrush(QColor(*t["text"]))
            p.drawRoundedRect(QRectF(box.x() + 22, y + rh * 0.38, box.width() * 0.38, rh * 0.24), 1, 1)
            p.setBrush(QColor(*(t["good"] if i % 2 else t["dim"])))
            p.drawRoundedRect(QRectF(box.right() - 34, y + rh * 0.38, 26, rh * 0.24), 1, 1)
        p.setPen(qcolor("text"))
        p.setFont(ui_font(13, QFont.Weight.DemiBold))
        p.drawText(QRectF(r.x() + 14, stage.bottom() + 6, r.width() - 40, 22), Qt.AlignmentFlag.AlignVCenter,
                   t["name"])
        fk = t.get("font")
        if fk in FONT_CHOICES:
            p.setPen(qcolor("faint"))
            p.setFont(ui_font(11.5))
            p.drawText(QRectF(r.x() + 14, stage.bottom() + 26, r.width() - 40, 18), Qt.AlignmentFlag.AlignVCenter,
                       FONT_CHOICES[fk][0])
        if self.selected:
            p.drawPixmap(int(r.right() - 30), int(stage.bottom() + 13), icon_pixmap("check", T["accent"], 16))


class FontRow(QWidget):
    clicked = Signal(str)

    def __init__(self, key, selected=False):
        super().__init__()
        self.key = key
        self.selected = selected
        self.fonts = Fonts(1.25, key)
        self.setFixedHeight(48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        self.clicked.emit(self.key)

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(qcolor("accent") if self.selected else (qcolor("border2") if self.underMouse() else
                                                                 qcolor("border")), 1.5 if self.selected else 1))
        p.setBrush(qcolor("surface2") if self.selected else qcolor("bg"))
        p.drawRoundedRect(r, 10, 10)
        p.setPen(qcolor("muted"))
        p.setFont(ui_font(12.5, QFont.Weight.Medium))
        p.drawText(QRectF(16, 0, 240, r.height()), Qt.AlignmentFlag.AlignVCenter, FONT_CHOICES[self.key][1])
        p.setPen(qcolor("text"))
        p.setFont(self.fonts.base)
        p.drawText(QRectF(260, 0, r.width() - 300, r.height()), Qt.AlignmentFlag.AlignVCenter,
                   "P3   #7   P. ŽEMAITIS   1:32.418   +4.2")
        if self.selected:
            p.drawPixmap(int(r.right() - 30), int(r.center().y() - 8), icon_pixmap("check", T["accent"], 16))


COLOR_TOKENS = (("accent", "Accent", "Headers, highlights"), ("text", "Text", "Main text"),
                ("dim", "Secondary text", "Labels, hints"), ("good", "Gaining / faster", "Green numbers"),
                ("bad", "Losing / slower", "Red numbers"), ("purple", "Fastest lap", "Purple times"),
                ("yellow", "Warning", "Yellow flags, caution"), ("blue", "Info", "Blue flags, lapped cars"),
                ("bg", "Background", "Widget background"))


class AppearancePage(Page):
    TITLE = "Appearance"
    SUBTITLE = "Theme, font and colours for all widgets"

    def __init__(self, center):
        super().__init__(center)
        self.t_theme_font = Toggle(bool(self.ctx.config.data.get("theme_font", True)))
        self.t_theme_font.toggled.connect(lambda v: (self.ctx.config.data.__setitem__("theme_font", bool(v)),
                                                     self.ctx.save_config_soon()))
        tf = QWidget()
        tf.setLayout(hbox(label("Use the theme's font", "muted"), self.t_theme_font))
        self.theme_card = Card("Theme", "The base look of every widget: colours, corners, header and font.", tf)
        self.theme_grid = QGridLayout()
        self.theme_grid.setSpacing(12)
        self.theme_card.add(self.theme_grid)
        self.content.addWidget(self.theme_card)
        # kontūras (stroke) visiems valdikliams
        from .components import SliderField
        og = self.ctx.config.data.setdefault("outline", {"width": 1.0, "color": "accent", "opacity": 0.5})
        self.outline_card = Card("Outline", "A thin border around every widget. Single widgets can override it in "
                                            "their Look settings.")
        self.o_width = SliderField(float(og.get("width", 1.0)), 0.0, 6.0, 0.5, " px")
        self.o_width.changed.connect(lambda v: self._set_outline("width", float(v)))
        self.outline_card.add(SettingRow("Width", self.o_width, "0 = no outline"))
        col = og.get("color", "accent")
        self.o_mode = Segmented({"accent": "Theme accent", "text": "Theme text", "custom": "Custom"},
                                col if col in ("accent", "text") else "custom")
        self.o_mode.changed.connect(self._outline_mode)
        self.o_color = ColorButton(col if str(col).startswith("#") else "#ECBE58")
        self.o_color.changed.connect(lambda v: (self.o_mode.set_value("custom"), self._set_outline("color", v)))
        self.outline_card.add(SettingRow("Colour", self._wrap(hbox(self.o_mode, self.o_color))))
        self.o_opacity = SliderField(float(og.get("opacity", 0.5)), 0.1, 1.0, 0.05, percent=True)
        self.o_opacity.changed.connect(lambda v: self._set_outline("opacity", float(v)))
        self.outline_card.add(SettingRow("Opacity", self.o_opacity))
        self.content.addWidget(self.outline_card)
        self.font_card = Card("Font", "Bundled with the app, nothing is installed on Windows.")
        self.font_rows = QVBoxLayout()
        self.font_rows.setSpacing(8)
        self.font_card.add(self.font_rows)
        self.content.addWidget(self.font_card)
        reset = button("Reset colours", "ghost", "reset")
        reset.clicked.connect(self._reset_colors)
        self.color_card = Card("Colours", "Override single colours of the theme.", reset)
        self.color_grid = QGridLayout()
        self.color_grid.setHorizontalSpacing(24)
        self.color_grid.setVerticalSpacing(10)
        self.color_card.add(self.color_grid)
        self.content.addWidget(self.color_card)
        add = button("Add class", None, "plus")
        add.clicked.connect(self._add_class)
        self.class_card = Card("Class colours", "Colour of each car class in Standings, Relative and the track "
                                                "map. Classes of the current session are listed automatically.", add)
        self.class_rows = QVBoxLayout()
        self.class_rows.setSpacing(8)
        self.class_card.add(self.class_rows)
        self.content.addWidget(self.class_card)
        self.content.addStretch(1)

    def on_show(self):
        self._fill_themes()
        self._fill_fonts()
        self._fill_colors()
        self._fill_classes()

    @staticmethod
    def _wrap(layout):
        w = QWidget()
        w.setLayout(layout)
        return w

    def _set_outline(self, key, value):
        self.ctx.config.data.setdefault("outline", {})[key] = value
        for w in self.ctx.widgets.values():
            w.update()
        self.ctx.save_config_soon()
        self.center.preview.invalidate()

    def _outline_mode(self, v):
        self._set_outline("color", self.o_color.value if v == "custom" else v)

    def _fill_themes(self):
        clear_layout(self.theme_grid)
        cur = self.ctx.config.data.get("theme", "lth")
        for i, key in enumerate(THEMES):
            c = ThemeCard(key, key == cur)
            c.clicked.connect(self._set_theme)
            self.theme_grid.addWidget(c, i // 5, i % 5)

    def _set_theme(self, key):
        self.ctx.config.data["theme"] = key
        fk = THEMES[key].get("font")
        if self.ctx.config.data.get("theme_font", True) and fk:
            self.ctx.config.data["font"] = fk
            self._fill_fonts()
        self.ctx.all_widgets_changed()
        self.center.preview.invalidate()
        self._fill_themes()
        self._fill_colors()

    def _fill_fonts(self):
        clear_layout(self.font_rows)
        cur = self.ctx.config.data.get("font", "montserrat")
        from ..theme import FONT_GROUPS
        for group in FONT_GROUPS:
            keys = [k for k, v in FONT_CHOICES.items() if v[2] == group]
            if not keys:
                continue
            e = label(group.upper(), "eyebrow")
            e.setContentsMargins(2, 8, 0, 0)
            self.font_rows.addWidget(e)
            for key in keys:
                r = FontRow(key, key == cur)
                r.clicked.connect(self._set_font)
                self.font_rows.addWidget(r)

    def _set_font(self, key):
        self.ctx.config.data["font"] = key
        self.ctx.all_widgets_changed()
        self.center.preview.invalidate()
        self._fill_fonts()

    def _theme_default(self, token):
        t = THEMES.get(self.ctx.config.data.get("theme", "racelab"), THEMES["lth"])
        v = t.get(token, (255, 255, 255))
        return QColor(v[0], v[1], v[2]).name()

    def _fill_colors(self):
        clear_layout(self.color_grid)
        cc = self.ctx.config.data.setdefault("custom_colors", {})
        for i, (tok, title, sub) in enumerate(COLOR_TOKENS):
            r, c = divmod(i, 2)
            cell = QHBoxLayout()
            cell.setSpacing(10)
            cell.addLayout(vbox(label(title), label(sub, "faint"), spacing=1), 1)
            btn = ColorButton(cc.get(tok) or self._theme_default(tok))
            btn.changed.connect(lambda v, t=tok: self._set_color(t, v))
            cell.addWidget(btn)
            if tok in cc:
                x = button("", "ghost", "reset", "Back to theme colour")
                x.setFixedWidth(34)
                x.clicked.connect(lambda _=False, t=tok: self._set_color(t, None))
                cell.addWidget(x)
            else:
                sp = QWidget()
                sp.setFixedWidth(34)
                cell.addWidget(sp)
            self.color_grid.addLayout(cell, r, c)

    def _set_color(self, token, value):
        cc = self.ctx.config.data.setdefault("custom_colors", {})
        if value is None:
            cc.pop(token, None)
        else:
            cc[token] = value
        self.ctx.all_widgets_changed()
        self.center.preview.invalidate()
        self._fill_colors()

    def _reset_colors(self):
        self.ctx.config.data["custom_colors"] = {}
        self.ctx.all_widgets_changed()
        self.center.preview.invalidate()
        self._fill_colors()

    def _fill_classes(self):
        clear_layout(self.class_rows)
        cc = self.ctx.config.data.setdefault("class_colors", {})
        snap = self.ctx.engine.latest
        names = {}
        for c in (snap.classes or {}).values():
            names[c.get("name") or "?"] = "#%06x" % (int(c.get("color") or 0) & 0xFFFFFF)
        for n in cc:
            names.setdefault(n, cc[n])
        if not names:
            self.class_rows.addWidget(label("Join a multiclass session to see its classes here, or add one by name.",
                                            "muted"))
        for n, default in sorted(names.items()):
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(label(n, "h3"), 1)
            if n in cc:
                row.addWidget(Badge("Custom", "accent"))
            btn = ColorButton(cc.get(n, default))
            btn.changed.connect(lambda v, k=n: self._set_class(k, v))
            row.addWidget(btn)
            x = button("", "ghost", "reset", "Use the iRacing colour")
            x.setFixedWidth(34)
            x.setEnabled(n in cc)
            x.clicked.connect(lambda _=False, k=n: self._set_class(k, None))
            row.addWidget(x)
            self.class_rows.addLayout(row)

    def _set_class(self, name, value):
        cc = self.ctx.config.data.setdefault("class_colors", {})
        if value is None:
            cc.pop(name, None)
        else:
            cc[name] = value
        self.ctx.save_config_soon()
        self.center.preview.invalidate()
        self._fill_classes()

    def _add_class(self):
        name, ok = QInputDialog.getText(self, "Class colour", "Class name exactly as iRacing shows it (e.g. GT3):")
        if ok and name.strip():
            self._set_class(name.strip(), "#ff5888")


# ====================================================================== Hotkeys
class HotkeysPage(Page):
    TITLE = "Hotkeys"
    SUBTITLE = "Work from inside iRacing without alt-tabbing"
    ACTIONS = (("edit", "Edit layout", "Turn edit mode on or off: drag, resize and right-click widgets."),
               ("toggle_all", "Hide all overlays", "Hide or show every widget at once."),
               ("rain_next", "Rain Master: next tip", "Show the next rain tip for the current conditions. "
                                                      "Put it on a button box key."),
               ("next_profile", "Next profile", "Switch to the next profile (Race, Qualifying, Practice...). "
                                                "Turns automatic profile switching off."))

    def __init__(self, center):
        super().__init__(center)
        c = Card("Keyboard", "Use a combination with Ctrl, Alt or Shift. Click a field and press the keys.")
        self.edits, self.states = {}, {}
        for key, title, sub in self.ACTIONS:
            e = QKeySequenceEdit()
            try:
                e.setMaximumSequenceLength(1)
            except AttributeError:
                pass
            e.setFixedWidth(200)
            e.setKeySequence(QKeySequence(self.ctx.config.data.get("hotkeys", {}).get(key, "")))
            e.editingFinished.connect(lambda k=key: self._changed(k))
            st = Badge("", "muted")
            self.edits[key], self.states[key] = e, st
            row = QHBoxLayout()
            row.setSpacing(12)
            row.addLayout(vbox(label(title, "h3"), label(sub, "faint", wrap=True), spacing=2), 1)
            row.addWidget(st)
            row.addWidget(e)
            c.add(row)
        self.content.addWidget(c)
        wc = Card("Show / hide a widget", "Optional. One key per widget, handy on a button box.")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        for i, spec in enumerate(WIDGETS):
            key = f"widget:{spec.name}"
            e = QKeySequenceEdit()
            try:
                e.setMaximumSequenceLength(1)
            except AttributeError:
                pass
            e.setFixedWidth(170)
            e.setKeySequence(QKeySequence(self.ctx.config.data.get("hotkeys", {}).get(key, "")))
            e.editingFinished.connect(lambda k=key: self._changed(k))
            clr = button("", "ghost", "x", "Remove")
            clr.clicked.connect(lambda _=False, k=key, ed=e: (ed.clear(), self._changed(k)))
            st = Badge("", "muted")
            self.edits[key], self.states[key] = e, st
            r, col = divmod(i, 2)
            cell = QHBoxLayout()
            cell.setSpacing(6)
            cell.addWidget(label(spec.title), 1)
            cell.addWidget(st)
            cell.addWidget(e)
            cell.addWidget(clr)
            grid.addLayout(cell, r, col)
        wc.add(grid)
        self.content.addWidget(wc)
        m = Card("Mouse in edit mode")
        for a, b in (("Drag", "Move a widget. It snaps to screen edges and other widgets."),
                     ("Drag a corner", "Scale the whole widget (text and all)."),
                     ("Drag left / right edge", "Change the width."),
                     ("Drag top / bottom edge", "Change the height: more or fewer rows in tables."),
                     ("Double-click", "Height back to automatic."),
                     ("Ctrl + wheel", "Scale in 5% steps."),
                     ("Settings button / right-click", "Open the widget's settings here.")):
            m.add(hbox(label(a, "h3"), None, label(b, "muted")))
        self.content.addWidget(m)
        self.content.addStretch(1)

    def on_show(self):
        self._states(getattr(self.ctx, "_hotkeys", {}))

    def _states(self, res):
        for key, st in self.states.items():
            if not self.edits[key].keySequence().toString():
                st.setText("")
                st.setStyleSheet("")
                continue
            if key not in res:
                st.setText("Windows only")
                continue
            ok = res.get(key)
            st.setText("Active" if ok else "Not available")
            c = qcolor("good" if ok else "bad")
            st.setStyleSheet(f"QLabel {{ background: rgba({c.red()},{c.green()},{c.blue()},0.13); color: {c.name()};"
                             f" border-radius: 6px; padding: 2px 8px; font-size: 11px; font-weight: 600; }}")
            st.setToolTip("" if ok else "Another program already uses this combination. Pick a different one.")

    def _changed(self, key):
        seq = self.edits[key].keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        seq = seq.split(",")[0].strip()
        hk = self.ctx.config.data.setdefault("hotkeys", {})
        if seq == hk.get(key):
            return
        hk[key] = seq
        if key == "edit":
            self.ctx.config.data["hotkey"] = seq
        self.ctx.save_config()
        res = self.ctx.register_hotkeys() if hasattr(self.ctx, "_filter") else {}
        self._states(res)


# ====================================================================== General
class GeneralPage(Page):
    TITLE = "General"
    SUBTITLE = "Startup, timing engine and track maps"

    def __init__(self, center):
        super().__init__(center)
        d = self.ctx.config.data
        s = Card("Startup")
        self.t_auto = Toggle(self.ctx.autostart_enabled())
        self.t_auto.toggled.connect(self._autostart)
        s.add(SettingRow("Start with Windows", self.t_auto,
                         "Starts quietly in the tray and waits for iRacing. Uses the standard Windows startup list."))
        t_cc = Toggle(bool(d.get("open_control_center", True)))
        t_cc.toggled.connect(lambda v: self._set("open_control_center", bool(v)))
        s.add(SettingRow("Open Control Center when started by hand", t_cc,
                         "When Windows starts the app it always stays in the tray."))
        self.content.addWidget(s)

        e = Card("Timing engine")
        seg = Segmented({"10": "10 Hz", "20": "20 Hz", "30": "30 Hz"}, str(int(d.get("engine_hz", 20))))
        seg.changed.connect(lambda v: self._set("engine_hz", int(v)))
        e.add(SettingRow("Update rate", seg, "20 Hz is plenty for gaps. Higher costs more CPU. Applies after restart."))
        t_snap = Toggle(bool(d.get("snap", True)))
        t_snap.toggled.connect(lambda v: self._set("snap", bool(v)))
        e.add(SettingRow("Snap widgets while dragging", t_snap, "To screen edges, other widgets and an 8 px grid."))
        self.content.addWidget(e)

        tm = Card("Track maps", "Recorded from your first clean lap on each track and saved for next time.")
        b1 = button("Re-record current track", None, "record")
        b1.clicked.connect(self._forget_map)
        b2 = button("Open maps folder", "ghost", "folder")
        b2.clicked.connect(lambda: open_folder(os.path.join(app_dir(), "maps")))
        self.map_state = label("", "faint")
        tm.add(hbox(b1, b2, None, self.map_state))
        self.content.addWidget(tm)

        dz = Card("Data")
        b3 = button("Open settings folder", "ghost", "folder")
        b3.clicked.connect(lambda: open_folder(app_dir()))
        b4 = button("Reset all settings", "danger", "reset")
        b4.clicked.connect(self._reset_all)
        dz.add(hbox(b3, None, b4))
        self.content.addWidget(dz)
        self.content.addStretch(1)

    def on_show(self):
        self.t_auto.set_silent(self.ctx.autostart_enabled())

    def _set(self, k, v):
        self.ctx.config.data[k] = v
        self.ctx.save_config_soon()

    def _autostart(self, on):
        ok = self.ctx.set_autostart(on)
        if not ok:
            self.t_auto.set_silent(self.ctx.autostart_enabled())
            if sys.platform == "win32":
                QMessageBox.warning(self, "Start with Windows", "Could not change the Windows startup setting.")

    def _forget_map(self):
        self.ctx.engine.forget_map = True
        self.map_state.setText("Drive a clean lap to record it again.")

    def _reset_all(self):
        if QMessageBox.question(self, "Reset all settings", "Reset every widget, profile and setting to defaults?") \
                != QMessageBox.StandardButton.Yes:
            return
        import copy
        from ..config import DEFAULT_CONFIG
        keep = {k: self.ctx.config.data.get(k) for k in ("autostart", "autostart_done")}
        self.ctx.config.data = copy.deepcopy(DEFAULT_CONFIG)
        self.ctx.config.data.update(keep)
        self.ctx.all_widgets_changed()
        self.ctx.save_config()
        self.center.profile_changed()


# ====================================================================== Performance
class PerformancePage(Page):
    TITLE = "Performance"
    SUBTITLE = "What LTH Overlays costs your PC"

    def __init__(self, center):
        super().__init__(center)
        grid = QGridLayout()
        grid.setSpacing(14)
        self.k_cpu = KpiTile("CPU", "–", "of one core", "cpu")
        self.k_ram = KpiTile("Memory", "–", "working set", "activity")
        self.k_fps = KpiTile("iRacing FPS", "–", "", "gauge")
        self.k_eng = KpiTile("Engine update", "–", "per frame", "timer")
        for i, k in enumerate((self.k_cpu, self.k_ram, self.k_fps, self.k_eng)):
            grid.addWidget(k, 0, i)
        self.content.addLayout(grid)
        row = QHBoxLayout()
        row.setSpacing(16)
        c1 = Card("CPU %", "Last 2 minutes")
        self.ch_cpu = LineChart("accent")
        c1.add(self.ch_cpu)
        c2 = Card("iRacing FPS", "Last 2 minutes")
        self.ch_fps = LineChart("info")
        c2.add(self.ch_fps)
        row.addWidget(c1)
        row.addWidget(c2)
        self.content.addLayout(row)
        tips = Card("How it stays light")
        for t in ("Widgets are redrawn only when a number they show actually changes.",
                  "Each widget has its own refresh rate: Relative 10× per second, Standings 2×, Weather once.",
                  "Text layouts are cached, so a redraw is mostly copying pixels.",
                  "The timing engine runs at below-normal priority and sleeps while iRacing is not running.",
                  "Inputs (and Dash or Delta bar with Smooth on) draw straight from telemetry at up to 60 fps. "
                  "They cost a little more: turn Smooth off or use 30 fps on slower PCs."):
            tips.add(label("•  " + t, "muted", wrap=True))
        self.content.addWidget(tips)
        self.content.addStretch(1)

    def on_show(self):
        self.tick(self.ctx.engine.latest)

    def tick(self, snap):
        p = self.ctx.perf
        cpu, ram, fps, us = p.get("cpu"), p.get("ram"), p.get("fps"), p.get("engine_us")
        self.k_cpu.set("–" if cpu is None else f"{cpu:.1f}%")
        self.k_ram.set("–" if ram is None else f"{ram:.0f} MB")
        self.k_fps.set("–" if not fps else f"{fps:.0f}", "" if fps else "iRacing not running")
        self.k_eng.set("–" if not us else f"{us:.0f} µs")
        h = self.ctx.perf_hist
        self.ch_cpu.set_values([x[0] for x in h])
        self.ch_fps.set_values([x[2] for x in h])


# ====================================================================== Diagnostics
class DiagnosticsPage(Page):
    TITLE = "Diagnostics"
    SUBTITLE = "Help us fix problems"

    def __init__(self, center):
        super().__init__(center)
        r = Card("Record a session", "If gaps look wrong or a widget misbehaves, record a few minutes with LTH "
                                     "Diagnostics and send the file in Discord.")
        b = button("Open LTH Diagnostics", "primary", "record")
        b.clicked.connect(self._diag)
        self.diag_state = label("", "faint")
        r.add(hbox(b, self.diag_state, None))
        self.content.addWidget(r)
        pv = Card("Preview image", "A picture of all your widgets with demo data. Handy for sharing a layout.")
        b2 = button("Save preview image", None, "image")
        b2.clicked.connect(self._preview)
        self.pv_state = label("", "faint")
        pv.add(hbox(b2, self.pv_state, None))
        self.content.addWidget(pv)
        refresh = button("Refresh", "ghost", "reset")
        refresh.clicked.connect(self._load_logs)
        folder = button("Open folder", "ghost", "folder")
        folder.clicked.connect(lambda: open_folder(app_dir()))
        lg = Card("Logs", "engine.log, ui.log and visibility.log in your settings folder.", hbox(refresh, folder))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(320)
        lg.add(self.log)
        self.content.addWidget(lg)
        self.content.addStretch(1)

    def on_show(self):
        self._load_logs()

    def _load_logs(self):
        out = []
        for name in ("engine.log", "ui.log"):
            path = os.path.join(app_dir(), name)
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    lines = fh.readlines()[-60:]
                out.append(f"── {name} ──\n" + "".join(lines))
            except OSError:
                out.append(f"── {name} ── (empty)\n")
        self.log.setPlainText("\n".join(out))
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def _diag(self):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        exe = os.path.join(root, "LTH Diagnostics.exe")
        if os.path.exists(exe):
            from PySide6.QtCore import QProcess
            QProcess.startDetached(exe, [], root)
            self.diag_state.setText("Started. Follow the window that opened.")
        else:
            self.diag_state.setText("LTH Diagnostics.exe is next to LTH Overlays.exe in the app folder.")

    def _preview(self):
        from ..app import render_screenshot
        path = os.path.join(app_dir(), "preview.png")
        try:
            render_screenshot(self.ctx, path, sim_seconds=200)
            self.pv_state.setText("Saved: preview.png in the settings folder")
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception as e:  # noqa: BLE001
            self.pv_state.setText(f"Failed: {e}")


# ====================================================================== About
class AboutPage(Page):
    TITLE = "About"
    SUBTITLE = ""

    def __init__(self, center):
        super().__init__(center)
        c = Card(padding=24)
        top = QHBoxLayout()
        top.setSpacing(16)
        logo = QLabel()
        from ..brand import logo_pixmap
        logo.setPixmap(logo_pixmap(48))
        top.addWidget(logo)
        top.addSpacing(8)
        top.addLayout(vbox(label("LTH Overlays", "h1"), label(f"Version {VERSION}", "muted"), spacing=2), 1)
        c.add(top)
        c.add(label("In-house iRacing overlays for the LTH community. Accurate gaps that do not jump, "
                    "multiclass done right, and nothing you do not need running in the background.", "muted",
                    wrap=True))
        tut = button("Show tutorial", None, "play")
        tut.clicked.connect(center.show_onboarding)
        c.add(hbox(tut, None))
        self.content.addWidget(c)
        lic = Card("Built with")
        for a, b in (("Python 3.13", "PSF License"), ("Qt 6 / PySide6", "LGPL v3"), ("NumPy", "BSD"),
                     ("PyYAML", "MIT"), ("Inter and all bundled overlay fonts (Geist, Manrope, Montserrat, Saira, Barlow, "
                                         "Sofia Sans, Oswald, Exo 2, Oxanium and more)", "SIL Open Font License"),
                     ("Country flags: flag-icons by Lipis", "MIT"),
                     ("FlairID to country table based on irDashies", "MIT")):
            lic.add(hbox(label(a), None, label(b, "faint")))
        self.content.addWidget(lic)
        self.content.addWidget(label("Not affiliated with iRacing.com Motorsport Simulations. iRacing data is read "
                                     "from the official telemetry interface on your own PC.", "faint", wrap=True))
        self.content.addStretch(1)


__all__ = ["OverviewPage", "WidgetsPage", "WidgetDetailPage", "ProfilesPage", "AppearancePage", "HotkeysPage",
           "GeneralPage", "PerformancePage", "DiagnosticsPage", "AboutPage", "divider", "QSize", "QPixmap"]
