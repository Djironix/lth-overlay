"""Pirmo paleidimo tutorialas: 5 trumpi žingsniai virš Control Center lango."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from .components import Segmented, Toggle, button, label
from .dialogs import PresetPicker
from .style import T, icon_pixmap, qcolor, ui_font


def _body(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setWordWrap(True)
    lb.setStyleSheet(f"font-size: 14px; color: {T['muted']}; line-height: 140%;")
    return lb


def _title(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setWordWrap(True)
    lb.setStyleSheet("font-size: 24px; font-weight: 600;")
    return lb


class KeyCaps(QWidget):
    """Klavišų kombinacija kaip klaviatūros klavišai."""

    def __init__(self, combo: str):
        super().__init__()
        self.keys = [k.strip() for k in combo.split("+") if k.strip()]
        self.setFixedHeight(48)
        self._f = ui_font(15, QFont.Weight.DemiBold)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(self._f)
        x = 0.0
        fm = p.fontMetrics()
        for i, k in enumerate(self.keys):
            w = max(48, fm.horizontalAdvance(k) + 28)
            r = QRectF(x, 2, w, 42)
            p.setPen(QPen(qcolor("border2"), 1))
            p.setBrush(qcolor("surface3"))
            p.drawRoundedRect(r.adjusted(0, 3, 0, 0), 8, 8)
            p.setBrush(qcolor("surface2"))
            p.drawRoundedRect(r.adjusted(0, 0, 0, -3), 8, 8)
            p.setPen(qcolor("text"))
            p.drawText(r.adjusted(0, 0, 0, -3), Qt.AlignmentFlag.AlignCenter, k)
            x += w
            if i < len(self.keys) - 1:
                p.setPen(qcolor("faint"))
                p.drawText(QRectF(x, 0, 28, 44), Qt.AlignmentFlag.AlignCenter, "+")
                x += 28


class _Bullet(QWidget):
    def __init__(self, icon_name: str, title: str, text: str):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(14)
        ic = QLabel()
        ic.setPixmap(icon_pixmap(icon_name, T["accent"], 22))
        ic.setFixedWidth(26)
        lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet("font-size: 14px; font-weight: 600;")
        col.addWidget(t)
        b = QLabel(text)
        b.setWordWrap(True)
        b.setStyleSheet(f"font-size: 13px; color: {T['muted']};")
        col.addWidget(b)
        lay.addLayout(col, 1)


class Onboarding(QWidget):
    """Uždengia visą Control Center langą (tamsus fonas + kortelė per vidurį)."""

    finished = Signal()

    def __init__(self, center):
        super().__init__(center)
        self.center = center
        self.ctx = center.ctx
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        hk = self.ctx.config.data.get("hotkeys") or {}
        self.hk_edit = hk.get("edit", "Ctrl+Shift+E")
        self.hk_hide = hk.get("toggle_all", "Ctrl+Shift+H")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.addStretch(1)
        self.card = QFrame()
        self.card.setObjectName("OnbCard")
        self.card.setStyleSheet(f"QFrame#OnbCard {{ background: {T['surface']}; border: 1px solid {T['border2']};"
                                f" border-radius: 18px; }}")
        self.card.setFixedWidth(820)
        cl = QVBoxLayout(self.card)
        cl.setContentsMargins(36, 30, 36, 26)
        cl.setSpacing(18)
        top = QHBoxLayout()
        self.step_lbl = label("", "eyebrow")
        top.addWidget(self.step_lbl)
        top.addStretch(1)
        skip = button("Skip tutorial", "ghost")
        skip.clicked.connect(self._finish)
        top.addWidget(skip)
        cl.addLayout(top)
        self.stack = QStackedWidget()
        cl.addWidget(self.stack, 1)
        nav = QHBoxLayout()
        self.dots = _Dots(5)
        nav.addWidget(self.dots)
        nav.addStretch(1)
        self.b_back = button("Back", "ghost", "chevron_left")
        self.b_back.clicked.connect(lambda: self._go(self.stack.currentIndex() - 1))
        self.b_next = button("Next", "primary")
        self.b_next.setMinimumWidth(130)
        self.b_next.clicked.connect(self._next)
        nav.addWidget(self.b_back)
        nav.addWidget(self.b_next)
        cl.addLayout(nav)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)
        self._build()
        self._go(0)

    # ---------------------------------------------------------------- žingsniai
    def _page(self, *widgets):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        for x in widgets:
            if isinstance(x, QWidget):
                lay.addWidget(x)
            else:
                lay.addLayout(x)
        lay.addStretch(1)
        self.stack.addWidget(w)
        return w

    def _build(self):
        # 1. Sveiki
        logo = QLabel()
        from ..brand import logo_pixmap
        logo.setPixmap(logo_pixmap(54))
        warn = QFrame()
        warn.setObjectName("Warn")
        warn.setStyleSheet(f"QFrame#Warn {{ background: rgba(236,190,88,0.10); border: 1px solid "
                           f"rgba(236,190,88,0.45); border-radius: 12px; }}")
        wl = QVBoxLayout(warn)
        wl.setContentsMargins(18, 14, 18, 14)
        wl.addWidget(_Bullet("alert", "Run iRacing in Borderless window or Windowed mode",
                             "In exclusive fullscreen no overlay program can draw on top of iRacing. "
                             "Set it in iRacing: Options → Graphics → Window mode."))
        self._page(logo, _title("Welcome to LTH Overlays"),
                   _body("Timing, relative, weather and 20+ more widgets for iRacing, made by and for the LTH "
                         "community. This short setup takes under a minute."), warn)
        # 2. Išdėstymas
        fresh = getattr(self.ctx.config, "fresh", True)
        self.layout_mode = Segmented({"preset": "Start from a preset", "keep": "Keep my current layout"},
                                     "preset" if fresh else "keep")
        self.picker = PresetPicker("simple")
        self.layout_mode.changed.connect(lambda v: self.picker.setEnabled(v == "preset"))
        self.picker.setEnabled(self.layout_mode.value == "preset")
        self.picker.changed.connect(lambda _: self.layout_mode.set_value("preset") or self.picker.setEnabled(True))
        self._page(_title("Pick a starting layout"),
                   _body("You can change everything later. The preset is applied to the Race, Qualifying and "
                         "Practice profiles."), self.layout_mode, self.picker)
        # 3. Valdikliai
        demo = QFrame()
        demo.setObjectName("Demo")
        demo.setStyleSheet(f"QFrame#Demo {{ background: {T['bg']}; border: 1px solid {T['border']};"
                           f" border-radius: 12px; }}")
        dl = QVBoxLayout(demo)
        dl.setContentsMargins(18, 12, 18, 12)
        for name, on in (("Standings", True), ("Relative", True), ("Fuel", False)):
            r = QHBoxLayout()
            r.addWidget(label(name, "h3"))
            r.addStretch(1)
            t = Toggle(on)
            t.setEnabled(False)
            r.addWidget(t)
            dl.addLayout(r)
        self._page(_title("Turn widgets on and off"),
                   _body("The Widgets page lists every widget. Switch on what you need. Click a widget to change "
                         "its columns, size, colours and when it shows. Everything applies instantly, "
                         "with a live preview."), demo,
                   _Bullet("layers", "Profiles", "Race, Qualifying and Practice have their own layouts and switch "
                                                 "automatically with the session."))
        # 4. Vieta ekrane
        self._page(_title("Place them on screen"),
                   _body("In iRacing press this to edit the layout (press it again when you are done):"),
                   KeyCaps(self.hk_edit),
                   _Bullet("move", "Move and resize", "Drag a widget to move it. Drag a corner to scale it, an edge "
                                                     "to change width or height."),
                   _Bullet("settings", "Settings button", "Every widget shows a Settings button while editing. "
                                                         "Click it (or right-click the widget) to open its settings."),
                   _Bullet("layout", "Several monitors", "The Layout page shows all your screens. Drag widgets "
                                                        "between them, or use a preset."),
                   _Bullet("eye_off", f"{self.hk_hide} hides everything", "Handy for screenshots and streams."))
        # 5. Pabaiga
        self.try_edit = button("Try edit mode now", None, "move")
        self.try_edit.clicked.connect(lambda: (self._finish(), self.ctx.editing or self.ctx.toggle_edit()))
        auto = QFrame()
        auto.setObjectName("Demo")
        auto.setStyleSheet(f"QFrame#Demo {{ background: {T['bg']}; border: 1px solid {T['border']};"
                           f" border-radius: 12px; }}")
        al = QHBoxLayout(auto)
        al.setContentsMargins(18, 12, 18, 12)
        al.addWidget(label("Start with Windows (waits quietly for iRacing)", "h3"))
        al.addStretch(1)
        self.t_autostart = Toggle(bool(self.ctx.config.data.get("autostart", True)))
        al.addWidget(self.t_autostart)
        self._page(_title("You are set"),
                   _body("LTH Overlays lives next to the clock (the LTH icon). Closing this window keeps the "
                         "overlays running."),
                   auto,
                   _Bullet("info", "Tutorial again", "About page → Show tutorial."),
                   self.try_edit)

    # ---------------------------------------------------------------- navigacija
    def _go(self, i):
        i = max(0, min(self.stack.count() - 1, i))
        self.stack.setCurrentIndex(i)
        self.dots.set(i)
        self.step_lbl.setText(f"STEP {i + 1} OF {self.stack.count()}")
        self.b_back.setVisible(i > 0)
        self.b_next.setText("Finish" if i == self.stack.count() - 1 else "Next")

    def _next(self):
        i = self.stack.currentIndex()
        if i == 1 and self.layout_mode.value == "preset" and self.picker.value:
            from ..presets import apply_preset
            apply_preset(self.ctx, self.picker.value, ["race", "qualify", "practice"])
            self.center.preview.invalidate()
            self.center.profile_changed()
        if i >= self.stack.count() - 1:
            self._finish()
        else:
            self._go(i + 1)

    def _finish(self):
        if getattr(self, "_done", False):
            return
        self._done = True
        d = self.ctx.config.data
        if not d.get("autostart_done"):  # tik vartotojui sutikus (ne tyliai) - antivirusai to nemėgsta
            d["autostart_done"] = True
            try:
                self.ctx.set_autostart(bool(self.t_autostart.isChecked()))
            except Exception:  # noqa: BLE001
                pass
        self.ctx.config.data["onboarding_done"] = True
        self.ctx.save_config()
        self.hide()
        self.finished.emit()
        self.deleteLater()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 170))

    def resizeEvent(self, e):
        super().resizeEvent(e)


class _Dots(QWidget):
    def __init__(self, n):
        super().__init__()
        self.n, self.i = n, 0
        self.setFixedSize(n * 14 + 16, 12)

    def set(self, i):
        self.i = i
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        x = 0.0
        for k in range(self.n):
            p.setBrush(qcolor("accent") if k == self.i else qcolor("surface3"))
            w = 18 if k == self.i else 8
            p.drawRoundedRect(QRectF(x, 2, w, 8), 4, 4)
            x += w + 6
