"""Lietaus patarimai (Rain Master): trumpi call'ai virš Weather ir ilgesni paaiškinimai.

Žinios - iš Regio (LTH Racing) video „Mokomės važiuoti per lietų iRacing“.
iRacing lietaus modelis keičiasi kas sezoną, todėl trasoms skirti patarimai
pažymėti „may change by season“.

Call'ai: 2-3 žodžiai, didžiosiomis. Vienas vienu metu. Atsiranda pasikeitus
sąlygoms ir dingsta po SHOW_S; tas pats call kartojamas ne dažniau nei COOLDOWN_S.
Padangų call'ai (WET TYRES / TRY DRY TYRES) rodomi visą laiką, kol padangos netinka.
"""
from __future__ import annotations

from dataclasses import dataclass

SHOW_S = 8.0
COOLDOWN_S = 300.0

# lygiai (iRacing TrackWetness)
DRY, MOSTLY_DRY, VERY_LIGHT, LIGHT, MODERATE, VERY_WET, EXTREME = 1, 2, 3, 4, 5, 6, 7

# raktas: (call, rūšis, paaiškinimas)   rūšis: tyres (geltona), change (mėlyna), drive (pilka)
CALLS = {
    "wet_tyres": ("WET TYRES", "tyres", "Lightly wet or wetter: wet tyres are the way to go."),
    "try_dries": ("TRY DRY TYRES", "tyres", "The line is drying. Consider dry tyres."),
    "dries_ok": ("DRY TYRES OK", "tyres", "Very lightly wet: dry tyres still work if they are warm."),
    "keep_hot": ("KEEP TYRES HOT", "tyres", "Dry tyres in the wet only work when fully warm."),
    "hidden_water": ("HIDDEN WATER", "change", "Track looks dry, but water is collecting in some corners."),
    "puddles": ("PUDDLES ON TRACK", "change", "Drying, but puddles are still there. Easy to spin."),
    "cold_wet": ("COLD WET TYRES", "tyres", "Pit exit in the wet: cold tyres, be gentle."),
    "markers": ("BRAKE BY MARKERS", "drive", "No visibility in spray: brake by landmarks, count 1-2."),
    "white_lines": ("NO WHITE LINES", "drive", "Never brake on white lines in the rain."),
    "smooth": ("SMOOTH INPUTS", "drive", "Light inputs. Never full throttle out of wet corners."),
    "brake_earlier": ("BRAKE EARLIER", "drive", "Most braking points as dry, some corners much earlier."),
    "short_shift": ("SHORT SHIFT", "drive", "Wheelspin? Exit a corner one gear higher."),
    "rain_near": ("RAIN NEAR TRACK", "change", "Trust the radar, not the rain % or the spotter."),
}
ENGINEER_KEYS = ("wet_tyres", "try_dries", "hidden_water", "puddles")

# Ilgesni patarimai Rain Master išskleistam režimui: (nuo lygio, iki lygio, tema, tekstas)
TIPS = [
    (VERY_LIGHT, VERY_LIGHT, "Tyres", "Very lightly wet: dry tyres still work."),
    (LIGHT, LIGHT, "Tyres", "Lightly wet: wet tyres advised. Dries only if they are fully warm."),
    (LIGHT, EXTREME, "Tyres", "Wet tyres work from about 70°C. After that, stop watching temps and push."),
    (VERY_LIGHT, MODERATE, "Danger", "Invisible track: it looks dry while water already collects in corners."),
    (MOSTLY_DRY, EXTREME, "Golden rule", "Found your wet pattern? Don't change it mid-race, or you will spin."),
    (VERY_LIGHT, EXTREME, "Slow corners", "Normal line through the water. With lots of water: half the car on "
                                          "the dry, half on the wet."),
    (VERY_LIGHT, EXTREME, "Fast corners", "Go wide around the water. The wet line works with careful throttle."),
    (VERY_LIGHT, EXTREME, "Straights", "Find the dry strip. Driving through water costs 1-3 km/h."),
    (LIGHT, EXTREME, "Inputs", "Smooth and light. Never full throttle out of wet corners."),
    (LIGHT, EXTREME, "Aquaplaning", "Lift when the car starts to slide, then pulse the throttle to push the "
                                    "water out of the tyres."),
    (LIGHT, EXTREME, "Wheelspin", "Exit corners a gear higher than in the dry."),
    (LIGHT, EXTREME, "Braking", "About 90% of braking points are as dry. Where water collects, brake much earlier."),
    (LIGHT, EXTREME, "White lines", "Never brake on white lines. The car snaps instantly."),
    (VERY_LIGHT, EXTREME, "Kerbs", "Stay off kerbs. The green paint behind them is very slippery."),
    (MODERATE, EXTREME, "Pit exit", "Cold, wet tyres after a stop: many cars spin on pit exit."),
    (MODERATE, EXTREME, "Visibility", "In spray, pick landmarks (a sign, a truck, a tree) and count 1-2 to brake."),
    (VERY_LIGHT, EXTREME, "Learn it", "Practise in moderately wet to learn where the puddles are. Test drive with "
                                      "the racing line on: there is no shame in it."),
    (MOSTLY_DRY, EXTREME, "Setup", "Rain all race: wet setup and wet tyres. Avoid dry tyres on a wet setup."),
]

# Trasoms skirti patarimai (pavadinimo fragmentas -> patarimai). Gali keistis kas sezoną.
TRACK_TIPS = {
    "spa": ["Eau Rouge: middle of the track along the water edge, kerb is fine, lift into Raidillon.",
            "Watch the water wedge where the car drifts left: it spins you, especially when drying.",
            "Blanchimont: fast and brave, but stay away from the left kerb, water collects there."],
    "le mans": ["Straights: drive right in the middle.",
                "The 90° corner after the first straight sometimes has a dry line, sometimes not."],
    "sarthe": ["Straights: drive right in the middle."],
    "silverstone": ["Some kerbs can be used even on dry tyres. Elsewhere they push you onto slippery grass."],
    "barcelona": ["One corner collects a lot of water: brake much earlier there."],
    "catalunya": ["One corner collects a lot of water: brake much earlier there."],
}


@dataclass
class RainCall:
    key: str
    text: str
    kind: str
    detail: str
    persistent: bool = False


class RainCaller:
    def __init__(self):
        self.reset()

    def reset(self):
        self._last = None  # (lygis, tendencija, padangos, boksuose, mašina arti)
        self._shown = None  # (RainCall, nuo kada)
        self._cool = {}

    def _call(self, key, persistent=False) -> RainCall:
        text, kind, detail = CALLS[key]
        return RainCall(key, text, kind, detail, persistent)

    def update(self, t: float, wetness: int, trend: str, precipitation: float, tyres: int, on_pit: bool,
               car_close_ahead: bool) -> RainCall | None:
        if wetness <= 0:  # nežinoma (garaže, meniu)
            return None
        if self._shown is not None and t < self._shown[1] - 1:  # replay / nauja sesija
            self.reset()
        # 1) padangos - visada, kol netinka
        if tyres == 0 and wetness >= LIGHT:
            return self._call("wet_tyres", True)
        if tyres == 1 and (wetness <= DRY or (wetness <= MOSTLY_DRY and trend == "drying")):
            return self._call("try_dries", True)
        # 2) trumpi call'ai pasikeitus sąlygoms
        state = (wetness, trend, tyres, on_pit, car_close_ahead, precipitation > 0.02)
        changed = state != self._last
        self._last = state
        if self._shown is not None and t - self._shown[1] < SHOW_S:
            return self._shown[0]
        self._shown = None
        if not changed:
            return None
        for key in self._candidates(wetness, trend, precipitation, tyres, on_pit, car_close_ahead):
            if t - self._cool.get(key, -1e9) >= COOLDOWN_S:
                self._cool[key] = t
                call = self._call(key)
                self._shown = (call, t)
                return call
        return None

    @staticmethod
    def _candidates(w, trend, precip, tyres, on_pit, close):
        out = []
        if on_pit and w >= MODERATE:
            out.append("cold_wet")
        if tyres == 0 and w == VERY_LIGHT:
            out.append("dries_ok")
        if tyres == 0 and VERY_LIGHT <= w <= LIGHT:
            out.append("keep_hot")
        if trend == "wetter" and MOSTLY_DRY <= w <= LIGHT:
            out.append("hidden_water")
        if trend == "drying" and w >= MOSTLY_DRY:
            out.append("puddles")
        if w >= MODERATE and close:
            out.append("markers")
        if w >= LIGHT:
            out += ["white_lines", "smooth"]
        if w >= MODERATE:
            out.append("brake_earlier")
        if w >= VERY_WET:
            out.append("short_shift")
        if w <= DRY and precip > 0.02:
            out.append("rain_near")
        return out


def tips_for(wetness: int, track_name: str = "") -> list:
    """Rain Master išskleistam režimui: [(tema, tekstas)] dabartinėms sąlygoms + trasos patarimai."""
    general = [(topic, text) for lo, hi, topic, text in TIPS if lo <= wetness <= hi]
    if not general:
        return []
    track = [("This track (may change by season)", t) for t in track_tips(track_name)]
    return general[:1] + track + general[1:]  # padangos, tada trasa, tada visa kita


def track_tips(track_name: str) -> list:
    name = (track_name or "").lower()
    for frag, tips in TRACK_TIPS.items():
        if frag in name:
            return list(tips)
    return []
