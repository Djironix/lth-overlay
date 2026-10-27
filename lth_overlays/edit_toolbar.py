"""Plaukiojanti juosta redagavimo režime: ką daryti ir mygtukai Done / Control Center.

Rodoma ekrano viršuje, kur yra pelė. Galima nutempti. Fokuso nepaima.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import win32


class EditToolbar(QWidget):
    H = 56

    def __init__(self, ctx):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
                 | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.NoDropShadowWindowHint)
        super().__init__(None, flags)
        self.ctx = ctx
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setWindowTitle("LTH edit layout")
        from .control.style import ui_font
        self.f_title = ui_font(13, QFont.Weight.Bold)
        self.f_text = ui_font(12, QFont.Weight.Medium)
        self.f_btn = ui_font(12.5, QFont.Weight.DemiBold)
        self._hover = None
        self._drag = None
        self._native = False
        self.resize(self._width(), self.H)

    HINT = "Drag to move  ·  Corners scale  ·  Edges resize  ·  Settings button for options"

    def _width(self):
        from PySide6.QtGui import QFontMetricsF
        return int(QFontMetricsF(self.f_text).horizontalAdvance(self.HINT) + 520)

    def _buttons(self):
        w = self.width()
        done = QRectF(w - 96, 11, 84, self.H - 22)
        cc = QRectF(done.left() - 148, 11, 140, self.H - 22)
        return {"done": done, "cc": cc}

    def place(self):
        scr = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        g = scr.geometry()
        w = min(self._width(), g.width() - 40)
        self.resize(w, self.H)
        self.move(g.x() + (g.width() - w) // 2, g.y() + 14)

    def showEvent(self, e):
        super().showEvent(e)
        if not self._native:
            win32.make_overlay(self, click_through=False)
            self._native = True

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(236, 190, 88, 160), 1.2))
        p.setBrush(QColor(12, 12, 15, 240))
        p.drawRoundedRect(r, 14, 14)
        from .brand import logo_pixmap
        pm = logo_pixmap(18)
        x = 18
        if not pm.isNull():
            p.drawPixmap(x, int((self.H - 18) / 2), pm)
            x += int(pm.width() / pm.devicePixelRatio()) + 14
        p.setPen(QColor(255, 255, 255))
        p.setFont(self.f_title)
        p.drawText(QRectF(x, 0, 140, self.H), Qt.AlignmentFlag.AlignVCenter, "Editing layout")
        x += 130
        btn = self._buttons()
        p.setPen(QColor(190, 190, 200))
        p.setFont(self.f_text)
        hint = p.fontMetrics().elidedText(self.HINT, Qt.TextElideMode.ElideRight, int(btn["cc"].left() - x - 16))
        p.drawText(QRectF(x, 0, btn["cc"].left() - x - 12, self.H), Qt.AlignmentFlag.AlignVCenter, hint)
        p.setFont(self.f_btn)
        cc = btn["cc"]
        p.setPen(QPen(QColor(60, 60, 70), 1))
        p.setBrush(QColor(40, 40, 48) if self._hover == "cc" else QColor(26, 26, 32))
        p.drawRoundedRect(cc, 8, 8)
        p.setPen(QColor(240, 240, 244))
        p.drawText(cc, Qt.AlignmentFlag.AlignCenter, "Control Center")
        d = btn["done"]
        g = QLinearGradient(d.topLeft(), d.topRight())
        g.setColorAt(0, QColor(251, 208, 105) if self._hover != "done" else QColor(255, 222, 130))
        g.setColorAt(1, QColor(209, 160, 58) if self._hover != "done" else QColor(230, 180, 70))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(d, 8, 8)
        p.setPen(QColor(20, 16, 6))
        p.drawText(d, Qt.AlignmentFlag.AlignCenter, "Done")

    def _hit(self, pos):
        for k, rr in self._buttons().items():
            if rr.contains(pos):
                return k
        return None

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)
            return
        h = self._hit(e.position())
        if h != self._hover:
            self._hover = h
            self.setCursor(Qt.CursorShape.PointingHandCursor if h else Qt.CursorShape.SizeAllCursor)
            self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        h = self._hit(e.position())
        if h == "done":
            self.ctx.toggle_edit()
        elif h == "cc":
            self.ctx.open_control_center()
        else:
            self._drag = e.globalPosition().toPoint() - self.pos()

    def mouseReleaseEvent(self, e):
        self._drag = None


__all__ = ["EditToolbar", "QPoint"]
