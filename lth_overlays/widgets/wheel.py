"""GT3 stiliaus D formos vairas (be jokių žymių) ir stabilus pėdsakų mažinimas Inputs valdikliui."""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap


# ---------------------------------------------------------------- pėdsakai
def decimate(vals: np.ndarray, seq: int, buckets: int):
    """Sumažina taškų skaičių nemirksint: grupės pririštos prie absoliutaus mėginio numerio (seq - paskutinio
    mėginio numeris), todėl kadras po kadro ta pati grupė turi tuos pačius mėginius ir tik pasislenka.
    Iš kiekvienos grupės paimamas min ir max (laiko tvarka), todėl trumpi pikai niekada nedingsta.

    Grąžina (indeksai vals masyve, reikšmės)."""
    n = len(vals)
    if n < 2:
        return np.arange(n), vals
    stride = max(1, int(math.ceil(n / max(1, buckets))))
    if stride == 1:
        return np.arange(n), vals
    a0 = int(seq) - n + 1  # vals[0] absoliutus numeris
    off = (-a0) % stride
    k = (n - off) // stride
    idx_parts, val_parts = [], []
    if off:  # seniausia (iš dalies išslinkusi) grupė
        idx_parts.append(np.array([0, off - 1]))
    if k > 0:
        block = vals[off:off + k * stride].reshape(k, stride)
        i_min = block.argmin(axis=1)
        i_max = block.argmax(axis=1)
        first = np.minimum(i_min, i_max)
        second = np.maximum(i_min, i_max)
        base = off + np.arange(k) * stride
        pair = np.empty(2 * k, dtype=np.int64)
        pair[0::2] = base + first
        pair[1::2] = base + second
        idx_parts.append(pair)
    tail = off + k * stride
    if tail < n:  # naujausia (dar pildoma) grupė - visi jos mėginiai
        idx_parts.append(np.arange(tail, n))
    idx = np.concatenate(idx_parts)
    idx = idx[np.concatenate(([True], np.diff(idx) != 0))]
    return idx, vals[idx]


def runs(mask: np.ndarray):
    """[(pradžia, pabaiga)] ištisinės True atkarpos (pabaiga imtinai)."""
    if mask is None or not len(mask):
        return []
    m = np.concatenate(([False], mask.astype(bool), [False]))
    d = np.diff(m.astype(np.int8))
    starts = np.nonzero(d == 1)[0]
    ends = np.nonzero(d == -1)[0] - 1
    return list(zip(starts.tolist(), ends.tolist()))


# ---------------------------------------------------------------- vairas
def _d_path(r: float, flat: float = 0.70) -> QPainterPath:
    """D forma: apvalus viršus, tiesi apačia (flat - apačios atstumas nuo centro, r dalimis)."""
    p = QPainterPath()
    a = math.degrees(math.asin(min(0.999, flat)))
    rect = QRectF(-r, -r, 2 * r, 2 * r)
    p.moveTo(-math.cos(math.radians(a)) * r, r * flat)
    p.arcTo(rect, 180 + a, -(180 + 2 * a))
    p.closeSubpath()
    return p


class GT3Wheel:
    """Paruoštas (nepasuktas) vairo paveikslėlis; kas kadrą tik pasukamas - pigu net 60 fps."""

    def __init__(self):
        self._key = None
        self._pm = None

    def pixmap(self, size: float, dpr: float) -> QPixmap:
        key = (round(size, 1), dpr)
        if key == self._key and self._pm is not None:
            return self._pm
        s = int(math.ceil(size * dpr)) + 2
        pm = QPixmap(s, s)
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.translate(s / dpr / 2, s / dpr / 2)
        r = size / 2 * 0.94
        ring = r * 0.17
        rim = _d_path(r - ring / 2)
        q.setBrush(Qt.BrushStyle.NoBrush)
        q.setPen(QPen(QColor(0, 0, 0, 170), ring + max(2.0, r * 0.03), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        q.drawPath(rim)
        g = QLinearGradient(0, -r, 0, r)
        g.setColorAt(0, QColor(118, 121, 128))
        g.setColorAt(0.5, QColor(78, 80, 86))
        g.setColorAt(1, QColor(52, 54, 58))
        q.setPen(QPen(QBrush(g), ring, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        q.drawPath(rim)
        # raudona centro žymė ratlankio viršuje (12 val.) - matosi, kiek tiksliai pasuktas vairas
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(QColor(232, 36, 43))
        mw = max(2.5, ring * 0.55)
        q.drawRoundedRect(QRectF(-mw / 2, -r - 0.5, mw, ring + 1.0), mw * 0.25, mw * 0.25)
        pw, ph = r * 1.18, r * 0.78
        plate = QPainterPath()
        plate.addRoundedRect(QRectF(-pw / 2, -ph * 0.52, pw, ph), r * 0.16, r * 0.16)
        wing = QPainterPath()
        wing.addRoundedRect(QRectF(-(r - ring * 0.6), -ph * 0.22, 2 * (r - ring * 0.6), ph * 0.40),
                            ph * 0.12, ph * 0.12)
        body = plate.united(wing)
        cg = QLinearGradient(0, -ph / 2, 0, ph / 2)
        cg.setColorAt(0, QColor(58, 60, 66))
        cg.setColorAt(1, QColor(28, 29, 33))
        q.setPen(QPen(QColor(0, 0, 0, 200), max(1.0, r * 0.012)))
        q.setBrush(QBrush(cg))
        q.drawPath(body)
        q.drawRoundedRect(QRectF(-r * 0.10, ph * 0.20, r * 0.20, (r - ring) * 0.70 - ph * 0.20 + 2), 3, 3)
        q.end()
        self._key, self._pm = key, pm
        return pm

    def draw(self, p: QPainter, center: QPointF, size: float, steer_rad: float, dpr: float):
        """steer_rad - iRacing SteeringWheelAngle: teigiamas = į kairę (prieš laikrodžio rodyklę)."""
        pm = self.pixmap(size, dpr)
        half = pm.width() / dpr / 2
        p.save()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.translate(center)
        p.rotate(-math.degrees(steer_rad))  # Qt: teigiamas kampas = pagal laikrodžio rodyklę
        p.drawPixmap(QPointF(-half, -half), pm)
        p.restore()
