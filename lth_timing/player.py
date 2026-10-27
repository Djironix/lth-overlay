"""Savo mašinos būsena papildomiems valdikliams.

Kuras, ratų istorija, delta, incidentai, nustatymų (dc*) pokyčiai, stintas,
input'ai, G jėgos, padangos, boksai, įspėjimai, ryšys, vėliavos.

Kaina: update() kviečiamas variklio dažniu (20 Hz) ir daro tik paprastus
palyginimus; input'ų buferis pildomas tik kai input valdiklis įjungtas.
"""
from __future__ import annotations

import math
import re
from collections import deque
from dataclasses import dataclass, field

import numpy as np

INPUT_SECONDS = 6.0
G = 9.80665

# irsdk_EngineWarnings
WARN_BITS = {0x01: "Water temp", 0x02: "Fuel pressure", 0x04: "Oil pressure", 0x08: "Engine stalled",
             0x40: "Oil temp"}
WARN_LIMITER = 0x10
WARN_REV_LIMITER = 0x20

# irsdk_Flags (svarbumo tvarka)
FLAG_BITS = (
    (0x00020000, "disqualify", "DISQUALIFIED"), (0x00010000, "black", "BLACK FLAG"),
    (0x00100000, "repair", "MEATBALL - REPAIR"), (0x00000010, "red", "RED FLAG"),
    (0x00008000, "caution_waving", "CAUTION"), (0x00004000, "caution", "CAUTION"),
    (0x00000100, "yellow_waving", "YELLOW - WAVING"), (0x00000008, "yellow", "YELLOW"),
    (0x00000040, "debris", "DEBRIS"), (0x00000020, "blue", "BLUE FLAG"),
    (0x00000002, "white", "WHITE FLAG - LAST LAP"), (0x00000001, "checkered", "CHEQUERED FLAG"),
    (0x00000200, "one_to_green", "ONE LAP TO GREEN"), (0x00000004, "green", "GREEN"),
)

# Vairuotojo (ne sesijos) vėliavos: skaitomos iš CarIdxSessionFlags[aš]
DRIVER_FLAG_MASK = 0x00000020 | 0x00010000 | 0x00020000 | 0x00080000 | 0x00100000  # blue, black, DQ, furled, repair
FLAG_BLUE = 0x00000020
BLUE_GRACE_S = 10.0  # po žalios vėliavos mėlyna dar nerodoma (rolling startas)

# irsdk_PitSvFlags
PIT_SV = ((0x01, "LF"), (0x02, "RF"), (0x04, "LR"), (0x08, "RR"), (0x10, "Fuel"), (0x20, "Tear-off"),
          (0x40, "Fast repair"))

_DC_SKIP = re.compile(r"Toggle|Trigger|Flash|Starter|Dash|Wiper|Tearoff|LowFuel|PushToPass|Ignition|Headlight|"
                      r"Pit|Display|Map|Page|Reset|Enter|Exit", re.I)
_DC_NAMES = {"dcBrakeBias": "Brake bias", "dcBrakeBiasFine": "Brake bias fine", "dcTractionControl": "TC",
             "dcTractionControl2": "TC 2", "dcTractionControl3": "TC 3", "dcABS": "ABS",
             "dcAntiRollFront": "ARB front", "dcAntiRollRear": "ARB rear", "dcFuelMixture": "Fuel mix",
             "dcThrottleShape": "Throttle map", "dcEnginePower": "Engine power", "dcEngineBraking": "Engine braking",
             "dcPeakBrakeBias": "Peak brake bias", "dcWeightJackerRight": "Weight jacker",
             "dcDiffEntry": "Diff entry", "dcDiffMiddle": "Diff mid", "dcDiffExit": "Diff exit",
             "dcBrakeMigration": "Brake migration", "dcMGUKDeployMode": "MGU-K deploy", "dcMGUKRegenGain": "MGU-K regen"}


def dc_label(name: str) -> str:
    if name in _DC_NAMES:
        return _DC_NAMES[name]
    core = name[2:] if name.startswith("dc") else name
    return re.sub(r"(?<!^)(?=[A-Z])", " ", core).strip()


def fmt_dc(name: str, v: float) -> str:
    if "BrakeBias" in name or "Bias" in name:
        return f"{v:.1f}"
    return f"{v:.0f}" if abs(v - round(v)) < 1e-3 else f"{v:.2f}"


@dataclass
class LapRec:
    lap: int
    time: float
    pit: bool
    fuel: float | None  # sunaudota per ratą, l


@dataclass
class PlayerState:
    valid: bool = False
    t: float = 0.0
    # kuras
    fuel_l: float = math.nan
    fuel_pct: float = math.nan
    fuel_max_l: float = 0.0
    fuel_per_lap: float | None = None
    fuel_last_lap: float | None = None
    fuel_laps_counted: int = 0
    fuel_laps_left: float | None = None
    race_laps_left: float | None = None
    fuel_to_finish: float | None = None
    # ratai
    lap_no: int = 0
    laps: tuple = ()
    last_lap: float = 0.0
    best_lap: float = 0.0
    current_lap_time: float = 0.0
    stint_avg: float | None = None
    consistency: float | None = None
    # delta
    deltas: dict = field(default_factory=dict)
    # incidentai
    inc_my: int = 0
    inc_team: int = 0
    inc_last_add: int = 0
    inc_age: float = 1e9
    # nustatymų pokyčiai
    dc_events: tuple = ()
    # stintas
    stint_time: float = 0.0
    stint_laps: int = 0
    drivers_so_far: int = 0
    dc_lap_status: int = 0
    # input'ai
    inputs: dict = field(default_factory=dict)
    throttle: float = 0.0
    brake: float = 0.0
    clutch: float = 0.0
    steer: float = 0.0
    abs_active: bool = False
    gear: int = 0
    speed: float = 0.0
    rpm: float = 0.0
    lat_g: float = 0.0
    long_g: float = 0.0
    g_trail: tuple = ()
    # padangos
    tyres: dict = field(default_factory=dict)
    # boksai
    pit_flags: int = 0
    pit_fuel: float = 0.0
    repair_left: float = 0.0
    opt_repair_left: float = 0.0
    fast_repairs: int = 0
    limiter: bool = False
    on_pit_road: bool = False
    in_stall: bool = False
    tow_time: float = 0.0
    # įspėjimai
    warn_bits: int = 0
    warnings: tuple = ()
    water_temp: float = math.nan
    oil_temp: float = math.nan
    oil_press: float = math.nan
    voltage: float = math.nan
    # ryšys
    chan_quality: float | None = None
    chan_partner: float | None = None
    latency: float | None = None
    avg_latency: float | None = None
    # vėliavos
    flag_bits: int = 0
    flags: tuple = ()  # (key, text) svarbumo tvarka
    # kita
    radio_idx: int = -1
    car_left_right: int = 0
    pace_mode: int = -1
    pace_row: int = -1
    pace_line: int = -1
    tyre_compound: int = -1  # iRacing CarIdxTireCompound: 0 = sausos, 1 = lietaus (-1 = nežinoma)


class PlayerTracker:
    def __init__(self):
        self.inputs_enabled = False
        self.reset()

    def reset(self):
        self._lap_completed = None
        self._lap_fuel_start = None
        self._lap_had_pit = False
        self._lap_refuel = False
        self._pending_lap = None
        self._last_lap_value = None
        self._laps = deque(maxlen=60)
        self._fuel_hist = deque(maxlen=5)
        self._stint_start = None
        self._racing_since = None
        self._stint_lap0 = 0
        self._was_on_pit = None
        self._inc_prev = None
        self._inc_last = (0, -1e9)
        self._dc_prev = {}
        self._dc_events = deque(maxlen=6)
        n = int(INPUT_SECONDS * 60)
        self._inp = np.zeros((5, n), dtype=np.float32)
        self._inp_i = 0
        self._inp_n = 0
        self.inp_seq = 0  # didėja su kiekvienu nauju mėginiu (Inputs valdiklis žino, ar perpiešti)
        self._g = deque(maxlen=20)
        self._last_t = None
        self._prev_fuel = None
        self.fuel_max_l = 0.0
        self._state = PlayerState()

    # ---- kiekvienam kadrui (60 Hz, tik jei įjungtas input valdiklis) ----
    def sample_inputs(self, f):
        if not self.inputs_enabled:
            return
        i = self._inp_i
        buf = self._inp
        buf[0, i] = f.get("Throttle", 0.0)
        buf[1, i] = f.get("Brake", 0.0)
        buf[2, i] = 1.0 - float(f.get("Clutch", 1.0))  # iRacing: 1 = sankaba atleista
        buf[3, i] = f.get("SteeringWheelAngle", 0.0)
        buf[4, i] = 1.0 if f.BrakeABSactive else 0.0
        self._inp_i = (i + 1) % buf.shape[1]
        self._inp_n = min(self._inp_n + 1, buf.shape[1])
        self.inp_seq += 1

    def input_trace(self, n: int):
        """Paskutiniai n mėginių (5, n) - kopija; saugu skaityti iš UI gijos."""
        buf, i, have = self._inp, self._inp_i, self._inp_n
        n = min(n, have)
        if n <= 1:
            return None
        idx = (np.arange(i - n, i)) % buf.shape[1]
        return buf[:, idx]

    # ---- variklio dažniu (20 Hz) ----
    def update(self, f, t: float):
        if self._last_t is not None and t < self._last_t - 0.5:
            self.reset()
        self._last_t = t
        on_pit = bool(f.OnPitRoad)
        on_track = bool(f.IsOnTrack)
        fuel = f.FuelLevel

        # stintas: nuo išvažiavimo iš boksų
        if self._was_on_pit is None or (self._was_on_pit and not on_pit and on_track):
            self._stint_start = t
            self._stint_lap0 = int(f.get("LapCompleted", 0) or 0)
            self._fuel_hist.clear() if self._was_on_pit is None else None
        self._was_on_pit = on_pit

        # ratai ir kuras
        lc = f.LapCompleted
        if lc is not None:
            lc = int(lc)
            if on_pit:
                self._lap_had_pit = True
            if fuel is not None and self._prev_fuel is not None and fuel > self._prev_fuel + 0.3:
                self._lap_refuel = True
            if self._lap_completed is None:
                self._lap_completed = lc
                self._lap_fuel_start = fuel
            elif lc > self._lap_completed:
                used = None
                if fuel is not None and self._lap_fuel_start is not None and not self._lap_refuel:
                    used = float(self._lap_fuel_start) - float(fuel)
                    if used <= 0.01:
                        used = None
                clean = not self._lap_had_pit and lc == self._lap_completed + 1
                if used is not None and clean and on_track:
                    self._fuel_hist.append(used)
                self._pending_lap = (lc, self._lap_had_pit, used, t)
                self._lap_completed = lc
                self._lap_fuel_start = fuel
                self._lap_had_pit = on_pit
                self._lap_refuel = False
            elif lc < self._lap_completed:  # nauja sesija / reset
                self._lap_completed = lc
                self._lap_fuel_start = fuel
        self._prev_fuel = fuel
        last = f.LapLastLapTime
        if self._pending_lap is not None and last is not None:
            lap, pit, used, t0 = self._pending_lap
            if last > 0 and (last != self._last_lap_value or t - t0 > 2.0):
                self._laps.append(LapRec(lap, float(last), pit, used))
                self._last_lap_value = last
                self._pending_lap = None
            elif t - t0 > 3.0:
                self._pending_lap = None

        # incidentai
        inc = f.PlayerCarMyIncidentCount
        if inc is not None:
            if self._inc_prev is not None and inc > self._inc_prev:
                self._inc_last = (int(inc - self._inc_prev), t)
            self._inc_prev = inc

        # dc* nustatymai
        for name in f.values.get("_dc", ()) or ():
            v = f.values.get(name)
            if v is None or isinstance(v, bool) or _DC_SKIP.search(name):
                continue
            v = float(v)
            old = self._dc_prev.get(name)
            if old is not None and abs(v - old) > 1e-4 and on_track:
                self._dc_events.append((dc_label(name), fmt_dc(name, old), fmt_dc(name, v), t))
            self._dc_prev[name] = v

        lat, lon = f.LatAccel, f.LongAccel
        if lat is not None and lon is not None:
            self._g.append((float(lat) / G, float(lon) / G))

    def _flag_bits(self, f, t: float) -> int:
        """Sesijos vėliavos iš SessionFlags, vairuotojo - iš CarIdxSessionFlags[aš].
        Mėlyna nerodoma prieš lenktynes, per parade / pace laps ir pirmas BLUE_GRACE_S po žalios."""
        session = int(f.get("SessionFlags", 0) or 0)
        bits = session & ~DRIVER_FLAG_MASK
        pl = f.PlayerCarIdx
        per_car = f.CarIdxSessionFlags
        if per_car is not None and pl is not None and 0 <= pl < len(per_car):
            bits |= int(per_car[pl]) & DRIVER_FLAG_MASK
        else:  # senas iRacing / įrašas be kintamojo
            bits |= session & DRIVER_FLAG_MASK
        state = int(f.get("SessionState", 0) or 0)
        pace = f.PaceMode
        pacing = pace is not None and 0 <= int(pace) <= 3
        if state >= 4 and not pacing:  # STATE_RACING
            if self._racing_since is None:
                self._racing_since = t
        else:
            self._racing_since = None
        if self._racing_since is None or t - self._racing_since < BLUE_GRACE_S:
            bits &= ~FLAG_BLUE
        return bits

    # ---- būsena valdikliams ----
    def state(self, f, t: float, laps_remain: int, time_remain: float, race: bool) -> PlayerState:
        s = PlayerState(valid=f is not None, t=t)
        if f is None:
            return s
        s.fuel_l = _f(f.FuelLevel)
        s.fuel_pct = _f(f.FuelLevelPct)
        s.fuel_max_l = self.fuel_max_l
        hist = list(self._fuel_hist)
        s.fuel_laps_counted = len(hist)
        if hist:
            s.fuel_per_lap = sum(hist) / len(hist)
            s.fuel_last_lap = hist[-1]
            if s.fuel_per_lap > 0 and math.isfinite(s.fuel_l):
                s.fuel_laps_left = s.fuel_l / s.fuel_per_lap
        laps = list(self._laps)
        s.laps = tuple(laps[-15:])
        s.last_lap = _f(f.LapLastLapTime, 0.0)
        s.best_lap = _f(f.LapBestLapTime, 0.0)
        s.current_lap_time = _f(f.LapCurrentLapTime, 0.0)
        s.lap_no = int(f.get("Lap", 0) or 0)
        stint_laps = [x.time for x in laps if not x.pit and x.lap > self._stint_lap0 and x.time > 0]
        if stint_laps:
            s.stint_avg = sum(stint_laps) / len(stint_laps)
        clean = [x.time for x in laps[-10:] if not x.pit and x.time > 0]
        if len(clean) >= 3:
            best = min(clean)
            clean = [x for x in clean if x < best * 1.07]  # be avarijų / lėtų ratų
            if len(clean) >= 3:
                s.consistency = float(np.std(clean))
        # likęs atstumas iki finišo (ratais)
        pct = _f(f.LapDistPct, 0.0)
        avg_lap = s.stint_avg or (s.last_lap if s.last_lap > 0 else None)
        if race:
            if 0 <= laps_remain < 30000:
                s.race_laps_left = max(0.0, laps_remain - (pct if math.isfinite(pct) else 0.0))
            elif avg_lap and time_remain > 0 and time_remain < 1e6:
                s.race_laps_left = math.ceil(time_remain / avg_lap) + 1 - (pct if math.isfinite(pct) else 0.0)
            if s.race_laps_left is not None and s.fuel_per_lap:
                s.fuel_to_finish = s.race_laps_left * s.fuel_per_lap
        # delta
        for key, name in (("best", "LapDeltaToBestLap"), ("optimal", "LapDeltaToOptimalLap"),
                          ("session_best", "LapDeltaToSessionBestLap"), ("session_last", "LapDeltaToSessionLastlLap")):
            v = f.values.get(name)
            ok = f.values.get(name + "_OK")
            s.deltas[key] = float(v) if v is not None and ok else None
        # incidentai
        s.inc_my = int(f.get("PlayerCarMyIncidentCount", 0) or 0)
        s.inc_team = int(f.get("PlayerCarTeamIncidentCount", 0) or 0)
        s.inc_last_add, inc_t = self._inc_last
        s.inc_age = t - inc_t
        s.dc_events = tuple((a, b, c, t - tt) for a, b, c, tt in self._dc_events if t - tt < 6.0)
        # stintas
        if self._stint_start is not None:
            s.stint_time = max(0.0, t - self._stint_start)
        s.stint_laps = max(0, int(f.get("LapCompleted", 0) or 0) - self._stint_lap0)
        s.drivers_so_far = int(f.get("DCDriversSoFar", 0) or 0)
        s.dc_lap_status = int(f.get("DCLapStatus", 0) or 0)
        # input'ai
        s.throttle = _f(f.Throttle, 0.0)
        s.brake = _f(f.Brake, 0.0)
        s.clutch = 1.0 - _f(f.Clutch, 1.0)
        s.steer = _f(f.SteeringWheelAngle, 0.0)
        s.abs_active = bool(f.BrakeABSactive)
        s.gear = int(f.get("Gear", 0) or 0)
        s.speed = _f(f.Speed, 0.0)
        s.rpm = _f(f.RPM, 0.0)
        if self.inputs_enabled and self._inp_n:
            n = self._inp_n
            idx = (np.arange(self._inp_i - n, self._inp_i)) % self._inp.shape[1]
            seg = self._inp[:, idx]
            s.inputs = {"throttle": seg[0].copy(), "brake": seg[1].copy(), "clutch": seg[2].copy(),
                        "steer": seg[3].copy(), "abs": seg[4].copy()}
        if self._g:
            s.lat_g, s.long_g = self._g[-1]
            s.g_trail = tuple(self._g)
        # padangos
        for w in ("LF", "RF", "LR", "RR"):
            temps = tuple(_f(f.values.get(f"{w}temp{z}")) for z in ("CL", "CM", "CR"))
            wear = tuple(_f(f.values.get(f"{w}wear{z}")) for z in ("L", "M", "R"))
            s.tyres[w] = (temps, wear, _f(f.values.get(f"{w}coldPressure")))
        # boksai
        s.pit_flags = int(f.get("PitSvFlags", 0) or 0)
        s.pit_fuel = _f(f.PitSvFuel, 0.0)
        s.repair_left = _f(f.PitRepairLeft, 0.0)
        s.opt_repair_left = _f(f.PitOptRepairLeft, 0.0)
        s.fast_repairs = int(f.get("FastRepairAvailable", 0) or 0)
        warn = int(f.get("EngineWarnings", 0) or 0)
        s.warn_bits = warn
        s.limiter = bool(warn & WARN_LIMITER)
        s.on_pit_road = bool(f.OnPitRoad)
        s.in_stall = bool(f.PlayerCarInPitStall)
        s.tow_time = _f(f.PlayerCarTowTime, 0.0)
        s.warnings = tuple(txt for bit, txt in WARN_BITS.items() if warn & bit)
        s.water_temp = _f(f.WaterTemp)
        s.oil_temp = _f(f.OilTemp)
        s.oil_press = _f(f.OilPress)
        s.voltage = _f(f.Voltage)
        # ryšys
        for attr, name in (("chan_quality", "ChanQuality"), ("chan_partner", "ChanPartnerQuality"),
                           ("latency", "ChanLatency"), ("avg_latency", "ChanAvgLatency")):
            v = f.values.get(name)
            setattr(s, attr, float(v) if v is not None else None)
        # vėliavos
        bits = self._flag_bits(f, t)
        s.flag_bits = bits
        s.flags = tuple((key, text) for bit, key, text in FLAG_BITS if bits & bit)
        # kita
        tc = f.CarIdxTireCompound
        if tc is not None and pl_ok(f, tc):
            s.tyre_compound = int(tc[f.PlayerCarIdx])
        s.radio_idx = int(f.get("RadioTransmitCarIdx", -1) if f.RadioTransmitCarIdx is not None else -1)
        s.car_left_right = int(f.get("CarLeftRight", 0) or 0)
        s.pace_mode = int(f.get("PaceMode", -1) if f.PaceMode is not None else -1)
        pl = f.PlayerCarIdx
        rows, lines = f.CarIdxPaceRow, f.CarIdxPaceLine
        if pl is not None and rows is not None and 0 <= pl < len(rows):
            s.pace_row = int(rows[pl])
            s.pace_line = int(lines[pl]) if lines is not None else -1
        self._state = s
        return s


def pl_ok(f, arr) -> bool:
    pl = f.PlayerCarIdx
    return pl is not None and 0 <= pl < len(arr)


def _f(v, default=math.nan) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default
