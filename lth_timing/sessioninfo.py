"""iRacing sesijos informacijos (YAML) skaitymas.

YAML gali būti 100+ KB, todėl jis parsinamas tik kai pasikeičia
(SessionInfoUpdate) ir atskirame gije, kad nestabdytų telemetrijos.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from .countries import iso_for

import yaml

try:  # C parseris yra ~10x greitesnis
    _Loader = yaml.CSafeLoader
except AttributeError:  # pragma: no cover
    _Loader = yaml.SafeLoader

# Laukai, kuriuose iRacing neįkabina reikšmių į kabutes (vardai su ':' ir pan.)
_UNSAFE_KEYS = re.compile(
    r"^(\s*(?:DriverSetupName|UserName|TeamName|AbbrevName|Initials|CarScreenName|"
    r"CarScreenNameShort|CarClassShortName|CarDesignStr|HelmetDesignStr|SuitDesignStr|"
    r"CarNumberDesignStr|ClubName|DivisionName|TrackDisplayName|TrackDisplayShortName|"
    r"TrackConfigName|TrackCity|TrackCountry|SeriesName|SessionName|ReasonOutStr|LicString)): (.*)$",
    re.MULTILINE,
)

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _quote(m: re.Match) -> str:
    value = m.group(2).rstrip()
    if value.startswith('"') and value.endswith('"') and len(value) > 1:
        return m.group(0)
    return '%s: "%s"' % (m.group(1), value.replace("\\", "\\\\").replace('"', '\\"'))


def parse_yaml(text: str) -> dict:
    text = text.rstrip("\x00")
    text = _UNSAFE_KEYS.sub(_quote, text)
    data = yaml.load(text, Loader=_Loader)
    return data if isinstance(data, dict) else {}


def _num(v, default=0.0) -> float:
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    m = re.match(r"\s*(-?[\d.]+)", str(v))
    return float(m.group(1)) if m else default


def _color(v) -> int:
    if isinstance(v, int):
        return v & 0xFFFFFF
    try:
        return int(str(v), 16) & 0xFFFFFF
    except ValueError:
        return 0


# Gamintojų žemėlapis: iRacing mašinos kodo (CarPath) dalis -> gamintojas.
# Pildomas faile data/brands.json be programos keitimo.
def _load_brands():
    try:
        with open(os.path.join(_DATA_DIR, "brands.json"), encoding="utf-8") as f:
            data = json.load(f)
        return [(k.lower(), v) for k, v in data["match"].items()]
    except (OSError, ValueError, KeyError):
        return []


_BRANDS = _load_brands()


def brand_for(car_path: str, screen_name: str = "") -> dict:
    key = (car_path or "").lower() + " " + (screen_name or "").lower()
    for needle, brand in _BRANDS:
        if needle in key:
            return brand
    short = (screen_name or car_path or "?")[:3].upper()
    return {"name": screen_name or car_path or "", "short": short, "color": "#808080"}


@dataclass
class Driver:
    idx: int
    name: str
    abbrev: str
    team: str
    number: str
    user_id: int
    class_id: int
    class_name: str
    class_color: int
    class_est_lap: float
    car_path: str
    car_name: str
    brand: dict
    irating: int
    license: str
    is_pace_car: bool
    is_spectator: bool
    country: str = ""  # ISO kodas (iš iRacing Flair)
    country_name: str = ""
    lic_color: int = -1  # iRacing licencijos spalva (RGB)
    car_short: str = ""  # CarScreenNameShort
    team_id: int = 0


@dataclass
class SessionDesc:
    num: int
    type: str  # "race", "qualify", "practice", "warmup"
    name: str
    laps: str
    results: list = field(default_factory=list)  # [{CarIdx, Position, ClassPosition, ...}]


@dataclass
class SessionModel:
    track_name: str = ""
    track_id: int = 0
    track_config: str = ""
    track_length_m: float = 0.0
    sectors: list = field(default_factory=list)  # sektorių pradžios (0..1), iš SplitTimeInfo
    fuel_max_l: float = 0.0  # bako talpa × DriverCarMaxFuelPct (0 = nežinoma)
    league_id: int = 0
    series_id: int = 0
    team_racing: bool = False
    driver_car_idx: int = -1
    drivers: dict = field(default_factory=dict)  # idx -> Driver
    classes: dict = field(default_factory=dict)  # class_id -> {name, color, est_lap}
    sessions: dict = field(default_factory=dict)  # num -> SessionDesc
    update: int = -1
    incident_limit: int = 0  # 0 = neribota / nežinoma
    car_path: str = ""  # mano mašina (asmeniniam rekordui)

    @property
    def multiclass(self) -> bool:
        return len(self.classes) > 1

    @property
    def track_key(self) -> str:
        """Unikalus trasos + konfigūracijos raktas (trasos žemėlapio failui)."""
        cfg = re.sub(r"[^A-Za-z0-9]+", "_", self.track_config or "").strip("_")
        name = re.sub(r"[^A-Za-z0-9]+", "_", self.track_name or "track").strip("_")
        return f"{self.track_id or name}_{cfg}" if cfg else f"{self.track_id or name}"

    def session_type(self, num: int) -> str:
        s = self.sessions.get(num)
        return s.type if s else "practice"


def _session_type(raw: str) -> str:
    r = (raw or "").lower()
    if "race" in r:
        return "race"
    if "qual" in r:
        return "qualify"
    if "warm" in r:
        return "warmup"
    return "practice"


# Numatytos klasių spalvos, kai iRacing jų neduoda (vienos klasės serijose 0)
_DEFAULT_CLASS_COLORS = (0xFFDA59, 0x33CEFF, 0xFF5888, 0xAE6BFF, 0x53FF77, 0xFF9C3A)


def build_model(data: dict, update: int = -1) -> SessionModel:
    m = SessionModel(update=update)
    wi = data.get("WeekendInfo") or {}
    m.track_name = str(wi.get("TrackDisplayName") or wi.get("TrackName") or "")
    length = str(wi.get("TrackLength") or "0 km")
    m.track_length_m = _num(length) * (1609.344 if "mi" in length else 1000.0)
    m.track_id = int(_num(wi.get("TrackID"), 0))
    m.track_config = str(wi.get("TrackConfigName") or "")
    m.league_id = int(_num(wi.get("LeagueID"), 0))
    m.series_id = int(_num(wi.get("SeriesID"), 0))
    m.team_racing = bool(int(_num(wi.get("TeamRacing"), 0)))
    lim = str((wi.get("WeekendOptions") or {}).get("IncidentLimit") or "")
    m.incident_limit = int(_num(lim, 0)) if lim.strip().isdigit() else 0

    sti = data.get("SplitTimeInfo") or {}
    starts = sorted({float(_num(x.get("SectorStartPct"), -1)) for x in (sti.get("Sectors") or [])
                     if isinstance(x, dict)})
    m.sectors = [v for v in starts if 0.0 <= v < 1.0] or [0.0, 1 / 3, 2 / 3]
    if m.sectors[0] != 0.0:
        m.sectors.insert(0, 0.0)

    di = data.get("DriverInfo") or {}
    m.driver_car_idx = int(_num(di.get("DriverCarIdx"), -1))
    tank = _num(di.get("DriverCarFuelMaxLtr"), 0.0)
    m.fuel_max_l = tank * (_num(di.get("DriverCarMaxFuelPct"), 1.0) or 1.0)
    for d in di.get("Drivers") or []:
        try:
            idx = int(d.get("CarIdx"))
        except (TypeError, ValueError):
            continue
        class_id = int(_num(d.get("CarClassID"), 0))
        car_path = str(d.get("CarPath") or "")
        car_name = str(d.get("CarScreenNameShort") or d.get("CarScreenName") or "")
        drv = Driver(
            idx=idx,
            name=str(d.get("UserName") or ""),
            abbrev=str(d.get("AbbrevName") or ""),
            team=str(d.get("TeamName") or ""),
            number=str(d.get("CarNumber") or ""),
            user_id=int(_num(d.get("UserID"), 0)),
            class_id=class_id,
            class_name=str(d.get("CarClassShortName") or ""),
            class_color=_color(d.get("CarClassColor")),
            class_est_lap=_num(d.get("CarClassEstLapTime"), 0.0),
            car_path=car_path,
            car_name=car_name,
            brand=brand_for(car_path, car_name),
            irating=int(_num(d.get("IRating"), 0)),
            license=str(d.get("LicString") or ""),
            is_pace_car=bool(int(_num(d.get("CarIsPaceCar"), 0))),
            is_spectator=bool(int(_num(d.get("IsSpectator"), 0))),
            country=iso_for(d.get("FlairID"), d.get("FlairName") or ""),
            country_name=str(d.get("FlairName") or ""),
            lic_color=_color(d.get("LicColor")) if d.get("LicColor") not in (None, "") else -1,
            car_short=str(d.get("CarScreenNameShort") or car_name or ""),
            team_id=int(_num(d.get("TeamID"), 0)),
        )
        m.drivers[idx] = drv
        if not drv.is_pace_car and not drv.is_spectator and class_id not in m.classes:
            m.classes[class_id] = {
                "name": drv.class_name or car_name,
                "color": drv.class_color,
                "est_lap": drv.class_est_lap,
            }
    # Spalvos, kai iRacing jų neduoda
    for i, (cid, c) in enumerate(sorted(m.classes.items(), key=lambda kv: kv[1]["est_lap"] or 1e9)):
        if not c["color"]:
            c["color"] = _DEFAULT_CLASS_COLORS[i % len(_DEFAULT_CLASS_COLORS)]
    for drv in m.drivers.values():
        if drv.class_id in m.classes:
            drv.class_color = m.classes[drv.class_id]["color"]

    si = data.get("SessionInfo") or {}
    for s in si.get("Sessions") or []:
        num = int(_num(s.get("SessionNum"), 0))
        m.sessions[num] = SessionDesc(
            num=num,
            type=_session_type(str(s.get("SessionType") or "")),
            name=str(s.get("SessionName") or ""),
            laps=str(s.get("SessionLaps") or ""),
            results=list(s.get("ResultsPositions") or []),
        )
    me = m.drivers.get(m.driver_car_idx)
    m.car_path = me.car_path if me else ""
    return m
