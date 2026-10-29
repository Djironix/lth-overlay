"""Orai: dabartinės reikšmės ir tendencija per paskutines 10 min."""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

WETNESS_TEXT = (
    "Unknown", "Dry", "Mostly dry", "Very lightly wet", "Lightly wet",
    "Moderately wet", "Very wet", "Extremely wet",
)
SKIES_TEXT = ("Clear", "Partly cloudy", "Mostly cloudy", "Overcast")
TREND_WETTER, TREND_DRYING, TREND_STABLE = "wetter", "drying", "stable"

SAMPLE_EVERY_S = 10.0
WINDOW_S = 600.0


@dataclass
class WeatherState:
    track_temp: float = math.nan
    air_temp: float = math.nan
    wetness: int = 0
    wetness_text: str = WETNESS_TEXT[0]
    precipitation: float = 0.0  # 0..1
    declared_wet: bool = False
    skies: int = 0
    skies_text: str = SKIES_TEXT[0]
    wind_speed: float = 0.0  # m/s
    wind_dir: float = 0.0  # rad (iš kur pučia, nuo šiaurės)
    wind_rel: float | None = None  # rad, santykinai su mašinos kryptimi; 0 = priešinis
    heading: float | None = None  # mašinos kryptis (YawNorth), rad nuo šiaurės
    humidity: float = 0.0
    fog: float = 0.0
    time_of_day: float = 0.0  # s nuo vidurnakčio
    solar_altitude: float = 0.0  # rad
    trend: str = TREND_STABLE  # wetter, drying, stable
    wetness_change: int = 0  # lygių pokytis per langą
    track_temp_change: float = 0.0  # °C per langą
    window_s: float = 0.0
    valid: bool = False


class WeatherTracker:
    def __init__(self):
        self._hist = deque()  # (t, wetness, precip, track_temp)
        self._last_sample = -1e9
        self._cur = WeatherState()
        self._last_update = -1e9

    def update(self, f):
        """Orai keičiasi lėtai: atnaujinam ne dažniau kaip 1 kartą per sekundę."""
        t = f.SessionTime
        if t is None:
            return
        if 0 <= t - self._last_update < 1.0:
            return
        self._last_update = t
        w = self._cur
        w.valid = f.TrackTempCrew is not None
        w.track_temp = _f(f.TrackTempCrew)
        w.air_temp = _f(f.AirTemp)
        w.wetness = int(f.get("TrackWetness", 0))
        w.wetness_text = WETNESS_TEXT[w.wetness] if 0 <= w.wetness < len(WETNESS_TEXT) else WETNESS_TEXT[0]
        w.precipitation = _f(f.get("Precipitation", 0.0), 0.0)
        w.declared_wet = bool(f.get("WeatherDeclaredWet", False))
        w.skies = int(f.get("Skies", 0))
        w.skies_text = SKIES_TEXT[w.skies] if 0 <= w.skies < len(SKIES_TEXT) else ""
        w.wind_speed = _f(f.get("WindVel", 0.0), 0.0)
        w.wind_dir = _f(f.get("WindDir", 0.0), 0.0)
        yaw = f.YawNorth
        w.wind_rel = None if yaw is None else _wrap(w.wind_dir - float(yaw))
        w.heading = None if yaw is None else float(yaw)
        w.humidity = _f(f.get("RelativeHumidity", 0.0), 0.0)
        w.fog = _f(f.get("FogLevel", 0.0), 0.0)
        w.time_of_day = _f(f.get("SessionTimeOfDay", 0.0), 0.0)
        w.solar_altitude = _f(f.get("SolarAltitude", 0.0), 0.0)
        if t < self._last_sample - 1.0:  # replay atgal
            self._hist.clear()
            self._last_sample = -1e9
            self._last_update = t
        if t - self._last_sample >= SAMPLE_EVERY_S:
            self._last_sample = t
            self._hist.append((t, w.wetness, w.precipitation, w.track_temp))
            while self._hist and t - self._hist[0][0] > WINDOW_S:
                self._hist.popleft()
            self._trend()

    def _trend(self):
        w = self._cur
        if len(self._hist) < 2:
            return
        t0, wet0, pr0, tt0 = self._hist[0]
        t1, wet1, pr1, tt1 = self._hist[-1]
        w.window_s = t1 - t0
        w.wetness_change = wet1 - wet0
        w.track_temp_change = tt1 - tt0 if math.isfinite(tt0) and math.isfinite(tt1) else 0.0
        if wet1 > wet0 or (wet1 == wet0 and pr1 - pr0 > 0.05 and wet1 > 1):
            w.trend = TREND_WETTER
        elif wet1 < wet0 or (wet1 == wet0 and wet1 > 1 and pr1 < 0.01 and pr0 < 0.01 and tt1 > tt0 + 0.5):
            w.trend = TREND_DRYING
        else:
            w.trend = TREND_STABLE

    def state(self) -> WeatherState:
        s = self._cur
        return WeatherState(**s.__dict__)


def _f(v, default=math.nan) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi
