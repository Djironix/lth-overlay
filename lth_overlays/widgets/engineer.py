"""Engineer juosta ir našumo langelis."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter

from ..window import OverlayWidget

PRIO_COLOR = {2: "red", 1: "accent", 0: "good"}


class EngineerWidget(OverlayWidget):
    NAME = "engineer"
    TITLE = "Engineer"
    MIN_WIDTH = 240

    def __init__(self, ctx):
        self._msg = None
        super().__init__(ctx)

    def content_key(self, snap):
        msgs = snap.messages or []
        m = max(msgs, key=lambda x: (x.priority, x.shown_at)) if msgs else None
        self._msg = (m.text, m.priority) if m else None
        return (self._msg, self.width())

    def desired_height(self) -> int:
        return int(self.fonts.em_bold * 2.4)

    def paint_content(self, p: QPainter):
        msg = self._msg
        if msg is None:
            if not self.editing:
                return  # nieko nepiešiam - langas visiškai permatomas
            msg = ("Race engineer messages appear here", 0)
        text, prio = msg
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.pal.bg)
        p.drawRoundedRect(r, 6, 6)
        p.fillRect(QRectF(0, 0, 5, r.height()), getattr(self.pal, PRIO_COLOR.get(prio, "accent")))
        p.setPen(self.pal.accent)
        self.draw_text(p, QRectF(16, 0, 80, r.height()), "ENG", "tiny")
        p.setPen(self.pal.text)
        avail = r.width() - 70
        self.draw_text(p, QRectF(56, 0, avail, r.height()), self.elide(text, avail, "bold"), "bold")


class PerfWidget(OverlayWidget):
    NAME = "perf"
    TITLE = "Performance"
    MIN_WIDTH = 180

    def __init__(self, ctx):
        self._lines = ()
        super().__init__(ctx)

    def content_key(self, snap):
        st = self.ctx.perf
        cpu, ram = st.get("cpu", 0.0), st.get("ram", 0.0)
        eng_us = st.get("engine_us", 0.0)
        fps = st.get("fps")
        self._lines = (
            f"LTH CPU {cpu:.1f} %   RAM {ram:.0f} MB",
            f"Engine {eng_us:.0f} µs/frame" + (f"   iRacing {fps:.0f} FPS" if fps else ""),
        )
        return (self._lines, self.width())

    def desired_height(self) -> int:
        return int(self.fonts.em_small * 3.4)

    def paint_content(self, p: QPainter):
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.pal.bg)
        p.drawRoundedRect(r, 6, 6)
        lh = self.fonts.em_small * 1.3
        y = (r.height() - lh * len(self._lines)) / 2
        p.setPen(self.pal.text)
        for line in self._lines:
            self.draw_text(p, QRectF(10, y, r.width() - 20, lh), line, "small")
            y += lh
