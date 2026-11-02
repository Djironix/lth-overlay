"""Bazinis overlay langas: visada viršuje, pelė kiaurai, redagavimo režimas.

Efektyvumas: valdiklis perpiešiamas TIK kai pasikeičia tai, kas rodoma
(content_key). Jei skaičiai ekrane tie patys - jokio darbo.
"""
from __future__ import annotations

import time

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

_CURSORS = {"gear": Qt.CursorShape.PointingHandCursor, "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
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
    obs_demo = False
    obs_mode = False  # OBS kopija (preview_mode, bet su tikrais duomenimis)
    preview_mode = False  # Control Center peržiūros kopija: be redagavimo rėmelio
    FAST_CAPABLE = False
    INTERACTIVE = False  # valdiklis su mygtukais: pelė jam veikia visada (ne tik redaguojant)  # valdiklis moka fast_tick(): savo laikmatis (iki 60 Hz) tiesiai iš variklio

    def __init__(self, ctx):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
                 | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.NoDropShadowWindowHint)
        if not win32.IS_WIN and not self.INTERACTIVE:
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

    def _make_fonts(self, scale):
        from .theme import font_style
        d = self.ctx.config.data
        choice = d.get("font", "saira")
        shift, italic = font_style(d, choice)
        return Fonts(scale, choice, shift, italic)

    def apply_settings(self):
        c = self.cfg
        self.fonts = self._make_fonts(c.get("scale", 1.0))
        self._texts = {}
        self.pal = Palette(self.ctx.theme, c.get("opacity", 1.0), self.ctx.config.data.get("custom_colors"))
        self._key = object()  # priverstinis perpiešimas
        self._place()
        if hasattr(self, "_native_ready"):
            self._update_fast()
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
        """Padėtis iš nustatymų. Nuo v0.5 x / y - absoliučios virtualaus darbalaukio koordinatės
        (pos_v = 2), todėl veikia bet kuriame monitoriuje, taip pat kairėje nuo pagrindinio
        (neigiamos koordinatės). Senas formatas (be pos_v): neigiamas = nuo pagrindinio ekrano
        dešinio / apatinio krašto, -1 = centre - paverčiamas vieną kartą."""
        c = self.cfg
        w = self.target_width()
        h = max(self.height(), 20)
        if int(c.get("pos_v", 1) or 1) < 2:
            self._migrate_position(w)
        x, y = int(c.get("x", 0)), int(c.get("y", 0))
        scr = self.ctx.screen_for_rect(QRect(x, y, w, h))
        if scr is None:  # monitorius atjungtas: rodom pagrindiniame, nustatymų nekeičiam
            scr = self.ctx.screen_rect()
            x = min(max(x, scr.left()), scr.right() + 1 - w) if w < scr.width() else scr.left()
            y = min(max(y, scr.top()), scr.bottom() - 20)
        else:  # neišlįsti už to monitoriaus kraštų
            if x + w > scr.right() + 1:
                x = max(scr.left(), scr.right() + 1 - w)
            x = max(x, scr.left())
            y = min(max(y, scr.top()), scr.bottom() - 20)
        self.setGeometry(x, y, w, h)

    def _migrate_position(self, w):
        c = self.cfg
        scr = self.ctx.screen_rect()
        x, y = int(c.get("x", 0)), int(c.get("y", 0))
        if x == -1:
            x = scr.x() + (scr.width() - w) // 2
        elif x < 0:
            x = scr.x() + scr.width() + x - max(0, w - int(c.get("width", 300)))
        else:
            x = scr.x() + x
        if y < 0:
            y = scr.y() + scr.height() + y
        else:
            y = scr.y() + y
        c["x"], c["y"], c["pos_v"] = int(x), int(y), 2

    def center_on_screen(self):
        """Centruoja horizontaliai monitoriuje, kuriame dabar yra."""
        scr = self.ctx.screen_for_rect(self.geometry()) or self.ctx.screen_rect()
        self.cfg["x"] = scr.x() + (scr.width() - self.width()) // 2
        self.cfg["y"] = self.y()
        self.cfg["pos_v"] = 2
        self.apply_settings()

    def save_geometry(self):
        c = self.cfg
        c["x"], c["y"], c["pos_v"] = self.x(), self.y(), 2
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
            if len(self._texts) > 1500:  # riba atminčiai (ilgos lenktynės)
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
        style = pal.header_style
        if style == "marker":  # modernus: akcento žymė kairėje, baltas pavadinimas
            p.fillRect(QRectF(0, hh * 0.2, 3, hh * 0.6), pal.accent)
            p.setPen(pal.text)
            self.draw_text(p, QRectF(12, 0, r.width() - 24, hh), title, "tiny")
        elif style == "gold":  # LTH: aukso gradiento linija apačioje, auksinis pavadinimas
            from PySide6.QtGui import QLinearGradient
            g = QLinearGradient(0, 0, r.width(), 0)
            g.setColorAt(0.0, QColor(251, 208, 105))
            g.setColorAt(1.0, QColor(209, 160, 58))
            p.fillRect(QRectF(0, hh - 2, r.width(), 2), g)
            p.fillRect(QRectF(0, hh * 0.22, 3, hh * 0.56), g)
            p.setPen(pal.accent)
            self.draw_text(p, QRectF(12, 0, r.width() - 24, hh), title, "tiny")
        elif style == "tab":  # įstrižas akcento skirtukas po pavadinimu (TV transliacijų stilius)
            from PySide6.QtGui import QPolygonF
            tw = min(r.width() * 0.7, self.text_width(title, "tiny") + hh * 1.6)
            sl = hh * 0.45
            p.setBrush(pal.accent)
            p.drawPolygon(QPolygonF([QPointF(0, 0), QPointF(tw, 0), QPointF(tw - sl, hh), QPointF(0, hh)]))
            p.fillRect(QRectF(0, hh - 2, r.width(), 2), pal.accent)
            p.setPen(pal.ink)
            self.draw_text(p, QRectF(12, 0, tw - sl - 12, hh), title, "tiny")
        elif style == "solid":  # TV grafika: antraštė visa akcento spalvos, baltas tekstas
            p.setPen(pal.text)
            self.draw_text(p, QRectF(10, 0, r.width() - 20, hh), title, "tiny")
        elif style == "plain":
            p.setPen(pal.text)
            self.draw_text(p, QRectF(10, 0, r.width() - 20, hh), title, "tiny")
        else:  # "line"
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
        if c.get("hide_in_garage") and snap.in_garage:
            return False
        if c.get("hide_when_spectating") and (snap.watching or snap.replay):
            return False
        if c.get("race_only") and snap.session_type != "race":  # seni nustatymai (iki v0.6)
            return False
        sess = c.get("sessions")
        if isinstance(sess, dict) and sess.get(snap.session_type, True) is False:
            return False
        return True

    def push(self, snap, force=False):
        self._snap = snap
        key = self.content_key(snap)
        if not force and key == self._key:
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
            win32.make_overlay(self, click_through=not (self.editing or self.INTERACTIVE))
            self._native_ready = True
        self._update_fast()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._update_fast()

    # ---------------- greitas kelias (Inputs, Dash...) ----------------
    def fast_hz(self) -> int:
        if not self.FAST_CAPABLE or self.preview_mode or not self.cfg.get("smooth", True):
            return 0
        hz = int(self.cfg.get("smooth_hz", 60) or 60)
        cap = int(self.ctx.config.data.get("fps_cap", 0) or 0)  # Eco: bendra viršutinė riba
        return min(hz, cap) if cap > 0 else hz

    def _update_fast(self):
        hz = self.fast_hz() if self.isVisible() else 0
        t = getattr(self, "_fast_timer", None)
        if hz <= 0:
            if t is not None:
                t.stop()
            return
        if t is None:
            from PySide6.QtCore import QTimer
            t = self._fast_timer = QTimer(self)
            t.setTimerType(Qt.TimerType.PreciseTimer)
            t.timeout.connect(self._on_fast)
        t.setInterval(max(8, int(1000 / hz)))
        if not t.isActive():
            t.start()

    def fast_source(self):
        """Gyvas laiko variklis (None - be iRacing: tada piešiama iš momentinės būsenos)."""
        eng = getattr(self.ctx, "engine", None)
        timing = getattr(eng, "timing", None)
        if timing is None or not getattr(eng, "connected", False) or timing.frame is None:
            return None
        return timing

    def fast_active(self) -> bool:
        t = getattr(self, "_fast_timer", None)
        return t is not None and t.isActive() and self.fast_source() is not None

    IDLE_HZ = 12  # kai stovi (garaže, boksuose, po finišo) - greitas kelias sulėtinamas

    def _on_fast(self):
        timing = self.fast_source()
        if timing is None:
            return
        if not self.editing and self.IDLE_THROTTLE and getattr(self.ctx, "idle", False):
            now = time.perf_counter()
            if now - getattr(self, "_last_fast", 0.0) < 1.0 / self.IDLE_HZ:
                return
            self._last_fast = now
        t0 = time.perf_counter()
        try:
            if self.fast_tick(timing):
                self.update()
        except Exception:  # noqa: BLE001 - laikmatis neturi nulaužti programos
            pass
        self.cost_s += time.perf_counter() - t0

    IDLE_THROTTLE = True  # stovint (garaže, boksuose) sklandūs valdikliai sulėtinami iki IDLE_HZ

    def fast_tick(self, timing) -> bool:
        return False

    def set_editing(self, on: bool):
        self.editing = on
        self.setMouseTracking(on)
        if not on:
            self.unsetCursor()
            self._drag = None
        if win32.IS_WIN:
            win32.set_click_through(self, not (on or self.INTERACTIVE))
        else:
            vis = self.isVisible()
            self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, not (on or self.INTERACTIVE))
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

    cost_s = 0.0  # kiek CPU laiko suvalgė piešimas + fast_tick (Performance puslapiui)

    def paintEvent(self, e):
        t0 = time.perf_counter()
        self._paint(e)
        self.cost_s += time.perf_counter() - t0

    def _paint(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        self._drew_bg = False
        shape = getattr(self.pal, "shape", "round")
        if shape != "round":  # temos forma (nukirsti kampai / pasvirę šonai): viskas piešiama formos viduje
            p.setClipPath(self.shape_path(QRectF(self.rect())))
        self.paint_content(p)
        if shape != "round":
            p.setClipping(False)
        if self._drew_bg:
            self._paint_outline(p)
        if self.editing and not self.preview_mode:
            self._paint_edit(p)
        p.end()

    # ---------------- temos forma ----------------
    def shape_cut(self) -> float:
        return max(5.0, min(14.0, self.fonts.em_small * 0.9))

    def shape_path(self, r: QRectF):
        """Valdiklio kontūras pagal temą: chamfer - nukirsti viršutinis kairys ir apatinis dešinys kampai,
        slant - abu šonai pasvirę (lyg greitis)."""
        from PySide6.QtGui import QPainterPath, QPolygonF
        path = QPainterPath()
        shape = getattr(self.pal, "shape", "round")
        c = min(self.shape_cut(), r.height() / 3, r.width() / 4)
        if shape == "chamfer":
            path.addPolygon(QPolygonF([QPointF(r.left() + c, r.top()), QPointF(r.right(), r.top()),
                                       QPointF(r.right(), r.bottom() - c), QPointF(r.right() - c, r.bottom()),
                                       QPointF(r.left(), r.bottom()), QPointF(r.left(), r.top() + c)]))
        elif shape == "slant":
            path.addPolygon(QPolygonF([QPointF(r.left() + c, r.top()), QPointF(r.right(), r.top()),
                                       QPointF(r.right() - c, r.bottom()), QPointF(r.left(), r.bottom())]))
        else:
            path.addRoundedRect(r, self.pal.radius, self.pal.radius)
        path.closeSubpath()
        return path

    # ---------------- kontūras (stroke) ----------------
    def outline_style(self):
        """(storis, QColor) arba None. Valdiklio nustatymas arba globalus (Appearance)."""
        c = self.cfg
        mode = c.get("outline_mode", "global")
        if mode == "off":
            return None
        if mode == "custom":
            width = float(c.get("outline_width", 1.5) or 0)
            color = c.get("outline_color") or "accent"
            opacity = float(c.get("outline_opacity", 0.8))
        else:
            g = self.ctx.config.data.get("outline") or {}
            width = float(g.get("width", 1.0) or 0)
            color = g.get("color", "accent")
            opacity = float(g.get("opacity", 0.5))
        if width <= 0:
            return None
        if isinstance(color, str) and color.startswith("#"):
            col = QColor(color)
        else:
            col = QColor(getattr(self.pal, color, self.pal.accent))
        col.setAlpha(int(255 * max(0.0, min(1.0, opacity))))
        return width, col

    def _paint_outline(self, p: QPainter):
        st = self.outline_style()
        if st is None:
            return
        width, col = st
        rad = self._drew_bg if not isinstance(self._drew_bg, bool) else self.pal.radius
        dpr = self.devicePixelRatioF()
        shape = getattr(self.pal, "shape", "round")
        key = (self.width(), self.height(), width, col.rgba(), rad, dpr, shape)
        cache = getattr(self, "_outline_pm", None)
        if cache is None or cache[0] != key:  # antialiasintas kontūras kainuoja - piešiam vieną kartą
            from PySide6.QtGui import QPixmap
            pm = QPixmap(max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr)))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            q.setPen(QPen(col, width))
            q.setBrush(Qt.BrushStyle.NoBrush)
            inner = QRectF(self.rect()).adjusted(width / 2, width / 2, -width / 2, -width / 2)
            if shape == "round":
                q.drawRoundedRect(inner, rad, rad)
            else:
                q.drawPath(self.shape_path(inner))
            q.end()
            cache = self._outline_pm = (key, pm)
        pm = cache[1]
        w, h = self.width(), self.height()
        edge = rad if shape == "round" else self.shape_cut()
        b = int(min(min(w, h) / 2, edge + width + 2))  # tik kraštų juostos, ne visas paveikslėlis
        if shape == "slant":
            p.drawPixmap(0, 0, pm)  # pasvirę šonai eina per visą aukštį
            return
        for x, y, bw, bh in ((0, 0, w, b), (0, h - b, w, b), (0, b, b, h - 2 * b), (w - b, b, b, h - 2 * b)):
            if bw > 0 and bh > 0:
                p.drawPixmap(QRectF(x, y, bw, bh), pm, QRectF(x * dpr, y * dpr, bw * dpr, bh * dpr))

    # ---------------- redagavimo rėmelis ----------------
    def _edit_font(self):
        f = getattr(self, "_edit_f", None)
        if f is None:
            from .control.style import ui_font
            from PySide6.QtGui import QFont, QFontMetricsF
            f = ui_font(11, QFont.Weight.DemiBold)
            self._edit_f = f
            self._edit_m = QFontMetricsF(f)
        return f

    def _edit_rects(self):
        """(pavadinimo juostelė, Settings mygtukas) - fiksuoto dydžio, nepriklauso nuo valdiklio mastelio."""
        self._edit_font()
        m = self._edit_m
        size = f"{self.width()}×{self.height()} · {self._scale() * 100:.0f}%"
        label = f"{self.TITLE}  {size}"
        w = self.width()
        tw = m.horizontalAdvance(label) + 18
        full = m.horizontalAdvance("Settings") + 34
        room = w - 4 - CORNER - 2  # iki viršutinio dešinio kampo rankenėlės
        gw = full if tw + 6 + full <= room or room - full - 6 >= 90 else 26
        cw = max(40, min(tw, room - gw - 6))
        chip = QRectF(4, 4, cw, 22)
        gear = QRectF(chip.right() + 6, 4, gw, 22)
        return chip, gear, label

    def _paint_edit(self, p: QPainter):
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        gold = QColor(236, 190, 88)
        p.setPen(QPen(gold, 1.5, Qt.PenStyle.DashLine))
        p.setBrush(QColor(236, 190, 88, 22))
        p.drawRoundedRect(r, 6, 6)
        chip, gear, label = self._edit_rects()
        p.setFont(self._edit_font())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(236, 190, 88, 240))
        p.drawRoundedRect(chip, 5, 5)
        p.setPen(QColor(20, 16, 6))
        p.drawText(chip.adjusted(9, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter,
                   self._edit_m.elidedText(label, Qt.TextElideMode.ElideRight, chip.width() - 12))
        # Settings mygtukas: aiškiai matoma vieta nustatymams atidaryti
        hover = getattr(self, "_hover_gear", False)
        p.setPen(QPen(gold, 1))
        p.setBrush(QColor(236, 190, 88) if hover else QColor(14, 14, 18, 235))
        p.drawRoundedRect(gear, 5, 5)
        col = QColor(20, 16, 6) if hover else gold
        self._draw_gear(p, QPointF(gear.x() + 13, gear.center().y()), 5.2, col)
        if gear.width() > 30:
            p.setPen(col)
            p.drawText(gear.adjusted(24, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, "Settings")
        # rankenėlės: kampai (mastelis) ir kraštų vidurys (plotis / aukštis)
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor(0, 0, 0, 160), 1))
        p.setBrush(gold)
        for x, y in ((0, 0), (w, 0), (0, h), (w, h)):
            p.drawRoundedRect(QRectF(min(max(x - 5, 1), w - 11), min(max(y - 5, 1), h - 11), 10, 10), 2, 2)
        p.setBrush(QColor(255, 255, 255))
        for x, y in ((w / 2, 0), (w / 2, h), (0, h / 2), (w, h / 2)):
            p.drawRoundedRect(QRectF(min(max(x - 4, 1), w - 9), min(max(y - 4, 1), h - 9), 8, 8), 2, 2)

    @staticmethod
    def _draw_gear(p: QPainter, c: QPointF, rad: float, col: QColor):
        import math
        p.save()
        p.setPen(QPen(col, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(QPointF(c.x() + math.cos(a) * rad * 0.75, c.y() + math.sin(a) * rad * 0.75),
                       QPointF(c.x() + math.cos(a) * rad * 1.25, c.y() + math.sin(a) * rad * 1.25))
        p.setPen(QPen(col, 1.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, rad * 0.78, rad * 0.78)
        p.restore()

    # ---------------- redagavimas pele ----------------
    def _zone(self, pos) -> str:
        x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
        if self._edit_rects()[1].contains(QPointF(pos)):
            return "gear"
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
        if zone == "gear":
            self.ctx.open_settings(self.NAME)
            return
        self._drag = (zone, e.globalPosition().toPoint(), self.geometry(), self._scale())

    def leaveEvent(self, e):
        if getattr(self, "_hover_gear", False):
            self._hover_gear = False
            self.update()

    def mouseDoubleClickEvent(self, e):
        """Dvigubas spustelėjimas redaguojant: aukštis vėl pagal turinį."""
        if self.editing and self._zone(e.position().toPoint()) == "gear":
            return
        if self.editing and self.HEIGHT_MODE != "auto":
            self.cfg["height"] = None
            self._drag = None
            self.apply_settings()
            self.save_geometry()

    def mouseMoveEvent(self, e):
        if not self.editing:
            return
        if self._drag is None:
            zone = self._zone(e.position().toPoint())
            self.setCursor(_CURSORS[zone])
            if (zone == "gear") != getattr(self, "_hover_gear", False):
                self._hover_gear = zone == "gear"
                self.update()
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
        self.fonts = self._make_fonts(self._scale())
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
        c["x"], c["y"], c["pos_v"] = pos.x(), pos.y(), 2
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
        for _, sg in self.ctx.screens():  # visų monitorių kraštai
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
