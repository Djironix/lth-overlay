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
    "flag": ("Country flag", True),
    "name": ("Name", True),
    "brand": ("Car (manufacturer badge)", True),
    "carname": ("Car model name", False),
    "pit": ("Pit / status", True),
    "gap": ("Gap to leader", True),
    "interval": ("Interval", True),
    "last": ("Last lap", True),
    "best": ("Best lap", True),
    "start": ("Positions since start", False),
    "license": ("License (coloured)", True),
    "irating": ("iRating", True),
    "irchange": ("iRating change (projected)", False),
    "tire": ("Tyres", True),
}

RELATIVE_COLUMNS = {
    "pos": ("Position", True),
    "number": ("Car number", True),
    "flag": ("Country flag", True),
    "name": ("Name", True),
    "brand": ("Car (manufacturer badge)", True),
    "carname": ("Car model name", False),
    "status": ("Pit / status badges", True),
    "license": ("License (coloured)", True),
    "irating": ("iRating", True),
    "irchange": ("iRating change (projected)", False),
    "delta": ("Delta per lap", True),
    "catch": ("Laps to catch", False),
    "gap": ("Gap", True),
}

# Informacija antraštėje / apatinėje juostoje (Standings, Relative)
INFO_ITEMS = {
    "session": ("Time or laps left", True),
    "position": ("My position", True),
    "sof": ("Strength of field", True),
    "lap": ("Lap", False),
    "track_temp": ("Track temperature", False),
    "air_temp": ("Air temperature", False),
    "wetness": ("Track wetness", False),
    "precip": ("Rain", False),
    "clock": ("Time of day (sim)", False),
    "local": ("PC clock", False),
    "incidents": ("My incidents", False),
    "ir_proj": ("My projected iRating change", False),
    "fuel": ("Fuel", False),
    "bias": ("Brake bias", False),
    "last": ("My last lap", False),
    "best": ("My best lap", False),
    "delta": ("Delta to best", False),
    "track": ("Track name", False),
}
FOOTER_ITEMS = {k: (v[0], False) for k, v in INFO_ITEMS.items()}

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
    kind: str  # bool, int, float, percent, choice, columns, checks, items, text
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


CATEGORIES = ("Timing", "Race", "Car", "Track", "Stream", "System")


def _cols(spec):
    return {k: v[1] for k, v in spec.items()}


COMMON_FIELDS = [
    Field("visible", "Show this widget", "bool", False, group="Visibility"),
    Field("hide_in_garage", "Hide while my car is in the garage", "bool", False, group="Visibility"),
    Field("hide_when_spectating", "Hide while spectating / watching", "bool", False, group="Visibility"),
    Field("sessions", "Show in", "checks", None, group="Visibility",
          spec={"practice": ("Practice", True), "qualify": ("Qualifying", True), "warmup": ("Warmup", True),
                "race": ("Race", True)}),
    Field("scale", "Size", "percent", 1.0, 0.5, 3.0, 0.05, group="Look"),
    Field("opacity", "Background opacity", "percent", 1.0, 0.2, 1.0, 0.05, group="Look"),
    Field("outline_mode", "Outline", "choice", "global", group="Look",
          options={"global": "Global", "off": "Off", "custom": "Custom"},
          help="Global = the outline set in Appearance"),
    Field("outline_width", "Outline width", "float", 1.5, 0.5, 6.0, 0.5, suffix=" px", group="Look"),
    Field("outline_color", "Outline colour", "color", "#ECBE58", group="Look"),
    Field("outline_opacity", "Outline opacity", "percent", 0.8, 0.1, 1.0, 0.05, group="Look"),
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
          Field("license_style", "License shows", "choice", "letter",
                options={"letter": "Letter (A)", "full": "Letter + SR (A 4.2)"}),
          Field("density", "Row height", "choice", "normal", group="Look",
                options={"roomy": "Roomy", "normal": "Normal", "compact": "Compact", "ultra": "Ultra"}),
          Field("row_style", "Rows", "choice", "alternate", group="Look",
                options={"alternate": "Alternating", "lines": "Lines", "class": "Class lines", "plain": "Plain"}),
          Field("flag_border", "Flag border", "int", 2, 0, 6, suffix=" px", group="Look",
                help="Coloured border when a flag is out (yellow, blue, white...). 0 = off"),
          Field("columns", "Columns", "columns", None, spec=STANDINGS_COLUMNS, group="Columns"),
          Field("column_header", "Column titles", "bool", False, group="Columns",
                help="Thin row with column names (P, #, DRIVER, GAP...) under the title"),
          Field("header_items", "Header", "items", None, spec=INFO_ITEMS, group="Header & footer",
                help="Shown on the right of the title bar"),
          Field("footer_items", "Footer", "items", None, spec=FOOTER_ITEMS, group="Header & footer",
                help="Bar under the table. Empty = no footer"),
      ]),
    W("relative", "Relative", "Timing", "Cars closest to you on track with gap and closing delta per lap.",
      "lth_overlays.widgets.relative", "RelativeWidget", "relative",
      {"x": -480, "y": -340, "width": 420, "height": None}, visible=True, rate=1, fields=[
          Field("ahead", "Cars ahead", "int", 4, 1, 10, help="Drag the bottom edge to fit more rows"),
          Field("behind", "Cars behind", "int", 4, 1, 10),
          Field("name_mode", "Names", "choice", "abbrev", options=NAME_MODES),
          Field("license_style", "License shows", "choice", "letter",
                options={"letter": "Letter (A)", "full": "Letter + SR (A 4.2)"}),
          Field("density", "Row height", "choice", "normal", group="Look",
                options={"roomy": "Roomy", "normal": "Normal", "compact": "Compact", "ultra": "Ultra"}),
          Field("row_style", "Rows", "choice", "alternate", group="Look",
                options={"alternate": "Alternating", "lines": "Lines", "class": "Class lines", "plain": "Plain"}),
          Field("flag_border", "Flag border", "int", 2, 0, 6, suffix=" px", group="Look",
                help="Coloured border when a flag is out (yellow, blue, white...). 0 = off"),
          Field("columns", "Columns", "columns", None, spec=RELATIVE_COLUMNS, group="Columns"),
          Field("column_header", "Column titles", "bool", False, group="Columns",
                help="Thin row with column names (P, #, DRIVER, GAP...) under the title"),
          Field("header_items", "Header", "items", None, spec=INFO_ITEMS, group="Header & footer",
                help="Shown on the right of the title bar"),
          Field("footer_items", "Footer", "items", None, spec=FOOTER_ITEMS, group="Header & footer",
                help="Bar under the table. Empty = no footer"),
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
    W("lap_timer", "Lap timer", "Timing", "Running lap time with delta, last, best, predicted lap and your "
      "all-time personal best for this car and track (saved on your PC).",
      "lth_overlays.widgets.laps", "LapTimerWidget", "timer",
      {"x": -1, "y": 220, "width": 260, "height": None}, rate=2, fields=[
          Field("show_last", "Last lap", "bool", True),
          Field("show_best", "Best lap (session)", "bool", True),
          Field("show_pb", "Personal best (all time)", "bool", True),
          Field("show_pred", "Predicted lap", "bool", True),
          Field("smooth", "Smooth running time", "bool", True),
          Field("smooth_hz", "Smooth rate", "choice", 30, options={30: "30 fps", 60: "60 fps"}),
      ]),
    W("sectors", "Sectors", "Timing", "Your sector times this lap against your best sectors: purple = new best, "
      "green = close, yellow / red = time lost.",
      "lth_overlays.widgets.laps", "SectorsWidget", "list",
      {"x": -1, "y": 340, "width": 360, "height": None}, rate=2, fields=[
          Field("show_optimal", "Optimal lap in the header", "bool", True),
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
    W("overtake_alert", "Overtake alert", "Race", "Multiclass: a faster class closing from behind, or a slower "
      "class car just ahead. Hidden when there is nothing to report.",
      "lth_overlays.widgets.alerts", "OvertakeAlertWidget", "alert",
      {"x": -1, "y": -470, "width": 340, "height": None}, rate=1, has_header=False, fields=[
          Field("range_behind", "Warn when behind within", "float", 3.0, 1.0, 8.0, 0.5, suffix=" s"),
          Field("slower_ahead", "Slower class ahead", "bool", True),
          Field("range_ahead", "Slower car ahead within", "float", 2.0, 0.5, 6.0, 0.5, suffix=" s"),
          Field("same_class_lapping", "Also leaders lapping me (same class)", "bool", False),
          Field("max_cars", "Cars shown", "int", 2, 1, 4),
      ]),
    W("rejoin", "Rejoin indicator", "Race", "After an off or a spin: who is coming from behind and whether it is "
      "safe to rejoin.", "lth_overlays.widgets.alerts", "RejoinWidget", "route",
      {"x": -1, "y": -560, "width": 300, "height": None}, rate=1, has_header=False, fields=[
          Field("wait_s", "WAIT when a car is closer than", "float", 2.0, 0.5, 5.0, 0.5, suffix=" s"),
          Field("clear_s", "CLEAR when the gap is over", "float", 4.0, 1.0, 10.0, 0.5, suffix=" s"),
          Field("slow_kmh", "Also show when slower than", "int", 40, 10, 100, suffix=" km/h",
                help="On track, not on pit road"),
      ]),
    W("pit_helper", "Pit helper", "Race", "Pit service selection, repairs, limiter warning on pit road.",
      "lth_overlays.widgets.race", "PitHelperWidget", "wrench",
      {"x": -1, "y": -560, "width": 300, "height": None}, rate=2, fields=[
          Field("always", "Show outside the pit lane too", "bool", False),
      ]),
    W("pit_commands", "Pit commands", "Race", "Buttons to set your pit stop with the mouse, no black box: "
      "all tyres, fuel to finish, full tank, fast repair, windscreen.", "lth_overlays.widgets.race",
      "PitCommandsWidget", "wrench", {"x": -320, "y": 560, "width": 300, "height": None}, rate=2, fields=[]),
    W("pit_strategy", "Pit window", "Race", "Measured pit loss on this track and where you would rejoin "
      "if you pitted now.", "lth_overlays.widgets.race", "PitStrategyWidget", "route",
      {"x": -300, "y": 440, "width": 270, "height": None}, rate=5, fields=[
          Field("service", "Planned service time", "float", 30.0, 0.0, 120.0, 1.0, suffix=" s",
                help="Fuel + tyres stationary time for the prediction"),
      ]),
    W("incidents", "Incidents", "Race", "Your incident count with a popup when it changes.",
      "lth_overlays.widgets.race", "IncidentsWidget", "alert",
      {"x": 540, "y": 24, "width": 180, "height": None}, rate=2, fields=[
          Field("limit", "Incident limit", "int", 0, 0, 200, help="0 = take it from the session (shown when the race has one)"),
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
    W("inputs", "Inputs", "Car", "Throttle, brake, clutch and steering trace, pedal percentages and a "
      "steering wheel with gear and speed.", "lth_overlays.widgets.car",
      "InputsWidget", "pedals", {"x": -760, "y": -170, "width": 420, "height": 110}, rate=1, needs_inputs=True,
      has_header=False, fields=[
          Field("seconds", "Trace length", "float", 4.0, 2.0, 6.0, 0.5, suffix=" s"),
          Field("show_clutch", "Clutch", "bool", False),
          Field("show_steering", "Steering", "bool", True),
          Field("show_bars", "Pedal bars", "bool", True),
          Field("show_percent", "Pedal percentages", "bool", True),
          Field("show_wheel", "Steering wheel with gear", "bool", True),
          Field("show_speed", "Speed in the wheel", "bool", True),
          Field("unit", "Speed unit", "choice", "kmh", options={"kmh": "km/h", "mph": "mph"}),
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
          Field("smooth", "Smooth (up to 60 fps)", "bool", True,
                help="Cars move every telemetry frame. The track itself is drawn once."),
          Field("smooth_hz", "Smooth rate", "choice", 30, options={30: "30 fps", 60: "60 fps", 120: "120 fps"}),
      ]),
    W("flat_map", "Flat track map", "Track", "The lap as a straight line with every car on it. Works without "
      "a recorded track outline.", "lth_overlays.widgets.track", "FlatMapWidget", "route",
      {"x": -1, "y": -80, "width": 520, "height": None}, rate=2, has_header=False, fields=[
          Field("center_me", "Keep me in the middle", "bool", False),
          Field("dot", "Car size", "float", 1.0, 0.5, 2.5, 0.1, suffix="×"),
          Field("numbers", "Car numbers", "bool", False),
          Field("smooth", "Smooth (up to 60 fps)", "bool", True),
          Field("smooth_hz", "Smooth rate", "choice", 30, options={30: "30 fps", 60: "60 fps", 120: "120 fps"}),
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
    # ------------------------------------------------------------- Stream
    W("garage_cover", "Garage cover", "Stream", "Covers part of the screen while you are in the garage, "
      "so your setup is not on stream.", "lth_overlays.widgets.cover", "GarageCoverWidget", "eye_off",
      {"x": -1, "y": -1, "width": 900, "height": 520}, rate=5, has_header=False, fields=[
          Field("logo", "LTH logo", "bool", True),
          Field("text", "Text", "text", "Back on track soon"),
          Field("color", "Background", "color", "#0B0C10"),
          Field("image", "Image file (optional)", "text", "", help="Full path to a PNG or JPG. Fills the cover."),
      ]),
    W("chat", "Stream chat", "Stream", "Your Twitch and YouTube chat on screen and in OBS. "
      "Read-only, no login needed.",
      "lth_overlays.widgets.chat", "ChatWidget", "chat",
      {"x": 24, "y": -360, "width": 340, "height": 300}, rate=2, fields=[
          Field("twitch", "Twitch channel", "text", "", help="Channel name or link, e.g. twitch.tv/lthracing"),
          Field("youtube", "YouTube", "text", "",
                help="Live video link, or your channel (@handle) to follow whatever is live. "
                     "Uses YouTube's web chat, which may change without notice."),
          Field("max_messages", "Messages kept", "int", 30, 5, 100),
          Field("fade", "Hide messages after", "int", 0, 0, 300, suffix=" s", help="0 = keep them"),
          Field("show_platform", "Show Twitch / YouTube badge", "bool", True, group="Look"),
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
        elif f.kind == "items":  # įjungti + tvarka
            d[f.key] = _cols(f.spec)
            d[f.key + "_order"] = list(f.spec)
        else:
            d[f.key] = copy.deepcopy(f.default)
    d["visible"] = spec.visible
    return d


DEFAULT_WIDGETS = {w.name: defaults_for(w) for w in WIDGETS}
