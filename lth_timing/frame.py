"""Vienas telemetrijos kadras ir kintamųjų sąrašas.

Skaitome tik tuos kintamuosius, kurių reikia (ne visus ~300), todėl
kiekvienas kadras kainuoja kelias mikrosekundes.
"""
from __future__ import annotations

import numpy as np

MAX_CARS = 128  # iRacing dabar skelbia 72 vietas; masyvai pritaikomi (žr. irsdk.fit_car_array)

# Kintamieji, kuriuos skaito variklis. (pavadinimas, numpy tipas, kiekis)
CAR_VARS = (
    ("CarIdxLapDistPct", np.float32),
    ("CarIdxLap", np.int32),
    ("CarIdxLapCompleted", np.int32),
    ("CarIdxOnPitRoad", np.bool_),
    ("CarIdxTrackSurface", np.int32),
    ("CarIdxPosition", np.int32),
    ("CarIdxClassPosition", np.int32),
    ("CarIdxLastLapTime", np.float32),
    ("CarIdxBestLapTime", np.float32),
    ("CarIdxEstTime", np.float32),
    ("CarIdxF2Time", np.float32),
    ("CarIdxTireCompound", np.int32),
)

SCALAR_VARS = (
    ("SessionTime", np.float64),
    ("SessionNum", np.int32),
    ("SessionState", np.int32),
    ("SessionFlags", np.uint32),
    ("SessionTimeRemain", np.float64),
    ("SessionLapsRemainEx", np.int32),
    ("SessionTimeOfDay", np.float32),
    ("PlayerCarIdx", np.int32),
    ("CamCarIdx", np.int32),
    ("IsOnTrack", np.bool_),
    ("IsReplayPlaying", np.bool_),
    ("IsInGarage", np.bool_),
    ("CamCameraState", np.uint32),
    ("Throttle", np.float32),
    ("SteeringWheelAngle", np.float32),
    ("Speed", np.float32),
    ("YawNorth", np.float32),
    ("PlayerCarMyIncidentCount", np.int32),
    ("DisplayUnits", np.int32),
    ("AirTemp", np.float32),
    ("TrackTempCrew", np.float32),
    ("TrackWetness", np.int32),
    ("Precipitation", np.float32),
    ("WeatherDeclaredWet", np.bool_),
    ("Skies", np.int32),
    ("WindVel", np.float32),
    ("WindDir", np.float32),
    ("RelativeHumidity", np.float32),
    ("FogLevel", np.float32),
    ("SolarAltitude", np.float32),
    ("FrameRate", np.float32),
)

ALL_VARS = CAR_VARS + SCALAR_VARS

# irsdk_SessionState
STATE_INVALID, STATE_GET_IN_CAR, STATE_WARMUP, STATE_PARADE, STATE_RACING, STATE_CHECKERED, STATE_COOLDOWN = range(7)

# irsdk_TrkLoc
SURF_NOT_IN_WORLD, SURF_OFF_TRACK, SURF_IN_PIT_STALL, SURF_APPROACHING_PITS, SURF_ON_TRACK = -1, 0, 1, 2, 3


class Frame:
    """Vieno kadro reikšmės. Atributai = iRacing kintamųjų vardai.

    Trūkstami kintamieji (sena iRacing versija) grąžina None.
    """

    __slots__ = ("values",)

    def __init__(self, values: dict):
        self.values = values

    def __getattr__(self, name):
        try:
            return self.values[name]
        except KeyError:
            return None

    def get(self, name, default=None):
        v = self.values.get(name)
        return default if v is None else v
