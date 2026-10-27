"""Trasos žemėlapis: vieną švarų ratą įrašome iš savo mašinos greičio ir krypties.

iRacing telemetrijoje trasos formos nėra, todėl ją „nubrėžiame“ patys:
x += v·sin(kryptis)·dt, y -= v·cos(kryptis)·dt. Po pilno rato uždarymo
paklaida tolygiai paskirstoma, žemėlapis išsaugomas
%APPDATA%\\LTH Overlays\\maps\\<trasa>.json ir vėliau tik užkraunamas.
"""
from __future__ import annotations

import json
import math
import os

import numpy as np

BINS = 400


class TrackMap:
    def __init__(self, folder: str | None):
        self.folder = folder
        self.key = None
        self.points = None  # np.ndarray (BINS, 2), normalizuota 0..1
        self.recording = False
        self.progress = 0.0  # kiek rato surinkta (0..1)
        self._reset_lap()

    def _reset_lap(self):
        self._xy = np.full((BINS, 2), np.nan)
        self._x = self._y = 0.0
        self._last_t = None
        self._last_pct = None
        self._ok = False
        self.progress = 0.0

    def _path(self, key):
        return os.path.join(self.folder, f"{key}.json") if self.folder else None

    def set_track(self, key: str):
        if key == self.key:
            return
        self.key = key
        self.points = None
        self._reset_lap()
        p = self._path(key)
        if p and os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    data = json.load(fh)
                pts = np.asarray(data["pts"], dtype=float)
                if pts.shape == (BINS, 2):
                    self.points = pts
            except (OSError, ValueError, KeyError):
                self.points = None

    def forget(self):
        """Ištrina žemėlapį (įrašys iš naujo)."""
        p = self._path(self.key) if self.key else None
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass
        self.points = None
        self._reset_lap()

    def update(self, f, t: float):
        """Kviečiama variklio dažniu. Įrašo tik kol žemėlapio dar nėra."""
        if self.points is not None or self.key is None:
            self.recording = False
            return
        pct, v, yaw = f.LapDistPct, f.Speed, f.YawNorth
        usable = (f.IsOnTrack and not f.OnPitRoad and pct is not None and v is not None and yaw is not None
                  and 0.0 <= pct <= 1.0 and v > 5.0)
        self.recording = bool(usable)
        if not usable:
            self._reset_lap()
            return
        if self._last_t is None:
            self._last_t, self._last_pct = t, pct
            return
        dt = t - self._last_t
        if dt <= 0 or dt > 0.4:  # trūkis - pradedam iš naujo
            self._reset_lap()
            self._last_t, self._last_pct = t, pct
            return
        wrap = self._last_pct > 0.9 and pct < 0.1
        self._x += v * math.sin(yaw) * dt
        self._y -= v * math.cos(yaw) * dt
        self._last_t = t
        if wrap:
            if self._ok:
                self._finish()
                return
            # rato pradžia: skaičiuojam nuo linijos
            self._xy[:] = np.nan
            self._x = self._y = 0.0
            self._ok = True
        self._last_pct = pct
        if self._ok:
            b = min(BINS - 1, int(pct * BINS))
            if np.isnan(self._xy[b, 0]):
                self._xy[b] = (self._x, self._y)
            self.progress = float(np.count_nonzero(~np.isnan(self._xy[:, 0])) / BINS)

    def _finish(self):
        xy = self._xy
        have = ~np.isnan(xy[:, 0])
        if have.mean() < 0.9:
            self._reset_lap()
            return
        idx = np.arange(BINS)
        for k in (0, 1):  # užpildom spragas
            xy[:, k] = np.interp(idx, idx[have], xy[have, k])
        # uždarymo paklaida: pabaiga turi sutapti su pradžia
        end = np.array([self._x, self._y])
        err = end - xy[0]
        xy = xy - np.outer(idx / BINS, err)
        lo, hi = xy.min(axis=0), xy.max(axis=0)
        span = max(hi[0] - lo[0], hi[1] - lo[1])
        if span < 50:  # per maža trasa - kažkas negerai
            self._reset_lap()
            return
        pts = (xy - lo) / span
        pts += (1 - (hi - lo) / span) / 2  # centruojam
        self.points = pts
        self.recording = False
        p = self._path(self.key)
        if p:
            try:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as fh:
                    json.dump({"key": self.key, "bins": BINS, "pts": np.round(pts, 5).tolist()}, fh)
            except OSError:
                pass

    def position(self, pct: float):
        """Taškas žemėlapyje pagal rato dalį (0..1)."""
        if self.points is None or not math.isfinite(pct):
            return None
        x = (pct % 1.0) * BINS
        i = int(x) % BINS
        j = (i + 1) % BINS
        k = x - int(x)
        return self.points[i] * (1 - k) + self.points[j] * k
