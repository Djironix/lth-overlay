"""Rain Master: lietaus call juostelė virš Weather ir atskiras patarimų valdiklis.

Call juostelė - atskiras mažas langas, prilipęs prie Weather valdiklio viršaus
(arba apačios, jei viršuje nėra vietos). Weather turinys dėl jos nepajuda.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPainter
from PySide6.QtWidgets import QWidget

from lth_timing import rain_tips

from .. import win32
from .panel import PanelWidget

KIND_COLOR = {"tyres": "yellow", "change": "blue", "drive": "dim"}
STOPPED_MS = 2.0  # m/s - laikom, kad stovi (išskleidžiam patarimus)


class CallStrip(QWidget):
    """Juostelė su vienu call'u virš Weather valdiklio. Pelė eina kiaurai."""

    def __init__(self, owner):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
                 | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.NoDropShadowWindowHint)
        if not win32.IS_WIN:
            flags |= Qt.WindowType.WindowTransparentForInput
        super().__init__(None, flags)
        self.owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.call = None
        self._native = False

    def showEvent(self, e):
        super().showEvent(e)
        if not self._native:
            win32.make_overlay(self, click_through=True)
            self._native = True

    def set_call(self, call):
        self.call = call
        self.follow()
        self.update()

    def follow(self):
        o = self.owner
        h = int(o.fonts.em_base * 1.75)
        gap = 4
        y = o.y() - h - gap
        scr = o.ctx.screen_for_rect(o.geometry()) or o.ctx.screen_rect()
        if y < scr.top():  # viršuje nėra vietos - po valdikliu
            y = o.y() + o.height() + gap
        self.setGeometry(o.x(), y, o.width(), h)

    def paintEvent(self, e):
        if self.call is None:
            return
        o = self.owner
        pal = o.pal
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        col = getattr(pal, KIND_COLOR.get(self.call.kind, "text"))
        bg = QColor(pal.bg)
        bg.setAlpha(max(bg.alpha(), 215))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, pal.radius, pal.radius)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(0, 0, 5, r.height()), 2, 2)
        # mažas lašo ženklas
        d = r.height() * 0.32
        p.drawEllipse(QRectF(14, (r.height() - d) / 2, d, d))
        p.setPen(col if self.call.kind != "drive" else pal.text)
        o.draw_text(p, QRectF(14 + d + 10, 0, r.width() - d - 30, r.height()), self.call.text, "bold")


class RainMasterWidget(PanelWidget):
    NAME = "rain_master"
    TITLE = "Rain Master"
    MIN_WIDTH = 240

    def __init__(self, ctx):
        self._tip_i = 0
        self._tip_t = -1e9
        super().__init__(ctx)

    def next_tip(self):
        self._tip_i += 1
        self._tip_t = self._snap.t if self._snap is not None else 0.0
        self._key = object()
        if self._snap is not None:
            self.push(self._snap, force=True)

    def wants_visible(self, snap) -> bool:
        if not super().wants_visible(snap):
            return False
        if self.editing or snap is None:
            return True
        w = snap.weather
        wet = w is not None and w.valid and (w.wetness >= rain_tips.MOSTLY_DRY or w.precipitation > 0.02)
        return wet or snap.rain_call is not None

    def _expanded(self, snap) -> bool:
        mode = self.cfg.get("mode", "auto")
        if mode != "auto":
            return mode == "expanded"
        p = snap.player
        return p is None or p.on_pit_road or p.in_stall or snap.in_garage or snap.replay or p.speed < STOPPED_MS

    def content_key(self, snap):
        w = snap.weather
        p = snap.player
        wet = w.wetness if w is not None and w.valid else 0
        if self.editing and wet < rain_tips.LIGHT:
            wet = rain_tips.LIGHT  # pavyzdys redaguojant
        call = snap.rain_call
        if call is None and self.editing:
            from lth_timing.rain_tips import RainCall, CALLS
            t, k, d = CALLS["wet_tyres"]
            call = RainCall("wet_tyres", t, k, d, True)
        tyres = "WET" if p is not None and p.tyre_compound == 1 else "DRY" if p is not None and p.tyre_compound == 0 \
            else ""
        trend = w.trend if w is not None and w.valid else "stable"
        if w is not None and w.valid and not (self.editing and w.wetness < rain_tips.LIGHT):
            wtext = w.wetness_text
        else:
            wtext = "Lightly wet" if self.editing else ""
        expanded = self._expanded(snap)
        track = snap.track_name if self.cfg.get("track_tips", True) else ""
        tips = rain_tips.tips_for(wet, track)
        if expanded:
            body = tuple(tips[: int(self.cfg.get("max_tips", 6))])
            detail = None
        else:
            body = ()
            # ilgesnis tekstas tik tiesiojoje (nesukam vairo, nestabdom)
            straight = p is None or (abs(p.steer) < 0.12 and p.brake < 0.05)
            if snap.t - self._tip_t < 15 and tips:
                detail = tips[self._tip_i % len(tips)][1]  # „next tip“ klavišas
            elif call is not None and straight:
                detail = call.detail
            else:
                detail = ""
        self._view = (wtext, wet, trend, tyres, None if call is None else (call.text, call.kind), detail, body,
                      expanded)
        return (self._view, self.width())

    # ---- matmenys ----
    def _wrap_h(self, text, width, font="small"):
        m = getattr(self.fonts, "m_" + font, self.fonts.m_small)
        flags = int(Qt.TextFlag.TextWordWrap)
        return m.boundingRect(QRectF(0, 0, width, 1000), flags, text).height()

    def desired_height(self) -> int:
        if self._view is None:
            return self.body_height(2)
        wtext, wet, trend, tyres, call, detail, body, expanded = self._view
        lh = self.lh()
        x0 = self.pad() * 1.4
        w = self.width() - 2 * x0
        h = lh * 1.2  # būsenos eilutė
        if call is not None:
            h += lh * 1.5
        if not expanded:
            h += max(lh, self._wrap_h(detail or " ", w) + 4) if detail is not None else 0
        else:
            for topic, text in body:
                h += lh * 0.8 + self._wrap_h(text, w) + lh * 0.25
        h += lh * 0.9  # prierašas
        return int(self.header_h() + h + self.pad() * 1.4)

    # ---- piešimas ----
    def paint_content(self, p: QPainter):
        if self._view is None:
            return
        wtext, wet, trend, tyres, call, detail, body, expanded = self._view
        pal = self.pal
        y = self.card(p, "RAIN MASTER", wtext)
        lh = self.lh()
        x0 = self.pad() * 1.4
        w = self.width() - 2 * x0
        # būsena: šlapumo segmentai + tendencija + padangos
        seg_w = min(18.0, (w * 0.5 - 6 * 2) / 7)
        for i in range(7):
            on = i < wet
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(pal.blue if on and wet > 1 else (pal.good if on else pal.track))
            p.drawRoundedRect(QRectF(x0 + i * (seg_w + 2), y + lh * 0.35, seg_w, lh * 0.32), 1.5, 1.5)
        tx = x0 + 7 * (seg_w + 2) + 8
        arrow = {"wetter": ("▲ wetter", pal.blue), "drying": ("▼ drying", pal.yellow)}.get(trend)
        if arrow:
            p.setPen(arrow[1])
            self.draw_text(p, QRectF(tx, y, w, lh), arrow[0], "small")
        if tyres:
            tw = self.text_width(tyres, "tiny") + 14
            self.chip(p, QRectF(x0 + w - tw, y + lh * 0.12, tw, lh * 0.76), tyres,
                      pal.blue if tyres == "WET" else pal.track, pal.text, "tiny")
        y += lh * 1.2
        if call is not None:
            text, kind = call
            col = getattr(pal, KIND_COLOR.get(kind, "text"))
            p.setPen(col if kind != "drive" else pal.text)
            self.draw_text(p, QRectF(x0, y, w, lh * 1.4), text, "mid")
            y += lh * 1.5
        flags = int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        p.setFont(self.fonts.small)
        if not expanded:
            if detail:
                p.setPen(pal.text)
                h = self._wrap_h(detail, w)
                p.drawText(QRectF(x0, y + 2, w, h + 2), flags, detail)
                y += max(lh, h + 4)
            elif detail is not None:
                y += lh
        else:
            for topic, text in body:
                p.setPen(pal.accent)
                self.draw_text(p, QRectF(x0, y, w, lh * 0.8), topic.upper(), "tiny")
                y += lh * 0.8
                p.setPen(pal.text)
                p.setFont(self.fonts.small)
                h = self._wrap_h(text, w)
                p.drawText(QRectF(x0, y, w, h + 2), flags, text)
                y += h + lh * 0.25
        p.setPen(pal.dim)
        self.draw_text(p, QRectF(x0, y + lh * 0.1, w, lh * 0.8), "Tips: Regis / LTH Racing", "tiny")


__all__ = ["CallStrip", "RainMasterWidget", "QFontMetricsF"]
