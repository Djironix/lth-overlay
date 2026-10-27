"""Spalvos, šriftai ir skaičių formatavimas.

Visi QColor/QFont objektai sukuriami vieną kartą ir pernaudojami, kad
piešimas neturėtų alokacijų.
"""
from __future__ import annotations

import math

from PySide6.QtGui import QColor, QFont, QFontMetricsF

THEMES = {
    # LTH: logotipo auksas ant beveik juodo fono
    "lth": {
        "name": "LTH", "font": "montserrat", "header_style": "gold",
        "bg": (11, 11, 13), "bg_alpha": 0.78, "row_alt": (255, 255, 255, 14), "header": (6, 6, 8),
        "text": (246, 244, 238), "dim": (168, 160, 144), "accent": (236, 190, 88), "me_bg": (236, 190, 88, 46),
        "good": (92, 214, 122), "bad": (255, 88, 88), "purple": (190, 120, 255), "blue": (104, 172, 255),
        "red": (255, 88, 88), "pit": (130, 128, 122), "yellow": (251, 208, 105), "border": (0, 0, 0, 0),
        "ink": (12, 10, 4), "shadow": True, "row_k": 1.58, "radius": 3, "lumina": True, "upper_names": True,
    },
    # Tamsus, modernus stilius: Montserrat, tamsios eilutės, klasės spalvos linijos, šešėliai
    "racelab": {
        "name": "Modern dark", "font": "montserrat", "header_style": "marker",
        "bg": (18, 18, 21), "bg_alpha": 0.55, "row_alt": (255, 255, 255, 21), "header": (10, 10, 12),
        "text": (240, 240, 244), "dim": (160, 160, 170), "accent": (209, 4, 4), "me_bg": (255, 255, 255, 52),
        "good": (77, 211, 14), "bad": (254, 23, 31), "purple": (186, 104, 255), "blue": (92, 170, 255),
        "red": (254, 23, 31), "pit": (130, 130, 138), "yellow": (255, 210, 60), "border": (0, 0, 0, 0),
        "ink": (0, 0, 0), "shadow": True, "row_k": 1.58, "radius": 4, "lumina": True, "upper_names": True,
    },
    "carbon": {
        "name": "Carbon", "font": "barlow", "header_style": "line",
        "bg": (22, 23, 26), "bg_alpha": 0.9, "row_alt": (255, 255, 255, 10), "header": (32, 33, 38),
        "text": (232, 233, 238), "dim": (142, 145, 156), "accent": (226, 228, 235), "me_bg": (255, 255, 255, 34),
        "good": (70, 220, 140), "bad": (255, 96, 96), "purple": (184, 122, 255), "blue": (96, 176, 255),
        "red": (255, 96, 96), "pit": (118, 120, 128), "yellow": (255, 206, 72), "border": (0, 0, 0, 0),
        "ink": (0, 0, 0), "shadow": False, "row_k": 1.55, "radius": 2, "lumina": False, "upper_names": True,
    },
    "neon": {
        "name": "Midnight neon", "font": "rajdhani", "header_style": "marker",
        "bg": (10, 8, 24), "bg_alpha": 0.82, "row_alt": (120, 90, 255, 18), "header": (18, 12, 40),
        "text": (240, 238, 255), "dim": (150, 140, 190), "accent": (255, 46, 136), "me_bg": (255, 46, 136, 44),
        "good": (0, 245, 170), "bad": (255, 70, 110), "purple": (196, 120, 255), "blue": (0, 214, 255),
        "red": (255, 70, 110), "pit": (120, 110, 150), "yellow": (255, 222, 80), "border": (0, 0, 0, 0),
        "ink": (8, 4, 20), "shadow": True, "row_k": 1.6, "radius": 8, "lumina": True, "upper_names": True,
    },
    "broadcast": {
        "name": "Broadcast", "font": "saira", "header_style": "solid",
        "bg": (14, 22, 38), "bg_alpha": 0.92, "row_alt": (255, 255, 255, 12), "header": (226, 34, 44),
        "text": (248, 250, 255), "dim": (150, 166, 190), "accent": (226, 34, 44), "me_bg": (255, 255, 255, 40),
        "good": (60, 220, 120), "bad": (255, 84, 84), "purple": (190, 120, 255), "blue": (90, 170, 255),
        "red": (255, 84, 84), "pit": (120, 132, 150), "yellow": (255, 210, 70), "border": (0, 0, 0, 0),
        "ink": (0, 0, 0), "shadow": False, "row_k": 1.62, "radius": 0, "lumina": False, "upper_names": True,
    },
    "glass": {
        "name": "Glass", "font": "montserrat", "header_style": "plain",
        "bg": (18, 20, 26), "bg_alpha": 0.36, "row_alt": (255, 255, 255, 16), "header": (255, 255, 255),
        "header_alpha": 0.08,
        "text": (255, 255, 255), "dim": (205, 210, 220), "accent": (140, 200, 255), "me_bg": (255, 255, 255, 50),
        "good": (110, 240, 150), "bad": (255, 120, 120), "purple": (205, 150, 255), "blue": (140, 200, 255),
        "red": (255, 120, 120), "pit": (180, 186, 196), "yellow": (255, 224, 110), "border": (0, 0, 0, 0),
        "ink": (0, 0, 0), "shadow": True, "row_k": 1.6, "radius": 10, "lumina": True, "upper_names": False,
    },
    "contrast": {
        "name": "High contrast", "font": "system", "header_style": "line",
        "bg": (0, 0, 0), "bg_alpha": 0.94, "row_alt": (255, 255, 255, 22), "header": (0, 0, 0),
        "text": (255, 255, 255), "dim": (215, 215, 215), "accent": (255, 214, 0), "me_bg": (255, 214, 0, 60),
        "good": (0, 255, 120), "bad": (255, 70, 70), "purple": (215, 140, 255), "blue": (80, 190, 255),
        "red": (255, 70, 70), "pit": (170, 170, 170), "yellow": (255, 214, 0), "border": (0, 0, 0, 0),
        "ink": (0, 0, 0), "shadow": False, "row_k": 1.72, "radius": 2, "lumina": False, "upper_names": True,
    },
    "classic": {
        "name": "Classic gold", "font": "saira", "header_style": "line",
        "bg": (12, 12, 14), "bg_alpha": 0.82, "row_alt": (255, 255, 255, 10), "header": (24, 24, 28),
        "text": (238, 238, 238), "dim": (150, 150, 158), "accent": (226, 177, 60), "me_bg": (226, 177, 60, 46),
        "good": (64, 214, 120), "bad": (255, 86, 86), "purple": (186, 104, 255), "blue": (92, 160, 255),
        "red": (255, 92, 92), "pit": (120, 120, 128), "yellow": (255, 210, 60), "border": (226, 177, 60, 0),
    },
    "light": {
        "name": "Paddock light", "font": "montserrat", "header_style": "line",
        "bg": (247, 246, 242), "bg_alpha": 0.92, "row_alt": (0, 0, 0, 10), "header": (232, 230, 224),
        "text": (18, 18, 22), "dim": (96, 96, 104), "accent": (186, 134, 22), "me_bg": (236, 190, 88, 80),
        "good": (16, 150, 72), "bad": (200, 40, 40), "purple": (130, 60, 200), "blue": (30, 100, 210),
        "red": (210, 40, 40), "pit": (140, 140, 140), "yellow": (176, 128, 0), "border": (0, 0, 0, 0),
        "row_k": 1.6, "radius": 6,
    },
    "minimal": {
        "name": "Minimal", "font": "barlow", "header_style": "plain",
        "bg": (0, 0, 0), "bg_alpha": 0.45, "row_alt": (255, 255, 255, 0), "header": (0, 0, 0),
        "text": (255, 255, 255), "dim": (190, 190, 190), "accent": (255, 255, 255), "me_bg": (255, 255, 255, 40),
        "good": (90, 230, 140), "bad": (255, 110, 110), "purple": (200, 130, 255), "blue": (120, 180, 255),
        "red": (255, 110, 110), "pit": (150, 150, 150), "yellow": (255, 220, 90), "border": (0, 0, 0, 0),
    },
}

import os

FONT_DIR = os.path.join(os.path.dirname(__file__), "data", "fonts")
# Bundled fonts (SIL Open Font License, see data/fonts/OFL-*.txt)
FONT_CHOICES = {  # raktas: (šeima, pavadinimas, grupė)
    "montserrat": ("Montserrat", "Montserrat", "Wide"),
    "exo2": ("Exo 2", "Exo 2", "Techno"),
    "spacegrotesk": ("Space Grotesk", "Space Grotesk", "Wide"),
    "kanit": ("Kanit", "Kanit", "Wide"),
    "titillium": ("Titillium Web", "Titillium Web", "Wide"),
    "russo": ("Russo One", "Russo One", "Techno"),
    "saira": ("Saira Condensed", "Saira Condensed", "Condensed"),
    "sairasemi": ("Saira SemiCondensed", "Saira SemiCondensed", "Condensed"),
    "barlow": ("Barlow Condensed", "Barlow Condensed", "Condensed"),
    "barlowsemi": ("Barlow Semi Condensed", "Barlow Semi Condensed", "Condensed"),
    "oswald": ("Oswald", "Oswald", "Condensed"),
    "robotocondensed": ("Roboto Condensed", "Roboto Condensed", "Condensed"),
    "archivo": ("Archivo Narrow", "Archivo Narrow", "Condensed"),
    "plex": ("IBM Plex Sans Condensed", "IBM Plex Sans Condensed", "Condensed"),
    "teko": ("Teko", "Teko", "Condensed"),
    "rajdhani": ("Rajdhani", "Rajdhani", "Techno"),
    "chakra": ("Chakra Petch", "Chakra Petch", "Techno"),
    "jetbrains": ("JetBrains Mono", "JetBrains Mono", "Mono"),
    "system": ("Bahnschrift", "Bahnschrift (Windows)", "System"),
}
FONT_GROUPS = ("Wide", "Condensed", "Techno", "Mono", "System")
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
    def __init__(self, theme: str = "lth", opacity: float = 1.0, overrides: dict | None = None):
        t = dict(THEMES.get(theme, THEMES["lth"]))
        for k, v in (overrides or {}).items():  # vartotojo spalvos (Control Center → Appearance)
            if k in t and isinstance(v, str) and v.startswith("#") and len(v) in (7, 9):
                c = QColor(v)
                if c.isValid():
                    t[k] = (c.red(), c.green(), c.blue()) if len(t[k]) == 3 else (c.red(), c.green(), c.blue(), t[k][3])
        self.key = theme
        self.bg = QColor(*t["bg"], int(255 * t["bg_alpha"] * opacity))
        ha = t.get("header_alpha")
        self.header = QColor(*t["header"], int(255 * (ha * opacity if ha is not None
                                                      else min(1.0, t["bg_alpha"] * opacity + 0.08))))
        self.header_style = t.get("header_style", "marker" if t.get("lumina") else "line")
        self.recommended_font = t.get("font")
        self.row_alt = QColor(*t["row_alt"])
        for k in ("text", "dim", "accent", "good", "bad", "purple", "blue", "red", "pit", "yellow"):
            setattr(self, k, QColor(*t[k]))
        self.me_bg = QColor(*t["me_bg"])
        # neutrali „tuščios juostos“ spalva (progreso juostos, segmentai) - nepriklauso nuo antraštės stiliaus
        self.track = QColor(self.text.red(), self.text.green(), self.text.blue(), 34)
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


_PROBE = {}
try:
    _TNUM = QFont.Tag("tnum")
except (AttributeError, TypeError):
    _TNUM = None


def _probe(family: str):
    """(didžiųjų raidžių aukštis / px, skaitmens plotis / didž. aukštis) - kad visi šriftai atrodytų vienodo dydžio."""
    hit = _PROBE.get(family)
    if hit is None:
        f = QFont()
        f.setFamilies([family])
        f.setPixelSize(100)
        m = QFontMetricsF(f)
        cap = m.capHeight() / 100.0 or 0.7
        digit = m.horizontalAdvance("0123456789") / 10.0 / 100.0
        hit = _PROBE[family] = (max(0.4, min(0.9, cap)), digit / max(cap, 0.01))
    return hit


class Fonts:
    def __init__(self, scale: float = 1.0, choice: str = "saira"):
        load_fonts()
        self.scale = scale
        family = FONT_CHOICES.get(choice, FONT_CHOICES["saira"])[0]
        self.families = [family] + [f for f in FALLBACK if f != family]
        cap, digit_ratio = _probe(family)
        wide = digit_ratio > 0.8
        # Atskaitos: Montserrat (platūs) ir Saira Condensed (siauri) - tokio dydžio, kaip buvo suderinta
        ref_cap = _probe("Montserrat" if wide else "Saira Condensed")[0]
        k = ref_cap / cap  # vienodas didžiųjų raidžių aukštis visiems šriftams
        if not wide:
            k *= 1.14  # siauri šriftai - šiek tiek aukštesni
        if wide:  # platūs: šiek tiek mažesni, pusjuodžiai kaip modernuose overlay'uose
            self.base = self._font(12.0 * scale * k, QFont.Weight.DemiBold)
            self.bold = self._font(12.0 * scale * k, QFont.Weight.Bold)
            self.small = self._font(10.2 * scale * k, QFont.Weight.Medium)
            self.tiny = self._font(8.8 * scale * k, QFont.Weight.Bold)
            self.big = self._font(19.0 * scale * k, QFont.Weight.DemiBold)
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
        self.huge = self._font(self.big.pixelSize() * 1.9, QFont.Weight.Bold)
        self.mid = self._font(self.base.pixelSize() * 1.35, QFont.Weight.DemiBold)
        self.m_big = QFontMetricsF(self.big)
        self.m_huge = QFontMetricsF(self.huge)
        self.m_mid = QFontMetricsF(self.mid)
        # Išdėstymo vienetai iš didžiųjų raidžių aukščio, ne iš šrifto eilutės aukščio
        # (siaurų lenktyninių šriftų tarpai tarp eilučių labai dideli).
        em_k = (1.45 if wide else 1.22) * cap / ref_cap
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
        if _TNUM is not None:  # vienodo pločio skaitmenys: gap'ai „nešokinėja“ pločiu
            try:
                f.setFeature(_TNUM, 1)
            except (AttributeError, TypeError):
                pass
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
