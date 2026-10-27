"""Spalvos, šriftai ir skaičių formatavimas.

Visi QColor/QFont objektai sukuriami vieną kartą ir pernaudojami, kad
piešimas neturėtų alokacijų.
"""
from __future__ import annotations

import math

from PySide6.QtGui import QColor, QFont, QFontMetricsF

THEMES = {
    # Tamsus, modernus stilius: Montserrat, tamsios eilutės, klasės spalvos linijos, šešėliai
    "racelab": {
        "name": "Modern dark (Montserrat)",
        "bg": (18, 18, 21), "bg_alpha": 0.55, "row_alt": (255, 255, 255, 21), "header": (10, 10, 12),
        "text": (240, 240, 244), "dim": (160, 160, 170), "accent": (209, 4, 4), "me_bg": (255, 255, 255, 52),
        "good": (77, 211, 14), "bad": (254, 23, 31), "purple": (186, 104, 255), "blue": (92, 170, 255),
        "red": (254, 23, 31), "pit": (130, 130, 138), "yellow": (255, 210, 60), "border": (0, 0, 0, 0),
        "ink": (0, 0, 0), "shadow": True, "row_k": 1.58, "radius": 4, "lumina": True, "upper_names": True,
    },
    "lth": {
        "name": "LTH dark",
        "bg": (12, 12, 14), "bg_alpha": 0.82, "row_alt": (255, 255, 255, 10), "header": (24, 24, 28),
        "text": (238, 238, 238), "dim": (150, 150, 158), "accent": (226, 177, 60), "me_bg": (226, 177, 60, 46),
        "good": (64, 214, 120), "bad": (255, 86, 86), "purple": (186, 104, 255), "blue": (92, 160, 255),
        "red": (255, 92, 92), "pit": (120, 120, 128), "yellow": (255, 210, 60), "border": (226, 177, 60, 0),
    },
    "light": {
        "name": "LTH light",
        "bg": (246, 246, 244), "bg_alpha": 0.88, "row_alt": (0, 0, 0, 10), "header": (232, 232, 228),
        "text": (20, 20, 22), "dim": (100, 100, 108), "accent": (176, 128, 20), "me_bg": (226, 177, 60, 70),
        "good": (16, 150, 72), "bad": (200, 40, 40), "purple": (130, 60, 200), "blue": (30, 100, 210),
        "red": (210, 40, 40), "pit": (140, 140, 140), "yellow": (190, 140, 0), "border": (0, 0, 0, 0),
    },
    "minimal": {
        "name": "Minimal",
        "bg": (0, 0, 0), "bg_alpha": 0.45, "row_alt": (255, 255, 255, 0), "header": (0, 0, 0),
        "text": (255, 255, 255), "dim": (190, 190, 190), "accent": (255, 255, 255), "me_bg": (255, 255, 255, 40),
        "good": (90, 230, 140), "bad": (255, 110, 110), "purple": (200, 130, 255), "blue": (120, 180, 255),
        "red": (255, 110, 110), "pit": (150, 150, 150), "yellow": (255, 220, 90), "border": (0, 0, 0, 0),
    },
}

import os

FONT_DIR = os.path.join(os.path.dirname(__file__), "data", "fonts")
# Bundled fonts (SIL Open Font License, see data/fonts/OFL-*.txt)
FONT_CHOICES = {
    "montserrat": ("Montserrat", "Montserrat (modern, wide)"),
    "saira": ("Saira Condensed", "Saira Condensed (slim, racing)"),
    "barlow": ("Barlow Condensed", "Barlow Condensed (slim, clean)"),
    "rajdhani": ("Rajdhani", "Rajdhani (squared, technical)"),
    "chakra": ("Chakra Petch", "Chakra Petch (angular)"),
    "system": ("Bahnschrift", "Bahnschrift (Windows system)"),
}
FALLBACK = ["Bahnschrift", "Segoe UI", "Segoe UI Symbol", "DejaVu Sans", "Arial"]
_loaded = False


def load_fonts():
    """Registers bundled fonts once (no install needed, nothing written to Windows)."""
    global _loaded
    if _loaded:
        return
    from PySide6.QtGui import QFontDatabase
    for name in sorted(os.listdir(FONT_DIR)) if os.path.isdir(FONT_DIR) else []:
        if name.lower().endswith(".ttf"):
            QFontDatabase.addApplicationFont(os.path.join(FONT_DIR, name))
    _loaded = True


class Palette:
    def __init__(self, theme: str = "lth", opacity: float = 1.0):
        t = THEMES.get(theme, THEMES["lth"])
        self.key = theme
        self.bg = QColor(*t["bg"], int(255 * t["bg_alpha"] * opacity))
        self.header = QColor(*t["header"], int(255 * min(1.0, t["bg_alpha"] * opacity + 0.08)))
        self.row_alt = QColor(*t["row_alt"])
        for k in ("text", "dim", "accent", "good", "bad", "purple", "blue", "red", "pit", "yellow"):
            setattr(self, k, QColor(*t[k]))
        self.me_bg = QColor(*t["me_bg"])
        self.border = QColor(*t["border"])
        self.ink = QColor(*t.get("ink", (0, 0, 0)), 230)  # tekstas ant ryškių (klasės spalvos) fonų
        self.shadow = bool(t.get("shadow", False))
        self.shadow_color = QColor(0, 0, 0, 190)
        self.row_k = float(t.get("row_k", 1.62))
        self.radius = float(t.get("radius", 6))
        self.lumina = bool(t.get("lumina", False))  # klasės spalvos linija po eilute
        self.upper_names = bool(t.get("upper_names", False))
        self.edit = QColor(226, 177, 60)
        self._class_cache = {}

    def class_color(self, rgb: int) -> QColor:
        c = self._class_cache.get(rgb)
        if c is None:
            c = QColor((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255)
            self._class_cache[rgb] = c
        return c

    def hex_color(self, value: str) -> QColor:
        c = self._class_cache.get(value)
        if c is None:
            c = QColor(value)
            self._class_cache[value] = c
        return c


class Fonts:
    def __init__(self, scale: float = 1.0, choice: str = "saira"):
        load_fonts()
        self.scale = scale
        family = FONT_CHOICES.get(choice, FONT_CHOICES["saira"])[0]
        self.families = [family] + [f for f in FALLBACK if f != family]
        wide = choice == "montserrat"
        k = 1.0 if choice == "system" else 1.0 if wide else 1.14  # condensed fonts are narrow: a bit taller
        if wide:  # Montserrat: plati, todėl šiek tiek mažesnė; pusjuodis kaip modernuose overlay'uose
            self.base = self._font(12.0 * scale, QFont.Weight.DemiBold)
            self.bold = self._font(12.0 * scale, QFont.Weight.Bold)
            self.small = self._font(10.2 * scale, QFont.Weight.Medium)
            self.tiny = self._font(8.8 * scale, QFont.Weight.Bold)
            self.big = self._font(19.0 * scale, QFont.Weight.DemiBold)
        else:
            self.base = self._font(12.0 * scale * k, QFont.Weight.Normal)
            self.bold = self._font(12.0 * scale * k, QFont.Weight.DemiBold)
            self.small = self._font(10.5 * scale * k, QFont.Weight.Normal)
            self.tiny = self._font(9.0 * scale * k, QFont.Weight.DemiBold)
            self.big = self._font(20.0 * scale * k, QFont.Weight.Medium)
        self.m_base = QFontMetricsF(self.base)
        self.m_bold = QFontMetricsF(self.bold)
        self.m_small = QFontMetricsF(self.small)
        self.m_tiny = QFontMetricsF(self.tiny)
        # Layout units from the pixel size, not the font's line height (condensed racing
        # fonts have very tall line gaps, which would make rows too high).
        em_k = 1.45 if wide else 1.22  # Montserrat turi didesnį skaitmenų aukštį
        self.em_base = self.base.pixelSize() * em_k
        self.em_bold = self.bold.pixelSize() * em_k
        self.em_small = self.small.pixelSize() * em_k

    def _font(self, px: float, weight) -> QFont:
        f = QFont()
        f.setFamilies(self.families)
        f.setPixelSize(max(6, int(round(px))))
        f.setWeight(weight)
        f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        return f


# ---------------- formatavimas ----------------
def fmt_lap(s: float) -> str:
    if not s or s <= 0 or not math.isfinite(s):
        return "–"
    m, sec = divmod(s, 60.0)
    return f"{int(m)}:{sec:06.3f}"


def fmt_gap(s, laps: int = 0, approx: bool = False) -> str:
    if laps:
        return f"+{laps} {'lap' if laps == 1 else 'laps'}"
    if s is None or not math.isfinite(s):
        return ""
    pre = "~" if approx else ""
    if abs(s) >= 60:
        m, sec = divmod(abs(s), 60)
        return f"{pre}{'+' if s >= 0 else '-'}{int(m)}:{sec:04.1f}"
    return f"{pre}{s:+.1f}"


def fmt_rel(s: float, approx: bool = False) -> str:
    pre = "~" if approx else ""
    return f"{pre}{s:+.1f}"


def fmt_clock(seconds: float) -> str:
    if seconds is None or seconds < 0 or seconds > 1e6:
        return ""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def short_name(row, mode: str, upper: bool = False) -> str:
    """upper=True: pavardė didžiosiomis (modernus stilius): "J. SMITH"."""
    u = (lambda s: s.upper()) if upper else (lambda s: s)
    if mode == "abbrev":
        if row.abbrev and "," in row.abbrev:  # iRacing: "Pavardė, V"
            last, first = [x.strip() for x in row.abbrev.split(",", 1)]
            return f"{first[:1]}. {u(last)}" if first else u(last)
        if row.name:
            parts = row.name.split()
            return f"{parts[0][0]}. {u(' '.join(parts[1:]))}" if len(parts) > 1 else row.name
        return row.abbrev
    if mode == "last":
        parts = (row.name or "").split()
        return u(parts[-1]) if parts else row.abbrev
    if mode == "three":
        parts = (row.name or row.abbrev or "?").split()
        return (parts[-1] if parts else "???")[:3].upper()
    return row.name or row.abbrev


def lt_count(n: int, one: str, few: str, many: str) -> str:
    """Lietuviška daugiskaita: 1 mašina, 2 mašinos, 10 mašinų, 21 mašina."""
    if n % 10 == 1 and n % 100 != 11:
        w = one
    elif 2 <= n % 10 <= 9 and not 12 <= n % 100 <= 19:
        w = few
    else:
        w = many
    return f"{n} {w}"
