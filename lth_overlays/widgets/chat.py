"""Stream chat (Twitch + YouTube) ekrane ir OBS."""
from __future__ import annotations

import time
import zlib

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter

from ..chat import demo_messages
from .panel import PanelWidget

PLATFORM = {"t": ("#9146FF", "T"), "y": ("#FF0033", "Y")}
NAME_COLORS = ("#ff7a7a", "#ffb35c", "#f5d76e", "#8be28b", "#5fd3c6", "#6fb6ff", "#a991ff", "#f08cd8",
               "#ecbe58", "#7fe0ff")
FADE_MS = 1.5  # kiek sekundžių blėsta


def name_color(m) -> str:
    if m.color:
        return m.color
    return NAME_COLORS[zlib.crc32(m.author.encode("utf-8", "replace")) % len(NAME_COLORS)]


class ChatWidget(PanelWidget):
    NAME = "chat"
    TITLE = "Stream chat"
    HEIGHT_MODE = "free"
    MIN_WIDTH = 180
    MIN_HEIGHT = 80
    OBS_ALWAYS = True  # OBS rodo chat ir kai iRacing išjungtas

    def __init__(self, ctx):
        self._msgs = []
        self._status = {}
        super().__init__(ctx)

    def desired_height(self) -> int:
        return int(self.fonts.em_base * 14)

    def _hub(self):
        return getattr(self.ctx, "chat", None)

    def content_key(self, snap):
        c = self.cfg
        n = int(c.get("max_messages", 30) or 30)
        hub = self._hub()
        live = hub is not None and (not self.preview_mode or self.obs_mode)
        msgs, status, seq = [], {}, 0
        if live:
            hub.configure(c.get("twitch", ""), c.get("youtube", ""))
            hub.touch()
            seq, msgs, status = hub.snapshot(n)
        demo = not msgs and (self.editing or (self.preview_mode and not self.obs_mode) or self.obs_demo)
        if demo:
            msgs = demo_messages()
            seq = -1
        fade = float(c.get("fade", 0) or 0)
        now = time.time()
        if fade > 0 and not demo:
            msgs = [m for m in msgs if now - m.ts < fade]
        self._msgs = msgs
        self._status = status
        self._fade_now = now
        bucket = int(now * 4) if fade > 0 and msgs else 0  # blėsimui - 4 kartai per sekundę
        return (seq, tuple(m.mid for m in msgs), tuple(sorted(status.items())), bucket, self.width(),
                self.height(), self.editing, demo)

    # ---- teksto laužymas ----
    def _wrap(self, text: str, first_w: float, w: float, font: str) -> list:
        lines, cur, avail = [], "", first_w
        for word in text.replace("\n", " ").split(" "):
            cand = word if not cur else cur + " " + word
            if self.text_width(cand, font) <= avail:
                cur = cand
                continue
            if cur:
                lines.append(cur)
                avail = w
                cur = ""
            while self.text_width(word, font) > avail and len(word) > 1:  # labai ilgas žodis
                k = len(word)
                while k > 1 and self.text_width(word[:k], font) > avail:
                    k -= 1
                lines.append(word[:k])
                avail = w
                word = word[k:]
            cur = word
        if cur or not lines:
            lines.append(cur)
        return lines

    def paint_content(self, p: QPainter):
        c = self.cfg
        title = "CHAT"
        right = ""
        st = self._status
        bad = [f"{'Twitch' if k == 't' else 'YouTube'}: {v}" for k, v in sorted(st.items()) if v and v != "live"]
        if bad:
            right = bad[0]
        elif not (c.get("twitch") or c.get("youtube")) and self.editing:
            right = "set channel in settings"
        y0 = self.card(p, title, right)
        pad = self.pad()
        x0 = pad * 1.2
        w = self.width() - 2 * x0
        lh = round(self.fonts.em_base * 1.3)
        show_plat = c.get("show_platform", True)
        badge = self.fonts.em_small * 1.35 if show_plat else 0.0
        fade = float(c.get("fade", 0) or 0)
        now = getattr(self, "_fade_now", time.time())
        # nuo apačios į viršų: naujausia žinutė - apačioje
        y = self.height() - pad * 0.8
        p.save()
        p.setClipRect(QRectF(0, y0, self.width(), self.height() - y0))
        for m in reversed(self._msgs):
            author = m.author + (" " if m.kind == "action" else ":  ")
            aw = self.text_width(author, "bold")
            lead = badge + (pad * 0.5 if badge else 0)
            text = m.text
            lines = self._wrap(text, max(w * 0.25, w - lead - aw), w - lead, "base")
            h = lh * len(lines) + lh * 0.18
            y -= h
            if y + h < y0:
                break
            alpha = 1.0
            if fade > 0 and m.mid and not str(m.mid).startswith("demo"):
                left = fade - (now - m.ts)
                alpha = max(0.0, min(1.0, left / FADE_MS))
            p.setOpacity(alpha)
            if m.kind in ("paid", "member"):
                hl = QColor(self.pal.accent)
                hl.setAlpha(40)
                p.fillRect(QRectF(x0 - pad * 0.5, y, w + pad, h), hl)
            if badge:
                col, letter = PLATFORM.get(m.platform, ("#888888", "?"))
                br = QRectF(x0, y + (lh - badge) / 2, badge, badge)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(col))
                p.drawRoundedRect(br, 3, 3)
                p.setPen(QColor(255, 255, 255))
                self.draw_text(p, br, letter, "tiny", "c")
            xa = x0 + lead
            p.setPen(QColor(name_color(m)))
            self.draw_text(p, QRectF(xa, y, aw + 2, lh), author, "bold")
            p.setPen(self.pal.text if m.kind != "action" else QColor(name_color(m)))
            for i, ln in enumerate(lines):
                lx = xa + aw if i == 0 else xa
                self.draw_text(p, QRectF(lx, y + i * lh, w - (lx - x0), lh), ln, "base")
        p.restore()
        p.setOpacity(1.0)
