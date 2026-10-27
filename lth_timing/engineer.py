"""Engineer žinutės: trumpai, retai ir tik tiesiojoje.

Taisyklės:
- ne daugiau kaip 1 žinutė per MIN_GAP_S (saugumo žinutės - iškart);
- rodoma tik kai pilotas važiuoja tiesiai pilnu greičiu;
- kiekvieną tipą galima išjungti (enabled).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

MIN_GAP_S = 20.0
SHOW_S = 6.0
QUEUE_TTL_S = 8.0

TYPES = ("ahead", "behind", "slow_car", "weather", "best_lap", "time", "faster_class")


@dataclass
class Message:
    kind: str
    text: str
    priority: int  # 2 = saugumas, 1 = svarbu, 0 = informacija
    created: float
    shown_at: float | None = None


@dataclass
class Engineer:
    enabled: set = field(default_factory=lambda: set(TYPES))
    _queue: list = field(default_factory=list)
    _active: list = field(default_factory=list)
    _last_shown: float = -1e9
    _done: dict = field(default_factory=dict)  # raktas -> laikas
    _best: float = 0.0
    _my_laps: int = -1
    _trend: str = "stable"
    _time_flag: set = field(default_factory=set)

    def reset(self):
        self.__init__(enabled=self.enabled)

    def _push(self, kind, text, prio, t, key=None, cooldown=0.0):
        if kind not in self.enabled:
            return
        key = key or kind
        last = self._done.get(key)
        if last is not None and t - last < cooldown:
            return
        self._done[key] = t
        self._queue = [m for m in self._queue if m.kind != kind]
        self._queue.append(Message(kind, text, prio, t))

    def update(self, snap, frame) -> list:
        t = snap.t
        if t < self._last_shown - 1:
            self.reset()
        me_row = next((r for r in snap.cars if r.is_me), None)
        if me_row is not None and snap.session_type == "race":
            self._race_rules(snap, me_row, t)
        if me_row is not None:
            self._lap_rules(snap, me_row, t)
        self._weather_rules(snap, t)
        self._time_rules(snap, t)
        self._deliver(frame, t)
        self._active = [m for m in self._active if t - m.shown_at < SHOW_S]
        return list(self._active)

    # ---------------- taisyklės ----------------
    def _race_rules(self, snap, me_row, t):
        lap = me_row.laps
        for rr in snap.relative:
            if rr.is_me:
                continue
            car = rr.car
            num = f"#{car.number}"
            # Lėta mašina priekyje (iki ~10 s)
            if rr.gap > 0 and rr.gap < 10 and car.status == "off":
                self._push("slow_car", f"Slow car ahead: {num}, {rr.gap:.1f}s", 2, t,
                           key=f"slow{car.idx}", cooldown=15)
            if rr.lap_rel != 0:
                # Greitesnė klasė iš už nugaros
                if (snap.multiclass and rr.gap < 0 and rr.gap > -3.0 and car.class_id != me_row.class_id
                        and self._faster_class(snap, car.class_id, me_row.class_id)):
                    self._push("faster_class", f"{car.class_name} behind, {-rr.gap:.1f}s", 1, t,
                               key=f"fc{car.idx}", cooldown=30)
                continue
            if car.class_id != me_row.class_id:
                if (snap.multiclass and rr.gap < 0 and rr.gap > -3.0
                        and self._faster_class(snap, car.class_id, me_row.class_id)):
                    self._push("faster_class", f"{car.class_name} behind, {-rr.gap:.1f}s", 1, t,
                               key=f"fc{car.idx}", cooldown=30)
                continue
            if 0 < rr.gap < 3.0 and rr.delta is not None:
                if rr.delta < -0.05:
                    tail = f", catch in {rr.laps_to_catch:.0f} laps" if rr.catchable else ""
                    txt = f"Ahead {num}: {rr.gap:.1f}s, you are {-rr.delta:.1f}/lap faster{tail}"
                elif rr.delta > 0.05:
                    txt = f"Ahead {num}: {rr.gap:.1f}s, he is {rr.delta:.1f}/lap faster"
                else:
                    txt = f"Ahead {num}: {rr.gap:.1f}s, same pace"
                self._push("ahead", txt, 0, t, key=f"ahead{lap}", cooldown=0)
            elif -1.5 < rr.gap < 0 and rr.delta is not None and rr.delta < -0.1:
                self._push("behind", f"Behind {num} closing {-rr.delta:.1f}/lap, {-rr.gap:.1f}s", 1, t,
                           key=f"behind{lap}", cooldown=0)

    @staticmethod
    def _faster_class(snap, other, mine):
        a = snap.classes.get(other, {}).get("est_lap") or 0
        b = snap.classes.get(mine, {}).get("est_lap") or 0
        return a and b and a < b - 1.0

    def _lap_rules(self, snap, me_row, t):
        if me_row.laps != self._my_laps:
            if self._my_laps >= 0 and me_row.last_lap > 0 and me_row.last_is_pb:
                diff = me_row.last_lap - self._best if self._best > 0 else 0.0
                tail = f" ({diff:+.3f})" if diff else ""
                self._push("best_lap", f"Personal best {fmt_lap(me_row.last_lap)}{tail}", 0, t)
            self._my_laps = me_row.laps
            if me_row.best_lap > 0:
                self._best = me_row.best_lap

    def _weather_rules(self, snap, t):
        w = snap.weather
        if w is None or not w.valid:
            return
        if w.trend != self._trend:
            if w.trend == "wetter":
                self._push("weather", f"Track getting wetter: {w.wetness_text.lower()}", 1, t, cooldown=120)
            elif w.trend == "drying":
                self._push("weather", f"Track drying: {w.wetness_text.lower()}", 1, t, cooldown=120)
            self._trend = w.trend
        rc = getattr(snap, "rain_call", None)
        if rc is not None and rc.key in ("wet_tyres", "try_dries"):
            self._push("weather", rc.detail, 2, t, key="rain_" + rc.key, cooldown=300)

    def _time_rules(self, snap, t):
        if snap.session_type != "race":
            return
        if 0 < snap.time_remain <= 300 and "5min" not in self._time_flag and snap.time_remain < 1e5:
            self._time_flag.add("5min")
            self._push("time", "5 minutes to go", 1, t)
        if snap.laps_remain == 1 and "last" not in self._time_flag:
            self._time_flag.add("last")
            self._push("time", "Last lap", 1, t)

    # ---------------- pristatymas ----------------
    def _deliver(self, frame, t):
        self._queue = [m for m in self._queue if t - m.created < QUEUE_TTL_S or m.priority >= 2]
        if not self._queue:
            return
        self._queue.sort(key=lambda m: (-m.priority, m.created))
        m = self._queue[0]
        if m.priority < 2:
            if t - self._last_shown < MIN_GAP_S:
                return
            if not on_straight(frame):
                return
        self._queue.pop(0)
        m.shown_at = t
        self._last_shown = t
        self._active = [x for x in self._active if x.priority > m.priority] + [m]


def on_straight(frame) -> bool:
    if frame is None:
        return True
    thr = frame.Throttle
    steer = frame.SteeringWheelAngle
    if thr is None or steer is None:
        return True
    return thr > 0.95 and abs(steer) < 0.15


def fmt_lap(s: float) -> str:
    if not s or s <= 0 or not math.isfinite(s):
        return "-"
    m, sec = divmod(s, 60)
    return f"{int(m)}:{sec:06.3f}"
