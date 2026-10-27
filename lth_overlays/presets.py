"""Išdėstymo presetai (vienas monitorius, trys monitoriai, paprastas).

Padėtys saugomos dalimis nuo tikslinio ekrano, todėl tinka bet kokiai
rezoliucijai: x = ekranas.x + ax * plotis - alx * valdiklio_plotis.
Presetai niekada neįjungiami savaime - tik kai vartotojas pasirenka.
"""
from __future__ import annotations

from PySide6.QtCore import QRect

# vardas: (ax, ay, alx, aly, plotis, papildomi nustatymai)
_FULL = {
    "engineer": (0.5, 0.025, 0.5, 0.0, 520, {}),
    "delta_bar": (0.5, 0.075, 0.5, 0.0, 420, {"height": 56}),
    "flags": (0.5, 0.135, 0.5, 0.0, 360, {}),
    "standings": (0.012, 0.14, 0.0, 0.0, 470, {}),
    "relative": (0.5, 0.67, 0.5, 0.0, 430, {}),
    "radar": (0.30, 0.63, 0.5, 0.0, 130, {"height": 170}),
    "inputs": (0.5, 0.905, 0.5, 0.0, 320, {"height": 84}),
    "weather": (0.988, 0.03, 1.0, 0.0, 260, {}),
    "session": (0.988, 0.31, 1.0, 0.0, 250, {}),
    "fuel": (0.988, 0.52, 1.0, 0.0, 250, {}),
    "pit_helper": (0.70, 0.63, 0.5, 0.0, 280, {}),
    "car_settings": (0.5, 0.56, 0.5, 0.0, 300, {}),
    "engine_warn": (0.5, 0.21, 0.5, 0.0, 300, {}),
    "incidents": (0.988, 0.80, 1.0, 0.0, 170, {}),
}

PRESETS = {
    "simple": {
        "title": "Simple",
        "subtitle": "Standings, Relative and Weather. A clean start.",
        "target": "primary",
        "widgets": {k: _FULL[k] for k in ("standings", "relative", "weather")},
    },
    "single": {
        "title": "Single monitor",
        "subtitle": "A full race setup on one screen: timing, delta, fuel, flags, radar, inputs.",
        "target": "primary",
        "widgets": dict(_FULL),
    },
    "triple": {
        "title": "Triple monitor",
        "subtitle": "The full setup on your middle screen, or the middle third of a surround display.",
        "target": "middle",
        "widgets": dict(_FULL),
    },
}


def target_rect(ctx, target: str) -> QRect:
    screens = [r for _, r in ctx.screens()]
    prim = screens[0]
    if target != "middle":
        return QRect(prim)
    if len(screens) >= 3:  # trys atskiri monitoriai: vidurinis pagal x
        srt = sorted(screens, key=lambda r: r.center().x())
        return QRect(srt[len(srt) // 2])
    if prim.width() >= prim.height() * 3:  # NVIDIA Surround / Eyefinity: vidurinis trečdalis
        third = prim.width() // 3
        return QRect(prim.x() + third, prim.y(), third, prim.height())
    return QRect(prim)


def apply_preset(ctx, key: str, profiles: list[str] | None = None):
    """Pritaiko presetą nurodytiems profiliams (numatyta - dabartiniam)."""
    from .registry import WIDGETS
    p = PRESETS[key]
    rect = target_rect(ctx, p["target"])
    cfg = ctx.config
    profiles = profiles or [cfg.profile_key]
    current = cfg.profile_key
    for prof in profiles:
        cfg.set_profile(prof)
        for spec in WIDGETS:
            wc = cfg.widget(spec.name)
            if spec.name not in p["widgets"]:
                wc["visible"] = False
                continue
            ax, ay, alx, aly, width, extra = p["widgets"][spec.name]
            k = rect.height() / 1080.0  # didesnis ekranas - didesni valdikliai
            scale = round(max(0.7, min(2.0, k)), 2)
            wc["visible"] = True
            wc["scale"] = scale
            wc["width"] = int(width)
            wc["height"] = extra.get("height")
            w_px = int(width * scale)
            wc["x"] = int(round(rect.x() + ax * rect.width() - alx * w_px))
            wc["y"] = int(round(rect.y() + ay * rect.height()))
            wc["pos_v"] = 2
    cfg.set_profile(current)
    ctx.all_widgets_changed()
    # centruoti valdikliai: tikras plotis gali būti didesnis (daugiau stulpelių) - pataisom x
    if current in profiles:
        for name, (ax, ay, alx, aly, width, extra) in p["widgets"].items():
            w = ctx.widgets.get(name)
            if w is None or not alx:
                continue
            want = int(round(rect.x() + ax * rect.width() - alx * w.width()))
            if want != w.x():
                w.cfg["x"] = want
                w.apply_settings()
        ctx.save_config_soon()
