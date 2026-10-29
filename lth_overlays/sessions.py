"""Automatinis sesijų išsaugojimas: kiekvienas practice / qualify / race ratas su telemetrija.

%APPDATA%\\LTH Overlays\\sessions\\<data>_<trasa>_<tipas>_<id>\\
    session.json        - santrauka (trasa, mašina, vairuotojas, ratų laikai)
    lap_007.lthlap      - kiekvienas ratas (tas pats formatas kaip Export)

Laikoma paskutinės KEEP sesijų (senesnės ištrinamos). Rašoma UI gijoje ~1 kartą per ratą.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time

from lth_timing import telemetry as T

KEEP = 50


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(s or "x")).strip("_")[:40] or "x"


class SessionStore:
    def __init__(self, root: str):
        self.root = root
        self._saved = set()  # id(lap) jau įrašytų
        self._folders = {}  # sesijos raktas -> aplankas
        self._ver = None

    # ---- įrašymas ----
    def _key(self, lap) -> tuple:
        m = lap.meta
        return (m.get("track_key"), m.get("car"), m.get("subsession") or 0, m.get("session_num", -1),
                m.get("session_type") or "session")

    def _folder(self, lap) -> str:
        key = self._key(lap)
        f = self._folders.get(key)
        if f is None:
            m = lap.meta
            stamp = time.strftime("%Y-%m-%d_%H%M")
            name = f"{stamp}_{_safe(m.get('track') or m.get('track_key'))}_{_safe(m.get('session_type') or 'session')}"
            if m.get("subsession"):
                name += f"_{m['subsession']}"
            f = os.path.join(self.root, name)
            n = 2
            while os.path.exists(f) and f not in self._folders.values():
                f = os.path.join(self.root, f"{name}_{n}")
                n += 1
            self._folders[key] = f
            self._prune()
        return f

    def observe(self, recorder, track_map=None) -> int:
        """Įrašo naujus ratus. Grąžina, kiek įrašyta."""
        if recorder is None or recorder.version == self._ver:
            return 0
        self._ver = recorder.version
        n = 0
        touched = set()
        for lap in list(recorder.laps):
            if id(lap) in self._saved or not lap.has_trace or lap.lap_time <= 0:
                continue
            folder = self._folder(lap)
            try:
                os.makedirs(folder, exist_ok=True)
                T.save_lap(os.path.join(folder, f"lap_{lap.number:03d}.lthlap"), lap, track_map)
            except OSError:
                continue
            self._saved.add(id(lap))
            touched.add(folder)
            n += 1
        for folder in touched:
            self._write_summary(folder, [x for x in recorder.laps if self._folders.get(self._key(x)) == folder])
        return n

    def _write_summary(self, folder, laps):
        if not laps:
            return
        m = laps[0].meta
        path = os.path.join(folder, "session.json")
        old = {}
        try:
            with open(path, encoding="utf-8") as fh:
                old = json.load(fh)
        except (OSError, ValueError):
            pass
        times = {str(x.number): [round(x.lap_time, 4), bool(x.valid), bool(x.pit)] for x in laps}
        times = dict(old.get("laps", {}), **times)
        valid = [v[0] for v in times.values() if v[1]]
        data = {"track": m.get("track"), "track_key": m.get("track_key"), "car": m.get("car"),
                "car_name": m.get("car_name"), "driver": m.get("driver"), "type": m.get("session_type"),
                "subsession": m.get("subsession"), "started": old.get("started") or m.get("date"),
                "updated": time.strftime("%Y-%m-%d %H:%M"), "laps": times, "best": min(valid) if valid else None}
        try:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        except OSError:
            pass

    def _prune(self):
        try:
            dirs = [os.path.join(self.root, d) for d in os.listdir(self.root)]
        except OSError:
            return
        dirs = [d for d in dirs if os.path.isdir(d)]
        dirs.sort(key=lambda d: os.path.getmtime(d), reverse=True)
        keep = set(self._folders.values())
        for d in dirs[KEEP:]:
            if d not in keep:
                shutil.rmtree(d, ignore_errors=True)

    # ---- skaitymas ----
    def list(self) -> list:
        """[(aplankas, santrauka)] naujausios pirma."""
        out = []
        try:
            names = os.listdir(self.root)
        except OSError:
            return out
        for d in names:
            path = os.path.join(self.root, d, "session.json")
            try:
                with open(path, encoding="utf-8") as fh:
                    meta = json.load(fh)
                out.append((os.path.join(self.root, d), meta, os.path.getmtime(path)))
            except (OSError, ValueError):
                continue
        out.sort(key=lambda x: x[2], reverse=True)
        return [(f, m) for f, m, _ in out]

    @staticmethod
    def load(folder: str) -> list:
        laps = []
        try:
            names = sorted(n for n in os.listdir(folder) if n.endswith(".lthlap"))
        except OSError:
            return laps
        for n in names:
            try:
                lap = T.load_lap(os.path.join(folder, n))
                lap.meta["imported"] = False
                lap.meta["from_session"] = os.path.basename(folder)
                laps.append(lap)
            except (OSError, ValueError, KeyError):
                continue
        return laps
