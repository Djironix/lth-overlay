"""Control Center komponentai: jungiklis, kortelės, segmentai, slankikliai, spalvos, stulpelių sąrašas..."""
from __future__ import annotations

from PySide6.QtCore import (Property, QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRectF, QSize, Qt,
                            Signal)
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractButton, QColorDialog, QComboBox, QDoubleSpinBox, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSlider, QVBoxLayout, QWidget)

from .style import T, icon, icon_pixmap, qcolor, ui_font


def label(text: str, role: str | None = None, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if role:
        lb.setProperty("role", role)
    if wrap:
        lb.setWordWrap(True)
    return lb


def button(text: str = "", variant: str | None = None, icon_name: str | None = None, tip: str = "") -> QPushButton:
    b = QPushButton(text)
    if variant:
        b.setProperty("variant", variant)
    if icon_name:
        col = T["accent_text"] if variant == "primary" else (T["bad"] if variant == "danger" else T["text"])
        b.setIcon(icon(icon_name, col, 16))
        b.setIconSize(QSize(16, 16))
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def divider() -> QFrame:
    f = QFrame()
    f.setObjectName("Divider")
    return f


def hbox(*items, spacing=8, margins=(0, 0, 0, 0), stretch_at=None) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for i, it in enumerate(items):
        if stretch_at == i:
            lay.addStretch(1)
        if it is None:
            lay.addStretch(1)
        elif isinstance(it, QWidget):
            lay.addWidget(it)
        else:
            lay.addLayout(it)
    return lay


def vbox(*items, spacing=8, margins=(0, 0, 0, 0)) -> QVBoxLayout:
    lay = QVBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for it in items:
        if it is None:
            lay.addStretch(1)
        elif isinstance(it, QWidget):
            lay.addWidget(it)
        else:
            lay.addLayout(it)
    return lay


# ---------------------------------------------------------------- jungiklis
class Toggle(QAbstractButton):
    """iOS / SaaS stiliaus jungiklis su animacija."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(36, 20)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def _animate(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def set_silent(self, on: bool):
        self.blockSignals(True)
        self.setChecked(on)
        self.blockSignals(False)
        self._pos = 1.0 if on else 0.0
        self.update()

    def _get(self):
        return self._pos

    def _set(self, v):
        self._pos = v
        self.update()

    knob = Property(float, _get, _set)

    def sizeHint(self):
        return QSize(36, 20)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        off, on = qcolor("surface3"), qcolor("accent")
        k = self._pos
        col = QColor(int(off.red() + (on.red() - off.red()) * k), int(off.green() + (on.green() - off.green()) * k),
                     int(off.blue() + (on.blue() - off.blue()) * k))
        if not self.isEnabled():
            col.setAlpha(90)
        p.setPen(QPen(qcolor("border2"), 1) if k < 0.5 else Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 4
        x = r.x() + 2 + (r.width() - d - 4) * k
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255) if k > 0.5 else QColor(200, 200, 210))
        p.drawEllipse(QRectF(x, r.y() + 2, d, d))


# ---------------------------------------------------------------- kortelė
class Card(QFrame):
    def __init__(self, title: str | None = None, subtitle: str | None = None, right=None,
                 padding: int = 18, spacing: int = 12, hover: bool = False):
        super().__init__()
        self.setObjectName("CardHover" if hover else "Card")
        if hover:  # QSS: tas pats stilius + hover
            self.setStyleSheet(f"QFrame#CardHover {{ background: {T['surface']}; border: 1px solid {T['border']};"
                               f" border-radius: 12px; }} QFrame#CardHover:hover {{ border-color: {T['border2']}; }}")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(padding, padding, padding, padding)
        outer.setSpacing(spacing)
        if title or right is not None:
            head = QHBoxLayout()
            head.setSpacing(10)
            col = QVBoxLayout()
            col.setSpacing(2)
            if title:
                col.addWidget(label(title, "h2"))
            if subtitle:
                col.addWidget(label(subtitle, "muted", wrap=True))
            head.addLayout(col, 1)
            if isinstance(right, QWidget):
                head.addWidget(right, 0, Qt.AlignmentFlag.AlignTop)
            elif right is not None:
                head.addLayout(right)
            outer.addLayout(head)
        self.body = QVBoxLayout()
        self.body.setSpacing(spacing)
        outer.addLayout(self.body)

    def add(self, w):
        if isinstance(w, QWidget):
            self.body.addWidget(w)
        else:
            self.body.addLayout(w)
        return w


class SettingRow(QWidget):
    """Eilutė: kairėje pavadinimas (+ paaiškinimas), dešinėje valdiklis."""

    def __init__(self, title: str, control: QWidget, help_text: str = "", stretch_control: bool = False):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(16)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.title = label(title)
        col.addWidget(self.title)
        if help_text:
            col.addWidget(label(help_text, "faint", wrap=True))
        lay.addLayout(col, 1 if not stretch_control else 0)
        if stretch_control:
            lay.addWidget(control, 1)
        else:
            lay.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self.control = control


# ---------------------------------------------------------------- segmentai
class Segmented(QWidget):
    changed = Signal(str)

    def __init__(self, options: dict, value=None, compact: bool = False):
        super().__init__()
        self.options = list(options.items())
        self.value = value if value in options else (self.options[0][0] if self.options else None)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self._hover = -1
        self._font = ui_font(12.5, QFont.Weight.Medium)
        self.setFont(self._font)
        self.setFixedHeight(30 if compact else 32)
        fm = self.fontMetrics()
        self._w = [max(56, fm.horizontalAdvance(t) + 28) for _, t in self.options]
        self.setMinimumWidth(sum(self._w) + 6)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def sizeHint(self):
        return QSize(sum(self._w) + 6, self.height())

    def set_value(self, v):
        if v != self.value:
            self.value = v
            self.update()

    def _rects(self):
        total = sum(self._w)
        avail = self.width() - 6
        k = avail / total if total else 1
        x = 3.0
        out = []
        for w in self._w:
            out.append(QRectF(x, 3, w * k, self.height() - 6))
            x += w * k
        return out

    def mouseMoveEvent(self, e):
        h = next((i for i, r in enumerate(self._rects()) if r.contains(e.position())), -1)
        if h != self._hover:
            self._hover = h
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mousePressEvent(self, e):
        for i, r in enumerate(self._rects()):
            if r.contains(e.position()):
                v = self.options[i][0]
                if v != self.value:
                    self.value = v
                    self.update()
                    self.changed.emit(v)
                return

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(qcolor("border2"), 1))
        p.setBrush(qcolor("bg"))
        p.drawRoundedRect(r, 9, 9)
        p.setFont(self._font)
        for i, (rect, (val, text)) in enumerate(zip(self._rects(), self.options)):
            sel = val == self.value
            if sel:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(qcolor("surface3"))
                p.drawRoundedRect(rect, 7, 7)
            elif i == self._hover:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(qcolor("surface"))
                p.drawRoundedRect(rect, 7, 7)
            p.setPen(qcolor("text") if sel else qcolor("muted"))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


# ---------------------------------------------------------------- slankiklis + skaičius
class SliderField(QWidget):
    changed = Signal(float)

    def __init__(self, value: float, lo: float, hi: float, step: float = 1.0, suffix: str = "",
                 percent: bool = False, decimals: int | None = None, width: int = 260):
        super().__init__()
        self.percent = percent
        self.k = 100.0 if percent else 1.0
        self.step = step or (0.01 if percent else 1.0)
        self.lo, self.hi = lo, hi
        self.n = max(1, int(round((hi - lo) / self.step)))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, self.n)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.spin = QDoubleSpinBox()
        if decimals is None:
            s = self.step * self.k
            decimals = 0 if abs(s - round(s)) < 1e-9 else (1 if abs(s * 10 - round(s * 10)) < 1e-9 else 2)
        self.spin.setDecimals(decimals)
        self.spin.setRange(lo * self.k, hi * self.k)
        self.spin.setSingleStep(self.step * self.k)
        self.spin.setSuffix("%" if percent else suffix)
        self.spin.setFixedWidth(84)
        self.spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.slider.setMinimumWidth(width - 94)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.spin)
        self.set_value(value)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)

    def set_value(self, v):
        v = float(v if v is not None else self.lo)
        self.slider.blockSignals(True)
        self.spin.blockSignals(True)
        self.slider.setValue(int(round((v - self.lo) / self.step)))
        self.spin.setValue(v * self.k)
        self.slider.blockSignals(False)
        self.spin.blockSignals(False)

    def value(self) -> float:
        return self.spin.value() / self.k

    def _from_slider(self, i):
        v = self.lo + i * self.step
        self.spin.blockSignals(True)
        self.spin.setValue(v * self.k)
        self.spin.blockSignals(False)
        self.changed.emit(round(v, 6))

    def _from_spin(self, x):
        v = x / self.k
        self.slider.blockSignals(True)
        self.slider.setValue(int(round((v - self.lo) / self.step)))
        self.slider.blockSignals(False)
        self.changed.emit(round(v, 6))


class NumberField(QDoubleSpinBox):
    """Skaičius be rodyklių (X / Y / plotis)."""

    def __init__(self, value=0, lo=-99999, hi=99999, decimals=0, suffix="", width=92):
        super().__init__()
        self.setDecimals(decimals)
        self.setRange(lo, hi)
        self.setSuffix(suffix)
        self.setValue(value or 0)
        self.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.setFixedWidth(width)
        self.setKeyboardTracking(False)

    def set_silent(self, v):
        self.blockSignals(True)
        self.setValue(v)
        self.blockSignals(False)


class Combo(QComboBox):
    changed = Signal(str)

    def __init__(self, options: dict, value=None, width: int = 220):
        super().__init__()
        self._keys = list(options)
        for k, t in options.items():
            self.addItem(t, k)
        if value in self._keys:
            self.setCurrentIndex(self._keys.index(value))
        self.setMinimumWidth(width)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.currentIndexChanged.connect(lambda i: self.changed.emit(self._keys[i]) if 0 <= i < len(self._keys) else None)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        pm = icon_pixmap("chevron_down", T["muted"], 14)
        p.drawPixmap(self.width() - 24, (self.height() - 14) // 2, pm)


# ---------------------------------------------------------------- spalva
class ColorButton(QPushButton):
    changed = Signal(str)

    def __init__(self, value: str = "#ffffff", allow_reset: bool = False):
        super().__init__()
        self.value = value
        self.setFixedSize(92, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._pick)

    def set_value(self, v):
        self.value = v
        self.update()

    def _pick(self):
        c = QColorDialog.getColor(QColor(self.value), self, "Pick a colour")
        if c.isValid():
            self.value = c.name()
            self.update()
            self.changed.emit(self.value)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(qcolor("border2") if not self.underMouse() else qcolor("faint"), 1))
        p.setBrush(qcolor("bg"))
        p.drawRoundedRect(r, 8, 8)
        sw = QRectF(6, 6, r.height() - 12, r.height() - 12)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(QColor(self.value))
        p.drawRoundedRect(sw, 5, 5)
        p.setPen(qcolor("muted"))
        p.setFont(ui_font(12))
        p.drawText(QRectF(sw.right() + 8, 0, r.width() - sw.right() - 10, r.height()),
                   Qt.AlignmentFlag.AlignVCenter, self.value.upper())


# ---------------------------------------------------------------- būsena / ženkliukai
class Pill(QWidget):
    def __init__(self, text: str = "", color: str = "faint"):
        super().__init__()
        self.text, self.color = text, color
        self.setFixedHeight(26)
        self._font = ui_font(12, QFont.Weight.Medium)

    def set(self, text, color):
        if (text, color) != (self.text, self.color):
            self.text, self.color = text, color
            self.updateGeometry()
            self.update()

    def sizeHint(self):
        from PySide6.QtGui import QFontMetrics
        return QSize(QFontMetrics(self._font).horizontalAdvance(self.text) + 34, 26)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        c = qcolor(self.color)
        bg = QColor(c)
        bg.setAlpha(28)
        p.setPen(QPen(QColor(c.red(), c.green(), c.blue(), 70), 1))
        p.setBrush(bg)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawEllipse(QPointF(13, r.center().y()), 3.5, 3.5)
        p.setPen(qcolor("text"))
        p.setFont(self._font)
        p.drawText(r.adjusted(22, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter, self.text)


class Badge(QLabel):
    def __init__(self, text: str, color: str = "muted"):
        super().__init__(text)
        c = qcolor(color)
        self.setStyleSheet(f"QLabel {{ background: rgba({c.red()},{c.green()},{c.blue()},0.13); color: {c.name()};"
                           f" border-radius: 6px; padding: 2px 8px; font-size: 11px; font-weight: 600; }}")


class IconTile(QWidget):
    """Kvadratas su ikona (kortelėms)."""

    def __init__(self, name: str, size: int = 38, color: str | None = None):
        super().__init__()
        self.name = name
        self.color = color
        self.setFixedSize(size, size)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(qcolor("border2"), 1))
        p.setBrush(qcolor("surface2"))
        p.drawRoundedRect(r, 9, 9)
        s = int(r.width() * 0.5)
        pm = icon_pixmap(self.name, self.color or T["text"], s)
        p.drawPixmap(int((self.width() - s) / 2), int((self.height() - s) / 2), pm)


class KpiTile(Card):
    def __init__(self, title: str, value: str = "–", sub: str = "", icon_name: str | None = None):
        super().__init__(padding=16, spacing=4)
        top = QHBoxLayout()
        top.addWidget(label(title.upper(), "eyebrow"))
        top.addStretch(1)
        if icon_name:
            ic = QLabel()
            ic.setPixmap(icon_pixmap(icon_name, T["faint"], 16))
            top.addWidget(ic)
        self.body.addLayout(top)
        self.value = label(value, "kpi")
        self.sub = label(sub, "faint")
        self.body.addWidget(self.value)
        self.body.addWidget(self.sub)

    def set(self, value: str, sub: str | None = None):
        self.value.setText(value)
        if sub is not None:
            self.sub.setText(sub)


# ---------------------------------------------------------------- linijinis grafikas
class LineChart(QWidget):
    def __init__(self, color: str = "accent", unit: str = "", fixed_max: float | None = None, height: int = 140):
        super().__init__()
        self.values = []
        self.color = color
        self.unit = unit
        self.fixed_max = fixed_max
        self.setMinimumHeight(height)

    def set_values(self, values):
        self.values = [v for v in values]
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(36, 8, -6, -18)
        vals = [v for v in self.values if v is not None]
        top = self.fixed_max or max([1.0] + vals) * 1.25
        p.setFont(ui_font(11))
        for i in range(5):
            y = r.bottom() - r.height() * i / 4
            p.setPen(QPen(qcolor("border"), 1, Qt.PenStyle.SolidLine if i == 0 else Qt.PenStyle.DotLine))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.setPen(qcolor("faint"))
            v = top * i / 4
            p.drawText(QRectF(0, y - 8, 32, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{v:.0f}" if top >= 10 else f"{v:.1f}")
        p.setPen(qcolor("faint"))
        p.drawText(QRectF(r.left(), r.bottom() + 2, r.width(), 16), Qt.AlignmentFlag.AlignLeft, "2 min ago")
        p.drawText(QRectF(r.left(), r.bottom() + 2, r.width(), 16), Qt.AlignmentFlag.AlignRight, "now")
        n = 120
        pts = [(i, v) for i, v in enumerate(self.values[-n:]) if v is not None]
        if len(pts) < 2:
            return
        off = n - len(self.values[-n:])
        path = QPainterPath()
        fill = QPainterPath()
        for k, (i, v) in enumerate(pts):
            x = r.left() + (i + off) / (n - 1) * r.width()
            y = r.bottom() - min(1.0, v / top) * r.height()
            if k == 0:
                path.moveTo(x, y)
                fill.moveTo(x, r.bottom())
                fill.lineTo(x, y)
            else:
                path.lineTo(x, y)
                fill.lineTo(x, y)
        fill.lineTo(path.currentPosition().x(), r.bottom())
        fill.closeSubpath()
        c = qcolor(self.color)
        fc = QColor(c)
        fc.setAlpha(36)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fc)
        p.drawPath(fill)
        p.setPen(QPen(c, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


# ---------------------------------------------------------------- stulpelių sąrašas (įjungti + tempti)
class _Grip(QLabel):
    def __init__(self, row):
        super().__init__()
        self.row = row
        self.setPixmap(icon_pixmap("grip", T["faint"], 16))
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setFixedWidth(18)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.row.owner._start_drag(self.row, e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        self.row.owner._drag_move(e.globalPosition().toPoint())

    def mouseReleaseEvent(self, e):
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.row.owner._end_drag()


class _ColRow(QFrame):
    def __init__(self, owner, key, text, on):
        super().__init__()
        self.owner, self.key = owner, key
        self.setObjectName("ColRow")
        self.setStyleSheet(f"QFrame#ColRow {{ background: {T['surface2']}; border: 1px solid {T['border']};"
                           f" border-radius: 8px; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 10, 6)
        lay.setSpacing(10)
        lay.addWidget(_Grip(self))
        lay.addWidget(label(text), 1)
        self.toggle = Toggle(on)
        self.toggle.toggled.connect(lambda v: owner._toggled(key, v))
        lay.addWidget(self.toggle)

    def set_dragging(self, on):
        border = T["accent"] if on else T["border"]
        self.setStyleSheet(f"QFrame#ColRow {{ background: {T['surface3'] if on else T['surface2']};"
                           f" border: 1px solid {border}; border-radius: 8px; }}")


class ColumnList(QWidget):
    """Stulpeliai: jungiklis kiekvienam + tvarka tempiant už rankenėlės."""

    changed = Signal(dict, list)

    def __init__(self, spec: dict, enabled: dict, order: list | None, reorder: bool = True):
        super().__init__()
        self.spec = spec
        self.enabled = {k: bool(enabled.get(k, v[1])) for k, v in spec.items()}
        order = [k for k in (order or []) if k in spec] + [k for k in spec if k not in (order or [])]
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(6)
        self.rows = []
        for k in order:
            row = _ColRow(self, k, spec[k][0], self.enabled[k])
            if not reorder:
                row.layout().itemAt(0).widget().hide()
            self.rows.append(row)
            self.lay.addWidget(row)
        self._drag = None

    def order(self):
        return [r.key for r in self.rows]

    def _toggled(self, key, v):
        self.enabled[key] = bool(v)
        self.changed.emit(dict(self.enabled), self.order())

    def _start_drag(self, row, gpos):
        self._drag = row
        row.set_dragging(True)

    def _drag_move(self, gpos):
        row = self._drag
        if row is None:
            return
        y = self.mapFromGlobal(gpos).y()
        idx = self.rows.index(row)
        target = idx
        for i, r in enumerate(self.rows):
            g = r.geometry()
            if y < g.center().y():
                target = i
                break
        else:
            target = len(self.rows) - 1
        if target != idx:
            self.rows.pop(idx)
            self.rows.insert(target, row)
            self.lay.removeWidget(row)
            self.lay.insertWidget(target, row)

    def _end_drag(self):
        if self._drag is not None:
            self._drag.set_dragging(False)
            self._drag = None
            self.changed.emit(dict(self.enabled), self.order())


# ---------------------------------------------------------------- prisitaikantis tinklelis
class FlowGrid(QWidget):
    """Kortelės stulpeliais pagal plotį (min_w)."""

    def __init__(self, min_w: int = 300, spacing: int = 14):
        super().__init__()
        self.min_w = min_w
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(spacing)
        self.items = []
        self._cols = 0

    def set_items(self, widgets):
        for w in self.items:
            self.grid.removeWidget(w)
            w.hide()
        self.items = list(widgets)
        self._cols = 0
        self._relayout()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()

    def _relayout(self):
        cols = max(1, (self.width() + self.grid.spacing()) // (self.min_w + self.grid.spacing()))
        if cols == self._cols and all(w.isVisible() for w in self.items):
            return
        self._cols = cols
        for w in self.items:
            self.grid.removeWidget(w)
        for i, w in enumerate(self.items):
            self.grid.addWidget(w, i // cols, i % cols)
            w.show()
        for c in range(8):
            self.grid.setColumnStretch(c, 1 if c < cols else 0)


class NavButton(QAbstractButton):
    def __init__(self, text: str, icon_name: str):
        super().__init__()
        self.setText(text)
        self.icon_name = icon_name
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(36)
        self._font = ui_font(13, QFont.Weight.Medium)

    def sizeHint(self):
        return QSize(200, 36)

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0, 1, 0, -1)
        on = self.isChecked()
        if on or self.underMouse():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qcolor("surface2") if on else qcolor("surface"))
            p.drawRoundedRect(r, 8, 8)
        if on:
            p.setBrush(qcolor("accent"))
            p.drawRoundedRect(QRectF(0, r.y() + 9, 3, r.height() - 18), 1.5, 1.5)
        col = T["text"] if on else T["muted"]
        p.drawPixmap(14, int(r.center().y() - 9), icon_pixmap(self.icon_name, T["accent"] if on else col, 18))
        p.setPen(QColor(col))
        p.setFont(self._font)
        p.drawText(r.adjusted(44, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter, self.text())


def clear_layout(lay):
    while lay.count():
        it = lay.takeAt(0)
        w = it.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        elif it.layout() is not None:
            clear_layout(it.layout())


__all__ = ["Toggle", "Card", "SettingRow", "Segmented", "SliderField", "NumberField", "Combo", "ColorButton", "Pill",
           "Badge", "IconTile", "KpiTile", "LineChart", "ColumnList", "FlowGrid", "NavButton", "label", "button",
           "divider", "hbox", "vbox", "clear_layout", "QPoint"]
