"""LTH Overlays Control Center - pagrindinis programos langas.

Šoninė juosta (puslapiai), viršutinė juosta (pavadinimas, iRacing būsena,
redagavimo mygtukas) ir puslapiai QStackedWidget'e. Uždarius langą programa
lieka veikti tray'uje.
"""
from __future__ import annotations

import os
import time

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QStackedWidget,
                               QSystemTrayIcon, QVBoxLayout, QWidget)

from lth_timing import VERSION

from ..config import app_dir
from ..registry import WIDGETS
from .components import Combo, IconTile, NavButton, Pill, button, label
from .layout_page import LayoutPage
from .pages import (AboutPage, AppearancePage, DiagnosticsPage, GeneralPage, HotkeysPage, OverviewPage,
                    PerformancePage, ProfilesPage, WidgetDetailPage, WidgetsPage)
from .preview import PreviewRenderer
from .style import T, qss, ui_font

NAV = (
    (None, (("overview", "Overview", "home"), ("widgets", "Widgets", "widgets"), ("layout", "Layout", "layout"))),
    ("CUSTOMIZE", (("profiles", "Profiles", "layers"), ("appearance", "Appearance", "palette"),
                   ("hotkeys", "Hotkeys", "keyboard"))),
    ("SYSTEM", (("general", "General", "settings"), ("performance", "Performance", "activity"),
                ("diagnostics", "Diagnostics", "bug"), ("about", "About", "info"))),
)
PAGES = {"overview": OverviewPage, "widgets": WidgetsPage, "layout": LayoutPage, "profiles": ProfilesPage,
         "appearance": AppearancePage, "hotkeys": HotkeysPage, "general": GeneralPage,
         "performance": PerformancePage, "diagnostics": DiagnosticsPage, "about": AboutPage}


class ControlCenter(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.preview = PreviewRenderer(ctx)
        self.setWindowTitle("LTH Overlays")
        from ..app import make_icon
        self.setWindowIcon(make_icon())
        self.setStyleSheet(qss())
        self.setMinimumSize(1080, 700)
        self.resize(1320, 860)
        self._pages = {}
        self._widget_pages = {}
        self._current = None
        self._told_tray = False

        root = QWidget()
        root.setObjectName("Root")
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._sidebar())
        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        main.addWidget(self._topbar())
        self.stack = QStackedWidget()
        main.addWidget(self.stack, 1)
        h.addLayout(main, 1)
        self.setCentralWidget(root)

    # ------------------------------------------------------------------ rėmas
    def _sidebar(self):
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(232)
        v = QVBoxLayout(side)
        v.setContentsMargins(14, 18, 14, 14)
        v.setSpacing(2)
        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        from ..app import make_icon
        logo.setPixmap(make_icon().pixmap(32, 32))
        brand.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(0)
        t = label("LTH Overlays")
        t.setFont(ui_font(15, QFont.Weight.DemiBold))
        col.addWidget(t)
        col.addWidget(label(f"v{VERSION}", "faint"))
        brand.addLayout(col, 1)
        v.addLayout(brand)
        v.addSpacing(18)
        self._nav = {}
        for section, items in NAV:
            if section:
                v.addSpacing(14)
                e = label(section, "eyebrow")
                e.setContentsMargins(12, 0, 0, 4)
                v.addWidget(e)
            for key, text, ic in items:
                b = NavButton(text, ic)
                b.clicked.connect(lambda _=False, k=key: self.go(k))
                v.addWidget(b)
                self._nav[key] = b
        v.addStretch(1)
        v.addWidget(label("PROFILE", "eyebrow"))
        v.addSpacing(4)
        self.profile_combo = Combo({}, None, 200)
        self.profile_combo.changed.connect(self._profile_selected)
        v.addWidget(self.profile_combo)
        self._fill_profiles()
        v.addSpacing(10)
        q = button("Quit LTH Overlays", "ghost", "power")
        q.clicked.connect(QApplication.instance().quit)
        v.addWidget(q)
        return side

    def _topbar(self):
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(68)
        h = QHBoxLayout(bar)
        h.setContentsMargins(32, 10, 24, 10)
        h.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.title = label("", "h2")
        self.title.setFont(ui_font(17, QFont.Weight.DemiBold))
        self.subtitle = label("", "faint")
        col.addWidget(self.title)
        col.addWidget(self.subtitle)
        h.addLayout(col, 1)
        self.status = Pill("Waiting for iRacing", "faint")
        h.addWidget(self.status)
        self.b_edit = button("Edit layout", None, "move", "Move and resize the widgets on screen")
        self.b_edit.setCheckable(True)
        self.b_edit.clicked.connect(lambda: self.ctx.toggle_edit())
        h.addWidget(self.b_edit)
        return bar

    # ------------------------------------------------------------------ navigacija
    def _page(self, key):
        p = self._pages.get(key)
        if p is None:
            p = PAGES[key](self)
            self._pages[key] = p
            self.stack.addWidget(p)
        return p

    def go(self, key, select=None):
        page = self._page(key)
        self._show(page, key)
        if key == "layout":
            page.on_show(select)
        else:
            page.on_show()

    def open_widget(self, name):
        page = self._widget_pages.get(name)
        if page is None:
            page = WidgetDetailPage(self, name)
            self._widget_pages[name] = page
            self.stack.addWidget(page)
        self._show(page, "widgets")
        page.on_show()

    def rebuild_widget_page(self, name):
        old = self._widget_pages.pop(name, None)
        if old is not None:
            self.stack.removeWidget(old)
            old.deleteLater()
        self.open_widget(name)

    def _show(self, page, nav_key):
        self.stack.setCurrentWidget(page)
        self._current = page
        for k, b in self._nav.items():
            b.setChecked(k == nav_key)
        self.title.setText(page.TITLE)
        self.subtitle.setText(page.SUBTITLE)
        self.subtitle.setVisible(bool(page.SUBTITLE))

    def open(self, page=None, widget=None):
        if widget:
            self.open_widget(widget)
        elif page:
            self.go(page)
        elif self._current is None:
            self.go("overview")
        self.showNormal() if self.isMinimized() else self.show()
        self.raise_()
        self.activateWindow()
        self.tick(self.ctx.engine.latest)

    # ------------------------------------------------------------------ iš programos
    def tick(self, snap):
        if snap.connected:
            self.status.set(f"iRacing · {snap.track_name}" if snap.track_name else "Connected to iRacing", "good")
        else:
            self.status.set("Waiting for iRacing", "faint")
        self.b_edit.setChecked(self.ctx.editing)
        if self._current is not None:
            try:
                self._current.tick(snap)
            except Exception:  # noqa: BLE001
                import traceback
                self.log_error(traceback.format_exc())

    def geometry_changed(self, name):
        self.preview.invalidate(name)
        page = self._widget_pages.get(name)
        if page is not None and page.isVisible():
            page.geometry_changed()
        lp = self._pages.get("layout")
        if lp is not None and lp.isVisible():
            lp.geometry_changed(name)

    def editing_changed(self, on):
        self.b_edit.setChecked(on)
        self.b_edit.setText("Done editing" if on else "Edit layout")
        lp = self._pages.get("layout")
        if lp is not None:
            lp.editing_changed(on)
        if on:
            self.ensure_sizes()

    def profile_changed(self):
        """Kitas profilis = kiti nustatymai: formos kuriamos iš naujo."""
        self._fill_profiles()
        cur_name = None
        for name, page in list(self._widget_pages.items()):
            if page is self._current:
                cur_name = name
            self.stack.removeWidget(page)
            page.deleteLater()
        self._widget_pages.clear()
        self.preview.invalidate()
        if cur_name:
            self.open_widget(cur_name)
        elif self._current is not None:
            self._current.on_show() if not isinstance(self._current, LayoutPage) else self._current.on_show(None)

    def profile_name(self) -> str:
        p = self.ctx.config.data["profiles"].get(self.ctx.config.profile_key, {})
        return p.get("name", self.ctx.config.profile_key)

    def _fill_profiles(self):
        c = self.profile_combo
        c.blockSignals(True)
        c.clear()
        c._keys = list(self.ctx.config.data["profiles"])
        for k in c._keys:
            c.addItem(self.ctx.config.data["profiles"][k].get("name", k), k)
        if self.ctx.config.profile_key in c._keys:
            c.setCurrentIndex(c._keys.index(self.ctx.config.profile_key))
        c.blockSignals(False)

    def _profile_selected(self, key):
        if key != self.ctx.config.profile_key:
            self.ctx.set_profile(key)

    def ensure_sizes(self, everything: bool = False):
        """Paslėpti valdikliai neturi tikro aukščio - paskaičiuojam iš dabartinių / demo duomenų."""
        snap = self.preview.snapshot()
        for spec in WIDGETS:
            w = self.ctx.widgets[spec.name]
            if not w.isVisible() and (everything or self.ctx.config.widget(spec.name).get("visible")):
                w.push(snap, force=True)

    def log_error(self, text):
        try:
            with open(os.path.join(app_dir(), "ui.log"), "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} control center\n{text}\n")
        except OSError:
            pass

    # ------------------------------------------------------------------ langas
    def closeEvent(self, e):
        e.ignore()
        self.hide()
        tray = getattr(self.ctx, "tray", None)
        if tray is not None and not self._told_tray:
            self._told_tray = True
            tray.showMessage("LTH Overlays is still running",
                             "Overlays stay active. Click the icon next to the clock to open the Control Center.",
                             QSystemTrayIcon.MessageIcon.Information, 4000)

    def sizeHint(self):
        return QSize(1320, 860)


__all__ = ["ControlCenter", "IconTile", "T", "QTimer"]
