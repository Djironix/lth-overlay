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
EDGE = 7  # krašto zona redaguojant (px)
CORNER = 16  # kampo zona
MIN_SCALE, MAX_SCALE = 0.5, 3.0

_CURSORS = {"l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
            "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
            "tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
            "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
            "move": Qt.CursorShape.SizeAllCursor}


class OverlayWidget(QWidget):
    NAME = "base"
    TITLE = "Widget"
    MIN_WIDTH = 160
    MIN_HEIGHT = 30
    # Kaip elgiasi aukštis: "rows" - lentelė (aukštis = kiek eilučių telpa),
    # "free" - grafika (piešiama į bet kokį aukštį), "auto" - pagal turinį
    # (viršaus / apačios kraštas tada keičia viso valdiklio dydį).
    HEIGHT_MODE = "auto"
    preview_mode = False  # Control Center peržiūros kopija: be redagavimo rėmelio

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
        self.pal = Palette(self.ctx.theme, c.get("opacity", 1.0), self.ctx.config.data.get("custom_colors"))
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

    def min_height(self) -> int:
        return int(self.MIN_HEIGHT * self._scale())

    def header_h(self) -> int:
        """Antraštės aukštis (Standings / Relative / Weather...)."""
        return round(self.fonts.em_small * 1.9) + 2 if self.cfg.get("show_header", True) else 4

    def user_height(self) -> int | None:
        """Vartotojo nustatytas aukštis (px su masteliu) arba None = pagal turinį."""
        if self.HEIGHT_MODE == "auto":
            return None
        h = self.cfg.get("height")
        try:
            h = float(h) if h else 0.0
        except (TypeError, ValueError):
            h = 0.0
        return int(round(h * self._scale())) if h > 0 else None

    def avail_body_height(self) -> float | None:
        """Kiek vietos eilutėms, kai aukštis nustatytas rankiniu būdu (lentelėms)."""
        uh = self.user_height() if self.HEIGHT_MODE == "rows" else None
        return None if uh is None else max(0.0, uh - self.header_h() - 6)

    def final_height(self) -> int:
        uh = self.user_height()
        if uh:
            return max(uh, self.min_height())
        return max(self.desired_height(), 8)

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
        if self.HEIGHT_MODE != "auto" and c.get("height"):
            c["height"] = int(round(self.height() / self._scale()))
        self.ctx.save_config()
        notify = getattr(self.ctx, "geometry_changed", None)
        if notify:
            notify(self.NAME)

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
        c = self.cfg
        if not c.get("visible", True):
            return False
        if self.editing or snap is None:
            return True
        if c.get("hide_in_garage") and snap.in_garage and not snap.watching:
            return False
        if c.get("hide_when_spectating") and snap.watching:
            return False
        if c.get("race_only") and snap.session_type != "race":
            return False
        return True

    def push(self, snap, force=False):
        self._snap = snap
        key = self.content_key(snap)
        if not force and key == self._key and not self.editing:
            return
        self._key = key
        if self.width() < self.min_width():  # įjungti nauji stulpeliai / platesnis šriftas
            self._place()
        h = self.final_height()
        if h != self.height() and self._drag is None:
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
        self.setMouseTracking(on)
        if not on:
            self.unsetCursor()
            self._drag = None
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
        if self.editing and not self.preview_mode:
            self._paint_edit(p)
        p.end()

    def _paint_edit(self, p: QPainter):
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        gold = self.pal.edit
        p.setPen(QPen(gold, 1.5, Qt.PenStyle.DashLine))
        p.setBrush(QColor(226, 177, 60, 22))
        p.drawRoundedRect(r, 6, 6)
        # pavadinimas + dydis
        p.setFont(self.fonts.tiny)
        size = f"{self.width()}×{self.height()}  ·  {self._scale() * 100:.0f}%"
        label = f"{self.TITLE}   {size}"
        tw = min(self.fonts.m_tiny.horizontalAdvance(label) + 16, self.width() - 8)
        chip = QRectF(4, 4, tw, 18)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(226, 177, 60, 235))
        p.drawRoundedRect(chip, 4, 4)
        p.setPen(QColor(0, 0, 0))
        p.drawText(chip.adjusted(8, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, label)
        # rankenėlės: kampai (mastelis) ir kraštų vidurys (plotis / aukštis)
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor(0, 0, 0, 160), 1))
        p.setBrush(gold)
        for x, y in ((0, 0), (w, 0), (0, h), (w, h)):
            p.drawRoundedRect(QRectF(min(max(x - 5, 1), w - 11), min(max(y - 5, 1), h - 11), 10, 10), 2, 2)
        p.setBrush(QColor(255, 255, 255))
        for x, y in ((w / 2, 0), (w / 2, h), (0, h / 2), (w, h / 2)):
            p.drawRoundedRect(QRectF(min(max(x - 4, 1), w - 9), min(max(y - 4, 1), h - 9), 8, 8), 2, 2)

    # ---------------- redagavimas pele ----------------
    def _zone(self, pos) -> str:
        x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
        left, right = x <= EDGE, x >= w - EDGE
        top, bottom = y <= EDGE, y >= h - EDGE
        near_l, near_r = x <= CORNER, x >= w - CORNER
        near_t, near_b = y <= CORNER, y >= h - CORNER
        if (top or left) and near_t and near_l:
            return "tl"
        if (top or right) and near_t and near_r:
            return "tr"
        if (bottom or left) and near_b and near_l:
            return "bl"
        if (bottom or right) and near_b and near_r:
            return "br"
        if left:
            return "l"
        if right:
            return "r"
        if top:
            return "t"
        if bottom:
            return "b"
        return "move"

    def mousePressEvent(self, e):
        if not self.editing:
            return
        if e.button() == Qt.MouseButton.RightButton:
            self.ctx.open_settings(self.NAME)
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        zone = self._zone(e.position().toPoint())
        self._drag = (zone, e.globalPosition().toPoint(), self.geometry(), self._scale())

    def mouseDoubleClickEvent(self, e):
        """Dvigubas spustelėjimas redaguojant: aukštis vėl pagal turinį."""
        if self.editing and self.HEIGHT_MODE != "auto":
            self.cfg["height"] = None
            self._drag = None
            self.apply_settings()
            self.save_geometry()

    def mouseMoveEvent(self, e):
        if not self.editing:
            return
        if self._drag is None:
            self.setCursor(_CURSORS[self._zone(e.position().toPoint())])
            return
        zone, start, geo, scale0 = self._drag
        d = e.globalPosition().toPoint() - start
        dx, dy = d.x(), d.y()
        if zone == "move":
            x, y = self._snap_xy(geo.x() + dx, geo.y() + dy, geo.width(), geo.height())
            self.move(x, y)
            return
        if len(zone) == 2:  # kampas: proporcingas mastelis, priešingas kampas lieka vietoje
            sx = 1 if "r" in zone else -1
            sy = 1 if "b" in zone else -1
            fx = (geo.width() + sx * dx) / max(geo.width(), 1)
            fy = (geo.height() + sy * dy) / max(geo.height(), 1)
            f = max(0.2, (fx + fy) / 2)
            new_scale = round(min(MAX_SCALE, max(MIN_SCALE, scale0 * f)), 2)
            if abs(new_scale - self._scale()) >= 0.01:
                self.cfg["scale"] = new_scale
                self._rescale_keep_corner(zone, geo)
            return
        x, y, w, h = geo.x(), geo.y(), geo.width(), geo.height()
        if zone in ("l", "r"):
            nw = round((w + (dx if zone == "r" else -dx)) / GRID) * GRID
            nw = max(self.min_width(), nw)
            if zone == "l":
                x = x + w - nw
            self.setGeometry(x, y, nw, h)
            self.cfg["width"] = int(round(nw / self._scale()))
        else:  # "t" / "b"
            nh = h + (dy if zone == "b" else -dy)
            if self.HEIGHT_MODE == "auto":  # aukštis pagal turinį: keičiam viso valdiklio dydį
                new_scale = round(min(MAX_SCALE, max(MIN_SCALE, scale0 * nh / max(h, 1))), 2)
                if abs(new_scale - self._scale()) >= 0.01:
                    self.cfg["scale"] = new_scale
                    self._rescale_keep_corner("br" if zone == "b" else "tr", geo)
                return
            nh = max(self.min_height(), round(nh / GRID) * GRID)
            if zone == "t":
                y = y + h - nh
            self.cfg["height"] = int(round(nh / self._scale()))
            self.setGeometry(x, y, w, nh)
        self._key = object()
        if self._snap is not None:
            self.push(self._snap, force=True)

    def _rescale_keep_corner(self, zone, geo):
        self.fonts = Fonts(self._scale(), self.ctx.config.data.get("font", "saira"))
        self._texts = {}
        w = self.target_width()
        self._key = object()
        if self._snap is not None:
            self.content_key(self._snap)
        h = self.final_height()
        x = geo.x() if "r" in zone else geo.x() + geo.width() - w
        y = geo.y() if "b" in zone else geo.y() + geo.height() - h
        self.setGeometry(x, y, w, h)
        self.update()

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            self.apply_settings_keep_pos()
            self.save_geometry()

    def apply_settings_keep_pos(self):
        pos = self.pos()
        c = self.cfg
        c["x"], c["y"] = pos.x(), pos.y()
        self.apply_settings()

    def wheelEvent(self, e):
        if self.editing and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            c = self.cfg
            step = 0.05 if e.angleDelta().y() > 0 else -0.05
            c["scale"] = round(min(MAX_SCALE, max(MIN_SCALE, c.get("scale", 1.0) + step)), 2)
            self.apply_settings_keep_pos()
            self.save_geometry()

    def _snap_xy(self, x, y, w, h):
        if not self.ctx.config.data.get("snap", True):
            return x, y
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
