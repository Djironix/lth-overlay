"""Gamintojų logotipai Standings / Relative stulpelyje „Car“.

Kartu su programa: data/logos/*.png (LTH paruoštas rinkinys). Žmogus gali pakeisti ar pridėti savų -
%APPDATA%\\LTH Overlays\\logos\\ (pvz. porsche.png); jo failai turi pirmenybę. Kur failo nėra -
rodomas įprastas spalvotas ženkliukas (POR, BMW...).
"""
from __future__ import annotations

import json
import os
import re
import time

from .config import app_dir

EXTS = (".png", ".webp", ".jpg", ".jpeg")


def folder() -> str:
    return os.path.join(app_dir(), "logos")


def bundled_folder() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "logos")


def user_files() -> set:
    try:
        return {slug(os.path.splitext(f)[0]) for f in os.listdir(folder()) if os.path.splitext(f)[1].lower() in EXTS}
    except OSError:
        return set()


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def brands() -> list:
    """[(gamintojas, trumpinys, failo vardas be plėtinio)] iš brands.json, be pasikartojimų."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lth_timing", "data",
                        "brands.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)["match"]
    except (OSError, ValueError, KeyError):
        return []
    out, seen = [], set()
    for v in data.values():
        n = v.get("name", "")
        if n and n not in seen:
            seen.add(n)
            out.append((n, v.get("short", ""), slug(n)))
    return sorted(out)


class _Store:
    def __init__(self):
        self._files = {}  # raktas (slug arba trumpinys) -> kelias
        self._scan_t = 0.0
        self._pix = {}
        self._by_short = {}

    def _scan(self):
        now = time.monotonic()
        if now - self._scan_t < 5.0:
            return
        self._scan_t = now
        files = {}
        for d in (bundled_folder(), folder()):  # vartotojo failai perrašo programos
            try:
                for f in os.listdir(d):
                    base, ext = os.path.splitext(f)
                    if ext.lower() in EXTS:
                        files[slug(base)] = os.path.join(d, f)
            except OSError:
                pass
        if files != self._files:
            self._files = files
            self._pix.clear()
        if not self._by_short:
            for name, short, sl in brands():
                self._by_short.setdefault(short.upper(), []).append(sl)

    def path_for(self, short: str) -> str | None:
        self._scan()
        if not self._files:
            return None
        for key in self._by_short.get((short or "").upper(), []) + [slug(short)]:
            if key in self._files:
                return self._files[key]
        return None

    def pixmap(self, short: str, w: float, h: float, dpr: float = 1.0):
        path = self.path_for(short)
        if path is None:
            return None
        key = (path, int(w * dpr), int(h * dpr))
        pm = self._pix.get(key)
        if pm is None:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QPixmap
            src = QPixmap(path)
            if src.isNull():
                self._pix[key] = False
                return None
            pm = src.scaled(int(w * dpr), int(h * dpr), Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
            pm.setDevicePixelRatio(dpr)
            if len(self._pix) > 200:
                self._pix.clear()
            self._pix[key] = pm
        return pm or None

    def found(self) -> set:
        self._scan_t = 0.0
        self._scan()
        return set(self._files)


STORE = _Store()
