"""Engineer juosta ir našumo langelis."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter

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
        self._drew_bg = True
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
        self._rows = ()
        super().__init__(ctx)

    def content_key(self, snap):
        st = self.ctx.perf
        c = self.cfg
        rows = []  # (pavadinimas, tekstas, apkrova 0..1 arba None)
        if c.get("show_system", True):
            cpu = st.get("sys_cpu")
            if cpu is not None:
                rows.append(("CPU", f"{cpu:.0f}%", cpu / 100))
            ram = st.get("sys_ram")
            if ram:
                rows.append(("RAM", f"{ram[0]:.1f} / {ram[1]:.0f} GB", ram[2] / 100))
        if c.get("show_gpu", True):
            g = st.get("gpu")
            if g:
                txt = f"{g[0]:.0f}%" + (f"   {g[1]:.1f} GB" if g[1] is not None else "")
                rows.append(("GPU", txt, g[0] / 100))
        if c.get("show_fps", True) and st.get("fps"):
            rows.append(("FPS", f"{st['fps']:.0f}", None))
        if c.get("show_lth", True):
            rows.append(("LTH", f"{st.get('cpu', 0.0):.1f}%   {st.get('ram', 0.0):.0f} MB", None))
        if c.get("show_engine"):
            rows.append(("Engine", f"{st.get('engine_us', 0.0):.0f} µs", None))
        self._rows = tuple((a, b, None if v is None else round(max(0.0, min(1.0, v)), 2)) for a, b, v in rows)
        return (self._rows, self.width(), bool(c.get("bars", True)))

    def desired_height(self) -> int:
        return int(self.fonts.em_small * (1.35 * max(1, len(self._rows)) + 1.0))

    def paint_content(self, p: QPainter):
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.pal.bg)
        p.drawRoundedRect(r, self.pal.radius, self.pal.radius)
        self._drew_bg = True
        lh = self.fonts.em_small * 1.35
        y = (r.height() - lh * len(self._rows)) / 2
        x0 = self.fonts.em_small * 0.7
        lw = self.text_width("Engine", "tiny") + x0
        bars = self.cfg.get("bars", True)
        for name, text, load in self._rows:
            p.setPen(self.pal.dim)
            self.draw_text(p, QRectF(x0, y, lw, lh), name, "tiny")
            vw = self.text_width(text, "small")
            p.setPen(self.pal.text)
            self.draw_text(p, QRectF(r.width() - x0 - vw, y, vw, lh), text, "small")
            if bars and load is not None:
                bx0, bx1 = x0 + lw, r.width() - x0 * 2 - vw
                if bx1 - bx0 > 16:
                    col = self.pal.bad if load >= 0.9 else self.pal.yellow if load >= 0.75 else self.pal.good
                    track = QColor(self.pal.dim)
                    track.setAlpha(50)
                    br = QRectF(bx0, y + lh * 0.42, bx1 - bx0, max(2.0, lh * 0.16))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(track)
                    p.drawRoundedRect(br, 1.5, 1.5)
                    p.setBrush(col)
                    p.drawRoundedRect(QRectF(br.x(), br.y(), br.width() * load, br.height()), 1.5, 1.5)
            y += lh
