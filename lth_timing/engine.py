"""Timing variklis: gap'ai pagal laiką, kada mašinos kirto tą patį tašką.

Pagrindinė idėja
----------------
Kiekvienai mašinai saugome laiką, kada ji kirto kiekvieną timing tašką
(maždaug kas 50 m). Gap'as tarp A (priekyje) ir B (už jos) yra:

    gap = laikas, kai B buvo taške X  -  laikas, kai A buvo tame pačiame taške X

kur X yra paskutinė vieta, kurioje B tikrai matėme. Taip nėra jokio
„atstumas × greitis“ konvertavimo, todėl gap'as nekvėpuoja posūkiuose.

Neperduodamos mašinos
---------------------
Jei iRacing neperduoda mašinos (Max Cars), jos pozicija atsinaujina retai
arba sustingsta. Mes saugome tik tikrus pokyčius (laikas, pozicija) ir
interpoliuojame tarp jų, todėl sustingimas neiškraipo laikų. Kol mašina
„pasenusi“, gap'as skaičiuojamas paskutinėje patikimoje vietoje ir
pažymimas stale=True (overlay'uje „~“).

Efektyvumas
-----------
Visi masyvai paruošti iš anksto (64 mašinos), kadro apdorojimas yra
keletas numpy operacijų; Python ciklas sukasi tik per tas mašinas, kurios
šiame kadre kirto timing tašką (dažniausiai 0-3).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .frame import (MAX_CARS, STATE_CHECKERED, STATE_RACING, SURF_NOT_IN_WORLD,
                    SURF_OFF_TRACK, Frame)
from .player import PlayerTracker
from .sessioninfo import SessionModel
from .trackmap import TrackMap
from .weather import WeatherTracker

POINT_SPACING_M = 50.0
HISTORY_LAPS = 4
STALE_AFTER_S = 0.25
MAX_EXTRAPOLATE_S = 3.0
SLEW_S_PER_S = 3.0  # rodomo gap'o greičiausias pokytis po „pasenusių“ duomenų
SLEW_HOLD_S = 2.0


@dataclass
class CarRow:
    idx: int
    number: str
    name: str
    abbrev: str
    team: str
    class_id: int
    class_name: str
    class_color: int
    brand: dict
    irating: int
    license: str
    user_id: int = 0
    pos: int = 0
    class_pos: int = 0
    laps: int = 0  # užbaigti ratai
    progress: float = 0.0
    gap: float | None = None  # iki (klasės) lyderio, s
    gap_laps: int = 0
    interval: float | None = None  # iki priekyje esančio (tos pačios klasės)
    interval_laps: int = 0
    last_lap: float = 0.0
    best_lap: float = 0.0
    best_is_fastest: bool = False  # violetinis (klasėje)
    last_is_pb: bool = False
    last_is_fastest: bool = False
    in_pit: bool = False
    pit_stops: int = 0
    laps_since_pit: int | None = None
    status: str = "track"  # track, pit, off, garage, out
    stale: bool = False
    approx: bool = False  # gap'as apytikslis (dar nėra istorijos)
    tire: int = 0
    pos_change_start: int = 0
    pos_change_lap: int = 0
    is_me: bool = False


@dataclass
class RelRow:
    idx: int
    car: CarRow
    gap: float  # s; + priekyje, - už
    distance: float  # rato dalis; + priekyje
    lap_rel: int  # +1 = jis ratu priekyje lenktynėse, -1 = ratu atsilikęs
    delta: float | None = None  # gap'o pokytis per ratą; < 0 = artėjam
    delta_exact: bool = False
    laps_to_catch: float | None = None
    catchable: bool | None = None
    stale: bool = False
    approx: bool = False
    is_me: bool = False


@dataclass
class Snapshot:
    t: float = 0.0
    connected: bool = False
    session_type: str = "practice"
    session_state: int = 0
    flags: int = 0
    time_remain: float = 0.0
    laps_remain: int = -1
    me: int = -1
    on_track: bool = False
    replay: bool = False
    in_garage: bool = False  # savo mašina garaže (ne stebime)
    watching: bool = False  # kamera ant kitos mašinos (garaže / žiūrėjimas)
    multiclass: bool = False
    classes: dict = field(default_factory=dict)
    cars: list = field(default_factory=list)  # CarRow, surikiuoti pagal poziciją
    relative: list = field(default_factory=list)  # RelRow
    weather: object = None
    messages: list = field(default_factory=list)
    track_length_m: float = 0.0
    league_id: int = 0
    series_id: int = 0
    stats: dict = field(default_factory=dict)
    track_name: str = ""
    sectors: list = field(default_factory=list)
    player: object = None  # PlayerState
    track_map: dict = field(default_factory=dict)  # points, recording, progress
    pit: dict = field(default_factory=dict)  # lane_loss, stop_loss, samples
    battle: list = field(default_factory=list)  # sektorių palyginimas su mašinomis šalia
    sof: dict = field(default_factory=dict)  # klasė -> SOF (0 = bendras)
    car_pct: object = None  # np.ndarray: kiekvienos mašinos rato dalis šiame kadre (trasos žemėlapiui)


class TimingEngine:
    def __init__(self, point_spacing_m: float = POINT_SPACING_M, history_laps: int = HISTORY_LAPS,
                 rate_hz: float = 20.0, standings_hz: float = 2.0, maps_dir: str | None = None):
        self.player = PlayerTracker()
        self.trackmap = TrackMap(maps_dir)
        self.pit_losses = []
        self._min_dt = 1.0 / rate_hz - 0.004 if rate_hz < 60 else 0.0
        self._standings_dt = 1.0 / standings_hz
        self._rows_cache = None  # (t, rows)
        self._derived = None  # (rows, sof, battle, pit)
        self.spacing = point_spacing_m
        self.history_laps = history_laps
        self.session: SessionModel | None = None
        self.weather = WeatherTracker()
        self._init_track(4000.0)
        self._session_num = None
        self._last_t = None
        self.frame: Frame | None = None
        self.stats = {"frames": 0, "crossings": 0, "resets": 0}

    # ------------------------------------------------------------------
    # Būsena
    # ------------------------------------------------------------------
    def _init_track(self, length_m: float):
        self.track_m = max(length_m, 500.0)
        self.P = int(min(400, max(40, round(self.track_m / self.spacing))))
        self.R = self.P * self.history_laps
        self._reset_cars()

    def _reset_cars(self):
        n = MAX_CARS
        self.hist_t = np.full((n, self.R), np.nan)
        self.hist_n = np.full((n, self.R), -1, dtype=np.int64)
        self.last_pct = np.full(n, -1.0)
        self.lap_ctr = np.zeros(n, dtype=np.int64)
        self.known = np.zeros(n, dtype=bool)
        self.obs_prog = np.full(n, np.nan)  # paskutinis tikras pokytis
        self.obs_t = np.full(n, np.nan)
        self.speed = np.zeros(n)  # ratai per sekundę (EMA)
        self.in_world = np.zeros(n, dtype=bool)
        self.on_pit = np.zeros(n, dtype=bool)
        self.surface = np.full(n, SURF_NOT_IN_WORLD, dtype=np.int64)
        self.pit_stops = np.zeros(n, dtype=np.int64)
        self.pit_exit_lap = np.full(n, -1, dtype=np.int64)
        self.start_class_pos = {}
        self.lap_pos = {}  # idx -> (lap, pos) paskutinio rato pradžioje
        self.pos_change_lap = {}
        self._rel_hist = {}  # idx -> (pusė, {mano taškas: |gap|}, delta talpykla)
        self._shown = {}  # (idx, ref) -> (value, t, was_stale, blend)
        self._race_started = False
        self._rows_cache = None
        self._derived = None
        self.pit_in = {}  # idx -> (progresas, laikas) įvažiuojant į boksus
        self.pit_stationary = np.zeros(n)  # kiek s stovėjo boksuose šio sustojimo metu
        self.pit_losses = []  # (klasė, viso nuostolis, boksų tako nuostolis)
        self._prev_proc_t = None
        if hasattr(self, "player"):
            self.player.reset()

    def set_session(self, model: SessionModel | None):
        if model is None or model is self.session:
            return
        old_len = self.session.track_length_m if self.session else None
        self.session = model
        if model.track_length_m and model.track_length_m != old_len:
            self._init_track(model.track_length_m)
        self.player.fuel_max_l = model.fuel_max_l
        if model.track_length_m:
            self.trackmap.set_track(model.track_key)

    # ------------------------------------------------------------------
    # Kadro apdorojimas (60 Hz)
    # ------------------------------------------------------------------
    def update(self, f: Frame):
        """Apdoroja kadrą. Kviečiama kiekvienam iRacing kadrui (60 Hz), bet
        skaičiuojama tik rate_hz dažniu (20 Hz): kirtimų laikai interpoliuojami,
        todėl tikslumas toks pat kaip 60 Hz (patikrinta iki 15 Hz) už trečdalį kainos."""
        self.frame = f
        self.stats["frames"] += 1
        self.player.sample_inputs(f)
        t = float(f.SessionTime)
        num = f.SessionNum
        # Nauja sesija arba šuolis laike (replay) -> pradedam iš naujo
        if num != self._session_num or (self._last_t is not None and (t < self._last_t - 0.5 or t > self._last_t + 5.0)):
            if self._session_num is not None:
                self.stats["resets"] += 1
            self._session_num = num
            self._reset_cars()
            self._last_t = None
        if self._last_t is not None and t - self._last_t < self._min_dt:
            return
        self._last_t = t
        self.stats["processed"] = self.stats.get("processed", 0) + 1
        self.weather.update(f)
        self.player.update(f, t)
        self.trackmap.update(f, t)
        dt_proc = t - self._prev_proc_t if self._prev_proc_t is not None else 0.0
        self._prev_proc_t = t

        pct = f.CarIdxLapDistPct.astype(np.float64)
        lap_started = f.CarIdxLap
        surface = f.CarIdxTrackSurface
        if surface is None:
            surface = np.where(pct >= 0, 3, -1)
        self.surface[:] = surface
        on_pit = f.CarIdxOnPitRoad
        if on_pit is not None:
            exited = self.on_pit & ~on_pit
            for c in np.nonzero(exited)[0]:
                self.pit_exit_lap[c] = self.lap_ctr[c]
                self._pit_loss(int(c), t)
            entered = ~self.on_pit & on_pit & self.known
            self.pit_stops[entered] += 1
            for c in np.nonzero(entered)[0]:
                self.pit_in[int(c)] = (self.obs_prog[c], self.obs_t[c])
                self.pit_stationary[c] = 0.0
            # stovėjimas boksuose: pozicija nesikeičia > 0,5 s
            if dt_proc > 0:
                stopped = self.on_pit & self.known & (t - self.obs_t > 0.5)
                self.pit_stationary[stopped] += dt_proc
            self.on_pit[:] = on_pit

        valid = pct >= 0.0
        self.in_world[:] = valid

        # Naujai pasirodžiusios mašinos
        new = valid & ~self.known
        if new.any():
            lap = np.maximum(lap_started[new], 0) if lap_started is not None else 0
            self.lap_ctr[new] = lap
            self.obs_prog[new] = lap + pct[new]
            self.obs_t[new] = t
            self.last_pct[new] = pct[new]
            self.known[new] = True

        changed = valid & self.known & (pct != self.last_pct) & ~new
        if not changed.any():
            return
        idx = np.nonzero(changed)[0]
        p_new = pct[idx]
        dp = p_new - self.last_pct[idx]
        lap = self.lap_ctr[idx] + (dp < -0.5) - (dp > 0.5)
        # Ratų skaičių sulyginam su iRacing tik toli nuo linijos
        if lap_started is not None:
            ls = lap_started[idx]
            mid = (p_new > 0.1) & (p_new < 0.9) & (ls >= 0)
            lap = np.where(mid, ls, lap)
        self.lap_ctr[idx] = lap
        prog = lap + p_new
        p0 = self.obs_prog[idx]
        t0 = self.obs_t[idx]
        dt = t - t0
        dprog = prog - p0
        # Pagrįstas judėjimas pirmyn: ne greičiau nei ~120 m/s ir ne atgal
        max_jump = np.maximum(dt, 1 / 60) * (120.0 / self.track_m) + 0.002
        ok = (dprog > 0) & (dprog <= max_jump)
        # Greitis (EMA), tik iš pagrįstų žingsnių
        good = ok & (dt > 0)
        if good.any():
            v = dprog[good] / dt[good]
            a = np.clip(dt[good] / 0.5, 0.05, 1.0)
            self.speed[idx[good]] = self.speed[idx[good]] * (1 - a) + v * a
        bad = ~ok & (np.abs(dprog) > 0.002)
        if bad.any():  # teleportas / atgal: istorijos nepildom
            self.speed[idx[bad]] = 0.0
        # Timing taškų kirtimai
        P = self.P
        n0 = np.floor(p0 * P).astype(np.int64)
        n1 = np.floor(prog * P).astype(np.int64)
        crossed = ok & (n1 > n0)
        for k in np.nonzero(crossed)[0]:
            c = idx[k]
            a_p, b_p, a_t = p0[k], prog[k], t0[k]
            span_p, span_t = b_p - a_p, t - a_t
            for j in range(n0[k] + 1, n1[k] + 1):
                tj = a_t + (j / P - a_p) / span_p * span_t
                s = j % self.R
                self.hist_t[c, s] = tj
                self.hist_n[c, s] = j
            self.stats["crossings"] += int(n1[k] - n0[k])
        self.obs_prog[idx] = prog
        self.obs_t[idx] = t
        self.last_pct[idx] = p_new

    # ------------------------------------------------------------------
    # Laiko paieška istorijoje
    # ------------------------------------------------------------------
    def time_at(self, c: int, prog: float) -> float:
        """Kada mašina c buvo progreso taške prog (absoliutus: ratai + dalis)."""
        if not np.isfinite(prog):
            return math.nan
        P = self.P
        x = prog * P
        n0 = int(math.floor(x))
        s0 = n0 % self.R
        if self.hist_n[c, s0] != n0:
            return math.nan
        t0 = self.hist_t[c, s0]
        n1 = n0 + 1
        s1 = n1 % self.R
        if self.hist_n[c, s1] == n1:
            return t0 + (x - n0) * (self.hist_t[c, s1] - t0)
        # Tarp paskutinio taško ir paskutinio stebėjimo
        op, ot = self.obs_prog[c], self.obs_t[c]
        if op >= prog and op * P > n0:
            return t0 + (x - n0) / (op * P - n0) * (ot - t0)
        return math.nan

    def _time_at_many(self, cars: np.ndarray, progs: np.ndarray) -> np.ndarray:
        """Vektorizuota time_at standings lentelei."""
        P, R = self.P, self.R
        x = progs * P
        n0 = np.floor(np.nan_to_num(x, nan=-10)).astype(np.int64)
        s0 = np.mod(n0, R)
        s1 = np.mod(n0 + 1, R)
        ok0 = self.hist_n[cars, s0] == n0
        ok1 = self.hist_n[cars, s1] == n0 + 1
        t0 = self.hist_t[cars, s0]
        t1 = self.hist_t[cars, s1]
        out = np.where(ok0 & ok1, t0 + (x - n0) * (t1 - t0), np.nan)
        # Atvejai be kito taško
        rest = ok0 & ~ok1 & np.isfinite(x)
        if rest.any():
            for i in np.nonzero(rest)[0]:
                out[i] = self.time_at(int(cars[i]), float(progs[i]))
        return out

    # ------------------------------------------------------------------
    # Momentinė būsena (UI kviečia ~10 Hz)
    # ------------------------------------------------------------------
    def est_progress(self, t: float) -> np.ndarray:
        age = np.clip(t - self.obs_t, 0, MAX_EXTRAPOLATE_S)
        return self.obs_prog + np.where(self.on_pit, 0.0, self.speed * age)

    def base_time(self, t: float) -> np.ndarray:
        """Laikas, kuriam galioja paskutinė žinoma pozicija.

        Važiuojanti mašina: paskutinio pokyčio laikas. Sustojusi (boksai,
        avarija) - „dabar“, nes ji vis dar ten stovi ir gap'as auga."""
        age = t - self.obs_t
        stopped = self.known & (age > STALE_AFTER_S) & ~self.is_stale(t)
        # Nuo trasos nuvažiavusi mašina, kurios iRacing neperduoda: greičiausiai
        # stovi arba lėtai grįžta - gap'as turi augti realiu laiku.
        stopped |= self.known & (age > STALE_AFTER_S) & (self.surface == SURF_OFF_TRACK)
        return np.where(stopped, t, self.obs_t)

    def is_stale(self, t: float) -> np.ndarray:
        age = t - self.obs_t
        moving = self.speed * self.track_m > 5.0  # > 5 m/s prieš sustingimą
        return self.known & self.in_world & (age > STALE_AFTER_S) & moving

    @staticmethod
    def is_watching(f: Frame, m) -> bool:
        """Žiūrime, o ne vairuojame: stebėtojas, kamera ant kitos mašinos arba
        mūsų mašinos sesijoje apskritai nėra. Garaže savo mašinoje - ne."""
        cam, pl = f.CamCarIdx, f.PlayerCarIdx
        if cam is not None and 0 <= cam < MAX_CARS and cam != pl:
            return True
        if pl is None or pl < 0 or pl >= MAX_CARS:
            return True
        if m is not None and m.drivers:
            d = m.drivers.get(int(pl))
            if d is None or d.is_spectator:
                return True
            if m.driver_car_idx >= 0 and m.driver_car_idx != pl:
                return True
        return False

    def ref_car(self, f: Frame) -> int:
        if f is None:
            return -1
        if f.IsReplayPlaying or not f.IsOnTrack:
            cam = f.CamCarIdx
            if cam is not None and 0 <= cam < MAX_CARS and self.known[cam]:
                return int(cam)
        p = f.PlayerCarIdx
        if p is not None and 0 <= p < MAX_CARS:
            return int(p)
        return -1

    def _smooth(self, key, value, t, stale):
        """Kai bent viena mašina neseniai buvo „pasenusi“ (neperduodama), rodoma
        reikšmė keičiasi ne greičiau nei SLEW_S_PER_S. Taip grįžus tikriems
        duomenims skaičius nuslenka, o ne peršoka. Šviežiems duomenims - be pokyčių."""
        if value is None or not math.isfinite(value):
            self._shown.pop(key, None)
            return value
        prev = self._shown.get(key)
        last_stale = t if stale else (prev[2] if prev else -1e9)
        if prev is None or t < prev[1] or t - prev[1] > 0.5:
            self._shown[key] = (value, t, last_stale)
            return value
        pv, pt, _ = prev
        if t - last_stale < SLEW_HOLD_S:
            step = SLEW_S_PER_S * max(t - pt, 1 / 30)
            value = pv + max(-step, min(step, value - pv))
        self._shown[key] = (value, t, last_stale)
        return value

    def snapshot(self) -> Snapshot:
        f = self.frame
        snap = Snapshot(stats=dict(self.stats))
        if f is None:
            return snap
        m = self.session
        t = float(f.SessionTime)
        snap.connected = True
        snap.t = t
        snap.session_state = int(f.get("SessionState", 0))
        snap.flags = int(f.get("SessionFlags", 0))
        snap.time_remain = float(f.get("SessionTimeRemain", 0.0))
        snap.laps_remain = int(f.get("SessionLapsRemainEx", -1))
        snap.on_track = bool(f.IsOnTrack)
        snap.replay = bool(f.IsReplayPlaying)
        snap.watching = self.is_watching(f, m)
        g = f.IsInGarage
        snap.in_garage = bool(g) if g is not None else (not snap.on_track and not snap.replay)
        snap.session_type = m.session_type(f.SessionNum) if m else "race"
        snap.multiclass = bool(m and m.multiclass)
        snap.classes = m.classes if m else {}
        snap.track_length_m = self.track_m
        snap.league_id = m.league_id if m else 0
        snap.series_id = m.series_id if m else 0
        snap.weather = self.weather.state()
        me = self.ref_car(f)
        snap.me = me

        # Standings perskaičiuojami ~2 Hz, relative - kiekvieną kartą
        cache = self._rows_cache
        if cache is None or not (0 <= t - cache[0] < self._standings_dt) or cache[2] != me:
            rows = self._standings(f, m, t, me, snap.session_type, snap.session_state)
            self._rows_cache = (t, rows, me)
        else:
            rows = cache[1]
        snap.cars = rows
        snap.relative = self._relative(f, t, me, rows, snap)
        race = snap.session_type == "race"
        snap.player = self.player.state(f, t, snap.laps_remain, snap.time_remain, race)
        tm = self.trackmap
        snap.track_map = {"points": tm.points, "recording": tm.recording, "progress": tm.progress}
        snap.track_name = m.track_name if m else ""
        snap.sectors = list(m.sectors) if m and m.sectors else [0.0, 1 / 3, 2 / 3]
        # SOF, sektorių palyginimas, boksų nuostoliai keičiasi retai - kartu su standings (~2 Hz)
        dc = self._derived
        if dc is None or dc[0] is not rows:
            dc = self._derived = (rows, self._sof(rows), self._battle(me, snap.relative, snap.sectors),
                                  self._pit_summary())
        snap.sof, snap.battle, snap.pit = dc[1], dc[2], dc[3]
        pct = f.CarIdxLapDistPct
        snap.car_pct = None if pct is None else np.array(pct, dtype=np.float32)
        return snap

    # ------------------------------------------------------------------
    # Boksai, SOF, sektoriai
    # ------------------------------------------------------------------
    def _pit_loss(self, c: int, t: float):
        """Kiek laiko kainavo sustojimas: boksų kelias, palyginus su tuo pačiu
        trasos ruožu ankstesniame rate."""
        start = self.pit_in.pop(c, None)
        if start is None:
            return
        prog_in, t_in = start
        prog_out, t_out = self.obs_prog[c], self.obs_t[c]
        if not (np.isfinite(prog_in) and np.isfinite(prog_out) and np.isfinite(t_in)):
            return
        a = self.time_at(c, prog_in - 1.0)
        b = self.time_at(c, prog_out - 1.0)
        if not (math.isfinite(a) and math.isfinite(b)) or b <= a:
            return
        total = (t_out - t_in) - (b - a)
        lane = total - float(self.pit_stationary[c])
        if 3.0 < total < 300.0:
            m = self.session
            cid = m.drivers[c].class_id if m and c in m.drivers else 0
            self.pit_losses.append((cid, total, max(0.0, lane)))
            del self.pit_losses[:-40]

    def _pit_summary(self) -> dict:
        if not self.pit_losses:
            return {"samples": 0, "lane_loss": None, "stop_loss": None}
        totals = sorted(x[1] for x in self.pit_losses)
        lanes = sorted(x[2] for x in self.pit_losses)
        return {"samples": len(totals), "lane_loss": lanes[len(lanes) // 2], "stop_loss": totals[len(totals) // 2]}

    @staticmethod
    def _sof(rows) -> dict:
        """iRacing stiprumo formulė (Strength of Field) kiekvienai klasei ir bendrai."""
        out = {}
        groups = {0: [r.irating for r in rows if r.irating > 0]}
        for r in rows:
            if r.irating > 0:
                groups.setdefault(r.class_id, []).append(r.irating)
        k = 1600.0 / math.log(2)
        for cid, irs in groups.items():
            if irs:
                s = sum(math.exp(-ir / k) for ir in irs)
                out[cid] = int(round(k * math.log(len(irs) / s)))
        return out

    def _sector_times(self, c: int, lap_n: int, bounds) -> list:
        ts = [self.time_at(c, lap_n + b) for b in bounds]
        return [ts[i + 1] - ts[i] if math.isfinite(ts[i]) and math.isfinite(ts[i + 1]) else None
                for i in range(len(ts) - 1)]

    def _battle(self, me: int, relative, sectors) -> list:
        """Sektorių palyginimas su artimiausiomis tos pačios klasės mašinomis priekyje ir už."""
        if me < 0 or not self.known[me] or not np.isfinite(self.obs_prog[me]):
            return []
        bounds = list(sectors) + [1.0]
        me_row = next((r for r in relative if r.is_me), None)
        if me_row is None:
            return []
        out = []
        for side in (1, -1):
            cands = [r for r in relative if not r.is_me and r.lap_rel == 0 and (r.gap > 0) == (side > 0)
                     and r.car.class_id == me_row.car.class_id]
            if not cands:
                continue
            rr = min(cands, key=lambda r: abs(r.gap))
            c = rr.idx
            my_lap = int(math.floor(self.obs_prog[me])) - 1
            his_lap = int(math.floor(self.obs_prog[c])) - 1
            mine = self._sector_times(me, my_lap, bounds)
            his = self._sector_times(c, his_lap, bounds)
            diff = [(a - b) if a is not None and b is not None else None for a, b in zip(mine, his)]
            out.append({"side": "ahead" if side > 0 else "behind", "idx": c, "number": rr.car.number,
                        "name": rr.car.name, "abbrev": rr.car.abbrev, "gap": rr.gap, "mine": mine,
                        "his": his, "diff": diff})
        return out

    # ------------------------------------------------------------------
    def _drivers(self, m):
        out = []
        for c in range(MAX_CARS):
            d = m.drivers.get(c) if m else None
            if m and (d is None or d.is_pace_car or d.is_spectator):
                continue
            if not m and not self.known[c]:
                continue
            out.append(c)
        return out

    def _make_row(self, c, m, me):
        d = m.drivers.get(c) if m else None
        if d is None:
            return CarRow(idx=c, number=str(c), name=f"#{c}", abbrev=f"#{c}", team="", class_id=0,
                          class_name="", class_color=0xFFDA59, brand={"short": "?", "color": "#808080"},
                          irating=0, license="", is_me=(c == me))
        return CarRow(idx=c, number=d.number, name=d.name, abbrev=d.abbrev, team=d.team,
                      class_id=d.class_id, class_name=d.class_name, class_color=d.class_color,
                      brand=d.brand, irating=d.irating, license=d.license, user_id=d.user_id, is_me=(c == me))

    def _standings(self, f, m, t, me, stype, state):
        cars = self._drivers(m)
        if not cars:
            return []
        prog_est = self.est_progress(t)
        stale = self.is_stale(t)
        last = f.CarIdxLastLapTime
        best = f.CarIdxBestLapTime
        lap_done = f.CarIdxLapCompleted
        ipos = f.CarIdxPosition
        tires = f.CarIdxTireCompound
        rows = {c: self._make_row(c, m, me) for c in cars}
        for c, r in rows.items():
            r.last_lap = float(last[c]) if last is not None and last[c] > 0 else 0.0
            r.best_lap = float(best[c]) if best is not None and best[c] > 0 else 0.0
            r.laps = int(lap_done[c]) if lap_done is not None and lap_done[c] >= 0 else 0
            r.progress = float(prog_est[c]) if np.isfinite(prog_est[c]) else -1.0
            r.in_pit = bool(self.on_pit[c])
            r.pit_stops = int(self.pit_stops[c])
            r.laps_since_pit = int(self.lap_ctr[c] - self.pit_exit_lap[c]) if self.pit_exit_lap[c] >= 0 else None
            r.stale = bool(stale[c])
            r.tire = int(tires[c]) if tires is not None else 0
            surf = self.surface[c]
            if not self.known[c] or not self.in_world[c]:
                r.status = "garage" if self.known[c] or surf == SURF_NOT_IN_WORLD else "out"
            elif self.on_pit[c]:
                r.status = "pit"
            elif surf == SURF_OFF_TRACK:
                r.status = "off"
            else:
                r.status = "track"
        results = {}
        if m and f.SessionNum in m.sessions:
            for res in m.sessions[f.SessionNum].results:
                try:
                    results[int(res.get("CarIdx"))] = res
                except (TypeError, ValueError):
                    pass

        # --- Tvarka ---
        if stype == "race":
            def key(c):
                r = rows[c]
                if state < STATE_RACING or state >= STATE_CHECKERED:
                    p = int(ipos[c]) if ipos is not None and ipos[c] > 0 else 0
                    if p == 0 and c in results:
                        p = int(results[c].get("Position") or 0)
                    if p > 0:
                        return (0, p, 0.0)
                if self.known[c] and r.progress >= 0:
                    return (0, 0, -r.progress)
                p = int(results.get(c, {}).get("Position") or 999)
                return (1, p, 0.0)
            order = sorted(cars, key=key)
        else:
            order = sorted(cars, key=lambda c: (rows[c].best_lap <= 0, rows[c].best_lap or 1e9, rows[c].number))

        # Pozicijos (bendra ir klasės)
        class_count = {}
        for i, c in enumerate(order, 1):
            r = rows[c]
            r.pos = i
            class_count[r.class_id] = class_count.get(r.class_id, 0) + 1
            r.class_pos = class_count[r.class_id]

        # Starto pozicijos ir pokytis per ratą
        if stype == "race":
            if state >= STATE_RACING and not self._race_started:
                self._race_started = True
                self.start_class_pos = {c: rows[c].class_pos for c in order}
            for c in order:
                r = rows[c]
                if c in self.start_class_pos:
                    r.pos_change_start = self.start_class_pos[c] - r.class_pos
                prev = self.lap_pos.get(c)
                if prev is None or prev[0] != r.laps:
                    if prev is not None:
                        self.pos_change_lap[c] = prev[1] - r.class_pos
                    self.lap_pos[c] = (r.laps, r.class_pos)
                r.pos_change_lap = self.pos_change_lap.get(c, 0)

        # Greičiausi ratai klasėse
        fastest = {}
        for c in order:
            r = rows[c]
            if r.best_lap > 0 and (r.class_id not in fastest or r.best_lap < fastest[r.class_id]):
                fastest[r.class_id] = r.best_lap
        for c in order:
            r = rows[c]
            fb = fastest.get(r.class_id)
            r.best_is_fastest = bool(fb and r.best_lap > 0 and abs(r.best_lap - fb) < 1e-4)
            r.last_is_pb = r.last_lap > 0 and abs(r.last_lap - r.best_lap) < 1e-4
            r.last_is_fastest = r.last_is_pb and r.best_is_fastest

        # --- Gap'ai ---
        if stype == "race":
            self._race_gaps(order, rows, t)
        else:
            leader_best = {}
            prev_best = {}
            for c in order:
                r = rows[c]
                if r.best_lap <= 0:
                    continue
                lb = leader_best.setdefault(r.class_id, r.best_lap)
                r.gap = r.best_lap - lb if r.best_lap != lb else None
                pb = prev_best.get(r.class_id)
                r.interval = (r.best_lap - pb) if pb else None
                prev_best[r.class_id] = r.best_lap
        return [rows[c] for c in order]

    def _race_gaps(self, order, rows, t):
        # Grupės pagal klasę: lyderis ir priekyje esantis tos pačios klasės
        leader = {}
        ahead = {}
        prev_in_class = {}
        for c in order:
            cid = rows[c].class_id
            leader.setdefault(cid, c)
            ahead[c] = prev_in_class.get(cid)
            prev_in_class[cid] = c
        valid = [c for c in order if self.known[c] and np.isfinite(self.obs_prog[c])]
        if not valid:
            return
        cars = np.array(valid, dtype=np.int64)
        my_prog = self.obs_prog[cars]
        my_t = self.base_time(t)[cars]
        stale = self.is_stale(t)
        lead = np.array([leader[rows[c].class_id] for c in valid], dtype=np.int64)
        ahd = np.array([ahead[c] if ahead[c] is not None else c for c in valid], dtype=np.int64)
        # laikas, kai lyderis / priekinis buvo mano paskutinėje patikimoje vietoje
        tl = self._time_at_many(lead, my_prog)
        ta = self._time_at_many(ahd, my_prog)
        prog_est = self.est_progress(t)
        for i, c in enumerate(valid):
            r = rows[c]
            L = int(lead[i])
            if L == c:
                r.gap = None
            else:
                laps = _whole_laps(prog_est[L] - prog_est[c])
                if laps >= 1:
                    r.gap, r.gap_laps = None, laps
                else:
                    g = my_t[i] - tl[i]
                    if not np.isfinite(g):
                        g = self._fallback_gap(L, c, prog_est)
                        r.approx = True
                    r.gap = self._smooth((c, "L", L), g, t, bool(stale[c] or stale[L]))
            A = ahead[c]
            if A is None:
                r.interval = None
            else:
                laps = _whole_laps(prog_est[A] - prog_est[c])
                if laps >= 1:
                    r.interval, r.interval_laps = None, laps
                else:
                    g = my_t[i] - ta[i]
                    if not np.isfinite(g):
                        g = self._fallback_gap(A, c, prog_est)
                        r.approx = True
                    r.interval = self._smooth((c, "A", A), g, t, bool(stale[c] or stale[A]))
            if r.gap is not None and r.gap < 0:
                r.gap = 0.0
            if r.interval is not None and r.interval < 0:
                r.interval = 0.0

    def _fallback_gap(self, a, b, prog_est):
        """Kai istorijos dar nėra (startas, prisijungėm vėliau): atstumas ×
        rato laikas. Apytiksliai (UI rodo „~“), bet stabilu - nešokinėja,
        kai greitis keičiasi."""
        d = prog_est[a] - prog_est[b]
        if not np.isfinite(d):
            return None
        lap = self._typical_lap(b)
        return d * lap if lap else None

    def _typical_lap(self, c):
        f = self.frame
        if f is not None and f.CarIdxBestLapTime is not None and f.CarIdxBestLapTime[c] > 0:
            return float(f.CarIdxBestLapTime[c])
        m = self.session
        if m and c in m.drivers and m.drivers[c].class_est_lap:
            return m.drivers[c].class_est_lap
        if self.speed[c] * self.track_m > 20.0:
            return 1.0 / self.speed[c]
        return None

    # ------------------------------------------------------------------
    def _relative(self, f, t, me, rows, snap, n_ahead=3, n_behind=3):
        if me < 0 or not self.known[me] or not np.isfinite(self.obs_prog[me]):
            return []
        by_idx = {r.idx: r for r in rows}
        prog_est = self.est_progress(t)
        stale = self.is_stale(t)
        my_pct = prog_est[me] % 1.0
        cand = []
        for r in rows:
            c = r.idx
            if c == me or not self.known[c] or not self.in_world[c] or not np.isfinite(prog_est[c]):
                continue
            off = ((prog_est[c] % 1.0) - my_pct + 0.5) % 1.0 - 0.5
            cand.append((off, c))
        ahead = sorted([x for x in cand if x[0] > 0])[:n_ahead]
        behind = sorted([x for x in cand if x[0] <= 0], reverse=True)[:n_behind]
        out = []
        race = snap.session_type == "race"
        my_lap_time = self._lap_time(me)
        laps_left = self._laps_left(snap, my_lap_time)
        my_point = int(math.floor(self.obs_prog[me] * self.P))
        self._base = self.base_time(t)
        for off, c in list(reversed(ahead)) + [(0.0, me)] + behind:
            r = by_idx.get(c)
            if r is None:
                continue
            if c == me:
                out.append(RelRow(idx=c, car=r, gap=0.0, distance=0.0, lap_rel=0, is_me=True))
                continue
            gap, gap_ago = self._pair_gap(me, c, off)
            approx = False
            if gap is None or not math.isfinite(gap):
                lap = self._typical_lap(me)
                gap = off * lap if lap else 0.0
                gap_ago = None
                approx = True
            shown = self._smooth((c, "R", me), gap, t, bool(stale[c] or stale[me]))
            lap_rel = 0
            if race:
                d = prog_est[c] - prog_est[me] - off
                lap_rel = int(round(d)) if np.isfinite(d) else 0
            row = RelRow(idx=c, car=r, gap=shown, distance=off, lap_rel=lap_rel, stale=bool(stale[c]), approx=approx)
            if gap_ago is not None and math.isfinite(gap_ago) and (gap_ago > 0) == (gap > 0):
                # Tikslus: gap'as dabar ir toje pačioje vietoje prieš vieną ratą
                row.delta = abs(gap) - abs(gap_ago)
                row.delta_exact = True
            self._delta(row, my_point, my_lap_time, laps_left)
            out.append(row)
        return out

    def _pair_gap(self, me, c, off):
        """Gap'as sekundėmis tarp manęs ir c toje pačioje vietoje trasoje.

        Grąžina (gap dabar, gap toje pačioje vietoje prieš ratą). + = c priekyje.
        """
        base = self._base
        my_prog, my_t = self.obs_prog[me], base[me]
        c_prog, c_t = self.obs_prog[c], base[c]
        if off > 0:  # c priekyje: kada c buvo mano paskutinėje patikimoje vietoje
            target = c_prog - (((c_prog % 1.0) - (my_prog % 1.0)) % 1.0)
            tc = self.time_at(c, target)
            if not math.isfinite(tc):
                return None, None
            ago = self.time_at(me, my_prog - 1.0) - self.time_at(c, target - 1.0)
            return my_t - tc, ago
        # c už manęs: kada aš buvau c paskutinėje patikimoje vietoje
        target = my_prog - (((my_prog % 1.0) - (c_prog % 1.0)) % 1.0)
        tm = self.time_at(me, target)
        if not math.isfinite(tm) or c_t < tm:
            return None, None
        ago = -(self.time_at(c, c_prog - 1.0) - self.time_at(me, target - 1.0))
        return -(c_t - tm), ago

    def _delta(self, row: RelRow, my_point: int, lap_time: float | None, laps_left: float | None):
        """Atsarginis delta: kai istorijoje dar nėra viso rato, nuolydis iš
        paskutinių gap'o reikšmių. Tikslų delta nustato _relative."""
        if row.delta_exact:
            self._laps_to_catch(row, laps_left)
            return
        h = self._rel_hist.get(row.idx)
        side = 1 if row.gap >= 0 else -1
        if h is None or h[0] != side:
            h = [side, {}, None, None]  # pusė, {taškas: |gap|}, talpyklos taškas, (delta, tikslus)
            self._rel_hist[row.idx] = h
        q = h[1]
        g = abs(row.gap)
        if h[2] != my_point:  # skaičiuojam tik kai pasiekiam naują tašką
            h[2] = my_point
            q.setdefault(my_point, g)
            if len(q) > self.P * 2 + 4:
                for p in [p for p in q if p < my_point - self.P - 2]:
                    del q[p]
            target = my_point - self.P
            old = q.get(target)
            if old is None:
                old = q.get(target + 1, q.get(target - 1))
            if old is not None:
                h[3] = (q[my_point] - old, True)
            elif len(q) >= 8:
                h[3] = (_slope_per_lap(q, self.P), False)
            else:
                h[3] = None
        if h[3] is not None and h[3][0] is not None:
            row.delta, row.delta_exact = h[3]
        self._laps_to_catch(row, laps_left)

    @staticmethod
    def _laps_to_catch(row: RelRow, laps_left):
        if row.delta is not None and row.delta < -0.05:
            row.laps_to_catch = abs(row.gap) / -row.delta
            if laps_left is not None:
                row.catchable = row.laps_to_catch <= laps_left

    def _lap_time(self, c):
        f = self.frame
        if f is not None and f.CarIdxLastLapTime is not None and f.CarIdxLastLapTime[c] > 0:
            return float(f.CarIdxLastLapTime[c])
        if self.speed[c] > 0:
            return 1.0 / self.speed[c]
        m = self.session
        if m and c in m.drivers and m.drivers[c].class_est_lap:
            return m.drivers[c].class_est_lap
        return None

    def _laps_left(self, snap, lap_time):
        if snap.session_type != "race":
            return None
        if 0 <= snap.laps_remain < 30000:
            return float(snap.laps_remain)
        if lap_time and snap.time_remain > 0:
            return snap.time_remain / lap_time
        return None


def _whole_laps(d) -> int:
    """Kiek pilnų ratų skiria; nežinoma pozicija (NaN, mašina dar nematyta) = 0."""
    return int(math.floor(d + 1e-6)) if np.isfinite(d) else 0


def _slope_per_lap(q: dict, P: int):
    """Tiesinės regresijos nuolydis (s per ratą), be numpy - masyvai maži."""
    n = len(q)
    xs = list(q.keys())
    if max(xs) - min(xs) < P * 0.25:
        return None
    ys = list(q.values())
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / sxx * P
