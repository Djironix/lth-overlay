"""Asmeniniai rekordai (geriausias ratas) kiekvienai trasai + mašinai. Saugoma pb.json."""
from __future__ import annotations

import json
import os
import time

from .config import app_dir


class PersonalBests:
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(app_dir(), "pb.json")
        self.data = {}
        self.new_pb_t = 0.0  # kada pagerintas (Lap timer parodo „NEW PB“)
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                self.data = d
        except (OSError, ValueError):
            pass

    def get(self, track_key: str, car_key: str) -> float | None:
        v = (self.data.get(track_key) or {}).get(car_key)
        return float(v["lap"]) if isinstance(v, dict) and v.get("lap") else None

    def observe(self, snap) -> bool:
        """Kviečiama ~1 Hz. Grąžina True, jei ką tik pagerintas rekordas."""
        p = snap.player
        if (not snap.connected or snap.replay or p is None or not p.valid or not snap.track_key
                or not snap.car_key or not (p.best_lap and p.best_lap > 0)):
            return False
        old = self.get(snap.track_key, snap.car_key)
        if old is not None and p.best_lap >= old - 1e-4:
            return False
        self.data.setdefault(snap.track_key, {})[snap.car_key] = {
            "lap": round(float(p.best_lap), 4), "track": snap.track_name, "date": time.strftime("%Y-%m-%d")}
        self.new_pb_t = time.monotonic() if old is not None else 0.0
        self.save()
        return True

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            pass
