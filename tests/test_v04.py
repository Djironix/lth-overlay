"""v0.4 testai: valdiklių registras, standings klasės / aukštis, žaidėjo duomenys,
config migracija, visų valdiklių piešimas ir Control Center (offscreen)."""
import json
import math
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from lth_timing.engine import TimingEngine  # noqa: E402
from lth_timing.sim import SimRace  # noqa: E402


# ---------------------------------------------------------------- pagalbininkai
@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def race_snap():
    sim = SimRace(n_cars=28, multiclass=True, max_cars=12, rain=True, events=True, record=False)
    eng = TimingEngine()
    eng.player.inputs_enabled = True
    eng.set_session(sim.model)
    for _ in range(60 * 240):
        eng.update(sim.step())
    return eng.snapshot()


@pytest.fixture()
def oapp(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from PySide6.QtCore import QRect
    from lth_overlays.app import OverlayApp
    from lth_overlays.config import Config
    from lth_overlays.sources import DemoSource
    cfg = Config(str(tmp_path / "config.json"))
    app = OverlayApp(qapp, DemoSource, cfg, virtual_screen=QRect(0, 0, 1920, 1080))
    yield app
    for w in app.widgets.values():
        w.close()
    if app.control is not None:
        app.control.deleteLater()


# ---------------------------------------------------------------- registras / config
def test_registry_specs_load_and_defaults():
    from lth_overlays.registry import WIDGETS, CATEGORIES, defaults_for, fields_for
    names = [w.name for w in WIDGETS]
    assert len(names) == len(set(names))
    for spec in WIDGETS:
        cls = spec.load()
        assert cls.NAME == spec.name, spec.name
        assert spec.category in CATEGORIES
        d = defaults_for(spec)
        assert {"x", "y", "width", "visible", "scale", "opacity"} <= set(d)
        for f in fields_for(spec):
            if f.kind in ("int", "float", "percent"):
                assert f.min <= f.default <= f.max, (spec.name, f.key)
            if f.kind == "choice":
                assert f.default in f.options, (spec.name, f.key)


def test_config_migration_v4_keeps_layout_and_adds_widgets(tmp_path):
    from lth_overlays.config import CONFIG_VERSION, Config
    old = {"version": 4, "theme": "lth", "profile": "race",
           "profiles": {"race": {"name": "Race", "widgets": {
               "standings": {"x": 100, "y": 200, "width": 480, "scale": 1.2, "visible": True,
                             "columns": {"pos": True}, "order": ["pos"]}}}}}
    p = tmp_path / "config.json"
    p.write_text(json.dumps(old), encoding="utf-8")
    cfg = Config(str(p))
    assert cfg.data["version"] == CONFIG_VERSION
    st = cfg.widget("standings")
    assert (st["x"], st["y"], st["width"], st["scale"]) == (100, 200, 480, 1.2)  # v4 plotis jau be mastelio
    assert st["other_classes_n"] == 3  # naujas laukas
    assert "irating" in st["columns"]  # nauji stulpeliai atsiranda
    assert cfg.widget("track_map")["visible"] is False  # nauji valdikliai - išjungti
    assert cfg.data["hotkeys"]["toggle_all"]


def test_profiles_add_delete():
    from lth_overlays.config import Config
    cfg = Config(os.devnull + "_nonexistent.json")
    cfg.add_profile("endurance", "Endurance")
    cfg.set_profile("endurance")
    cfg.widget("fuel")["visible"] = True
    assert cfg.data["profiles"]["race"]["widgets"]["fuel"]["visible"] is False
    with pytest.raises(ValueError):
        cfg.delete_profile("race")
    cfg.delete_profile("endurance")
    assert cfg.profile_key == "race"


def test_parse_hotkey():
    from lth_overlays import win32
    assert win32.parse_hotkey("Ctrl+Shift+E") == (win32.MOD_CONTROL | win32.MOD_SHIFT, ord("E"))
    assert win32.parse_hotkey("Alt+F5") == (win32.MOD_ALT, 0x74)
    assert win32.parse_hotkey("E") is None  # be modifikatoriaus - ne
    assert win32.parse_hotkey("Ctrl+Shift+Banana") is None
    assert win32.parse_hotkey("") is None


# ---------------------------------------------------------------- variklio priedai
def test_player_state_fuel_laps_tyres(race_snap):
    p = race_snap.player
    assert p.valid
    assert p.fuel_per_lap and 1.0 < p.fuel_per_lap < 5.0
    assert p.fuel_laps_left > 0
    assert p.fuel_to_finish is not None and p.race_laps_left > 0
    assert len(p.laps) >= 1 and all(x.time > 0 for x in p.laps)
    assert set(p.tyres) == {"LF", "RF", "LR", "RR"}
    assert p.inputs and len(p.inputs["throttle"]) > 60
    assert p.deltas.get("best") is not None


def test_sof_formula():
    from lth_timing.engine import TimingEngine as E

    class R:
        def __init__(self, ir, cid):
            self.irating, self.class_id = ir, cid
    rows = [R(2000, 1)] * 10
    sof = E._sof(rows)
    assert sof[1] == 2000 and sof[0] == 2000
    mixed = E._sof([R(1000, 1), R(3000, 1)])
    assert 1000 < mixed[1] < 3000


def test_battle_and_sectors(race_snap):
    assert len(race_snap.sectors) == 3
    for b in race_snap.battle:
        assert b["side"] in ("ahead", "behind")
        assert len(b["diff"]) == 3


def test_trackmap_records_and_saves(tmp_path):
    sim = SimRace(n_cars=6, multiclass=False, record=False)
    eng = TimingEngine(maps_dir=str(tmp_path))
    eng.set_session(sim.model)
    for _ in range(60 * 300):
        eng.update(sim.step())
        if eng.trackmap.points is not None:
            break
    pts = eng.trackmap.points
    assert pts is not None and pts.shape == (400, 2)
    assert np.all((pts >= -1e-6) & (pts <= 1 + 1e-6))
    # uždaras kontūras
    assert np.linalg.norm(pts[0] - pts[-1]) < 0.05
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    # užkraunamas iš failo
    eng2 = TimingEngine(maps_dir=str(tmp_path))
    eng2.set_session(sim.model)
    assert eng2.trackmap.points is not None


# ---------------------------------------------------------------- standings
def _car_rows(w):
    return [m for m in w._meta if m[0] == "car"]


def test_standings_other_classes_top3_my_class_full(oapp, race_snap):
    w = oapp.widgets["standings"]
    c = w.cfg
    c.update(class_mode="grouped", filter="all", other_classes_n=3, height=None, max_rows=72)
    w.apply_settings()
    w.push(race_snap, force=True)
    me = next(r for r in race_snap.cars if r.is_me)
    n_mine = sum(1 for r in race_snap.cars if r.class_id == me.class_id)
    mine = [m for m in _car_rows(w) if m[2]]
    assert len(mine) == n_mine
    for cid in {r.class_id for r in race_snap.cars if r.class_id != me.class_id}:
        assert len([m for m in _car_rows(w) if m[1] == cid]) <= 3
    # 0 = kitos klasės paslėptos
    c["other_classes_n"] = 0
    w.push(race_snap, force=True)
    assert all(m[2] for m in _car_rows(w))


def test_standings_height_fits_rows_and_keeps_me(oapp, race_snap):
    w = oapp.widgets["standings"]
    c = w.cfg
    c.update(class_mode="grouped", filter="all", other_classes_n=3, height=None)
    w.apply_settings()
    w.push(race_snap, force=True)
    full = len(w._meta)
    c["height"] = 300  # rankinis aukštis -> mažiau eilučių
    w.apply_settings()
    w.push(race_snap, force=True)
    assert w.height() >= 300 * w._scale() - 1
    assert len(w._meta) < full
    assert any(m[3] for m in w._meta), "my row must stay"
    used = w.header_h() + sum(w._row_units(m[0]) for m in w._meta) * w.row_h()
    assert used <= w.height() + 1


# ---------------------------------------------------------------- visi valdikliai
def test_every_widget_paints(oapp, race_snap):
    from lth_overlays.registry import WIDGETS
    for spec in WIDGETS:
        w = oapp.widgets[spec.name]
        for editing in (False, True):
            w.editing = editing
            w.push(race_snap, force=True)
            h = w.final_height()
            assert 8 <= h < 3000, spec.name
            w.resize(w.width(), h)
            img = w.grab()
            assert not img.isNull(), spec.name
        w.editing = False
        # tuščia būsena (be iRacing) neturi lūžti
        from lth_timing.engine import Snapshot
        w.push(Snapshot(), force=True)
        w.grab()


def test_widgets_follow_settings_changes(oapp, race_snap):
    from lth_overlays.registry import WIDGETS, fields_for
    for spec in WIDGETS:
        w = oapp.widgets[spec.name]
        for f in fields_for(spec):
            if f.kind == "bool":
                w.cfg[f.key] = not f.default
            elif f.kind == "choice":
                w.cfg[f.key] = list(f.options)[-1]
            elif f.kind in ("int", "float", "percent"):
                w.cfg[f.key] = f.max
        w.cfg["visible"] = True
        w.apply_settings()
        w.push(race_snap, force=True)
        w.grab()


# ---------------------------------------------------------------- Control Center
def test_control_center_pages_and_forms(oapp, qapp):
    oapp.preview_snapshot(wait=True)
    oapp.open_control_center()
    cc = oapp.control
    from lth_overlays.control.center import PAGES
    for key in PAGES:
        cc.go(key)
        qapp.processEvents()
        cc.tick(oapp.engine.latest)
    from lth_overlays.registry import WIDGETS
    for spec in WIDGETS:
        cc.open_widget(spec.name)
        qapp.processEvents()
    cc.close()  # paslepia, programa lieka
    assert not cc.isVisible()


def test_form_changes_apply_to_overlay(oapp, qapp):
    oapp.preview_snapshot(wait=True)
    oapp.open_control_center()
    cc = oapp.control
    cc.open_widget("relative")
    page = cc._widget_pages["relative"]
    form = page.form
    form._controls["scale"].changed.emit(1.5)
    assert oapp.config.widget("relative")["scale"] == 1.5
    w = oapp.widgets["relative"]
    assert abs(w.fonts.scale - 1.5) < 1e-9
    form.fx.setValue(333)
    assert oapp.config.widget("relative")["x"] == 333
    assert w.x() == 333


def test_layout_canvas_drag_moves_widget(oapp, qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    oapp.preview_snapshot(wait=True)
    oapp.open_control_center()
    cc = oapp.control
    cc.resize(1400, 900)
    cc.go("layout", select="relative")
    qapp.processEvents()
    page = cc._pages["layout"]
    canvas = page.canvas
    w = oapp.widgets["relative"]
    x0, y0 = w.x(), w.y()
    v = canvas.to_view(w.geometry())
    start = QPoint(int(v.center().x()), int(v.center().y()))
    k = canvas._xf()[0]
    end = start + QPoint(int(-200 * k), int(-100 * k))
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(canvas, end)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
    assert abs((w.x() - x0) + 200) <= 16 and abs((w.y() - y0) + 100) <= 16
    assert oapp.config.widget("relative")["x"] == w.x()
    # rodyklė pastumia 1 px
    x1 = w.x()
    QTest.keyClick(canvas, Qt.Key.Key_Right)
    assert w.x() == x1 + 1


def test_profile_switch_rebuilds(oapp, qapp):
    oapp.preview_snapshot(wait=True)
    oapp.open_control_center()
    cc = oapp.control
    cc.open_widget("standings")
    oapp.config.add_profile("test", "Test")
    oapp.set_profile("test")
    assert oapp.config.profile_key == "test"
    assert oapp.config.data["auto_profile"] is False
    qapp.processEvents()


def test_hide_all_toggle(oapp):
    oapp.toggle_hide_all()
    assert oapp.hidden_all
    oapp.toggle_hide_all()
    assert not oapp.hidden_all


def test_inputs_flag_follows_visibility(oapp):
    oapp.set_widget_visible("inputs", True)
    assert oapp.engine.inputs_wanted
    oapp.set_widget_visible("inputs", False)
    assert not oapp.engine.inputs_wanted


def test_palette_custom_colors():
    from PySide6.QtGui import QGuiApplication  # noqa: F401
    from lth_overlays.theme import Palette
    p = Palette("racelab", 1.0, {"accent": "#00ff00", "bg": "#112233", "bogus": "#ffffff", "good": "nope"})
    assert p.accent.name() == "#00ff00"
    assert p.bg.name() == "#112233"
    assert math.isclose(p.bg.alpha(), 255 * 0.55, abs_tol=1)
