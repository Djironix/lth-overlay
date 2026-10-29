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
from .overview_page import OverviewPage
from .pages import (AboutPage, AppearancePage, DiagnosticsPage, GeneralPage, HotkeysPage, PerformancePage,
                    ProfilesPage, WidgetDetailPage, WidgetsPage)
from .preview import PreviewRenderer
from .drivers_page import DriversPage
from .stream_page import StreamPage
from .library_pages import RecordsPage, SetupsPage
from .telemetry_page import TelemetryPage
from .style import T, icon, qcolor, qss, ui_font

# Viršutinis meniu (GoFast stiliaus „piliulės“) ir nustatymų meniu (krumpliaratis)
NAV_MAIN = (("overview", "Overview"), ("widgets", "Widgets"), ("layout", "Layout"), ("appearance", "Appearance"),
            ("telemetry", "Telemetry"), ("records", "Records"), ("drivers", "Drivers"))
NAV_MORE = (("profiles", "Profiles", "layers"), ("setups", "Setups", "wrench"), ("stream", "Stream", "broadcast"),
            ("hotkeys", "Hotkeys", "keyboard"), ("general", "General", "settings"),
            ("performance", "Performance", "activity"), ("diagnostics", "Diagnostics", "bug"), ("about", "About", "info"))
HIGHLIGHT = "appearance"  # apvestas auksu, kol žmogus jo neatidarė - kad pastebėtų temas
NAV = ((None, tuple((k, t, "") for k, t in NAV_MAIN)), ("MORE", NAV_MORE))
PAGES = {"overview": OverviewPage, "widgets": WidgetsPage, "layout": LayoutPage, "profiles": ProfilesPage,
         "appearance": AppearancePage, "hotkeys": HotkeysPage, "general": GeneralPage,
         "performance": PerformancePage, "diagnostics": DiagnosticsPage, "about": AboutPage,
         "stream": StreamPage, "drivers": DriversPage,
         "telemetry": TelemetryPage, "records": RecordsPage, "setups": SetupsPage}


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
        main = QVBoxLayout(root)
        main.setContentsMargins(22, 18, 22, 14)
        main.setSpacing(10)
        main.addWidget(self._topnav())
        self.stack = QStackedWidget()
        main.addWidget(self.stack, 1)
        main.addWidget(self._statusbar())
        self.setCentralWidget(root)
        self.setAcceptDrops(True)

    # ------------------------------------------------------------------ pranešimai
    def toast(self, text: str):
        """Trumpas pranešimas apatiniame dešiniajame kampe (pvz. naujas rekordas, įdiegti setupai)."""
        from PySide6.QtCore import QTimer
        t = getattr(self, "_toast", None)
        if t is None:
            t = self._toast = QFrame(self)
            t.setObjectName("Toast")
            t.setStyleSheet(f"QFrame#Toast {{ background: {T['surface']}; border: 1px solid {T['accent']};"
                            f" border-radius: 12px; }} QLabel {{ color: {T['text']}; font-size: 13px; }}")
            lay = QHBoxLayout(t)
            lay.setContentsMargins(16, 12, 16, 12)
            t.lbl = QLabel()
            lay.addWidget(t.lbl)
            t.timer = QTimer(t)
            t.timer.setSingleShot(True)
            t.timer.timeout.connect(t.hide)
        t.lbl.setText(text)
        t.adjustSize()
        t.move(self.width() - t.width() - 24, self.height() - t.height() - 80)
        t.raise_()
        t.show()
        t.timer.start(6000)


    # ------------------------------------------------------------------ rėmas
    def _topnav(self):
        """Viršutinė juosta: logotipas, puslapių „piliulės“, nustatymai, pranešimai, profilis."""
        from PySide6.QtWidgets import QMenu, QPushButton
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(64)
        h = QHBoxLayout(bar)
        h.setContentsMargins(20, 0, 12, 0)
        h.setSpacing(6)
        logo = QLabel()
        from ..brand import logo_pixmap
        pm = logo_pixmap(26)
        if pm.isNull():
            from ..app import make_icon
            pm = make_icon().pixmap(32, 32)
        logo.setPixmap(pm)
        h.addWidget(logo)
        h.addSpacing(6)
        t = label("OVERLAYS")
        t.setStyleSheet("font-size: 14px; font-weight: 700; letter-spacing: 2px;")
        h.addWidget(t)
        h.addSpacing(10)
        v = label(f"v{VERSION}", "faint")
        h.addWidget(v)
        self._brand_text, self._brand_ver, self._topbar_w = t, v, bar
        self._compact = -1
        h.addStretch(1)
        self._nav = {}
        for key, text in NAV_MAIN:
            b = QPushButton(text)
            b.setObjectName("NavPill")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.go(k))
            from PySide6.QtWidgets import QSizePolicy
            b.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)  # niekada nesuspaudžiamas tekstas
            if key == HIGHLIGHT and not self.ctx.config.data.get("seen_" + key):
                b.setProperty("hl", True)
                b.setToolTip("Themes, colours and fonts for your widgets - have a look")
            h.addWidget(b)
            self._nav[key] = b
        h.addStretch(1)

        def icon_btn(name, tip):
            b = QPushButton()
            b.setObjectName("IconBtn")
            b.setFixedSize(40, 40)
            b.setIcon(icon(name, T["muted"]))
            b.setIconSize(QSize(18, 18))
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            return b
        # nustatymai
        self.b_settings = icon_btn("settings", "Settings")
        m = QMenu(self.b_settings)
        for key, text, ic in NAV_MORE:
            a = m.addAction(icon(ic, T["muted"]), text)
            a.triggered.connect(lambda _=False, k=key: self.go(k))
        m.addSeparator()
        q = m.addAction(icon("power", T["bad"]), "Quit LTH Overlays")
        q.triggered.connect(self.ctx.quit)
        self.b_settings.setMenu(m)
        h.addWidget(self.b_settings)
        # pranešimai
        self.b_notes = icon_btn("bell", "Notifications")
        self.notes_menu = QMenu(self.b_notes)
        self.notes_menu.aboutToShow.connect(self._fill_notes)
        self.b_notes.setMenu(self.notes_menu)
        h.addWidget(self.b_notes)
        # profilis
        self.b_profile = QPushButton()
        self.b_profile.setObjectName("ProfileChip")
        self.b_profile.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_profile.setFixedHeight(48)
        self.profile_menu = QMenu(self.b_profile)
        self.profile_menu.aboutToShow.connect(self._fill_profile_menu)
        self.b_profile.setMenu(self.profile_menu)
        ch = QHBoxLayout(self.b_profile)
        ch.setContentsMargins(8, 0, 14, 0)
        ch.setSpacing(10)
        self.chip_avatar = QLabel()
        self.chip_avatar.setFixedSize(30, 30)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.setContentsMargins(0, 0, 0, 0)
        self.chip_name = QLabel()
        self.chip_name.setStyleSheet(f"color: {T['text']}; font-size: 13px; font-weight: 600; background: transparent;")
        self.chip_prof = QLabel()
        self.chip_prof.setStyleSheet(f"color: {T['accent']}; font-size: 11px; background: transparent;")
        col.addStretch(1)
        col.addWidget(self.chip_name)
        col.addWidget(self.chip_prof)
        col.addStretch(1)
        for w in (self.chip_avatar, self.chip_name, self.chip_prof):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        ch.addWidget(self.chip_avatar)
        ch.addLayout(col)
        h.addWidget(self.b_profile)
        self._fill_profiles()
        self._nav_more = {k for k, _, _ in NAV_MORE}
        return bar

    def _avatar(self, initials: str):
        from PySide6.QtGui import QPainter, QPixmap
        pm = QPixmap(60, 60)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(qcolor("accent"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, 60, 60, 18, 18)
        p.setPen(qcolor("accent_text"))
        p.setFont(ui_font(24, QFont.Weight.Bold))
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, initials)
        p.end()
        pm.setDevicePixelRatio(2.0)
        return pm

    def _driver_name(self) -> str:
        snap = self.ctx.engine.latest
        me = next((r for r in snap.cars if r.is_me), None) if snap.connected else None
        if me is not None and me.name and me.name != self.ctx.config.data.get("driver_name"):
            self.ctx.config.data["driver_name"] = me.name
            self.ctx.save_config_soon()
        return self.ctx.config.data.get("driver_name") or "Driver"

    def _fill_profile_menu(self):
        m = self.profile_menu
        m.clear()
        for k, pdata in self.ctx.config.data["profiles"].items():
            a = m.addAction(pdata.get("name", k))
            a.setCheckable(True)
            a.setChecked(k == self.ctx.config.profile_key)
            a.triggered.connect(lambda _=False, key=k: self._profile_selected(key))
        m.addSeparator()
        auto = m.addAction("Switch automatically with the session")
        auto.setCheckable(True)
        auto.setChecked(bool(self.ctx.config.data.get("auto_profile", True)))
        auto.triggered.connect(lambda v: (self.ctx.config.data.__setitem__("auto_profile", bool(v)),
                                          self.ctx.save_config_soon()))
        m.addAction("Manage profiles...").triggered.connect(lambda: self.go("profiles"))

    def _fill_notes(self):
        m = self.notes_menu
        m.clear()
        notes_all = getattr(self.ctx, "notifications", [])
        self._notes_seen = notes_all[-1][0] if notes_all else 0
        self._notes_hot = False
        self.b_notes.setIcon(icon("bell", T["muted"]))
        notes = list(reversed(getattr(self.ctx, "notifications", [])))
        if not notes:
            a = m.addAction("No notifications yet")
            a.setEnabled(False)
        import time as _t
        for ts, text in notes[:12]:
            m.addAction(f"{_t.strftime('%H:%M', _t.localtime(ts))}   {text}")

    def _statusbar(self):
        bar = QFrame()
        bar.setObjectName("StatusBar")
        bar.setFixedHeight(50)
        h = QHBoxLayout(bar)
        h.setContentsMargins(18, 0, 14, 0)
        h.setSpacing(18)
        self.status = Pill("Waiting for iRacing", "faint")
        h.addWidget(self.status)
        self.perf_lbl = label("", "faint")
        h.addWidget(self.perf_lbl)
        h.addStretch(1)
        from PySide6.QtWidgets import QPushButton
        self.b_edit = QPushButton()
        self.b_edit.setObjectName("EditKeys")
        self.b_edit.setCheckable(True)
        self.b_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_edit.setToolTip("Move and resize the widgets on screen")
        self.b_edit.setFixedHeight(34)
        self.b_edit.clicked.connect(lambda: self.ctx.toggle_edit())
        self._edit_row = QHBoxLayout(self.b_edit)
        self._edit_row.setContentsMargins(10, 0, 10, 0)
        self._edit_row.setSpacing(5)
        h.addWidget(self.b_edit)
        self.editing_changed(False, _boot=True)
        h.addWidget(label("Overlays on", "muted"))
        from .components import Toggle
        self.t_overlays = Toggle(not self.ctx.hidden_all)
        self.t_overlays.toggled.connect(self._overlays_toggled)
        h.addWidget(self.t_overlays)
        return bar

    def _overlays_toggled(self, on):
        if bool(on) == bool(self.ctx.hidden_all):
            self.ctx.toggle_hide_all()

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
        hb = self._nav.get(HIGHLIGHT)
        if nav_key == HIGHLIGHT and hb is not None and hb.property("hl"):
            hb.setProperty("hl", False)  # pamatė - apvadas nebereikalingas
            hb.style().unpolish(hb)
            hb.style().polish(hb)
            self.ctx.config.data["seen_" + HIGHLIGHT] = True
            self.ctx.save_config_soon()
        if nav_key != "overview" and not getattr(page, "OWN_HEAD", False) and not getattr(page, "_head_added", False) and hasattr(page, "content"):
            # puslapio antraštė - turinio stulpelio viršuje, kad lygiuotųsi su kortelėmis
            page._head_added = True
            head = QWidget()
            hv = QVBoxLayout(head)
            hv.setContentsMargins(2, 0, 0, 6)
            hv.setSpacing(2)
            t = QLabel(page.TITLE)
            t.setObjectName("PageTitle")
            hv.addWidget(t)
            if page.SUBTITLE:
                hv.addWidget(label(page.SUBTITLE, "muted", wrap=True))
            page.content.insertWidget(0, head)

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
        if not self.ctx.config.data.get("onboarding_done"):
            self.show_onboarding()

    def show_onboarding(self):
        from .onboarding import Onboarding
        if getattr(self, "_onb", None) is not None:
            return
        self._onb = Onboarding(self)
        self._onb.setGeometry(self.rect())
        self._onb.finished.connect(self._onb_done)
        self._onb.show()
        self._onb.raise_()

    def _onb_done(self):
        self._onb = None
        if self._current is not None:
            self._current.on_show() if not isinstance(self._current, LayoutPage) else self._current.on_show(None)

    def _fit_topnav(self):
        """Siauram langui (nuo 1080 px) viršutinė juosta glaudinama laipsniškai, kad tekstas niekada nesikirstų:
        1 - be versijos, 2 - profilis tik su avataru, 3 - siauresnės piliulės, 4 - be „OVERLAYS“ užrašo."""
        if not hasattr(self, "_topbar_w"):
            return
        w = self.width() - 44
        for level in range(5):
            self._apply_compact(level)
            need = self._topbar_w.layout().sizeHint().width()
            if need <= w:
                break

    def _apply_compact(self, level):
        if level == self._compact:
            return
        self._compact = level
        self._brand_ver.setVisible(level < 1)
        self.chip_name.setVisible(level < 2)
        self.chip_prof.setVisible(level < 2)
        if level >= 2:
            self.b_profile.setMinimumWidth(48)
            self.b_profile.setMaximumWidth(48)
            self.b_profile.layout().setContentsMargins(8, 0, 8, 0)
        else:
            self.b_profile.setMaximumWidth(16777215)
            self.b_profile.layout().setContentsMargins(8, 0, 14, 0)
            self._fill_profiles()
        pad = "padding: 9px 11px;" if level >= 3 else ""
        for b in self._nav.values():
            b.setStyleSheet(pad)
        self._brand_text.setVisible(level < 4)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit_topnav()
        onb = getattr(self, "_onb", None)
        if onb is not None:
            onb.setGeometry(self.rect())
        t = getattr(self, "_toast", None)
        if t is not None and t.isVisible():
            t.move(self.width() - t.width() - 24, self.height() - t.height() - 80)

    # ------------------------------------------------------------------ iš programos
    def tick(self, snap):
        if snap.connected:
            self.status.set(f"iRacing · {snap.track_name}" if snap.track_name else "Connected to iRacing", "good")
        else:
            self.status.set("Waiting for iRacing", "faint")
        self.b_edit.setChecked(self.ctx.editing)
        perf = self.ctx.perf
        if perf.get("cpu") is not None:
            self.perf_lbl.setText(f"CPU {perf['cpu']:.1f}%  ·  {perf.get('ram', 0):.0f} MB"
                                  + (f"  ·  iRacing {perf['fps']:.0f} FPS" if perf.get("fps") else ""))
        self.t_overlays.set_silent(not self.ctx.hidden_all)
        notes_all = getattr(self.ctx, "notifications", [])
        hot = bool(notes_all) and notes_all[-1][0] > getattr(self, "_notes_seen", 0)
        if hot != getattr(self, "_notes_hot", False):  # nauji pranešimai - auksinis varpelis
            self._notes_hot = hot
            self.b_notes.setIcon(icon("bell", T["accent"] if hot else T["muted"]))
        if snap.connected and self._driver_name() != self._chip_name:
            self._fill_profiles()
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

    def _edit_keys(self, on: bool):
        """„Edit layout [Ctrl] [Shift] [E]“ - klavišai kaip mygtukų kepurėlės."""
        from .components import clear_layout
        clear_layout(self._edit_row)
        hk = (self.ctx.config.data.get("hotkeys") or {}).get("edit") or ""
        t = QLabel("Done editing" if on else "Edit layout")
        t.setObjectName("EditKeysText")
        self._edit_row.addWidget(t)
        if not on:
            for k in [x for x in hk.replace("+", " + ").split(" + ") if x.strip()]:
                cap = QLabel(k.strip())
                cap.setObjectName("Keycap")
                self._edit_row.addWidget(cap)
        from PySide6.QtGui import QFontMetrics
        total = 20
        for i in range(self._edit_row.count()):
            w = self._edit_row.itemAt(i).widget()
            if w is None:
                continue
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            w.ensurePolished()
            cap = w.objectName() == "Keycap"
            wd = QFontMetrics(w.font()).horizontalAdvance(w.text()) + (16 if cap else 14)
            w.setFixedWidth(wd)
            if cap:
                w.setFixedHeight(20)
                w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            total += wd + self._edit_row.spacing()
        self.b_edit.setMinimumWidth(total)

    def editing_changed(self, on, _boot=False):
        self.b_edit.setChecked(on)
        self._edit_keys(on)
        if _boot:
            return
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
        name = self._driver_name()
        self._chip_name = name
        initials = "".join(w[0] for w in name.split()[:2]).upper() or "LTH"
        self.chip_avatar.setPixmap(self._avatar(initials[:2]))
        self.chip_name.setText(name)
        self.chip_prof.setText(f"Profile: {self.profile_name()}")
        if getattr(self, "_compact", 0) < 2:
            self.b_profile.setMinimumWidth(max(150, self.chip_name.sizeHint().width() + 70,
                                               self.chip_prof.sizeHint().width() + 70))

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
        # programos uždarymas (Quit, Windows atsijungimas) - leidžiam; lango X - tik paslepiam į tray
        if getattr(self.ctx, "quitting", False) or not e.spontaneous():
            e.accept()
            return
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

    # ---- .lthlayout failo nutempimas ant lango ----
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or (e.mimeData().hasText() and "LTH1:" in e.mimeData().text()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        from .. import share
        from .dialogs import ImportDialog
        data = None
        try:
            if e.mimeData().hasUrls():
                data = share.read_file(e.mimeData().urls()[0].toLocalFile())
            else:
                data = share.decode(e.mimeData().text())
        except (OSError, ValueError) as err:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Import layout", str(err))
            return
        ImportDialog(self, data).exec()


__all__ = ["ControlCenter", "IconTile", "T", "QTimer"]
