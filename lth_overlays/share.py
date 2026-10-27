"""Išdėstymo dalinimasis: .lthlayout failas arba trumpas kodas Discord žinutei.

Kodas: "LTH1:" + base64url(zlib(JSON)). Kad tilptų į Discord žinutę (2000 simbolių),
įrašomi tik įjungti valdikliai ir tik nuo numatytų reikšmių besiskiriantys laukai.
Importuojant padėtys perskaičiuojamos pagal gavėjo ekraną. Iš failo imami tik
duomenys - žinomi valdikliai ir laukai, to paties tipo kaip numatytieji.
"""
from __future__ import annotations

import base64
import copy
import json
import re
import zlib

from .registry import BY_NAME, DEFAULT_WIDGETS

PREFIX = "LTH1:"
DISCORD_LIMIT = 2000
_ALWAYS = ("x", "y", "width", "scale", "visible")
_FREE_TYPES = {"height": (int, float, type(None))}


def _diff(value, default):
    if isinstance(value, dict) and isinstance(default, dict):
        d = {k: _diff(v, default.get(k)) for k, v in value.items() if v != default.get(k)}
        return d
    return value


def export_layout(ctx, profile_key: str | None = None) -> dict:
    cfg = ctx.config
    key = profile_key or cfg.profile_key
    prof = cfg.data["profiles"][key]
    scr = ctx.screen_rect()
    widgets = {}
    for name, wc in prof["widgets"].items():
        if name not in DEFAULT_WIDGETS or not wc.get("visible"):
            continue
        d = DEFAULT_WIDGETS[name]
        out = {k: _diff(v, d.get(k)) for k, v in wc.items() if k in d and v != d.get(k) and k != "pos_v"}
        for k in _ALWAYS:
            out[k] = wc.get(k, d.get(k))
        if wc.get("height") is not None:
            out["height"] = wc["height"]
        # padėtis santykinai pagrindinio ekrano kampo
        out["x"] = int(out["x"]) - scr.x()
        out["y"] = int(out["y"]) - scr.y()
        widgets[name] = out
    return {"lth_layout": 1, "name": prof.get("name", key), "screen": [scr.width(), scr.height()],
            "theme": cfg.data.get("theme"), "font": cfg.data.get("font"), "widgets": widgets}


def encode(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return PREFIX + base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii").rstrip("=")


def decode(text: str) -> dict:
    """Priima kodą arba visą Discord žinutę su kodu viduje."""
    m = re.search(r"LTH1:([A-Za-z0-9_\-]+)", (text or "").replace("\n", "").replace(" ", ""))
    if not m:
        raise ValueError("No LTH layout code found. It starts with LTH1:")
    body = m.group(1)
    body += "=" * (-len(body) % 4)
    try:
        data = json.loads(zlib.decompress(base64.urlsafe_b64decode(body)).decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise ValueError("The code is damaged or incomplete. Copy the whole code and try again.") from e
    return validate(data)


def read_file(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if text.lstrip().startswith("LTH1:"):
        return decode(text)
    try:
        data = json.loads(text)
    except ValueError as e:
        raise ValueError("This is not an LTH layout file.") from e
    if isinstance(data, dict) and data.get("lth_overlays_profile"):  # senas 0.4 eksportas
        data = {"lth_layout": 1, "name": data.get("name", "Imported"), "screen": [1920, 1080],
                "widgets": {k: v for k, v in (data.get("widgets") or {}).items()
                            if isinstance(v, dict) and v.get("visible")}}
    return validate(data)


def write_file(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)


def _clean(value, default):
    """Tik to paties tipo reikšmės kaip numatytoji; žodynuose - tik žinomi raktai."""
    if isinstance(default, dict):
        if not isinstance(value, dict):
            return None
        out = {}
        for k, v in value.items():
            if k in default:
                c = _clean(v, default[k])
                if c is not None:
                    out[k] = c
        return out
    if isinstance(default, bool):
        return value if isinstance(value, bool) else None
    if isinstance(default, (int, float)) and not isinstance(default, bool):
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    if isinstance(default, str):
        return value if isinstance(value, str) and len(value) < 200 else None
    if isinstance(default, list):
        return [x for x in value if isinstance(x, str)][:64] if isinstance(value, list) else None
    if default is None:
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    return None


def validate(data) -> dict:
    if not isinstance(data, dict) or data.get("lth_layout") != 1 or not isinstance(data.get("widgets"), dict):
        raise ValueError("This is not an LTH layout.")
    widgets = {}
    for name, wc in data["widgets"].items():
        if name not in BY_NAME or not isinstance(wc, dict):
            continue
        d = DEFAULT_WIDGETS[name]
        clean = {}
        for k, v in wc.items():
            if k in d:
                c = _clean(v, d[k])
                if c is not None:
                    clean[k] = c
            elif k == "height" and isinstance(v, (int, float)) and not isinstance(v, bool):
                clean[k] = v
        widgets[name] = clean
    scr = data.get("screen")
    if not (isinstance(scr, list) and len(scr) == 2 and all(isinstance(x, int) and 200 < x < 20000 for x in scr)):
        scr = [1920, 1080]
    name = data.get("name") if isinstance(data.get("name"), str) else "Shared layout"
    return {"lth_layout": 1, "name": name[:60], "screen": scr, "widgets": widgets,
            "theme": data.get("theme") if isinstance(data.get("theme"), str) else None,
            "font": data.get("font") if isinstance(data.get("font"), str) else None}


def import_layout(ctx, data: dict, name: str | None = None) -> str:
    """Sukuria naują profilį iš išdėstymo. Grąžina profilio raktą."""
    data = validate(data)
    cfg = ctx.config
    scr = ctx.screen_rect()
    sw, sh = data["screen"]
    kx, ky = scr.width() / sw, scr.height() / sh
    ks = max(0.5, min(3.0, ky))
    widgets = copy.deepcopy(DEFAULT_WIDGETS)
    for n in widgets:
        widgets[n]["visible"] = False
    for n, wc in data["widgets"].items():
        target = widgets[n]
        for k, v in wc.items():
            if isinstance(v, dict) and isinstance(target.get(k), dict):
                target[k].update(v)
            else:
                target[k] = v
        target["x"] = int(round(scr.x() + float(wc.get("x", 0)) * kx))
        target["y"] = int(round(scr.y() + float(wc.get("y", 0)) * ky))
        target["scale"] = round(min(3.0, max(0.5, float(target.get("scale", 1.0)) * ks)), 2)
        target["pos_v"] = 2
    base = re.sub(r"[^a-z0-9]+", "_", (name or data["name"]).lower()).strip("_") or "shared"
    key, i = base, 2
    while key in cfg.data["profiles"]:
        key, i = f"{base}_{i}", i + 1
    cfg.data["profiles"][key] = {"name": (name or data["name"])[:60], "widgets": widgets}
    return key


def summary(data: dict) -> str:
    names = [BY_NAME[n].title for n in data["widgets"] if n in BY_NAME]
    w, h = data["screen"]
    return f"{len(names)} widgets made on a {w}×{h} screen: " + ", ".join(names)
