"""Telemetrijos įrašymas ir analizė (Max Cars diagnostika).

Įrašas: .npz failas su visais variklio kintamaisiais 30 Hz dažniu ir sesijos
YAML. Jį galima paleisti atgal per variklį (ReplaySource) bet kuriame
kompiuteryje - taip testuojame be iRacing.
"""
from __future__ import annotations

import io
import math

import numpy as np

from .frame import ALL_VARS, CAR_VARS, MAX_CARS, Frame

RECORD_HZ = 30.0


class Recorder:
    def __init__(self, minutes: float = 10.0, hz: float = RECORD_HZ):
        self.n_max = int(minutes * 60 * hz) + 1
        self.min_dt = 1.0 / hz - 0.004
        self.n = 0
        self.last_t = None
        self.data = {}
        for name, dt in CAR_VARS:
            self.data[name] = np.zeros((self.n_max, MAX_CARS), dtype=dt)
        for name, dt in ALL_VARS:
            if name not in self.data:
                self.data[name] = np.zeros(self.n_max, dtype=dt)
        self.present = set()
        self.session_yaml = ""

    @property
    def full(self) -> bool:
        return self.n >= self.n_max

    def add(self, f: Frame) -> bool:
        t = f.SessionTime
        if t is None or self.full:
            return False
        if self.last_t is not None and 0 <= t - self.last_t < self.min_dt:
            return False
        self.last_t = t
        i = self.n
        for name, arr in self.data.items():
            v = f.values.get(name)
            if v is None:
                continue
            self.present.add(name)
            arr[i] = v
        self.n += 1
        return True

    def save(self, path: str):
        out = {k: v[: self.n] for k, v in self.data.items() if k in self.present}
        out["_session_yaml"] = np.frombuffer(self.session_yaml.encode("utf-8"), dtype=np.uint8)
        np.savez_compressed(path, **out)


class ReplaySource:
    """Teikia įrašytus kadrus po vieną (kaip LiveSource)."""

    def __init__(self, path_or_bytes):
        src = io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, bytes) else path_or_bytes
        z = np.load(src, allow_pickle=False)
        self.arrays = {k: z[k] for k in z.files if not k.startswith("_")}
        self.session_yaml = bytes(z["_session_yaml"]).decode("utf-8") if "_session_yaml" in z.files else ""
        self.n = len(self.arrays["SessionTime"])
        self.i = 0
        self.session = None
        if self.session_yaml:
            from .sessioninfo import build_model, parse_yaml
            self.session = build_model(parse_yaml(self.session_yaml))

    def frame(self, i: int) -> Frame:
        vals = {}
        for k, a in self.arrays.items():
            v = a[i]
            vals[k] = v if a.ndim == 2 else v.item()
        return Frame(vals)

    def __iter__(self):
        for i in range(self.n):
            yield self.frame(i)


# ----------------------------------------------------------------------
# Analizė
# ----------------------------------------------------------------------
def analyze_updates(arrays: dict, session=None) -> dict:
    """Kiekvienai mašinai: kaip dažnai keičiasi pozicija, kai ji važiuoja.

    Perduodama mašina keičiasi kiekviename kadre (~0,03 s); neperduodama -
    retai (pvz. kas 1 s) arba sustingsta.
    """
    t = arrays["SessionTime"]
    pct = arrays["CarIdxLapDistPct"]
    surf = arrays.get("CarIdxTrackSurface")
    pit = arrays.get("CarIdxOnPitRoad")
    out = {}
    for c in range(MAX_CARS):
        p = pct[:, c]
        valid = p >= 0
        if valid.sum() < 30:
            continue
        idx = np.nonzero(valid)[0]
        pv = p[idx]
        tv = t[idx]
        changed = np.nonzero(np.diff(pv) != 0)[0] + 1
        if len(changed) < 5:
            out[c] = {"samples": int(valid.sum()), "changes": int(len(changed)), "moving": False}
            continue
        ct = tv[changed]
        gaps = np.diff(ct)
        # tik važiuojant (ne boksuose)
        if pit is not None:
            on_pit = pit[idx[changed][1:], c]
            gaps = gaps[~on_pit] if len(on_pit) == len(gaps) else gaps
        frozen_frames = 0
        if surf is not None:
            frozen_frames = int(np.sum((surf[idx, c] == -1)))
        out[c] = {
            "samples": int(valid.sum()),
            "changes": int(len(changed)),
            "moving": True,
            "median_interval_s": float(np.median(gaps)) if len(gaps) else math.nan,
            "p95_interval_s": float(np.percentile(gaps, 95)) if len(gaps) else math.nan,
            "max_interval_s": float(np.max(gaps)) if len(gaps) else math.nan,
            "not_in_world_frames": frozen_frames,
        }
        if session and c in session.drivers:
            d = session.drivers[c]
            out[c]["name"] = d.name
            out[c]["number"] = d.number
    return out


def engine_jitter(source: ReplaySource, max_cars_hint=None) -> dict:
    """Paleidžia variklį per įrašą ir matuoja gap'o šuolius tarp 0,1 s kadrų.

    Palygina su iRacing CarIdxF2Time (jei įrašytas).
    """
    from .engine import TimingEngine

    eng = TimingEngine()
    eng.set_session(source.session)
    last = {}
    last_f2 = {}
    jumps = []
    f2_jumps = []
    for i, f in enumerate(source):
        eng.update(f)
        if i % 3:
            continue
        s = eng.snapshot()
        if s.session_type != "race":
            continue
        leaders = {}
        for r in s.cars:
            leaders.setdefault(r.class_id, r.idx)
        f2 = f.CarIdxF2Time
        for r in s.cars:
            L = leaders[r.class_id]
            if r.gap is not None and not r.approx:
                p = last.get(r.idx)
                if p is not None and p[0] == L and s.t - p[1] < 0.2:
                    jumps.append(abs(r.gap - p[2]))
                last[r.idx] = (L, s.t, r.gap)
            if f2 is not None and f2[r.idx] > 0:
                g2 = float(f2[r.idx] - f2[L])
                p = last_f2.get(r.idx)
                if p is not None and p[0] == L and s.t - p[1] < 0.2:
                    f2_jumps.append(abs(g2 - p[2]))
                last_f2[r.idx] = (L, s.t, g2)

    def stats(x):
        if not x:
            return {}
        a = np.array(x)
        return {"p99_s": float(np.percentile(a, 99)), "max_s": float(a.max()), "n": len(a),
                "over_1s": int((a > 1.0).sum())}

    return {"lth_engine": stats(jumps), "iracing_f2time": stats(f2_jumps)}


def report(path: str) -> str:
    src = ReplaySource(path)
    upd = analyze_updates(src.arrays, src.session)
    lines = ["LTH Overlays diagnostics", "=" * 24, ""]
    t = src.arrays["SessionTime"]
    lines.append(f"Frames: {src.n}, duration {t[-1] - t[0]:.0f} s")
    if src.session:
        lines.append(f"Track: {src.session.track_name}, {src.session.track_length_m:.0f} m, "
                     f"cars: {len([d for d in src.session.drivers.values() if not d.is_pace_car and not d.is_spectator])}")
    lines.append("")
    lines.append("Position update interval (while moving):")
    lines.append(f"{'No':>4} {'Driver':<26} {'median':>8} {'95%':>8} {'max':>8}  verdict")
    rendered = slow = 0
    for c, u in sorted(upd.items(), key=lambda kv: kv[1].get("median_interval_s", 9)):
        if not u.get("moving"):
            continue
        med = u["median_interval_s"]
        verdict = "transmitted" if med < 0.1 else "NOT TRANSMITTED / rare updates"
        rendered += med < 0.1
        slow += med >= 0.1
        lines.append(f"{u.get('number', c):>4} {u.get('name', '')[:26]:<26} {med:8.3f} {u['p95_interval_s']:8.3f} "
                     f"{u['max_interval_s']:8.3f}  {verdict}")
    lines.append("")
    lines.append(f"Transmitted: {rendered}, rarely updated: {slow}")
    jit = engine_jitter(src)
    lines.append("")
    lines.append("Gap jumps between consecutive 0.1 s samples:")
    for name, st in jit.items():
        if st:
            lines.append(f"  {name}: 99% < {st['p99_s']:.3f} s, max {st['max_s']:.3f} s, jumps > 1 s: {st['over_1s']}")
        else:
            lines.append(f"  {name}: no data (not recorded or not a race)")
    return "\n".join(lines)
