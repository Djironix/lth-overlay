"""Savo ratų telemetrija: įrašymas, perskaičiavimas pagal atstumą, eksportas / importas (.lthlap).

Įrašoma tik sava mašina (ne stebima), tik kai vairuoji. Kiekvienas užbaigtas ratas
perskaičiuojamas į vienodą atstumo tinklelį (kas ~2 m), todėl du ratai (ir draugo ratas)
lyginami tiesiogiai: greitis, pedalai, vairas, pavara ir laiko skirtumas bet kurioje vietoje.

.lthlap = suspaustas NumPy archyvas (be pickle) su JSON metaduomenimis - saugu atidaryti.
"""
from __future__ import annotations

import io
import json
import math
import time
import zipfile
from dataclasses import dataclass, field

import numpy as np

CHANNELS = ("time", "speed", "throttle", "brake", "clutch", "steer", "gear", "rpm")
FORMAT = 1
MAX_LAPS = 80


@dataclass
class Lap:
    number: int
    lap_time: float
    valid: bool
    pit: bool = False
    meta: dict = field(default_factory=dict)  # track, track_key, car, driver, date, position, fuel_used...
    grid: np.ndarray | None = None  # rato dalis 0..1 (N)
    data: dict = field(default_factory=dict)  # kanalas -> np.ndarray (N)

    @property
    def has_trace(self) -> bool:
        return self.grid is not None and len(self.grid) > 10

    def label(self) -> str:
        from_ = self.meta.get("driver") or ""
        return f"Lap {self.number}  {fmt(self.lap_time)}" + (f"  ({from_})" if self.meta.get("imported") else "")


def fmt(t) -> str:
    if t is None or not math.isfinite(t) or t <= 0:
        return "–"
    m, s = divmod(t, 60)
    return f"{int(m)}:{s:06.3f}" if m else f"{s:.3f}"


class LapRecorder:
    """Kviečiama kiekvienam apdorotam kadrui (engine gijoje)."""

    TELEPORT = 0.03

    def __init__(self):
        self.enabled = True
        self.laps: list[Lap] = []
        self.version = 0  # didėja, kai pridedamas ratas (UI žino, ar perpiešti)
        self.track_m = 4000.0
        self.meta = {}
        self._reset_lap()
        self._prev_pct = None
        self._pending = None  # (Lap, iki kada laukti oficialaus laiko, ankstesnis LapLastLapTime)
        self._last_official = None

    def _reset_lap(self, t0=None, pct0=None):
        self._buf = []
        self._t0 = t0
        self._valid = t0 is not None
        self._pit = False
        self._fuel0 = None

    def set_session(self, meta: dict, track_m: float):
        if meta.get("track_key") != self.meta.get("track_key") or meta.get("car") != self.meta.get("car"):
            self.laps = []
            self.version += 1
        self.meta = dict(meta)
        self.track_m = max(500.0, float(track_m or 4000.0))
        self._reset_lap()
        self._prev_pct = None

    def reset(self):
        self._reset_lap()
        self._prev_pct = None
        self._pending = None

    def sample(self, f, driving: bool):
        if not self.enabled:
            return
        v = f.values
        t = float(v.get("SessionTime", 0.0) or 0.0)
        self._check_pending(v, t)
        pct = v.get("LapDistPct")
        if not driving or pct is None or not math.isfinite(float(pct)) or pct < 0:
            self._prev_pct = None
            self._reset_lap()
            return
        pct = float(pct)
        prev = self._prev_pct
        self._prev_pct = pct
        on_pit = bool(v.get("OnPitRoad"))
        if prev is not None:
            d = pct - prev
            if prev > 0.9 and pct < 0.1:  # linija
                d += 1.0
                if self._t0 is not None and self._buf:
                    # interpoliuotas kirtimo laikas
                    tp = self._buf[-1][0]
                    frac = (1.0 - prev) / d if d > 0 else 0.0
                    tc = tp + frac * (t - tp)
                    self._buf.append((tc, 1.0) + self._buf[-1][2:])
                    self._finish(tc, v)
                    self._reset_lap(tc, 0.0)
                    self._buf.append((tc, 0.0) + self._chan(v))
                else:
                    tp = t
                    self._reset_lap(t, pct)
                if self._fuel0 is None:
                    self._fuel0 = _num(v.get("FuelLevel"))
            elif d < -0.001 or d > self.TELEPORT:  # atgal / teleportas: ratas negalioja
                self._valid = False
        if self._t0 is None:
            return
        if on_pit:
            self._pit = True
        self._buf.append((t, pct) + self._chan(v))

    @staticmethod
    def _chan(v) -> tuple:
        return (_num(v.get("Speed")), _num(v.get("Throttle")), _num(v.get("Brake")),
                1.0 - _num(v.get("Clutch"), 1.0), _num(v.get("SteeringWheelAngle")), _num(v.get("Gear")),
                _num(v.get("RPM")))

    def _finish(self, tc, v):
        buf = self._buf
        if len(buf) < 20:
            return
        arr = np.array(buf, dtype=np.float64)
        ts, ps = arr[:, 0], arr[:, 1]
        lap_time = float(tc - self._t0)
        covered = ps.min() < 0.02 and ps.max() > 0.98
        n = int(min(4000, max(500, self.track_m / 2.0)))
        grid = np.linspace(0.0, 1.0, n, dtype=np.float64)
        ps_m = np.maximum.accumulate(ps)
        keep = np.concatenate(([True], np.diff(ps_m) > 1e-7))
        ps_m, sel = ps_m[keep], arr[keep]
        data = {"time": np.interp(grid, ps_m, sel[:, 0] - self._t0).astype(np.float32)}
        for i, ch in enumerate(CHANNELS[1:]):
            data[ch] = np.interp(grid, ps_m, sel[:, 2 + i]).astype(np.float32)
        data["gear"] = np.round(data["gear"])
        pl = int(_num(v.get("PlayerCarIdx"), -1))
        cpos = v.get("CarIdxClassPosition")
        pos = int(cpos[pl]) if cpos is not None and 0 <= pl < len(cpos) else 0
        fuel1 = _num(v.get("FuelLevel"))
        meta = dict(self.meta, date=time.strftime("%Y-%m-%d %H:%M"), position=pos,
                    fuel_used=(self._fuel0 - fuel1) if self._fuel0 is not None and math.isfinite(fuel1)
                    and self._fuel0 > fuel1 else None)
        lap_no = int(_num(v.get("LapCompleted"), 0))
        lap = Lap(number=lap_no, lap_time=lap_time, valid=self._valid and covered and not self._pit,
                  pit=self._pit, meta=meta, grid=grid.astype(np.float32), data=data)
        self.laps.append(lap)
        del self.laps[:-MAX_LAPS]
        self.version += 1
        self._pending = (lap, tc + 4.0, self._last_official)

    def _check_pending(self, v, t):
        last = v.get("LapLastLapTime")
        last = float(last) if last is not None else None
        pend = self._pending
        if pend is not None:
            lap, until, before = pend
            if last is not None and last > 0 and last != before and abs(last - lap.lap_time) < 0.25:
                lap.lap_time = last  # oficialus laikas
                self.version += 1
                self._pending = None
            elif t > until:
                self._pending = None
        self._last_official = last

    # ---- UI ----
    def best(self, valid_only=True) -> Lap | None:
        laps = [x for x in self.laps if x.has_trace and (x.valid or not valid_only)]
        return min(laps, key=lambda x: x.lap_time) if laps else None


def _num(x, default=math.nan) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- failai
def save_lap(path: str, lap: Lap):
    meta = dict(lap.meta, number=lap.number, lap_time=lap.lap_time, valid=lap.valid, pit=lap.pit, format=FORMAT,
                app="LTH Overlays")
    buf = io.BytesIO()
    arrays = {"grid": lap.grid.astype(np.float32)}
    arrays.update({k: np.asarray(v, dtype=np.float32) for k, v in lap.data.items() if k in CHANNELS})
    np.savez_compressed(buf, **arrays)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        z.writestr("meta.json", json.dumps(meta, ensure_ascii=False, indent=1))
        z.writestr("data.npz", buf.getvalue())


def load_lap(path: str) -> Lap:
    with zipfile.ZipFile(path) as z:
        meta = json.loads(z.read("meta.json").decode("utf-8"))
        raw = z.read("data.npz")
    if len(raw) > 50_000_000:
        raise ValueError("file too large")
    with np.load(io.BytesIO(raw), allow_pickle=False) as npz:
        grid = np.asarray(npz["grid"], dtype=np.float32)
        data = {k: np.asarray(npz[k], dtype=np.float32) for k in CHANNELS if k in npz.files}
    if grid.ndim != 1 or len(grid) < 10 or any(len(v) != len(grid) for v in data.values()) or "time" not in data:
        raise ValueError("not an LTH lap file")
    meta["imported"] = True
    return Lap(number=int(meta.get("number", 0) or 0), lap_time=float(meta.get("lap_time", 0) or 0),
               valid=bool(meta.get("valid", True)), pit=bool(meta.get("pit", False)), meta=meta, grid=grid, data=data)


def save_csv(path: str, lap: Lap, track_m: float | None = None):
    tm = float(track_m or lap.meta.get("track_m") or 0)
    cols = ["distance_m" if tm else "lap_pct"] + list(CHANNELS)
    with open(path, "w", encoding="utf-8") as f:
        f.write(",".join(cols) + "\n")
        for i in range(len(lap.grid)):
            x = lap.grid[i] * tm if tm else lap.grid[i]
            f.write(",".join([f"{x:.2f}"] + [f"{float(lap.data[c][i]):.4f}" if c in lap.data else ""
                                             for c in CHANNELS]) + "\n")


def delta_trace(a: Lap, b: Lap) -> np.ndarray:
    """b laikas - a laikas kiekviename a tinklelio taške (+ = b lėtesnis)."""
    tb = np.interp(a.grid, b.grid, b.data["time"])
    return (tb - a.data["time"]).astype(np.float32)


def channel_on(lap: Lap, grid: np.ndarray, ch: str) -> np.ndarray | None:
    if ch not in lap.data:
        return None
    if lap.grid is grid or (len(lap.grid) == len(grid) and np.allclose(lap.grid, grid)):
        return lap.data[ch]
    return np.interp(grid, lap.grid, lap.data[ch]).astype(np.float32)
