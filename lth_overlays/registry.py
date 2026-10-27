"""Visų valdiklių registras: vienas tiesos šaltinis.

Kiekvienas valdiklis aprašomas WidgetSpec: pavadinimas, kategorija, aprašymas,
numatyta vieta ir dydis, ir nustatymų laukai (Field). Iš to generuojami:
- numatyti nustatymai (config.DEFAULT_WIDGETS),
- Control Center nustatymų formos (be rankinio UI kodo kiekvienam valdikliui).

Naujas valdiklis = klasė widgets/ aplanke + vienas WidgetSpec čia.
"""
from __future__ import annotations

import copy
import importlib
from dataclasses import dataclass, field

# ---------------------------------------------------------------- stulpeliai
STANDINGS_COLUMNS = {
    "pos": ("Position", True),
    "change": ("Change this lap", True),
    "number": ("Car number", True),
    "brand": ("Manufacturer", True),
    "name": ("Name", True),
    "gap": ("Gap to leader", True),
    "interval": ("Interval", True),
    "last": ("Last lap", True),
    "best": ("Best lap", True),
    "start": ("Positions since start", False),
    "irating": ("iRating", True),
    "license": ("License", False),
    "pit": ("Pit", True),
    "tire": ("Tyres", True),
}

RELATIVE_COLUMNS = {
    "pos": ("Position", True),
    "number": ("Car number", True),
    "name": ("Name", True),
    "irating": ("iRating", True),
    "license": ("License", True),
    "delta": ("Delta per lap", True),
    "catch": ("Laps to catch", True),
    "gap": ("Gap", True),
}

WEATHER_FIELDS = {
    "wetness": ("Track wetness", True),
    "track_temp": ("Track temperature", True),
    "air_temp": ("Air temperature", True),
    "precip": ("Rain", True),
    "skies": ("Sky", True),
    "wind": ("Wind", True),
    "humidity": ("Humidity", False),
    "fog": ("Fog", False),
    "time": ("Time of day", True),
    "trend": ("Trend", True),
}

ENGINEER_TYPES = {
    "ahead": ("Car ahead (once per lap)", True),
    "behind": ("Car behind closing", True),
    "slow_car": ("Slow car ahead", True),
    "weather": ("Track getting wetter / drying", True),
    "best_lap": ("Personal best lap", True),
    "time": ("5 minutes / last lap", True),
    "faster_class": ("Faster class from behind", True),
}

NAME_MODES = {"abbrev": "J. Smith", "full": "John Smith", "last": "Smith", "three": "SMI"}


# ---------------------------------------------------------------- aprašai
@dataclass
class Field:
    key: str
    label: str
    kind: str  # bool, int, float, percent, choice, columns, checks, text
    default: object = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: dict | None = None  # choice: {reikšmė: pavadinimas}
    spec: dict | None = None  # columns / checks: {raktas: (pavadinimas, numatyta)}
    group: str = "Content"
    help: str = ""
    suffix: str = ""


@dataclass
class WidgetSpec:
    name: str
    title: str
    category: str
    description: str
    module: str
    cls: str
    icon: str
    geometry: dict  # x, y, width, height (height None = pagal turinį)
    visible: bool = False
    fields: list = field(default_factory=list)
    rate: int = 2  # UI atnaujinimas kas N × 0,1 s
    needs_inputs: bool = False  # reikia 60 Hz input'ų buferio
    has_header: bool = True

    def load(self):
        return getattr(importlib.import_module(self.module), self.cls)


CATEGORIES = ("Timing", "Race", "Car", "Track", "System")


def _cols(spec):
    return {k: v[1] for k, v in spec.items()}


COMMON_FIELDS = [
    Field("visible", "Show this widget", "bool", False, group="Visibility"),
    Field("hide_in_garage", "Hide while my car is in the garage", "bool", False, group="Visibility"),
    Field("hide_when_spectating", "Hide while spectating / watching", "bool", False, group="Visibility"),
    Field("race_only", "Only in race sessions", "bool", False, group="Visibility"),
    Field("scale", "Size", "percent", 1.0, 0.5, 3.0, 0.05, group="Look"),
    Field("opacity", "Background opacity", "percent", 1.0, 0.2, 1.0, 0.05, group="Look"),
]
HEADER_FIELD = Field("show_header", "Show header", "bool", True, group="Look")

W = WidgetSpec
WIDGETS: list[WidgetSpec] = [
    # ------------------------------------------------------------- Timing
    W("standings", "Standings", "Timing", "Whole field by position with gaps, intervals, lap times, pit info. "
      "Multiclass: your class in full, other classes top 3.",
      "lth_overlays.widgets.standings", "StandingsWidget", "list",
      {"x": 24, "y": 180, "width": 500, "height": None}, visible=True, rate=5, fields=[
          Field("class_mode", "Multiclass layout", "choice", "grouped",
                options={"grouped": "Grouped by class", "overall": "Overall", "mine": "My class only"}),
          Field("filter", "My class shows", "choice", "all",
                options={"all": "Everyone", "top_around": "Top N + around me", "around": "Around me only"}),
          Field("top_n", "Top N (my class)", "int", 3, 0, 20),
          Field("around_n", "Around me ±", "int", 5, 1, 20),
          Field("other_classes_n", "Other classes: top", "int", 3, 0, 20,
                help="0 hides other classes"),
          Field("max_rows", "Max rows (when height is automatic)", "int", 26, 5, 72),
          Field("name_mode", "Names", "choice", "abbrev", options=NAME_MODES),
          Field("columns", "Columns", "columns", None, spec=STANDINGS_COLUMNS, group="Columns"),
      ]),
    W("relative", "Relative", "Timing", "Cars closest to you on track with gap and closing delta per lap.",
      "lth_overlays.widgets.relative", "RelativeWidget", "relative",
      {"x": -500, "y": -340, "width": 420, "height": None}, visible=True, rate=1, fields=[
          Field("ahead", "Cars ahead", "int", 4, 1, 10, help="Drag the bottom edge to fit more rows"),
          Field("behind", "Cars behind", "int", 4, 1, 10),
          Field("name_mode", "Names", "choice", "abbrev", options=NAME_MODES),
          Field("columns", "Columns", "columns", None, spec=RELATIVE_COLUMNS, group="Columns"),
      ]),
    W("battle", "Battle analysis", "Timing", "Where you gain and lose against the cars just ahead and behind, "
      "sector by sector on the last lap.", "lth_overlays.widgets.timing", "BattleWidget", "swords",
      {"x": -500, "y": -520, "width": 420, "height": None}, rate=5, fields=[
          Field("show_ahead", "Car ahead", "bool", True),
          Field("show_behind", "Car behind", "bool", True),
          Field("show_times", "Show sector times", "bool", False),
      ]),
    W("lap_history", "Lap history", "Timing", "Your last laps, best, stint average and consistency.",
      "lth_overlays.widgets.timing", "LapHistoryWidget", "history",
      {"x": 24, "y": -360, "width": 300, "height": None}, rate=5, fields=[
          Field("rows", "Laps shown", "int", 8, 3, 15, help="Drag the bottom edge to fit more"),
          Field("show_fuel", "Fuel per lap", "bool", True),
      ]),
    W("delta_bar", "Delta bar", "Timing", "Live delta to your best, optimal or session best lap.",
      "lth_overlays.widgets.timing", "DeltaBarWidget", "delta",
      {"x": -1, "y": 150, "width": 420, "height": 58}, rate=1, has_header=False, fields=[
          Field("reference", "Compare to", "choice", "best",
                options={"best": "My best lap", "optimal": "My optimal lap", "session_best": "Session best",
                         "session_last": "My last lap"}),
          Field("range", "Bar range", "float", 2.0, 0.5, 5.0, 0.5, suffix=" s"),
          Field("show_lap_time", "Current lap time", "bool", True),
          Field("smooth", "Smooth (up to 60 fps)", "bool", False,
                help="Reads telemetry directly, independent of the other widgets. Costs a little more CPU."),
          Field("smooth_hz", "Smooth rate", "choice", 60, options={30: "30 fps", 60: "60 fps", 120: "120 fps"}),
      ]),
    W("session", "Session", "Timing", "Session, time or laps left, position, strength of field.",
      "lth_overlays.widgets.timing", "SessionWidget", "clock",
      {"x": -300, "y": 280, "width": 270, "height": None}, rate=5, fields=[
          Field("show_track", "Track name", "bool", True),
          Field("show_position", "My position", "bool", True),
          Field("show_sof", "Strength of field", "bool", True),
          Field("show_clock", "Time of day", "bool", True),
      ]),
    # ------------------------------------------------------------- Race
    W("engineer", "Race engineer", "Race", "Short spoken-style messages on straights: gaps, closing cars, "
      "weather changes, personal bests.", "lth_overlays.widgets.engineer", "EngineerWidget", "headset",
      {"x": -1, "y": 90, "width": 560, "height": None}, rate=2, has_header=False, fields=[
          Field("types", "Messages", "checks", None, spec=ENGINEER_TYPES),
      ]),
    W("flags", "Flags", "Race", "Big flag banner: yellow, blue, black, white, chequered, meatball.",
      "lth_overlays.widgets.race", "FlagsWidget", "flag",
      {"x": -1, "y": 230, "width": 380, "height": None}, rate=1, has_header=False, fields=[
          Field("show_green", "Show green flag at start", "bool", False),
          Field("hold", "Keep short flags for", "float", 4.0, 1.0, 15.0, 1.0, suffix=" s"),
          Field("blue_outside_race", "Blue flag in practice / qualifying", "bool", False,
                help="In races blue only shows when a car lapping you is really close behind"),
      ]),
    W("radar", "Radar", "Race", "Cars alongside and close behind / ahead, in metres.",
      "lth_overlays.widgets.race", "RadarWidget", "radar",
      {"x": -1, "y": -380, "width": 150, "height": 190}, rate=1, has_header=False, fields=[
          Field("range", "Range", "int", 20, 8, 50, suffix=" m"),
          Field("always", "Show when nobody is close", "bool", False),
      ]),
    W("pit_helper", "Pit helper", "Race", "Pit service selection, repairs, limiter warning on pit road.",
      "lth_overlays.widgets.race", "PitHelperWidget", "wrench",
      {"x": -1, "y": -560, "width": 300, "height": None}, rate=2, fields=[
          Field("always", "Show outside the pit lane too", "bool", False),
      ]),
    W("pit_strategy", "Pit window", "Race", "Measured pit loss on this track and where you would rejoin "
      "if you pitted now.", "lth_overlays.widgets.race", "PitStrategyWidget", "route",
      {"x": -300, "y": 440, "width": 270, "height": None}, rate=5, fields=[
          Field("service", "Planned service time", "float", 30.0, 0.0, 120.0, 1.0, suffix=" s",
                help="Fuel + tyres stationary time for the prediction"),
      ]),
    W("incidents", "Incidents", "Race", "Your incident count with a popup when it changes.",
      "lth_overlays.widgets.race", "IncidentsWidget", "alert",
      {"x": 540, "y": 24, "width": 180, "height": None}, rate=2, fields=[
          Field("limit", "Incident limit (0 = none)", "int", 0, 0, 200),
          Field("popup", "Popup time", "float", 5.0, 1.0, 15.0, 1.0, suffix=" s"),
      ]),
    W("stint", "Stint", "Race", "Stint time and laps, driver changes for team races.",
      "lth_overlays.widgets.race", "StintWidget", "timer",
      {"x": 540, "y": 120, "width": 200, "height": None}, rate=5, fields=[
          Field("show_drivers", "Driver change status", "bool", True),
      ]),
    W("formation", "Formation", "Race", "Your grid row and line during pace laps.",
      "lth_overlays.widgets.race", "FormationWidget", "grid",
      {"x": -1, "y": 300, "width": 260, "height": None}, rate=2, fields=[]),
    W("radio", "Radio", "Race", "Who is talking on the radio.", "lth_overlays.widgets.race", "RadioWidget", "mic",
      {"x": 24, "y": 120, "width": 260, "height": None}, rate=1, has_header=False, fields=[]),
    # ------------------------------------------------------------- Car
    W("fuel", "Fuel", "Car", "Fuel per lap, laps left, fuel to the finish and how much to add.",
      "lth_overlays.widgets.car", "FuelWidget", "fuel",
      {"x": 540, "y": -260, "width": 260, "height": None}, rate=5, fields=[
          Field("margin", "Safety margin", "float", 0.5, 0.0, 3.0, 0.1, suffix=" laps"),
          Field("unit", "Unit", "choice", "l", options={"l": "Litres", "gal": "Gallons"}),
      ]),
    W("dash", "Dash", "Car", "Gear, speed and RPM bar with shift light.", "lth_overlays.widgets.car", "DashWidget",
      "gauge", {"x": -1, "y": -170, "width": 260, "height": None}, rate=1, has_header=False, fields=[
          Field("unit", "Speed unit", "choice", "kmh", options={"kmh": "km/h", "mph": "mph"}),
          Field("shift_pct", "Shift light at", "percent", 0.94, 0.7, 1.0, 0.01),
          Field("smooth", "Smooth (up to 60 fps)", "bool", True,
                help="Reads telemetry directly, independent of the other widgets. Costs a little more CPU."),
          Field("smooth_hz", "Smooth rate", "choice", 30, options={30: "30 fps", 60: "60 fps", 120: "120 fps"}),
      ]),
    W("inputs", "Inputs", "Car", "Throttle, brake, clutch and steering trace.", "lth_overlays.widgets.car",
      "InputsWidget", "pedals", {"x": -720, "y": -170, "width": 360, "height": 110}, rate=1, needs_inputs=True,
      has_header=False, fields=[
          Field("seconds", "Trace length", "float", 4.0, 2.0, 6.0, 0.5, suffix=" s"),
          Field("show_clutch", "Clutch", "bool", False),
          Field("show_steering", "Steering", "bool", True),
          Field("show_bars", "Pedal bars", "bool", True),
          Field("smooth", "Smooth (up to 60 fps)", "bool", True,
                help="Reads telemetry directly, independent of the other widgets. Costs a little more CPU."),
          Field("smooth_hz", "Smooth rate", "choice", 60, options={30: "30 fps", 60: "60 fps", 120: "120 fps"}),
      ]),
    W("gforce", "G-force", "Car", "Lateral and longitudinal g with a short trail.", "lth_overlays.widgets.car",
      "GForceWidget", "target", {"x": -900, "y": -200, "width": 140, "height": 140}, rate=1,
      has_header=False, fields=[
          Field("max_g", "Scale", "float", 3.0, 1.5, 5.0, 0.5, suffix=" g"),
          Field("trail", "Trail", "bool", True),
      ]),
    W("tyres", "Tyres", "Car", "Tyre temperatures (inner / middle / outer), wear and pressures. "
      "iRacing updates these in the pits.", "lth_overlays.widgets.car", "TyresWidget", "tyre",
      {"x": 540, "y": -460, "width": 240, "height": None}, rate=10, fields=[
          Field("show_wear", "Wear", "bool", True),
          Field("show_pressure", "Cold pressure", "bool", False),
      ]),
    W("car_settings", "Car setting changes", "Car", "Popup when you change brake bias, TC, ABS and other "
      "in-car settings.", "lth_overlays.widgets.car", "CarSettingsWidget", "sliders",
      {"x": -1, "y": 380, "width": 300, "height": None}, rate=1, has_header=False, fields=[
          Field("hold", "Popup time", "float", 3.0, 1.0, 8.0, 0.5, suffix=" s"),
      ]),
    W("engine_warn", "Engine warnings", "Car", "Shows only when something is wrong: water / oil temperature, "
      "oil or fuel pressure, stalled engine.", "lth_overlays.widgets.car", "EngineWarningsWidget", "engine",
      {"x": -1, "y": 460, "width": 300, "height": None}, rate=5, has_header=False, fields=[
          Field("always", "Always show temperatures", "bool", False),
      ]),
    # ------------------------------------------------------------- Track
    W("track_map", "Track map", "Track", "All cars on the track outline. The outline is recorded from your "
      "first clean lap and saved for next time.", "lth_overlays.widgets.track", "TrackMapWidget", "map",
      {"x": -300, "y": -640, "width": 260, "height": 260}, rate=2, fields=[
          Field("dot", "Car size", "float", 1.0, 0.5, 2.5, 0.1, suffix="×"),
          Field("numbers", "Car numbers", "bool", False),
          Field("mirror", "Mirror", "bool", False),
          Field("rotate", "Rotate", "choice", "0", options={"0": "0°", "90": "90°", "180": "180°", "270": "270°"}),
      ]),
    W("weather", "Weather", "Track", "Track wetness with trend, temperatures, rain, wind relative to your car.",
      "lth_overlays.widgets.weather", "WeatherWidget", "cloud",
      {"x": -300, "y": 24, "width": 270, "height": None}, visible=True, rate=10, fields=[
          Field("mode", "Mode", "choice", "expanded", options={"expanded": "Expanded", "compact": "Compact"}),
          Field("only_when_wet", "Only when the track is not dry", "bool", False),
          Field("rain_calls", "Rain calls above the widget", "bool", True,
                help="Short calls like WET TYRES or HIDDEN WATER when conditions change"),
          Field("fields", "Fields", "checks", None, spec=WEATHER_FIELDS),
      ]),
    W("rain_master", "Rain Master", "Track", "Rain tips while you drive: the current call with a short "
      "explanation, and the full list for these conditions when you stop. Tips by Regis / LTH Racing.",
      "lth_overlays.widgets.rain", "RainMasterWidget", "cloud",
      {"x": -340, "y": 300, "width": 320, "height": None}, rate=5, fields=[
          Field("mode", "Mode", "choice", "auto",
                options={"auto": "Expand when stopped", "compact": "Always compact", "expanded": "Always expanded"}),
          Field("track_tips", "Track-specific tips (may change by season)", "bool", True),
          Field("max_tips", "Tips when expanded", "int", 6, 3, 14),
      ]),
    # ------------------------------------------------------------- System
    W("connection", "Connection", "System", "Warns about bad connection quality before you start warping.",
      "lth_overlays.widgets.race", "ConnectionWidget", "wifi",
      {"x": 24, "y": 24, "width": 220, "height": None}, rate=5, has_header=False, fields=[
          Field("threshold", "Warn below quality", "percent", 0.9, 0.5, 1.0, 0.01),
          Field("always", "Always show", "bool", False),
      ]),
    W("perf", "Performance", "System", "LTH Overlays' own CPU and RAM use and iRacing FPS.",
      "lth_overlays.widgets.engineer", "PerfWidget", "cpu",
      {"x": 24, "y": 70, "width": 230, "height": None}, rate=10, has_header=False, fields=[]),
]

BY_NAME = {w.name: w for w in WIDGETS}


def fields_for(spec: WidgetSpec) -> list:
    out = list(COMMON_FIELDS)
    if spec.has_header:
        out.append(HEADER_FIELD)
    return out + list(spec.fields)


def defaults_for(spec: WidgetSpec) -> dict:
    d = dict(copy.deepcopy(spec.geometry))
    for f in fields_for(spec):
        if f.kind == "columns":
            d["columns"] = _cols(f.spec)
            d["order"] = list(f.spec)
        elif f.kind == "checks":
            d[f.key] = _cols(f.spec)
        else:
            d[f.key] = copy.deepcopy(f.default)
    d["visible"] = spec.visible
    return d


DEFAULT_WIDGETS = {w.name: defaults_for(w) for w in WIDGETS}
