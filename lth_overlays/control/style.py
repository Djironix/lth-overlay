"""Control Center išvaizda: spalvų žetonai, QSS, Inter šriftas, vektorinės ikonos.

Ikonos - mūsų pačių paprasti SVG kontūrai (24×24, linijos storis 1.8),
piešiami per QtSvg ir talpinami pagal (pavadinimas, spalva, dydis).
"""
from __future__ import annotations

import os

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap

UI_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ui")

T = {
    "bg": "#0B0B0E",
    "sidebar": "#0F0F13",
    "surface": "#15151A",
    "surface2": "#1B1B22",
    "surface3": "#23232C",
    "border": "#24242D",
    "border2": "#30303B",
    "text": "#EDEDF1",
    "muted": "#9A9AA8",
    "faint": "#62626E",
    "accent": "#E2B13C",
    "accent_hover": "#EDC25C",
    "accent_soft": "rgba(226,177,60,0.12)",
    "accent_text": "#18140A",
    "good": "#3DD68C",
    "bad": "#F2555A",
    "warn": "#F5B83D",
    "info": "#5B9DFF",
}

_font_family = None


def ui_font_family() -> str:
    global _font_family
    if _font_family is None:
        fam = "Segoe UI"
        path = os.path.join(UI_DIR, "Inter.ttf")
        if os.path.exists(path):
            fid = QFontDatabase.addApplicationFont(path)
            fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
            if fams:
                fam = fams[0]
        _font_family = fam
    return _font_family


def ui_font(px: float = 13, weight=QFont.Weight.Normal) -> QFont:
    f = QFont(ui_font_family())
    f.setPixelSize(int(round(px)))
    f.setWeight(weight)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def qss() -> str:
    fam = ui_font_family()
    return f"""
* {{ font-family: "{fam}", "Segoe UI", sans-serif; font-size: 13px; color: {T['text']}; outline: 0; }}
QMainWindow, #Root {{ background: {T['bg']}; }}
QWidget#Page {{ background: {T['bg']}; }}
QToolTip {{ background: {T['surface3']}; color: {T['text']}; border: 1px solid {T['border2']};
            padding: 6px 8px; border-radius: 6px; }}
QLabel {{ background: transparent; }}
QLabel[role="h1"] {{ font-size: 22px; font-weight: 600; letter-spacing: -0.3px; }}
QLabel[role="h2"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="h3"] {{ font-size: 13px; font-weight: 600; }}
QLabel[role="muted"] {{ color: {T['muted']}; }}
QLabel[role="faint"] {{ color: {T['faint']}; font-size: 12px; }}
QLabel[role="eyebrow"] {{ color: {T['faint']}; font-size: 11px; font-weight: 600; letter-spacing: 0.8px; }}
QLabel[role="kpi"] {{ font-size: 26px; font-weight: 600; letter-spacing: -0.5px; }}
QLabel[role="mono"] {{ font-family: "Cascadia Mono", "Consolas", monospace; font-size: 12px; color: {T['muted']}; }}

QFrame#Card {{ background: {T['surface']}; border: 1px solid {T['border']}; border-radius: 12px; }}
QFrame#CardHover:hover {{ border-color: {T['border2']}; }}
QFrame#Sidebar {{ background: {T['sidebar']}; border-right: 1px solid {T['border']}; }}
QFrame#TopBar {{ background: {T['bg']}; border-bottom: 1px solid {T['border']}; }}
QFrame#Divider {{ background: {T['border']}; max-height: 1px; min-height: 1px; border: none; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {T['surface3']}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {T['border2']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {T['surface3']}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: none; width: 0; height: 0; }}

QPushButton {{ background: {T['surface2']}; border: 1px solid {T['border2']}; border-radius: 8px;
               padding: 7px 14px; font-weight: 500; }}
QPushButton:hover {{ background: {T['surface3']}; }}
QPushButton:pressed {{ background: {T['border']}; }}
QPushButton:disabled {{ color: {T['faint']}; }}
QPushButton[variant="primary"] {{ background: {T['accent']}; color: {T['accent_text']}; border: 1px solid {T['accent']}; }}
QPushButton[variant="primary"]:hover {{ background: {T['accent_hover']}; }}
QPushButton[variant="ghost"] {{ background: transparent; border: 1px solid transparent; color: {T['muted']}; }}
QPushButton[variant="ghost"]:hover {{ background: {T['surface2']}; color: {T['text']}; }}
QPushButton[variant="danger"] {{ background: transparent; border: 1px solid {T['border2']}; color: {T['bad']}; }}
QPushButton[variant="danger"]:hover {{ background: rgba(242,85,90,0.10); border-color: {T['bad']}; }}
QPushButton:checked {{ background: {T['accent_soft']}; border-color: {T['accent']}; color: {T['accent']}; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QKeySequenceEdit {{
    background: {T['bg']}; border: 1px solid {T['border2']}; border-radius: 8px; padding: 6px 9px;
    selection-background-color: {T['accent']}; selection-color: {T['accent_text']}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {T['accent']}; }}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{ border-color: {T['faint']}; }}
QSpinBox, QDoubleSpinBox {{ padding-right: 4px; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0px; border: none; subcontrol-origin: border; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: none; width: 0; }}
QComboBox QAbstractItemView {{ background: {T['surface2']}; border: 1px solid {T['border2']}; border-radius: 8px;
    padding: 4px; selection-background-color: {T['surface3']}; selection-color: {T['text']}; }}
QPlainTextEdit {{ font-family: "Cascadia Mono", "Consolas", monospace; font-size: 12px; }}

QSlider::groove:horizontal {{ height: 4px; background: {T['surface3']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {T['accent']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {T['text']}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
QSlider::handle:horizontal:hover {{ background: #FFFFFF; }}

QMenu {{ background: {T['surface2']}; border: 1px solid {T['border2']}; border-radius: 10px; padding: 5px; }}
QMenu::item {{ padding: 7px 18px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {T['surface3']}; }}
QMenu::separator {{ height: 1px; background: {T['border']}; margin: 5px 6px; }}
QMessageBox {{ background: {T['surface']}; }}
QInputDialog {{ background: {T['surface']}; }}
QDialog {{ background: {T['surface']}; }}
"""


# ---------------------------------------------------------------- ikonos
_P = '<path d="{}"/>'
_ICONS = {
    # navigacija
    "home": _P.format("M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"),
    "widgets": '<rect x="3" y="3" width="7.5" height="7.5" rx="1.8"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.8"/>'
               '<rect x="3" y="13.5" width="7.5" height="7.5" rx="1.8"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.8"/>',
    "layout": '<rect x="2.5" y="4" width="19" height="14" rx="2"/><path d="M8 21h8M12 18v3"/>'
              '<rect x="5.5" y="7" width="6" height="4" rx="1"/><rect x="14" y="11" width="5" height="4" rx="1"/>',
    "layers": _P.format("m12 3 9 5-9 5-9-5zM3 13l9 5 9-5M3 17.5l9 5 9-5"),
    "palette": '<path d="M12 3a9 9 0 1 0 0 18c1.1 0 1.8-.8 1.8-1.8 0-.5-.2-.9-.5-1.2-.3-.3-.5-.8-.5-1.2 0-1 .8-1.8 1.8-1.8H17a4 4 0 0 0 4-4C21 6.6 17 3 12 3z"/>'
               '<circle cx="7.5" cy="11" r="1.2"/><circle cx="10" cy="7" r="1.2"/><circle cx="15" cy="7.2" r="1.2"/>',
    "keyboard": '<rect x="2.5" y="6" width="19" height="12" rx="2"/><path d="M6.5 10h.01M10 10h.01M14 10h.01M17.5 10h.01M7 14h10"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3M12 18.5v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2.5 12h3M18.5 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>',
    "activity": _P.format("M3 12h4l3-8 4 16 3-8h4"),
    "bug": '<rect x="7" y="7" width="10" height="13" rx="5"/><path d="M9 4.5 10.5 7M15 4.5 13.5 7M3 13h4M17 13h4M4 8.5l3 2M20 8.5l-3 2M4 18.5l3-2M20 18.5l-3-2M12 11v9"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.6h.01"/>',
    # veiksmai
    "plus": _P.format("M12 5v14M5 12h14"),
    "trash": _P.format("M4 7h16M10 11v6M14 11v6M5.5 7l1 12.5A1.5 1.5 0 0 0 8 21h8a1.5 1.5 0 0 0 1.5-1.5L18.5 7M9 7V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V7"),
    "copy": '<rect x="8" y="8" width="12.5" height="12.5" rx="2"/><path d="M16 8V5.5A2 2 0 0 0 14 3.5H5.5a2 2 0 0 0-2 2V14a2 2 0 0 0 2 2H8"/>',
    "upload": _P.format("M12 15V3.5M7 8.5l5-5 5 5M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"),
    "download": _P.format("M12 3.5V15M7 10l5 5 5-5M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"),
    "reset": _P.format("M3.5 12a8.5 8.5 0 1 0 2.6-6.1M3.5 4v5h5"),
    "edit": _P.format("M5 19h4L19.5 8.5a2.1 2.1 0 0 0-3-3L6 16v3zM14.5 7.5l3 3"),
    "move": _P.format("M12 3v18M3 12h18M12 3 9.5 5.5M12 3l2.5 2.5M12 21l-2.5-2.5M12 21l2.5-2.5M3 12l2.5-2.5M3 12l2.5 2.5M21 12l-2.5-2.5M21 12l-2.5 2.5"),
    "eye": '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
    "eye_off": _P.format("M3 3l18 18M10.6 5.6A9.6 9.6 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-3.1 3.9M6.6 6.6C3.9 8.4 2.5 12 2.5 12S6 18.5 12 18.5c1.8 0 3.3-.5 4.6-1.3M9.9 9.9a3 3 0 0 0 4.2 4.2"),
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.9-3.9"/>',
    "check": _P.format("M5 12.5l4.5 4.5L19 7.5"),
    "chevron_left": _P.format("M15 5l-7 7 7 7"),
    "chevron_right": _P.format("M9 5l7 7-7 7"),
    "chevron_down": _P.format("M6 9l6 6 6-6"),
    "x": _P.format("M6 6l12 12M18 6 6 18"),
    "grip": '<circle cx="9" cy="6" r="1.1"/><circle cx="15" cy="6" r="1.1"/><circle cx="9" cy="12" r="1.1"/>'
            '<circle cx="15" cy="12" r="1.1"/><circle cx="9" cy="18" r="1.1"/><circle cx="15" cy="18" r="1.1"/>',
    "folder": _P.format("M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"),
    "play": _P.format("M7 4.5v15l12-7.5z"),
    "record": '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="3.5"/>',
    "power": _P.format("M12 3v8M6.3 6.3a8 8 0 1 0 11.4 0"),
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="1.8"/><path d="m4 18 5-5 4 4 3-3 4 4"/>',
    "magnet": _P.format("M5 4h4v8a3 3 0 0 0 6 0V4h4v8a7 7 0 0 1-14 0zM5 8h4M15 8h4"),
    "align_center": _P.format("M12 3v18M7 7h10v4H7zM5 14h14v4H5z"),
    "star": _P.format("m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"),
    # valdikliai
    "list": _P.format("M8.5 6h12M8.5 12h12M8.5 18h12M4 6h.01M4 12h.01M4 18h.01"),
    "relative": _P.format("M12 3v18M7 6.5h-3M7 10h-3M20 6.5h-3M20 10h-3M7 14h-3M20 14h-3M7 17.5h-3M20 17.5h-3")
                + '<rect x="9.5" y="10" width="5" height="4" rx="1"/>',
    "swords": _P.format("M14.5 17.5 3 6V3h3l11.5 11.5M13 19l6-6M16 16l4 4M19 21l2-2M9.5 14.5 6 18M4 16l4 4M3 19l2 2M14.5 9.5 18 6V3h3v3l-3.5 3.5"),
    "history": '<path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1M3.5 4v5h5"/><path d="M12 7.5V12l3 2"/>',
    "delta": '<rect x="2.5" y="9" width="19" height="6" rx="3"/><path d="M12 6v12"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
    "headset": _P.format("M4 15v-3a8 8 0 0 1 16 0v3M4 15a2 2 0 0 0 2 2h1v-6H6a2 2 0 0 0-2 2zM20 15a2 2 0 0 1-2 2h-1v-6h1a2 2 0 0 1 2 2zM17 17v1a3 3 0 0 1-3 3h-2"),
    "flag": _P.format("M5 21V4M5 4h11l-2 4 2 4H5"),
    "radar": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="M12 12 18.4 5.6"/>',
    "wrench": _P.format("M14.7 6.3a4 4 0 0 1 5 5l-1.4.4-2.6-2.6.4-1.4zM15.3 9.7 5 20a1.4 1.4 0 0 1-2-2L13.3 7.7a4 4 0 0 1 1.4-1.4"),
    "route": '<circle cx="6" cy="19" r="2.5"/><circle cx="18" cy="5" r="2.5"/><path d="M8.5 19H17a3.5 3.5 0 0 0 0-7H7a3.5 3.5 0 0 1 0-7h8.5"/>',
    "alert": _P.format("M12 3.5 2.5 20h19zM12 10v4.5M12 17.4h.01"),
    "timer": '<circle cx="12" cy="13.5" r="7.5"/><path d="M12 13.5V10M9.5 2.5h5M18.5 6.5l1.5-1.5"/>',
    "grid": '<rect x="4" y="3" width="6.5" height="5" rx="1"/><rect x="13.5" y="6" width="6.5" height="5" rx="1"/>'
            '<rect x="4" y="11" width="6.5" height="5" rx="1"/><rect x="13.5" y="14" width="6.5" height="5" rx="1"/>',
    "mic": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"/>',
    "fuel": _P.format("M4 21V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v16M3 21h12M4 10h10M14 8h2a2 2 0 0 1 2 2v6.5a1.5 1.5 0 0 0 3 0V8l-3-3"),
    "gauge": '<path d="M4.2 17.5a9 9 0 1 1 15.6 0"/><path d="m12 13.5 4.5-4.5"/><circle cx="12" cy="14" r="1.6"/>',
    "pedals": '<rect x="4" y="9" width="6" height="12" rx="1.5"/><rect x="13" y="4" width="7" height="17" rx="1.5"/><path d="M5.5 13h3M14.5 9h4M14.5 13h4"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3"/>',
    "tyre": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><path d="M12 3v5M12 16v5M3 12h5M16 12h5"/>',
    "sliders": _P.format("M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0")
               + '<circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    "engine": _P.format("M4 10v6M4 13h2.5M6.5 9H10V7h4v2h2l2 2.5h2v5h-2L16 19h-6l-3.5-3V9zM10 5h4"),
    "map": _P.format("M9 4 3 6.5v13.5l6-2.5 6 2.5 6-2.5V4l-6 2.5zM9 4v13.5M15 6.5V20"),
    "cloud": _P.format("M7 18.5a4.5 4.5 0 0 1-.6-9A6 6 0 0 1 18 8.5a4.5 4.5 0 0 1-.5 10z"),
    "wifi": _P.format("M2.5 9a14 14 0 0 1 19 0M5.5 12.5a9.5 9.5 0 0 1 13 0M8.5 16a5 5 0 0 1 7 0M12 19.5h.01"),
    "cpu": '<rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9.5" y="9.5" width="5" height="5" rx="1"/>'
           '<path d="M9.5 2.5v3.5M14.5 2.5v3.5M9.5 18v3.5M14.5 18v3.5M2.5 9.5H6M2.5 14.5H6M18 9.5h3.5M18 14.5h3.5"/>',
}

_cache: dict = {}


def icon_pixmap(name: str, color: str = None, size: int = 18, dpr: float = 2.0) -> QPixmap:
    color = color or T["muted"]
    key = (name, color, size, dpr)
    pm = _cache.get(key)
    if pm is not None:
        return pm
    try:
        from PySide6.QtSvg import QSvgRenderer
    except ImportError:  # be QtSvg - tuščia ikona, bet langas veikia
        pm = QPixmap(1, 1)
        pm.fill(Qt.GlobalColor.transparent)
        _cache[key] = pm
        return pm
    body = _ICONS.get(name, _ICONS["widgets"])
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    r = QSvgRenderer(QByteArray(svg.encode()))
    px = int(round(size * dpr))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p, QRectF(0, 0, px, px))
    p.end()
    pm.setDevicePixelRatio(dpr)
    _cache[key] = pm
    return pm


def icon(name: str, color: str = None, size: int = 18) -> QIcon:
    ic = QIcon()
    ic.addPixmap(icon_pixmap(name, color, size))
    return ic


def qcolor(token: str) -> QColor:
    v = T.get(token, token)
    if v.startswith("rgba"):
        r, g, b, a = [float(x) for x in v[5:-1].split(",")]
        return QColor(int(r), int(g), int(b), int(a * 255))
    return QColor(v)


ICON_SIZE = QSize(18, 18)
