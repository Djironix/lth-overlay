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

# Valdiklių aprašai ir numatyti nustatymai - registry.py (vienas tiesos šaltinis)
from .registry import (DEFAULT_WIDGETS, ENGINEER_TYPES, RELATIVE_COLUMNS,  # noqa: E402,F401
                       STANDINGS_COLUMNS, WEATHER_FIELDS)

CONFIG_VERSION = 5

DEFAULT_CONFIG = {
    "version": CONFIG_VERSION,
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
    "custom_colors": {},  # vartotojo spalvų perrašymai temai: {"accent": "#e2b13c", ...}
    "class_colors": {},  # klasės spalvos perrašymas: {"GT3": "#ff5888"}
    "hotkeys": {"edit": "Ctrl+Shift+E", "toggle_all": "Ctrl+Shift+H"},
    "open_control_center": True,  # atidaryti Control Center paleidus ranka
    "snap": True,  # prilipimas prie tinklelio ir kitų valdiklių
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
            # v5: nauji valdikliai ir laukai ateina iš numatytų reikšmių (_merge)
            raw["version"] = CONFIG_VERSION
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
        widgets = self.data["profiles"][self.profile_key]["widgets"]
        if name not in widgets:  # naujas valdiklis profilyje, kuris jo dar neturėjo
            widgets[name] = copy.deepcopy(DEFAULT_WIDGETS[name])
        return widgets[name]

    def add_profile(self, key: str, name: str, copy_from: str | None = None):
        src = self.data["profiles"].get(copy_from or self.profile_key)
        widgets = copy.deepcopy(src["widgets"]) if src else copy.deepcopy(DEFAULT_WIDGETS)
        self.data["profiles"][key] = {"name": name, "widgets": widgets}

    def delete_profile(self, key: str):
        if key in ("race", "qualify", "practice"):
            raise ValueError("Built-in profiles cannot be deleted")
        self.data["profiles"].pop(key, None)
        if self.profile_key == key:
            self.data["profile"] = "race"

    def reset_widget(self, name: str):
        self.data["profiles"][self.profile_key]["widgets"][name] = copy.deepcopy(DEFAULT_WIDGETS[name])

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
