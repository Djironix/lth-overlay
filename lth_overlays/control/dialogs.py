"""Control Center dialogai: presetai, dalinimasis (kodas / failas), importas."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLineEdit, QMessageBox, QPlainTextEdit,
                               QVBoxLayout, QWidget)

from .. import share
from ..presets import PRESETS, apply_preset
from ..registry import BY_NAME
from .components import Segmented, button, label
from .style import T, qcolor, qss, ui_font


class _Dialog(QDialog):
    def __init__(self, parent, title: str, width: int = 760):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setStyleSheet(qss() + f"QDialog {{ background: {T['surface']}; }}")
        self.setMinimumWidth(width)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(24, 22, 24, 20)
        self.lay.setSpacing(14)
        self.lay.addWidget(label(title, "h1"))


# ---------------------------------------------------------------- presetai
class PresetCard(QWidget):
    clicked = Signal(str)

    def __init__(self, key: str, selected: bool = False):
        super().__init__()
        self.key = key
        self.selected = selected
        self.setFixedHeight(220)
        self.setMinimumWidth(210)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        self.clicked.emit(self.key)

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()

    def paintEvent(self, e):
        pr = PRESETS[self.key]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(qcolor("accent") if self.selected else (qcolor("border2") if self.underMouse()
                                                                else qcolor("border")), 2 if self.selected else 1))
        p.setBrush(qcolor("surface2") if self.selected else qcolor("bg"))
        p.drawRoundedRect(r, 12, 12)
        stage = QRectF(r.x() + 12, r.y() + 12, r.width() - 24, 110)
        screens = 3 if pr["target"] == "middle" else 1
        gap = 4
        sw = (stage.width() - gap * (screens - 1)) / screens
        sh = min(stage.height(), sw * 9 / 16)
        y0 = stage.y() + (stage.height() - sh) / 2
        for i in range(screens):
            sr = QRectF(stage.x() + i * (sw + gap), y0, sw, sh)
            g = QLinearGradient(0, sr.top(), 0, sr.bottom())
            g.setColorAt(0, QColor(74, 92, 116))
            g.setColorAt(1, QColor(28, 30, 34))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawRoundedRect(sr, 4, 4)
            if screens == 3 and i != 1:
                continue
            for name, (ax, ay, alx, aly, width, extra) in pr["widgets"].items():
                w = width / 1920 * sr.width()
                h = (extra.get("height") or {"standings": 520, "relative": 210, "weather": 230, "session": 150,
                                              "fuel": 170, "engineer": 40, "flags": 50}.get(name, 90)) / 1080 * sr.height()
                rr = QRectF(sr.x() + ax * sr.width() - alx * w, sr.y() + ay * sr.height(), w, h)
                p.setBrush(QColor(236, 190, 88, 210) if name in ("standings", "relative") else QColor(255, 255, 255, 150))
                p.drawRoundedRect(rr, 1.5, 1.5)
        p.setPen(qcolor("text"))
        p.setFont(ui_font(14, QFont.Weight.DemiBold))
        p.drawText(QRectF(r.x() + 14, stage.bottom() + 10, r.width() - 28, 22), Qt.AlignmentFlag.AlignVCenter,
                   pr["title"])
        p.setPen(qcolor("muted"))
        p.setFont(ui_font(12))
        p.drawText(QRectF(r.x() + 14, stage.bottom() + 34, r.width() - 28, 60),
                   int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft) | int(Qt.TextFlag.TextWordWrap),
                   pr["subtitle"])


class PresetPicker(QWidget):
    """Trys presetų kortelės (naudojama ir pirmo paleidimo tutoriale)."""
    changed = Signal(str)

    def __init__(self, selected: str | None = "simple"):
        super().__init__()
        self.value = selected
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.cards = {}
        for key in PRESETS:
            c = PresetCard(key, key == selected)
            c.clicked.connect(self._pick)
            self.cards[key] = c
            lay.addWidget(c)

    def _pick(self, key):
        self.value = key
        for k, c in self.cards.items():
            c.selected = k == key
            c.update()
        self.changed.emit(key)


class PresetDialog(_Dialog):
    def __init__(self, center):
        super().__init__(center, "Layout presets", 820)
        self.center = center
        self.ctx = center.ctx
        self.lay.addWidget(label("Start from a ready layout. Your widget settings (columns, filters, colours) stay; "
                                 "only which widgets are on and where they sit changes.", "muted", wrap=True))
        self.picker = PresetPicker("simple")
        self.lay.addWidget(self.picker)
        self.target = Segmented({"current": "This profile", "all": "All profiles", "new": "New profile"}, "current")
        row = QHBoxLayout()
        row.addWidget(label("Apply to", "h3"))
        row.addWidget(self.target)
        row.addStretch(1)
        self.lay.addLayout(row)
        cancel = button("Cancel", "ghost")
        cancel.clicked.connect(self.reject)
        ok = button("Apply preset", "primary", "check")
        ok.clicked.connect(self._apply)
        self.lay.addLayout(_buttons(cancel, ok))

    def _apply(self):
        key = self.picker.value
        cfg = self.ctx.config
        mode = self.target.value
        if mode == "new":
            base = PRESETS[key]["title"]
            pkey = _unique(cfg, base)
            cfg.add_profile(pkey, base)
            self.ctx.set_profile(pkey)
            profiles = [pkey]
        elif mode == "all":
            if QMessageBox.question(self, "Apply to all profiles",
                                    "Replace the layout of every profile with this preset?") \
                    != QMessageBox.StandardButton.Yes:
                return
            profiles = list(cfg.data["profiles"])
        else:
            profiles = [cfg.profile_key]
        apply_preset(self.ctx, key, profiles)
        self.center.preview.invalidate()
        self.center.profile_changed()
        self.accept()


# ---------------------------------------------------------------- dalinimasis
class ShareDialog(_Dialog):
    def __init__(self, center, profile_key: str):
        super().__init__(center, "Share layout", 700)
        self.ctx = center.ctx
        self.data = share.export_layout(self.ctx, profile_key)
        self.code = share.encode(self.data)
        n = len(self.data["widgets"])
        self.lay.addWidget(label(f"“{self.data['name']}” · {n} widgets · theme and positions included. "
                                 "The receiver imports it as a new profile, scaled to their screen.", "muted",
                                 wrap=True))
        self.lay.addWidget(label("SHARE CODE", "eyebrow"))
        box = QPlainTextEdit(self.code)
        box.setReadOnly(True)
        box.setFixedHeight(110)
        self.lay.addWidget(box)
        fits = len(self.code) <= share.DISCORD_LIMIT - 40
        self.state = label(f"{len(self.code)} characters. " + ("Paste it straight into a Discord message."
                                                                if fits else "Too long for one Discord message - "
                                                                             "send the file instead."),
                           "faint" if fits else "muted", wrap=True)
        self.lay.addWidget(self.state)
        copy_b = button("Copy code", "primary", "copy")
        copy_b.clicked.connect(self._copy)
        copy_b.setEnabled(fits)
        file_b = button("Save .lthlayout file", None, "download")
        file_b.clicked.connect(self._save)
        close = button("Close", "ghost")
        close.clicked.connect(self.accept)
        self.lay.addLayout(_buttons(close, file_b, copy_b))

    def _copy(self):
        QGuiApplication.clipboard().setText(self.code)
        self.state.setText("Copied. Paste it in Discord. Others use Profiles → Import layout.")

    def _save(self):
        name = (self.data["name"] or "layout").replace(" ", "_")
        path, _ = QFileDialog.getSaveFileName(self, "Save layout", f"{name}.lthlayout", "LTH layout (*.lthlayout)")
        if path:
            try:
                share.write_file(path, self.data)
                self.state.setText("Saved. Drop the file into Discord. Others can drag it onto the Control Center.")
            except OSError as e:
                QMessageBox.warning(self, "Save failed", str(e))


class ImportDialog(_Dialog):
    def __init__(self, center, data: dict | None = None):
        super().__init__(center, "Import layout", 700)
        self.center = center
        self.ctx = center.ctx
        self.data = data
        self.lay.addWidget(label("Paste a share code from Discord, or open a .lthlayout file. "
                                 "It is added as a new profile; your current layouts stay untouched.", "muted",
                                 wrap=True))
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("LTH1:…")
        self.text.setFixedHeight(100)
        self.text.textChanged.connect(lambda: QTimer.singleShot(150, self._parse))
        self.lay.addWidget(self.text)
        open_b = button("Open file…", None, "folder")
        open_b.clicked.connect(self._open)
        self.lay.addLayout(_buttons(open_b, None))
        self.info = label("", "muted", wrap=True)
        self.lay.addWidget(self.info)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Profile name")
        nrow = QHBoxLayout()
        nrow.addWidget(label("Profile name", "h3"))
        nrow.addWidget(self.name, 1)
        self.lay.addLayout(nrow)
        cancel = button("Cancel", "ghost")
        cancel.clicked.connect(self.reject)
        self.ok = button("Import as new profile", "primary", "upload")
        self.ok.clicked.connect(self._import)
        self.lay.addLayout(_buttons(cancel, self.ok))
        self._show()

    def _parse(self):
        txt = self.text.toPlainText().strip()
        if not txt:
            return
        try:
            self.data = share.decode(txt)
        except ValueError as e:
            self.data = None
            self.info.setText(str(e))
        self._show()

    def _open(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open layout", "", "LTH layout (*.lthlayout *.json *.txt)")
        if not path:
            return
        try:
            self.data = share.read_file(path)
        except (OSError, ValueError) as e:
            self.data = None
            self.info.setText(str(e))
        self._show()

    def _show(self):
        ok = self.data is not None
        self.ok.setEnabled(ok)
        if ok:
            self.info.setText(share.summary(self.data))
            if not self.name.text():
                self.name.setText(self.data["name"])

    def _import(self):
        if self.data is None:
            return
        key = share.import_layout(self.ctx, self.data, self.name.text().strip() or None)
        self.ctx.save_config()
        if QMessageBox.question(self, "Layout imported", "Switch to the imported profile now?") \
                == QMessageBox.StandardButton.Yes:
            self.ctx.set_profile(key)
        self.center.profile_changed()
        self.accept()


def _buttons(*items):
    row = QHBoxLayout()
    row.setSpacing(10)
    if items and items[0] is not None and not any(i is None for i in items):
        row.addStretch(1)
    for it in items:
        if it is None:
            row.addStretch(1)
        else:
            row.addWidget(it)
    return row


def _unique(cfg, name: str) -> str:
    import re
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "profile"
    key, i = base, 2
    while key in cfg.data["profiles"]:
        key, i = f"{base}_{i}", i + 1
    return key


__all__ = ["PresetDialog", "PresetPicker", "ShareDialog", "ImportDialog", "BY_NAME"]
