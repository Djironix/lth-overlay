"""Stream puslapis: OBS Browser Source nuorodos (ir vėliau - chat)."""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QGridLayout, QLineEdit, QWidget

from ..registry import WIDGETS
from .components import Badge, Card, NumberField, Segmented, SettingRow, Toggle, button, hbox, label
from .pages import Page
from .style import qcolor


class StreamPage(Page):
    TITLE = "Stream"
    SUBTITLE = "Show your overlays in OBS, Streamlabs or any streaming app"

    def __init__(self, center):
        super().__init__(center)
        obs = self.ctx.obs
        c = Card("OBS browser source",
                 "Each widget becomes a web page on this PC only (127.0.0.1). Nothing is sent to the internet. "
                 "Widgets are drawn only while OBS asks for them.")
        self.t_on = Toggle(bool(obs.cfg.get("enabled")))
        self.t_on.toggled.connect(self._enable)
        self.state = Badge("", "muted")
        box = QWidget()
        box.setLayout(hbox(self.state, self.t_on))
        c.add(SettingRow("Enable", box, "Starts a small local web server for OBS."))
        self.port = NumberField(obs.port(), 1024, 65535, 0, "", 90)
        self.port.editingFinished.connect(self._port)
        c.add(SettingRow("Port", self.port, "Change only if another program already uses 8399."))
        seg = Segmented({"15": "15", "30": "30", "60": "60"}, str(obs.fps()))
        seg.changed.connect(self._fps)
        c.add(SettingRow("Frames per second", seg, "30 is smooth for tables. 60 for Inputs and the track map."))
        self.content.addWidget(c)

        how = Card("How to add it in OBS")
        for i, t in enumerate(("Sources  >  +  >  Browser.",
                               "Paste a URL from below. Leave \"Shutdown source when not visible\" on.",
                               "Whole layout: set Width / Height to your monitor resolution (e.g. 1920 x 1080). "
                               "Single widget: any size, the widget sits in the top-left corner.",
                               "Add ?demo=1 to the URL to see sample data while iRacing is closed."), 1):
            num = label(f"{i}.", "h3")
            num.setFixedWidth(22)
            row = hbox(num, label(t, "muted", wrap=True))
            row.setStretch(1, 1)
            how.add(row)
        self.content.addWidget(how)

        self.urls = Card("URLs")
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(6)
        self.urls.add(self.grid)
        b_open = button("Open list in browser", "ghost", "eye")
        b_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(obs.base_url())))
        self.urls.add(hbox(b_open, None))
        self.content.addWidget(self.urls)
        self.content.addStretch(1)
        self._fill()

    def _fill(self):
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget() is not None:
                it.widget().deleteLater()
        obs = self.ctx.obs
        rows = [(f"Whole layout - {n} ({r.width()}x{r.height()})", f"{obs.base_url()}/layout?screen={i}")
                for i, (n, r) in enumerate(self.ctx.screens())]
        rows += [(s.title, f"{obs.base_url()}/w/{s.name}") for s in WIDGETS]
        for r, (title, url) in enumerate(rows):
            e = QLineEdit(url)
            e.setReadOnly(True)
            b = button("Copy", "ghost", "copy")
            b.clicked.connect(lambda _=False, u=url, btn=b: self._copy(u, btn))
            self.grid.addWidget(label(title, "h3" if r < len(self.ctx.screens()) else None), r, 0)
            self.grid.addWidget(e, r, 1)
            self.grid.addWidget(b, r, 2)
        self.grid.setColumnStretch(1, 1)

    def _copy(self, url, btn):
        QGuiApplication.clipboard().setText(url)
        btn.setText("Copied")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1200, lambda: btn.setText("Copy"))

    def _save_apply(self):
        self.ctx.obs.apply()
        self.ctx.save_config_soon()
        self.on_show()

    def _enable(self, on):
        self.ctx.obs.cfg["enabled"] = bool(on)
        self._save_apply()

    def _port(self):
        v = int(self.port.value())
        if v != self.ctx.obs.port():
            self.ctx.obs.cfg["port"] = v
            self._save_apply()
            self._fill()

    def _fps(self, v):
        self.ctx.obs.cfg["fps"] = int(v)
        self._save_apply()

    def on_show(self):
        obs = self.ctx.obs
        if obs.running():
            txt, col = f"Running on port {obs.port()}", "good"
        elif obs.error and obs.cfg.get("enabled"):
            txt, col = obs.error, "bad"
        else:
            txt, col = "Off", "faint"
        self.state.setText(txt)
        c = qcolor(col)
        self.state.setStyleSheet(f"QLabel {{ background: rgba({c.red()},{c.green()},{c.blue()},0.13); color: {c.name()};"
                                 f" border-radius: 6px; padding: 2px 8px; font-size: 11px; font-weight: 600; }}")
