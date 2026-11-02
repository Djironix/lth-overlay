"""Šalių vėliavos (flag-icons, MIT) iš vieno sprite failo."""
from __future__ import annotations

import json
import os

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

_DIR = os.path.join(os.path.dirname(__file__), "data", "flags")
_sprite = None
_index = None
_cache = {}


def _load():
    global _sprite, _index
    if _index is None:
        try:
            with open(os.path.join(_DIR, "flags.json"), encoding="utf-8") as fh:
                _index = json.load(fh)
            _sprite = QPixmap(os.path.join(_DIR, "flags.png"))
        except (OSError, ValueError):
            _index, _sprite = {"codes": {}}, QPixmap()


def flag_pixmap(code: str) -> QPixmap | None:
    """Vėliava 48×36 px (arba None, jei šalies nėra)."""
    if not code:
        return None
    pm = _cache.get(code)
    if pm is None and code not in _cache:
        _load()
        i = _index.get("codes", {}).get(code)
        if i is None or _sprite.isNull():
            _cache[code] = None
            return None
        w, h, cols = _index["w"], _index["h"], _index["cols"]
        pm = _sprite.copy((i % cols) * w, (i // cols) * h, w, h)
        _cache[code] = pm
    return pm


def draw_flag(p: QPainter, rect: QRectF, code: str, radius: float = 2.0) -> bool:
    """Vėliava per rect vidurį (4:3), su ploniu kontūru - kad balta vėliava matytųsi ant šviesaus fono."""
    pm = flag_pixmap(code)
    if pm is None:
        return False
    h = min(rect.height(), rect.width() * 0.75)
    w = h * 4 / 3
    r = QRectF(rect.x() + (rect.width() - w) / 2, rect.y() + (rect.height() - h) / 2, w, h)
    p.save()
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    from PySide6.QtGui import QPainterPath
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    p.setClipPath(path)
    p.drawPixmap(r, pm, QRectF(pm.rect()))
    p.setClipping(False)
    p.setPen(QPen(QColor(0, 0, 0, 90), 0.8))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(r, radius, radius)
    p.restore()
    return True


_styled = {}


def draw_flag_styled(p: QPainter, rect: QRectF, code: str, style: str = "flat", frame: str = "none",
                     accent: QColor | None = None, radius: float = 1.5, dpr: float = 1.0) -> bool:
    """Vėliava su stiliumi: flat (plokščia) arba 3d (banguojanti, su blizgesiu ir šešėliu), ir su rėmeliu
    (none / dark / white / accent). Paruoštas paveikslėlis talpinamas - piešti kas kadrą pigu."""
    if style == "flat" and frame == "none":
        return draw_flag(p, rect, code, radius)
    src = flag_pixmap(code)
    if src is None:
        return False
    h = min(rect.height(), rect.width() * 0.75)
    w = h * 4 / 3
    acc = accent.rgba() if accent is not None else 0
    key = (code, round(w, 1), round(h, 1), style, frame, acc, round(radius, 1), dpr)
    pm = _styled.get(key)
    if pm is None:
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QLinearGradient, QPainterPath
        pad = 2.0  # vieta šešėliui / rėmeliui
        W, H = w + pad * 2, h + pad * 2
        pm = QPixmap(max(1, int(W * dpr)), max(1, int(H * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(pad, pad, w, h)
        wave = style == "3d"
        amp = h * 0.07 if wave else 0.0
        if wave:  # šešėlis po vėliava
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(QColor(0, 0, 0, 70))
            q.drawRoundedRect(r.translated(0.8, 1.2), radius, radius)
        # vėliavos audinys: vertikalios juostelės pastumtos pagal sinusą (banga)
        n = 16 if wave else 1
        sw = w / n
        path = QPainterPath()
        if wave:
            import math
            top = [QPointF(r.x() + i * sw, r.y() + amp * math.sin(i / n * math.pi * 1.6)) for i in range(n + 1)]
            path.moveTo(top[0])
            for t in top[1:]:
                path.lineTo(t)
            for t in reversed(top):
                path.lineTo(QPointF(t.x(), t.y() + h - amp))
            path.closeSubpath()
            q.save()
            q.setClipPath(path)
            sx = src.width() / n
            for i in range(n):
                import math as _m
                off = amp * _m.sin((i + 0.5) / n * _m.pi * 1.6)
                q.drawPixmap(QRectF(r.x() + i * sw - 0.3, r.y() + off, sw + 0.6, h - amp),
                             src, QRectF(i * sx, 0, sx, src.height()))
            # blizgesys ir šešėliai klostėse
            g = QLinearGradient(r.topLeft(), r.topRight())
            for i in range(n + 1):
                import math as _m
                v = _m.cos(i / n * _m.pi * 1.6)
                c = QColor(255, 255, 255, int(55 * max(0.0, v))) if v > 0 else QColor(0, 0, 0, int(70 * -v))
                g.setColorAt(i / n, c)
            q.fillRect(r.adjusted(0, -amp, 0, amp), g)
            gv = QLinearGradient(r.topLeft(), r.bottomLeft())
            gv.setColorAt(0.0, QColor(255, 255, 255, 60))
            gv.setColorAt(0.45, QColor(255, 255, 255, 0))
            gv.setColorAt(1.0, QColor(0, 0, 0, 60))
            q.fillRect(r.adjusted(0, -amp, 0, amp), gv)
            q.restore()
        else:
            path.addRoundedRect(r, radius, radius)
            q.save()
            q.setClipPath(path)
            q.drawPixmap(r, src, QRectF(src.rect()))
            q.restore()
        # rėmelis
        fc = {"dark": QColor(0, 0, 0, 200), "white": QColor(255, 255, 255, 230),
              "accent": QColor(accent) if accent is not None else QColor(236, 190, 88)}.get(frame)
        q.setBrush(Qt.BrushStyle.NoBrush)
        if fc is not None:
            q.setPen(QPen(fc, max(1.2, h * 0.09)))
        else:
            q.setPen(QPen(QColor(0, 0, 0, 90), 0.8))
        q.drawPath(path)
        q.end()
        if len(_styled) > 400:
            _styled.clear()
        _styled[key] = pm
    W = pm.width() / pm.devicePixelRatio()
    H = pm.height() / pm.devicePixelRatio()
    from PySide6.QtCore import QPointF
    p.drawPixmap(QPointF(rect.x() + (rect.width() - W) / 2, rect.y() + (rect.height() - H) / 2), pm)
    return True


# Lenktynių vėliavos (Flags valdiklis ir būsenos ženkliukai lentelėse): (fonas, tekstas)
RACE_FLAG_STYLE = {
    "disqualify": ((10, 10, 10), (255, 255, 255)), "black": ((10, 10, 10), (255, 255, 255)),
    "repair": ((10, 10, 10), (255, 150, 40)), "red": ((215, 30, 40), (255, 255, 255)),
    "caution_waving": ((250, 205, 20), (20, 20, 20)), "caution": ((250, 205, 20), (20, 20, 20)),
    "yellow_waving": ((250, 205, 20), (20, 20, 20)), "yellow": ((250, 205, 20), (20, 20, 20)),
    "debris": ((250, 205, 20), (180, 30, 30)), "blue": ((30, 110, 230), (255, 255, 255)),
    "white": ((245, 245, 245), (20, 20, 20)), "checkered": ((245, 245, 245), (10, 10, 10)),
    "one_to_green": ((40, 170, 80), (255, 255, 255)), "green": ((40, 170, 80), (255, 255, 255)),
    "formation": ((40, 44, 52), (255, 255, 255)),
}


def paint_race_flag(p, r: QRectF, key: str, wave: float = 0.0, rad: float = 0.0):
    """Vėliavos audinys (su raštu) - stačiakampis arba banguojantis (wave > 0)."""
    from PySide6.QtGui import QLinearGradient, QPainterPath
    bg, _fg = RACE_FLAG_STYLE.get(key, ((60, 60, 60), (255, 255, 255)))
    path = QPainterPath()
    if wave > 0:
        n = 24
        top = [QPointF(r.x() + r.width() * i / n, r.y() + wave * math.sin(i / n * 2 * math.pi * 1.2) * (i / n))
               for i in range(n + 1)]
        bot = [QPointF(q.x(), q.y() + r.height()) for q in top]
        path.moveTo(top[0])
        for q in top[1:]:
            path.lineTo(q)
        for q in reversed(bot):
            path.lineTo(q)
        path.closeSubpath()
    else:
        path.addRoundedRect(r, rad, rad)
    p.save()
    p.setClipPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.fillRect(r.adjusted(0, -wave * 2, 0, wave * 2), QColor(*bg))
    if key == "checkered":
        n = 6
        s = r.width() / n
        rows = int(r.height() / s + 2)
        for i in range(n + 1):
            for j in range(-1, rows + 1):
                if (i + j) % 2:
                    p.fillRect(QRectF(r.x() + i * s, r.y() + j * s - wave, s, s), QColor(15, 15, 15))
    elif key == "debris":
        w = r.width() / 7
        for i in range(1, 7, 2):
            p.fillRect(QRectF(r.x() + i * w, r.y() - wave * 2, w, r.height() + wave * 4), QColor(210, 35, 35))
    elif key == "repair":
        d = min(r.width(), r.height()) * 0.5
        p.setBrush(QColor(255, 120, 20))
        p.drawEllipse(r.center(), d / 2, d / 2)
    elif key in ("black", "disqualify"):
        p.setPen(QPen(QColor(255, 255, 255, 60), max(1.0, r.height() * 0.03)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r.adjusted(r.width() * 0.08, r.height() * 0.1, -r.width() * 0.08, -r.height() * 0.1))
    elif key == "blue" and (r.height() > 24 or abs(r.width() - r.height()) < 1):  # ne plonoje juostoje
        p.setPen(QPen(QColor(250, 205, 20), max(2.0, r.height() * 0.12)))
        p.drawLine(QPointF(r.left(), r.bottom()), QPointF(r.right(), r.top()))
    # šešėliai - kad atrodytų kaip audinys
    g = QLinearGradient(r.topLeft(), r.topRight())
    for k in range(7):
        g.setColorAt(k / 6, QColor(0, 0, 0, 0 if k % 2 == 0 else (46 if wave else 18)))
    p.fillRect(r.adjusted(0, -wave * 2, 0, wave * 2), g)
    sh = QLinearGradient(r.topLeft(), r.bottomLeft())
    sh.setColorAt(0.0, QColor(255, 255, 255, 40))
    sh.setColorAt(0.5, QColor(255, 255, 255, 0))
    sh.setColorAt(1.0, QColor(0, 0, 0, 40))
    p.fillRect(r.adjusted(0, -wave * 2, 0, wave * 2), sh)
    p.restore()

