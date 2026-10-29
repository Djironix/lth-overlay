"""Nustatymai ir profiliai (JSON vartotojo aplanke).

Profiliai: atskiras išdėstymas lenktynėms, kvalifikacijai ir praktikai.
Persijungia automatiškai pagal sesijos tipą. Temą galima priskirti iRacing lygos sesijai
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

CONFIG_VERSION = 9

DEFAULT_CONFIG = {
    "version": CONFIG_VERSION,
    "autostart": True,  # paleisti su Windows; laukia, kol įsijungs iRacing
    "autostart_done": False,
    "theme": "lth",
    "theme_font": True,  # pasirinkus temą pritaikyti ir jos šriftą
    "font": "montserrat",
    "hotkey": "Ctrl+Shift+E",
    "engine_hz": 20,
    "auto_profile": True,
    "profile": "race",
    "series_themes": {},
    "outline": {"width": 1.0, "color": "accent", "opacity": 0.5},  # kontūras visiems valdikliams
    "friends": {},  # {"123456": {"name": "J. Smith", "color": "#ecbe58"}} - paryškinti Standings / Relative  # {"league:12345": "lth", "series:228": "minimal"}
    "custom_colors": {},  # vartotojo spalvų perrašymai temai: {"accent": "#e2b13c", ...}
    "class_colors": {},  # klasės spalvos perrašymas: {"GT3": "#ff5888"}
    "hotkeys": {"edit": "Ctrl+Shift+E", "toggle_all": "Ctrl+Shift+H", "rain_next": "Ctrl+Shift+R"},
    "open_control_center": True,
    "onboarding_done": False,  # pirmo paleidimo tutorialas  # atidaryti Control Center paleidus ranka
    "setups": {"auto": False},  # LTH setupų automatinis įdiegimas prisijungus prie sesijos
    "fps_cap": 0,  # Eco: visų „smooth“ valdiklių fps riba (0 = be ribos)
    "telemetry": {"record": True, "hz": 30, "auto_save_best": True, "save_sessions": True},  # savo ratų telemetrija
    "obs": {"enabled": False, "port": 8399, "fps": 30},  # OBS Browser Source serveris (tik 127.0.0.1)
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
        self.fresh = not os.path.exists(self.path)  # pirmas paleidimas (tutorialui)
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
            ver = int(raw.get("version", 1))
            if ver < 2:  # 0.1.x išdėstymai slėpė kitus automobilius
                raw = {k: v for k, v in raw.items() if k in ("theme", "font", "hotkey", "series_themes")}
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
            # v6: pašalinti lygos narių filtrai (programa skirta visai LTH bendruomenei)
            raw.pop("lth_member_ids", None)
            for prof in (raw.get("profiles") or {}).values():
                for wc in ((prof or {}).get("widgets") or {}).values():
                    if isinstance(wc, dict):
                        wc.pop("lth_only", None)
                        if wc.pop("race_only", False) and "sessions" not in wc:  # v7: matomumas pagal sesiją
                            wc["sessions"] = {"practice": False, "qualify": False, "warmup": False, "race": True}
            for prof in (raw.get("profiles") or {}).values():
                ws = (prof or {}).get("widgets") or {}
                if ver < 8:  # v0.6.1: mažiau CPU - nauji numatyti greito kelio dažniai (jei vartotojas nekeitė)
                    for name, old_hz, new_hz in (("lap_timer", 30, 10), ("track_map", 60, 30), ("flat_map", 60, 30)):
                        wc = ws.get(name)
                        if isinstance(wc, dict) and wc.get("smooth_hz") == old_hz:
                            wc["smooth_hz"] = new_hz
                    for name in ("standings", "relative"):  # stulpelių pavadinimai dabar įjungti numatytai
                        wc = ws.get(name)
                        if isinstance(wc, dict) and wc.get("column_header") is False:
                            wc["column_header"] = True
                if ver < 9:  # v0.6.2: drėgmė rodoma numatytai
                    wf = (ws.get("weather") or {}).get("fields")
                    if isinstance(wf, dict) and wf.get("humidity") is False:
                        wf["humidity"] = True
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

    def friends(self) -> dict:
        """Draugų / žymų spalvos: {iRacing ID: "#rrggbb"}."""
        out = {}
        for k, v in (self.data.get("friends") or {}).items():
            try:
                out[int(k)] = v.get("color", "#ecbe58") if isinstance(v, dict) else str(v)
            except (TypeError, ValueError):
                pass
        return out

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
