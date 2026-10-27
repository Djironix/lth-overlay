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


# ---------------------------------------------------------------- v0.5: keli monitoriai
@pytest.fixture()
def oapp3(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from PySide6.QtCore import QRect
    from lth_overlays.app import OverlayApp
    from lth_overlays.config import Config
    from lth_overlays.sources import DemoSource
    cfg = Config(str(tmp_path / "config.json"))
    screens = [QRect(0, 0, 1920, 1080), QRect(-1920, 0, 1920, 1080), QRect(1920, 0, 2560, 1440)]
    app = OverlayApp(qapp, DemoSource, cfg, virtual_screen=screens)
    yield app
    for w in app.widgets.values():
        w.close()


def test_widget_stays_on_left_monitor(oapp3):
    w = oapp3.widgets["relative"]
    w.cfg.update(x=-1500, y=200, pos_v=2)
    w.apply_settings()
    assert (w.x(), w.y()) == (-1500, 200)
    w.save_geometry()
    w.apply_settings()
    assert w.x() == -1500


def test_widget_on_right_monitor_clamped_to_that_monitor(oapp3):
    w = oapp3.widgets["relative"]
    w.cfg.update(x=1920 + 2560 - 100, y=50, pos_v=2)  # išlenda už 3-io monitoriaus krašto
    w.apply_settings()
    assert w.x() + w.width() == 1920 + 2560
    assert w.x() > 1920


def test_disconnected_monitor_shows_on_primary_without_losing_position(oapp3):
    w = oapp3.widgets["relative"]
    w.cfg.update(x=9000, y=100, pos_v=2)
    w.apply_settings()
    assert 0 <= w.x() < 1920
    assert w.cfg["x"] == 9000


def test_legacy_negative_position_migrates_to_primary(oapp3):
    w = oapp3.widgets["relative"]
    w.cfg.pop("pos_v", None)
    w.cfg.update(x=-500, y=-340, width=420)
    w.apply_settings()
    assert w.cfg["pos_v"] == 2
    assert w.x() + w.width() <= 1920 and w.x() >= 1920 - 500 - 200
    assert w.y() == 1080 - 340


# ---------------------------------------------------------------- v0.5: vėliavos
def _flag_frame(state, pace, session_flags, car_flags=None):
    from lth_timing.frame import Frame
    vals = {"SessionFlags": session_flags, "SessionState": state, "PaceMode": pace, "PlayerCarIdx": 3}
    if car_flags is not None:
        arr = np.zeros(64, dtype=np.int32)
        arr[3] = car_flags
        vals["CarIdxSessionFlags"] = arr
    return Frame(vals)


def test_no_blue_flag_during_rolling_start():
    from lth_timing.player import FLAG_BLUE, PlayerTracker
    pt = PlayerTracker()
    # parade / pace laps: mėlynos nėra
    assert not pt._flag_bits(_flag_frame(3, 1, FLAG_BLUE, FLAG_BLUE), 100.0) & FLAG_BLUE
    # ką tik žalia: dar ne
    assert not pt._flag_bits(_flag_frame(4, 4, FLAG_BLUE, FLAG_BLUE), 101.0) & FLAG_BLUE
    # po 12 s - jau taip
    assert pt._flag_bits(_flag_frame(4, 4, 0, FLAG_BLUE), 113.0) & FLAG_BLUE
    # globalus mėlynos bitas nebe mano mašinai - ignoruojam
    assert not pt._flag_bits(_flag_frame(4, 4, FLAG_BLUE, 0), 120.0) & FLAG_BLUE


def test_flags_widget_ignores_blue_without_lapping_car(oapp, race_snap):
    import copy
    snap = copy.copy(race_snap)
    snap.player = copy.copy(race_snap.player)
    snap.player.flags = (("blue", "BLUE FLAG"),)
    snap.player.pace_mode = 4
    snap.relative = [r for r in race_snap.relative if r.gap >= 0 or r.is_me]  # už manęs nieko
    w = oapp.widgets["flags"]
    w._seen = {}
    w.push(snap, force=True)
    assert w._view is None or w._view[0] != "blue"


# ---------------------------------------------------------------- v0.5: greitas Inputs kelias
def test_inputs_fast_path_reads_engine_directly(oapp):
    sim = SimRace(n_cars=6, record=False)
    eng = TimingEngine()
    eng.player.inputs_enabled = True
    eng.set_session(sim.model)
    for _ in range(120):
        eng.update(sim.step())
    oapp.engine.timing = eng
    oapp.engine.connected = True
    for name in ("inputs", "dash", "delta_bar"):
        w = oapp.widgets[name]
        w.cfg["visible"] = True
        w.cfg["smooth"] = True
        w.show()
        w.apply_settings()
        assert w.fast_active(), name
        w._view = None
        assert w.fast_tick(eng), name
        assert w._view is not None
        w.hide()
        assert not w._fast_timer.isActive()
    w = oapp.widgets["inputs"]
    seq = eng.player.inp_seq
    w.show()
    w.fast_tick(eng)
    assert not w.fast_tick(eng)  # nėra naujo mėginio - neperpiešiam
    eng.update(sim.step())
    assert eng.player.inp_seq == seq + 1 and w.fast_tick(eng)
    w.hide()


# ---------------------------------------------------------------- v0.5: presetai ir dalinimasis
def test_presets_apply_and_fit_screen(oapp):
    from lth_overlays.presets import PRESETS, apply_preset
    for key in PRESETS:
        apply_preset(oapp, key)
        on = [n for n, w in oapp.widgets.items() if w.cfg.get("visible")]
        assert set(on) == set(PRESETS[key]["widgets"]), key
        for n in on:
            w = oapp.widgets[n]
            assert 0 <= w.x() and w.x() + w.width() <= 1920, (key, n)
            assert 0 <= w.y() < 1080, (key, n)


def test_triple_preset_targets_middle_screen(oapp3):
    from lth_overlays.presets import apply_preset
    apply_preset(oapp3, "triple")
    st = oapp3.widgets["standings"]
    # trys monitoriai: -1920..0, 0..1920, 1920..4480 -> vidurinis pagal x yra pagrindinis (0..1920)
    assert 0 <= st.x() < 1920


def test_triple_preset_surround_middle_third(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from PySide6.QtCore import QRect
    from lth_overlays.app import OverlayApp
    from lth_overlays.config import Config
    from lth_overlays.presets import apply_preset
    from lth_overlays.sources import DemoSource
    app = OverlayApp(qapp, DemoSource, Config(str(tmp_path / "c.json")), virtual_screen=QRect(0, 0, 5760, 1080))
    apply_preset(app, "triple")
    for n in ("standings", "relative", "weather"):
        w = app.widgets[n]
        assert 1920 <= w.x() and w.x() + w.width() <= 3840, n
    for w in app.widgets.values():
        w.close()


def test_share_code_roundtrip_and_rescale(oapp, qapp, tmp_path, monkeypatch):
    from lth_overlays import share
    from lth_overlays.presets import apply_preset
    apply_preset(oapp, "single")
    oapp.config.widget("standings")["columns"]["irating"] = False
    data = share.export_layout(oapp)
    code = share.encode(data)
    assert code.startswith("LTH1:") and len(code) < share.DISCORD_LIMIT
    back = share.decode("Here is my layout:\n" + code + "\nenjoy")
    assert set(back["widgets"]) == set(data["widgets"])
    # gavėjas su 2560x1440 ekranu
    from PySide6.QtCore import QRect
    from lth_overlays.app import OverlayApp
    from lth_overlays.config import Config
    from lth_overlays.sources import DemoSource
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "other"))
    other = OverlayApp(qapp, DemoSource, Config(str(tmp_path / "o.json")), virtual_screen=QRect(0, 0, 2560, 1440))
    key = share.import_layout(other, back, "From friend")
    prof = other.config.data["profiles"][key]["widgets"]
    assert prof["standings"]["columns"]["irating"] is False
    assert prof["standings"]["visible"] and not prof["lap_history"]["visible"]
    src_x = oapp.config.widget("weather")["x"]
    assert abs(prof["weather"]["x"] - src_x * 2560 / 1920) <= 2
    assert other.config.profile_key != key  # esamas profilis nepakeistas
    for w in other.widgets.values():
        w.close()


def test_share_rejects_garbage_and_bad_types():
    from lth_overlays import share
    with pytest.raises(ValueError):
        share.decode("hello")
    with pytest.raises(ValueError):
        share.decode("LTH1:abc")
    data = share.validate({"lth_layout": 1, "widgets": {
        "standings": {"visible": "yes", "scale": "__import__('os')", "x": 10, "evil": 1},
        "nope": {"visible": True}}})
    assert data["widgets"]["standings"] == {"x": 10}
    assert "nope" not in data["widgets"]


def test_preset_and_share_dialogs_open(oapp, qapp):
    oapp.preview_snapshot(wait=True)
    oapp.open_control_center()
    from lth_overlays.control.dialogs import ImportDialog, PresetDialog, ShareDialog
    from lth_overlays import share
    d = PresetDialog(oapp.control)
    d.picker._pick("single")
    d._apply()
    assert oapp.widgets["fuel"].cfg["visible"]
    s = ShareDialog(oapp.control, oapp.config.profile_key)
    assert s.code.startswith("LTH1:")
    i = ImportDialog(oapp.control)
    i.text.setPlainText(s.code)
    i._parse()
    assert i.data is not None and i.ok.isEnabled()
    n = len(oapp.config.data["profiles"])
    key = share.import_layout(oapp, i.data, "Copy")
    assert len(oapp.config.data["profiles"]) == n + 1 and key in oapp.config.data["profiles"]


# ---------------------------------------------------------------- v0.5: tutorialas ir redagavimas
def test_onboarding_walkthrough_applies_preset(oapp, qapp):
    oapp.preview_snapshot(wait=True)
    oapp.open_control_center()
    cc = oapp.control
    onb = cc._onb
    assert onb is not None and onb.isVisible()
    onb._next()  # -> 2 žingsnis
    onb.layout_mode.set_value("preset")
    onb.picker._pick("single")
    onb._next()  # pritaiko presetą visiems trims profiliams
    for prof in ("race", "qualify", "practice"):
        assert oapp.config.data["profiles"][prof]["widgets"]["fuel"]["visible"]
    while cc._onb is not None:
        onb._next()
    assert oapp.config.data["onboarding_done"] is True
    cc.close()
    oapp.open_control_center()
    assert cc._onb is None  # antrą kartą nerodomas


def test_edit_mode_settings_button_opens_settings(oapp, qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    oapp.preview_snapshot(wait=True)
    oapp.config.data["onboarding_done"] = True
    w = oapp.widgets["relative"]
    oapp.toggle_edit()
    w.show()
    w.push(oapp.preview_snapshot(), force=True)
    assert oapp.toolbar.isVisible()
    chip, gear, _ = w._edit_rects()
    assert gear.right() < w.width() - 10 and chip.height() == 22
    QTest.mouseClick(w, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, gear.center().toPoint())
    assert oapp.control is not None and oapp.control._current is oapp.control._widget_pages["relative"]
    # siauras valdiklis: mygtukas vis tiek telpa
    f = oapp.widgets["flags"]
    f.show()
    f.cfg["width"] = 170
    f.apply_settings()
    chip, gear, _ = f._edit_rects()
    assert gear.right() <= f.width() and gear.width() >= 26
    oapp.toggle_edit()
    assert not oapp.toolbar.isVisible()


# ---------------------------------------------------------------- v0.5: Rain Master
def test_rain_caller_rules():
    from lth_timing.rain_tips import RainCaller
    rc = RainCaller()
    # sausa sesija - nieko
    assert rc.update(0, 1, "stable", 0.0, 0, False, False) is None
    assert rc.update(10, 1, "stable", 0.0, 0, False, False) is None
    # lietus netoliese
    c = rc.update(20, 1, "stable", 0.3, 0, False, False)
    assert c is not None and c.text == "RAIN NEAR TRACK"
    # pradeda šlapti: very lightly wet ant sausų
    c = rc.update(40, 3, "wetter", 0.4, 0, False, False)
    assert c.text == "DRY TYRES OK" and len(c.text) <= 20
    assert rc.update(45, 3, "wetter", 0.4, 0, False, False).text == "DRY TYRES OK"  # dar rodoma
    assert rc.update(50, 3, "wetter", 0.4, 0, False, False) is None  # po 8 s dingsta
    # lightly wet ant sausų: padangų call visą laiką
    for t in (60, 120, 600):
        c = rc.update(t, 4, "wetter", 0.6, 0, False, False)
        assert c.text == "WET TYRES" and c.persistent
    # pasikeitė į lietaus padangas -> kiti call'ai
    c = rc.update(700, 4, "wetter", 0.6, 1, False, False)
    assert c is not None and not c.persistent
    # džiūsta ant lietaus padangų
    c = rc.update(2000, 2, "drying", 0.0, 1, False, False)
    assert c.text == "TRY DRY TYRES"


def test_rain_calls_are_short_and_explicit():
    from lth_timing.rain_tips import CALLS, tips_for
    for key, (text, kind, detail) in CALLS.items():
        assert text.isupper() and len(text) <= 20 and 1 < len(text.split()) <= 3, text
        assert kind in ("tyres", "change", "drive")
        if kind == "tyres":
            assert "TYRES" in text, text
    assert tips_for(1) == []
    assert any(t.startswith("This track") for t, _ in tips_for(5, "Circuit de Spa-Francorchamps")[:4])


def test_rain_master_and_call_strip_render(oapp, race_snap):
    import copy
    from lth_timing.rain_tips import CALLS, RainCall
    from lth_timing.weather import WeatherState
    snap = copy.copy(race_snap)
    snap.weather = WeatherState(wetness=5, wetness_text="Moderately wet", trend="wetter", valid=True)
    t, k, d = CALLS["brake_earlier"]
    snap.rain_call = RainCall("brake_earlier", t, k, d)
    snap.player = copy.copy(race_snap.player)
    rm = oapp.widgets["rain_master"]
    rm.cfg["visible"] = True
    for mode in ("compact", "expanded"):
        rm.cfg["mode"] = mode
        rm.apply_settings()
        assert rm.wants_visible(snap)
        rm.push(snap, force=True)
        rm.resize(rm.width(), rm.final_height())
        assert not rm.grab().isNull()
        assert rm._view[7] == (mode == "expanded")
    wx = oapp.widgets["weather"]
    wx.show()
    wx.push(snap, force=True)
    assert wx._strip.isVisible() and wx._strip.call.text == "BRAKE EARLIER"
    assert wx._strip.geometry().bottom() < wx.y() or wx._strip.y() > wx.y()
    snap.rain_call = None
    wx.push(snap, force=True)
    assert not wx._strip.isVisible()
    wx.hide()
