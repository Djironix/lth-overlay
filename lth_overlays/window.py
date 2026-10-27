"""Bazinis overlay langas: visada viršuje, pelė kiaurai, redagavimo režimas.

Efektyvumas: valdiklis perpiešiamas TIK kai pasikeičia tai, kas rodoma
(content_key). Jei skaičiai ekrane tie patys - jokio darbo.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QStaticText
from PySide6.QtWidgets import QWidget

from . import win32
from .theme import Fonts, Palette

GRID = 8
SNAP = 10
GRIP = 14


class OverlayWidget(QWidget):
    NAME = "base"
    TITLE = "Widget"
    MIN_WIDTH = 160

    def __init__(self, ctx):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
                 | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.NoDropShadowWindowHint)
        if not win32.IS_WIN:
            flags |= Qt.WindowType.WindowTransparentForInput
        super().__init__(None, flags)
        self.ctx = ctx
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowTitle(f"LTH {self.TITLE}")
        self.editing = False
        self._snap = None
        self._key = object()
        self._drag = None
        self._native_ready = False
        self.apply_settings()

    # ---------------- nustatymai ----------------
    @property
    def cfg(self) -> dict:
        return self.ctx.config.widget(self.NAME)

    def apply_settings(self):
        c = self.cfg
        self.fonts = Fonts(c.get("scale", 1.0), self.ctx.config.data.get("font", "saira"))
        self._texts = {}
        self.pal = Palette(self.ctx.theme, c.get("opacity", 1.0))
        self._key = object()  # priverstinis perpiešimas
        self._place()
        if self._snap is not None:
            self.push(self._snap, force=True)

    # ---------------- dydis ----------------
    # config "width" saugomas be mastelio (kaip esant Size = 1.0). Tikras plotis = width × scale,
    # todėl padidinus Size (Ctrl+ratukas) didėja visas langas, o ne tik tekstas jame.
    def _scale(self) -> float:
        return float(self.cfg.get("scale", 1.0) or 1.0)

    def content_min_width(self) -> int:
        """Mažiausias plotis, kad tilptų turinys (poklasiai perrašo)."""
        return 0

    def min_width(self) -> int:
        return max(int(self.MIN_WIDTH * self._scale()), self.content_min_width())

    def target_width(self) -> int:
        return max(self.min_width(), int(round(int(self.cfg.get("width", 300)) * self._scale())))

    def _place(self):
        c = self.cfg
        scr = self.ctx.screen_rect()
        w = self.target_width()
        x, y = int(c.get("x", 0)), int(c.get("y", 0))
        if x == -1:
            x = scr.x() + (scr.width() - w) // 2
        elif x < 0:  # prisegta prie dešinio krašto: platėja į kairę
            x = scr.x() + scr.width() + x - max(0, w - int(c.get("width", 300)))
        if y < 0:
            y = scr.y() + scr.height() + y
        # neišlįsti už ekrano dešinio krašto
        if x + w > scr.x() + scr.width():
            x = max(scr.x(), scr.x() + scr.width() - w)
        self.setGeometry(x, y, w, max(self.height(), 20))

    def save_geometry(self):
        c = self.cfg
        c["x"], c["y"] = self.x(), self.y()
        c["width"] = int(round(self.width() / self._scale()))
        self.ctx.save_config()

    # ---------------- tekstas su talpykla ----------------
    def draw_text(self, p: QPainter, rect: QRectF, text: str, font_key: str = "base", align: str = "l"):
        """Tekstas per QStaticText talpyklą: tas pats tekstas išdėstomas vieną kartą,
        vėliau tik nupiešiamas (kelis kartus pigiau nei drawText)."""
        if not text:
            return
        key = (font_key, text)
        st = self._texts.get(key)
        if st is None:
            if len(self._texts) > 4000:
                self._texts.clear()
            font = getattr(self.fonts, font_key)
            st = QStaticText(text)
            st.setTextFormat(Qt.TextFormat.PlainText)
            st.setPerformanceHint(QStaticText.PerformanceHint.AggressiveCaching)
            st.prepare(font=font)
            m = getattr(self.fonts, "m_" + font_key, self.fonts.m_base)
            # vertical centre on the cap height, so every font sits in the middle of the row
            self._texts[key] = (st, font, st.size(), m.capHeight() / 2 - m.ascent())
            st = self._texts[key]
        st, font, size, y_off = st
        if align == "r":
            x = rect.right() - size.width()
        elif align == "c":
            x = rect.x() + (rect.width() - size.width()) / 2
        else:
            x = rect.x()
        y = rect.y() + rect.height() / 2 + y_off
        p.setFont(font)
        if self.pal.shadow:  # nedidelis šešėlis - tekstas skaitomas ant bet kokio fono
            col = p.pen().color()
            p.setPen(self.pal.shadow_color)
            p.drawStaticText(QPointF(x + 1, y + 1), st)
            p.setPen(col)
        p.drawStaticText(QPointF(x, y), st)

    def text_width(self, text: str, font_key: str = "base") -> float:
        key = ("~w", font_key, text)
        v = self._texts.get(key)
        if v is None:
            m = getattr(self.fonts, "m_" + font_key, self.fonts.m_base)
            v = m.horizontalAdvance(text)
            self._texts[key] = v
        return v

    def elide(self, text: str, width: float, font_key: str = "base") -> str:
        key = ("~elide", font_key, text, int(width))
        v = self._texts.get(key)
        if v is None:
            m = getattr(self.fonts, "m_" + font_key, self.fonts.m_base)
            v = m.elidedText(text, Qt.TextElideMode.ElideRight, width)
            self._texts[key] = v
        return v

    # ---------------- turinys ----------------
    def content_key(self, snap):
        """Grąžina hashable reikšmę viskam, kas bus nupiešta. Poklasiai perrašo."""
        return None

    def desired_height(self) -> int:
        return 40

    def paint_content(self, p: QPainter):
        pass

    def paint_header(self, p: QPainter, title: str, right: str = "", right_font: str = "small") -> float:
        """Bendra antraštė (Standings / Relative / Weather). Grąžina jos aukštį."""
        pal = self.pal
        r = QRectF(self.rect())
        hh = round(self.fonts.em_small * 1.9)
        rad = pal.radius
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.header)
        p.drawRoundedRect(QRectF(0, 0, r.width(), hh), rad, rad)
        p.fillRect(QRectF(0, hh - rad, r.width(), rad), pal.header)
        if pal.lumina:  # modernus: raudona žymė kairėje, baltas pavadinimas
            p.fillRect(QRectF(0, hh * 0.2, 3, hh * 0.6), pal.accent)
            p.setPen(pal.text)
            self.draw_text(p, QRectF(12, 0, r.width() - 24, hh), title, "tiny")
        else:
            p.fillRect(QRectF(0, hh - 2, r.width(), 2), pal.accent)
            p.setPen(pal.accent)
            self.draw_text(p, QRectF(10, 0, r.width() - 20, hh), title, "tiny")
        if right:
            p.setPen(pal.dim)
            self.draw_text(p, QRectF(10, 0, r.width() - 22, hh), right, right_font, "r")
        return hh

    def wants_visible(self, snap) -> bool:
        return bool(self.cfg.get("visible", True))

    def push(self, snap, force=False):
        self._snap = snap
        key = self.content_key(snap)
        if not force and key == self._key and not self.editing:
            return
        self._key = key
        if self.width() < self.min_width():  # įjungti nauji stulpeliai / platesnis šriftas
            self._place()
        h = self.desired_height()
        if h != self.height():
            self.resize(self.width(), h)
        self.update()

    # ---------------- langas ----------------
    def showEvent(self, e):
        super().showEvent(e)
        if not self._native_ready:
            win32.make_overlay(self, click_through=not self.editing)
            self._native_ready = True

    def set_editing(self, on: bool):
        self.editing = on
        if win32.IS_WIN:
            win32.set_click_through(self, not on)
        else:
            vis = self.isVisible()
            self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, not on)
            if vis:
                self.show()
        self._key = object()
        if self._snap is not None:
            self.push(self._snap, force=True)
        else:
            self.update()

    def keep_on_top(self):
        if self.isVisible():
            win32.keep_on_top(self)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        self.paint_content(p)
        if self.editing:
            self._paint_edit(p)
        p.end()

    def _paint_edit(self, p: QPainter):
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(self.pal.edit, 2, Qt.PenStyle.DashLine))
        p.setBrush(QColor(226, 177, 60, 24))
        p.drawRoundedRect(r, 6, 6)
        p.setFont(self.fonts.tiny)
        label = f"{self.TITLE}  ·  drag to move, corner = width, Ctrl+wheel = size, right-click = settings"
        tw = self.fonts.m_tiny.horizontalAdvance(label) + 12
        p.fillRect(QRectF(4, 4, min(tw, self.width() - 8), 16), QColor(226, 177, 60, 220))
        p.setPen(QColor(0, 0, 0))
        p.drawText(QRectF(10, 4, self.width() - 16, 16), Qt.AlignmentFlag.AlignVCenter, label)
        g = QRectF(self.width() - GRIP - 2, self.height() - GRIP - 2, GRIP, GRIP)
        p.setPen(QPen(self.pal.edit, 2))
        for i in range(3):
            o = 4 + i * 4
            p.drawLine(int(g.right() - o), int(g.bottom()), int(g.right()), int(g.bottom() - o))

    # ---------------- redagavimas pele ----------------
    def mousePressEvent(self, e):
        if not self.editing:
            return
        if e.button() == Qt.MouseButton.RightButton:
            self.ctx.open_settings(self.NAME)
            return
        pos = e.position().toPoint()
        resize = pos.x() > self.width() - GRIP - 4 and pos.y() > self.height() - GRIP - 4
        self._drag = ("resize" if resize else "move", e.globalPosition().toPoint(), self.geometry())

    def mouseMoveEvent(self, e):
        if not self.editing or self._drag is None:
            return
        mode, start, geo = self._drag
        d = e.globalPosition().toPoint() - start
        if mode == "move":
            x, y = self._snap_xy(geo.x() + d.x(), geo.y() + d.y(), geo.width(), geo.height())
            self.move(x, y)
        else:
            w = max(self.min_width(), round((geo.width() + d.x()) / GRID) * GRID)
            self.resize(w, self.height())
            self._key = object()
            if self._snap is not None:
                self.push(self._snap, force=True)

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            self.save_geometry()

    def wheelEvent(self, e):
        if self.editing and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            c = self.cfg
            step = 0.05 if e.angleDelta().y() > 0 else -0.05
            c["scale"] = round(min(2.5, max(0.6, c.get("scale", 1.0) + step)), 2)
            self.apply_settings()
            self.ctx.save_config()

    def _snap_xy(self, x, y, w, h):
        xs, ys = [], []
        scr = QGuiApplication.screenAt(QPoint(x + w // 2, y + h // 2)) or QGuiApplication.primaryScreen()
        sg: QRect = scr.availableGeometry()
        xs += [sg.left(), sg.right() + 1]
        ys += [sg.top(), sg.bottom() + 1]
        for other in self.ctx.widgets.values():
            if other is self or not other.isVisible():
                continue
            g = other.geometry()
            xs += [g.left(), g.right() + 1]
            ys += [g.top(), g.bottom() + 1]

        def snap(v, size, edges):
            best, bd = None, SNAP + 1
            for edge in edges:
                for cand, off in ((edge, 0), (edge - size, size)):
                    dist = abs(v - cand)
                    if dist < bd:
                        best, bd = cand, dist
            if best is not None and bd <= SNAP:
                return best
            return round(v / GRID) * GRID

        return snap(x, w, xs), snap(y, h, ys)
