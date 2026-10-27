"""Sintetinės lenktynės testams ir overlay'ų peržiūrai be iRacing.

Simuliuoja tai, kas sukėlė šokinėjančius gap'us:
- greitis kinta per ratą (lėti posūkiai, greitos tiesiosios);
- „neperduodamos“ mašinos (Max Cars): jų pozicija atsinaujina tik kas ~1 s;
- boksų sustojimas, mašina nuo trasos, lietus.

Simuliatorius žino tikrą kiekvienos mašinos trajektoriją, todėl testai
gali palyginti variklio gap'us su tikrais.
"""
from __future__ import annotations

import math

import numpy as np

from .frame import MAX_CARS, STATE_RACING, Frame
from .sessioninfo import Driver, SessionDesc, SessionModel, brand_for

CLASSES = {
    1: {"name": "GTP", "color": 0xFFDA59, "pace": 1.16, "cars": ["cadillacvseriesrgtp", "porsche963gtp", "bmwmhybridv8", "acurarxa"]},
    2: {"name": "LMP2", "color": 0x33CEFF, "pace": 1.09, "cars": ["dallarap217", "orecalmp2"]},
    3: {"name": "GT3", "color": 0xFF5888, "pace": 1.00, "cars": ["bmwm4gt3", "porsche992rgt3", "ferrari296gt3", "mercedesamgevogt3", "audir8lmsevo2gt3", "mclaren720sgt3", "fordmustanggt3"]},
}

NAMES = ["Jonas Petraitis", "Mantas Kazlauskas", "Tomas Jankauskas", "Lukas Stankevičius", "Paulius Vasiliauskas",
         "Darius Žukauskas", "Andrius Butkus", "Marius Paulauskas", "Rokas Urbonas", "Karolis Kavaliauskas",
         "Ignas Navickas", "Deividas Ramanauskas", "Justas Savickas", "Vytautas Rimkus", "Edvinas Baranauskas",
         "Aurimas Kairys", "Simonas Mockus", "Gediminas Vaitkus", "Tadas Sakalauskas", "Arnas Gudaitis",
         "Benas Mikalauskas", "Ernestas Šimkus", "Linas Adomaitis", "Nerijus Lukoševičius", "Povilas Žemaitis",
         "Eimantas Jonaitis", "Dominykas Bielskis", "Matas Kubilius", "Saulius Gailius", "Rytis Malinauskas",
         "Kęstutis Norkus", "Giedrius Pocius", "Ramūnas Daukša", "Algirdas Tamošiūnas", "Ugnius Valančius",
         "Žygimantas Lapinskas", "Arūnas Juška", "Evaldas Ruzgys", "Haroldas Česnulis", "Valdas Grigas"]


class SimRace:
    """60 Hz sintetinė lenktynė."""

    def __init__(self, n_cars=30, multiclass=False, track_m=4100.0, max_cars=None, nt_interval=1.0,
                 seed=7, me=None, rain=False, events=True, dt=1 / 60, start_t=0.0, record=True):
        rng = np.random.default_rng(seed)
        self.rng = rng
        self.dt = dt
        self.track_m = track_m
        self.n = n_cars
        self.t = start_t
        # klasės
        if multiclass:
            cls = [1] * max(2, n_cars // 6) + [2] * max(2, n_cars // 4)
            cls += [3] * (n_cars - len(cls))
        else:
            cls = [3] * n_cars
        self.cls = np.array(cls)
        pace = np.array([CLASSES[c]["pace"] for c in cls])
        self.pace = pace * (1 + rng.normal(0, 0.006, n_cars))
        # starto grid: klasės iš eilės, 8 m tarpai
        order = np.argsort(-self.pace, kind="stable")
        self.prog = np.zeros(n_cars)
        for rank, c in enumerate(order):
            self.prog[c] = 1.0 - (rank * 8.0 + 5) / track_m  # prieš liniją
        self.prog -= 1.0  # pirmas kirtimas -> 0 ratų
        self.me = int(order[min(n_cars - 1, n_cars // 2)]) if me is None else me
        self.max_cars = max_cars
        self.nt_interval = nt_interval
        self.reported = self.prog.copy()  # tai, ką mato klientas
        self.next_report = rng.uniform(0, nt_interval, n_cars)
        self.on_pit = np.zeros(n_cars, dtype=bool)
        self.surface = np.full(n_cars, 3)
        self.stop_until = np.zeros(n_cars)
        self.lap_times = np.zeros(n_cars)
        self.best = np.zeros(n_cars)
        self.lap_start_t = np.full(n_cars, np.nan)
        self.lap_noise = 1 + rng.normal(0, 0.003, n_cars)
        self.rain = rain
        self.record = record
        self.events = events
        # renginiai: (mašina, ratas, tipas)
        self.pit_car = int(order[3]) if n_cars > 4 else None
        self.off_car = int(order[min(n_cars - 1, 8)]) if n_cars > 9 else None
        self._pit_state = {}
        self.traj_t = []
        self.traj_p = []
        self.model = self._model()

    # ---- sesijos modelis ----
    def _model(self) -> SessionModel:
        m = SessionModel(track_name="Sim Raceway", track_length_m=self.track_m, league_id=0, update=1)
        m.driver_car_idx = self.me
        used = set()
        for i in range(self.n):
            c = int(self.cls[i])
            car_path = CLASSES[c]["cars"][i % len(CLASSES[c]["cars"])]
            name = NAMES[i % len(NAMES)]
            first, last = name.split(" ", 1)
            num = str(10 + i * 3 % 89)
            while num in used:
                num = str(int(num) + 1)
            used.add(num)
            m.drivers[i] = Driver(idx=i, name=name, abbrev=f"{first[0]}. {last}", team="", number=num, user_id=100000 + i,
                                  class_id=c, class_name=CLASSES[c]["name"], class_color=CLASSES[c]["color"],
                                  class_est_lap=self.track_m / 45.0 / CLASSES[c]["pace"], car_path=car_path,
                                  car_name=car_path, brand=brand_for(car_path), irating=1200 + (i * 137) % 3800,
                                  license=["A 4.21", "B 3.10", "C 2.75", "A 2.99"][i % 4], is_pace_car=False,
                                  is_spectator=False)
            if c not in m.classes:
                m.classes[c] = {"name": CLASSES[c]["name"], "color": CLASSES[c]["color"],
                                "est_lap": self.track_m / 45.0 / CLASSES[c]["pace"]}
        m.sessions[0] = SessionDesc(num=0, type="race", name="RACE", laps="unlimited")
        return m

    # ---- fizika ----
    def speed_at(self, pct):
        """m/s pagal vietą rate: 3 lėti posūkiai (~24 m/s), tiesiosios ~76 m/s."""
        s = np.sin(2 * np.pi * 3 * pct + 0.4)
        return 24.0 + 52.0 * ((0.5 + 0.5 * s) ** 1.6)

    def step(self):
        dt = self.dt
        t = self.t + dt
        pct = np.mod(self.prog, 1.0)
        v = self.speed_at(pct) * self.pace * self.lap_noise
        # boksai ir sustojimai
        if self.events:
            self._events(t, pct, v)
        v = np.where(self.stop_until > t, 0.0, v)
        v = np.where(self.on_pit, np.minimum(v, 22.0), v)
        for c, st in self._pit_state.items():
            if st[0] == "stall" and t < st[1]:
                v[c] = 0.0
        new_prog = self.prog + v * dt / self.track_m
        # ratų laikai
        crossed = np.floor(new_prog) > np.floor(self.prog)
        for c in np.nonzero(crossed)[0]:
            frac = (math.floor(new_prog[c]) - self.prog[c]) / (new_prog[c] - self.prog[c])
            tc = self.t + frac * dt
            if np.isfinite(self.lap_start_t[c]) and new_prog[c] >= 1.0:
                lt = tc - self.lap_start_t[c]
                self.lap_times[c] = lt
                if self.best[c] == 0 or lt < self.best[c]:
                    self.best[c] = lt
            self.lap_start_t[c] = tc
            self.lap_noise[c] = 1 + self.rng.normal(0, 0.003)
        self.prog = new_prog
        self.t = t
        if self.record:
            self.traj_t.append(t)
            self.traj_p.append(self.prog.copy())
        # ką mato klientas (Max Cars emuliacija)
        transmitted = self._transmitted()
        due = t >= self.next_report
        upd = transmitted | due
        self.reported = np.where(upd, self.prog, self.reported)
        self.next_report = np.where(due & ~transmitted, t + self.nt_interval * self.rng.uniform(0.8, 1.2, self.n),
                                    self.next_report)
        return self.frame()

    def _transmitted(self):
        if self.max_cars is None or self.max_cars >= self.n:
            return np.ones(self.n, dtype=bool)
        my = self.prog[self.me] % 1.0
        d = np.abs(((self.prog % 1.0) - my + 0.5) % 1.0 - 0.5)
        keep = np.argsort(d)[: self.max_cars]
        out = np.zeros(self.n, dtype=bool)
        out[keep] = True
        return out

    def _events(self, t, pct, v):
        # boksai: pit_car 3 rato pabaigoje
        c = self.pit_car
        if c is not None:
            st = self._pit_state.get(c)
            lap = math.floor(self.prog[c])
            if st is None and lap == 2 and pct[c] > 0.93:
                self._pit_state[c] = ("lane", 0)
                self.on_pit[c] = True
            elif st and st[0] == "lane" and lap == 3 and pct[c] > 0.02:
                self._pit_state[c] = ("stall", t + 25.0)
            elif st and st[0] == "stall" and t >= st[1]:
                self._pit_state[c] = ("exit", 0)
            elif st and st[0] == "exit" and pct[c] > 0.10:
                self.on_pit[c] = False
                self._pit_state[c] = ("done", 0)
        # nuvažiavimas nuo trasos 2 rate
        c = self.off_car
        if c is not None and math.floor(self.prog[c]) == 1 and 0.40 < pct[c] < 0.41 and self.stop_until[c] == 0:
            self.stop_until[c] = t + 8.0
            self.surface[c] = 0
        if c is not None and self.surface[c] == 0 and t > self.stop_until[c] > 0:
            self.surface[c] = 3

    # ---- kadras ----
    def frame(self) -> Frame:
        n = self.n
        pct = np.full(MAX_CARS, -1.0, dtype=np.float32)
        rep = self.reported
        pct[:n] = np.mod(rep, 1.0)
        lap = np.full(MAX_CARS, -1, dtype=np.int32)
        lap[:n] = np.floor(rep).astype(np.int32) + 1  # ratai pradėti
        done = np.full(MAX_CARS, -1, dtype=np.int32)
        done[:n] = np.maximum(np.floor(rep).astype(np.int32), 0)
        pit = np.zeros(MAX_CARS, dtype=bool)
        pit[:n] = self.on_pit
        surf = np.full(MAX_CARS, -1, dtype=np.int32)
        surf[:n] = np.where(self.on_pit, 2, self.surface)
        last = np.full(MAX_CARS, -1, dtype=np.float32)
        last[:n] = np.where(self.lap_times > 0, self.lap_times, -1)
        best = np.full(MAX_CARS, -1, dtype=np.float32)
        best[:n] = np.where(self.best > 0, self.best, -1)
        zeros = np.zeros(MAX_CARS, dtype=np.int32)
        w = self._weather()
        my_pct = self.prog[self.me] % 1.0
        v_me = self.speed_at(my_pct)
        vals = {
            "SessionTime": self.t, "SessionNum": 0, "SessionState": STATE_RACING, "SessionFlags": 0,
            "SessionTimeRemain": max(0.0, 2400.0 - self.t), "SessionLapsRemainEx": 32767,
            "SessionTimeOfDay": 14 * 3600 + self.t, "PlayerCarIdx": self.me, "CamCarIdx": self.me,
            "IsOnTrack": True, "IsReplayPlaying": False,
            "Throttle": 1.0 if v_me > 60 else 0.4, "SteeringWheelAngle": 0.02 if v_me > 60 else 0.6,
            "Speed": float(v_me), "YawNorth": float(2 * np.pi * my_pct), "PlayerCarMyIncidentCount": 2,
            "DisplayUnits": 1,
            "CarIdxLapDistPct": pct, "CarIdxLap": lap, "CarIdxLapCompleted": done, "CarIdxOnPitRoad": pit,
            "CarIdxTrackSurface": surf, "CarIdxPosition": zeros, "CarIdxClassPosition": zeros,
            "CarIdxLastLapTime": last, "CarIdxBestLapTime": best,
            "CarIdxEstTime": np.zeros(MAX_CARS, dtype=np.float32), "CarIdxF2Time": np.zeros(MAX_CARS, dtype=np.float32),
            "CarIdxTireCompound": np.where(np.arange(MAX_CARS) < n, 1 if w["wet"] >= 4 else 0, 0).astype(np.int32),
        }
        vals.update({
            "AirTemp": 18.5, "TrackTempCrew": w["track"], "TrackWetness": w["wet"], "Precipitation": w["precip"],
            "WeatherDeclaredWet": w["wet"] >= 4, "Skies": 3 if self.rain else 1, "WindVel": 4.2, "WindDir": 1.1,
            "RelativeHumidity": 0.72, "FogLevel": 0.0, "SolarAltitude": 0.6,
        })
        return Frame(vals)

    def _weather(self):
        if not self.rain:
            return {"wet": 1, "precip": 0.0, "track": 31.0 - self.t / 600}
        k = min(1.0, self.t / 900.0)
        return {"wet": 1 + int(k * 4), "precip": 0.6 * k, "track": 31.0 - 6 * k}

    # ---- tikrieji gap'ai testams ----
    def true_time_at(self, c, prog):
        p = np.array([x[c] for x in self.traj_p])
        t = np.array(self.traj_t)
        return float(np.interp(prog, p, t))

    def true_gap(self, ahead, behind, t_idx=-1):
        """Kada behind buvo dabartinėje vietoje minus kada ahead ten buvo."""
        p_b = self.traj_p[t_idx][behind]
        return self.traj_t[t_idx] - self.true_time_at(ahead, p_b)
