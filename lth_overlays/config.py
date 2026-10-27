"""Nustatymai ir profiliai (JSON vartotojo aplanke).

Profiliai: atskiras išdėstymas lenktynėms, kvalifikacijai ir praktikai.
Persijungia automatiškai pagal sesijos tipą. Temą galima priskirti lygai
ar serijai (iRacing lygos / serijos ID).
"""
from __future__ import annotations

import copy
import json
import os
import sys

APP_DIR_NAME = "LTH Overlays"

STANDINGS_COLUMNS = {
    # raktas: (pavadinimas, numatyta)
    "pos": ("Position", True),
    "change": ("Change this lap", True),
    "number": ("Car number", True),
    "brand": ("Manufacturer", True),
    "name": ("Name", True),
    "gap": ("Gap to leader", True),
    "interval": ("Interval", True),
    "last": ("Last lap", True),
    "best": ("Best lap", True),
    "start": ("Positions since start", False),
    "irating": ("iRating", True),
    "license": ("License", False),
    "pit": ("Pit", True),
    "tire": ("Tyres", True),
}

RELATIVE_COLUMNS = {
    "pos": ("Position", True),
    "number": ("Car number", True),
    "name": ("Name", True),
    "irating": ("iRating", True),
    "license": ("License", True),
    "delta": ("Delta per lap", True),
    "catch": ("Laps to catch", True),
    "gap": ("Gap", True),
}

WEATHER_FIELDS = {
    "wetness": ("Track wetness", True),
    "track_temp": ("Track temperature", True),
    "air_temp": ("Air temperature", True),
    "precip": ("Rain", True),
    "skies": ("Sky", True),
    "wind": ("Wind", True),
    "humidity": ("Humidity", False),
    "fog": ("Fog", False),
    "time": ("Time of day", True),
    "trend": ("Trend", True),
}


def _cols(spec):
    return {k: v[1] for k, v in spec.items()}


DEFAULT_WIDGETS = {
    "standings": {"visible": True, "x": 24, "y": 180, "width": 500, "scale": 1.0, "opacity": 1.0,
                  "columns": _cols(STANDINGS_COLUMNS), "order": list(STANDINGS_COLUMNS),
                  "filter": "all", "top_n": 3, "around_n": 5, "max_rows": 26,
                  "class_mode": "grouped", "name_mode": "abbrev", "lth_only": False, "show_header": True},
    "relative": {"visible": True, "x": -500, "y": -340, "width": 420, "scale": 1.0, "opacity": 1.0,
                 "columns": _cols(RELATIVE_COLUMNS), "order": list(RELATIVE_COLUMNS),
                 "ahead": 4, "behind": 4, "name_mode": "abbrev", "show_header": True},
    "weather": {"visible": True, "x": -300, "y": 24, "width": 270, "scale": 1.0, "opacity": 1.0,
                "fields": _cols(WEATHER_FIELDS), "mode": "expanded", "only_when_wet": False},
    "engineer": {"visible": False, "x": -1, "y": 90, "width": 560, "scale": 1.0, "opacity": 1.0,
                 "types": {"ahead": True, "behind": True, "slow_car": True, "weather": True, "best_lap": True,
                           "time": True, "faster_class": True}},
    "perf": {"visible": False, "x": 24, "y": 24, "width": 230, "scale": 1.0, "opacity": 1.0},
}

DEFAULT_CONFIG = {
    "version": 4,
    "autostart": True,  # paleisti su Windows; laukia, kol įsijungs iRacing
    "autostart_done": False,
    "theme": "racelab",
    "font": "montserrat",
    "hotkey": "Ctrl+Shift+E",
    "engine_hz": 20,
    "auto_profile": True,
    "profile": "race",
    "lth_member_ids": [],  # iRacing ID sąrašas filtrui „tik LTH lyga“
    "series_themes": {},  # {"league:12345": "lth", "series:228": "minimal"}
    "profiles": {
        "race": {"name": "Race", "widgets": copy.deepcopy(DEFAULT_WIDGETS)},
        "qualify": {"name": "Qualifying", "widgets": copy.deepcopy(DEFAULT_WIDGETS)},
        "practice": {"name": "Practice", "widgets": copy.deepcopy(DEFAULT_WIDGETS)},
    },
}


def app_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(base, APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def _merge(defaults, data):
    """Nauji numatyti laukai atsiranda ir seniems failams."""
    if not isinstance(defaults, dict) or not isinstance(data, dict):
        return data if data is not None else copy.deepcopy(defaults)
    out = copy.deepcopy(defaults)
    for k, v in data.items():
        out[k] = _merge(defaults[k], v) if k in defaults else v
    return out


class Config:
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(app_dir(), "config.json")
        self.data = copy.deepcopy(DEFAULT_CONFIG)
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
            ver = int(raw.get("version", 1))
            if ver < 2:  # 0.1.x išdėstymai slėpė kitus automobilius
                raw = {k: v for k, v in raw.items() if k in ("theme", "font", "hotkey", "lth_member_ids", "series_themes")}
            if ver < 3:  # naujas numatytasis stilius (Montserrat + modernus); išdėstymas paliekamas
                raw.pop("theme", None)
                raw.pop("font", None)
            if ver < 4:  # "width" dabar saugomas be mastelio (plotis = width × scale): matomas plotis nesikeičia
                for prof in (raw.get("profiles") or {}).values():
                    for wc in ((prof or {}).get("widgets") or {}).values():
                        try:
                            s = float(wc.get("scale", 1.0) or 1.0)
                            if "width" in wc and s > 0:
                                wc["width"] = int(round(float(wc["width"]) / s))
                        except (TypeError, ValueError, AttributeError):
                            pass
            raw["version"] = 4
            self.data = _merge(DEFAULT_CONFIG, raw)
        except (OSError, ValueError):
            self.data = copy.deepcopy(DEFAULT_CONFIG)
        for p in self.data["profiles"].values():
            p["widgets"] = _merge(DEFAULT_WIDGETS, p.get("widgets", {}))

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)  # atominis: neliks pusiau įrašyto failo

    # ---- profiliai ----
    @property
    def profile_key(self) -> str:
        return self.data.get("profile", "race")

    def set_profile(self, key: str):
        if key in self.data["profiles"]:
            self.data["profile"] = key

    def widget(self, name: str) -> dict:
        return self.data["profiles"][self.profile_key]["widgets"][name]

    def theme_for(self, league_id: int, series_id: int) -> str:
        st = self.data.get("series_themes", {})
        return st.get(f"league:{league_id}") or st.get(f"series:{series_id}") or self.data.get("theme", "lth")

    def export_profile(self, key: str, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"lth_overlays_profile": 1, **self.data["profiles"][key]}, f, ensure_ascii=False, indent=1)

    def import_profile(self, key: str, path: str):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not data.get("lth_overlays_profile"):
            raise ValueError("Not an LTH Overlays profile file")
        data.pop("lth_overlays_profile")
        data["widgets"] = _merge(DEFAULT_WIDGETS, data.get("widgets", {}))
        self.data["profiles"][key] = data
