"""v0.6 testai: chat parseriai, OBS serveris, sektoriai, iRating, telemetrija, PB, hotkey'ai,
matomumas pagal sesiją, stulpelių antraštės, nauji valdikliai."""
import json
import os
import threading
import time
import urllib.request

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from lth_timing.engine import TimingEngine  # noqa: E402
from lth_timing.sim import SimRace  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def engine():
    sim = SimRace(n_cars=24, multiclass=True, max_cars=12, rain=False, events=False, record=False)
    eng = TimingEngine()
    eng.set_session(sim.model)
    for _ in range(60 * 360):
        eng.update(sim.step())
    return eng


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
    app.obs.stop()
    app.chat.stop()
    for w in app.widgets.values():
        w.close()


# ---------------------------------------------------------------- chat
def test_twitch_parsing():
    from lth_overlays import chat as C
    assert C.twitch_channel("https://www.twitch.tv/LTH_Racing") == "lth_racing"
    assert C.twitch_channel("not valid!") == ""
    kind, m = C.twitch_event("@color=#FF4500;display-name=Kartingas;id=a1;user-id=42 :k!k@k.tmi.twitch.tv "
                             "PRIVMSG #lth :Nice save")
    assert kind == "msg" and m.author == "Kartingas" and m.text == "Nice save" and m.color == "#FF4500"
    assert C.twitch_event(":k!k@k PRIVMSG #lth :\x01ACTION waves\x01")[1].kind == "action"
    assert C.twitch_event("PING :tmi.twitch.tv") == ("ping", "tmi.twitch.tv")
    assert C.twitch_event("@target-msg-id=a1 :tmi.twitch.tv CLEARMSG #lth :x") == ("del", "a1")
    hub = C.ChatHub()
    hub._apply([C.twitch_event("@id=a1;user-id=42 :k!k@k PRIVMSG #lth :hi")])
    assert len(hub.snapshot(10)[1]) == 1
    hub._apply([("clear_user", "42")])
    assert hub.snapshot(10)[1] == []


def test_youtube_parsing():
    from lth_overlays import chat as C
    assert C.youtube_target("https://youtu.be/dQw4w9WgXcQ") == ("video", "dQw4w9WgXcQ")
    assert C.youtube_target("@lth") == ("channel", "https://www.youtube.com/@lth/live")
    acts = [{"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {
        "id": "Y1", "authorName": {"simpleText": "Ieva"}, "authorExternalChannelId": "UC1",
        "message": {"runs": [{"text": "Labas "}, {"emoji": {"emojiId": "UCx/abc", "shortcuts": [":yt:"]}}]}}}}},
        {"removeChatItemAction": {"targetItemId": "Y1"}}]
    ev = C.youtube_events(acts)
    assert ev[0][1].text == "Labas :yt:" and ev[1] == ("del", "Y1")
    html = ('"INNERTUBE_API_KEY":"K","INNERTUBE_CONTEXT_CLIENT_VERSION":"2.1" window["ytInitialData"] = '
            '{"contents":{"liveChatRenderer":{"continuations":[{"timedContinuationData":{"continuation":"C1"}}]}}};')
    assert C.parse_live_chat_page(html)[:3] == ("K", "2.1", "C1")


# ---------------------------------------------------------------- OBS
def test_obs_server_serves_png_frames(oapp, qapp):
    oapp.preview_snapshot(wait=True)
    oapp.config.data["obs"] = {"enabled": True, "port": 18399 + os.getpid() % 500, "fps": 30}
    oapp.obs.apply()
    assert oapp.obs.running(), oapp.obs.error
    base = oapp.obs.base_url()
    res = {}

    def client():
        res["index"] = urllib.request.urlopen(base + "/", timeout=5).status
        for _ in range(40):
            r = urllib.request.urlopen(base + "/f/relative.png?have=-1&demo=1", timeout=5)
            if r.status == 200:
                res["png"] = r.read()[:8]
                res["seq"] = r.headers.get("X-Seq")
                break
            time.sleep(0.05)
        res["same"] = urllib.request.urlopen(f"{base}/f/relative.png?have={res.get('seq')}&demo=1", timeout=5).status
        res["layout"] = json.loads(urllib.request.urlopen(base + "/layout.json?screen=0", timeout=5).read())

    th = threading.Thread(target=client)
    th.start()
    end = time.time() + 15
    while th.is_alive() and time.time() < end:
        qapp.processEvents()
        time.sleep(0.005)
    assert res["index"] == 200
    assert res["png"] == b"\x89PNG\r\n\x1a\n"
    assert res["same"] == 204
    assert {w["name"] for w in res["layout"]["widgets"]} >= {"relative"}


# ---------------------------------------------------------------- engine
def test_sectors_and_recorder_match_lap_time(engine):
    snap = engine.snapshot()
    s = snap.my_sectors
    assert len(s.bounds) == 3
    assert all(v is not None for v in s.last)
    assert abs(sum(s.last) - snap.player.last_lap) < 0.05
    laps = engine.recorder.laps
    assert len(laps) >= 2
    assert abs(laps[-1].lap_time - snap.player.last_lap) < 0.02
    assert laps[-1].has_trace and float(laps[-1].data["time"][-1]) == pytest.approx(laps[-1].lap_time, abs=0.05)


def test_irating_projection(engine):
    from lth_timing.laps import irating_changes
    ch = irating_changes([(1, 2000, 1), (2, 2000, 2)])
    assert ch[1] > 40 and ch[2] < -40
    snap = engine.snapshot()
    assert snap.ir_change and abs(sum(snap.ir_change.values())) < 15 * len(snap.ir_change)


def test_incident_limit_from_session_yaml():
    from lth_timing.sessioninfo import build_model
    m = build_model({"WeekendInfo": {"TrackName": "x", "WeekendOptions": {"IncidentLimit": "17"}}})
    assert m.incident_limit == 17
    m = build_model({"WeekendInfo": {"TrackName": "x", "WeekendOptions": {"IncidentLimit": "unlimited"}}})
    assert m.incident_limit == 0


def test_lap_file_roundtrip_and_rejects_garbage(engine, tmp_path):
    from lth_timing import telemetry as T
    lap = engine.recorder.laps[-1]
    p = tmp_path / "a.lthlap"
    T.save_lap(str(p), lap)
    back = T.load_lap(str(p))
    assert back.lap_time == pytest.approx(lap.lap_time)
    assert back.meta["imported"] and np.allclose(back.data["speed"], lap.data["speed"])
    assert abs(float(T.delta_trace(lap, back)[-1])) < 1e-3
    bad = tmp_path / "bad.lthlap"
    bad.write_bytes(b"not a zip")
    with pytest.raises(Exception):
        T.load_lap(str(bad))
    csv = tmp_path / "a.csv"
    T.save_csv(str(csv), lap)
    assert csv.read_text().startswith("distance_m,time,speed")


# ---------------------------------------------------------------- overlay
def test_personal_best_store(tmp_path, engine):
    from lth_overlays.pb import PersonalBests
    snap = engine.snapshot()
    pb = PersonalBests(str(tmp_path / "pb.json"))
    assert pb.observe(snap)
    assert pb.get(snap.track_key, snap.car_key) == pytest.approx(snap.player.best_lap, abs=1e-3)
    assert not pb.observe(snap)
    assert PersonalBests(str(tmp_path / "pb.json")).get(snap.track_key, snap.car_key) is not None


def test_new_widgets_paint(oapp, engine):
    snap = engine.snapshot()
    for name in ("lap_timer", "sectors", "overtake_alert", "rejoin", "flat_map", "chat", "garage_cover"):
        w = oapp.widgets[name]
        for editing in (False, True):
            w.editing = editing
            w.push(snap, force=True)
            w.resize(w.target_width(), max(20, w.final_height()))
            assert not w.grab().isNull()
        w.editing = False


def test_column_header_adds_height(oapp, engine):
    snap = engine.snapshot()
    w = oapp.widgets["relative"]
    oapp.config.widget("relative")["column_header"] = False
    oapp.widget_changed("relative")
    w.push(snap, force=True)
    h0 = w.desired_height()
    oapp.config.widget("relative")["column_header"] = True
    oapp.widget_changed("relative")
    w.push(snap, force=True)
    assert w.desired_height() > h0
    oapp.config.widget("standings")["columns"]["irchange"] = True
    s = oapp.widgets["standings"]
    s.apply_settings()
    s.push(snap, force=True)
    assert "irchange" in s._cols


def test_session_visibility(oapp, engine):
    snap = engine.snapshot()
    w = oapp.widgets["relative"]
    oapp.config.widget("relative")["visible"] = True
    assert w.wants_visible(snap)
    oapp.config.widget("relative")["sessions"] = {"race": False, "practice": True}
    assert not w.wants_visible(snap)


def test_config_migrates_race_only(tmp_path):
    from lth_overlays.config import Config
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"version": 6, "profiles": {"race": {"name": "Race", "widgets": {
        "fuel": {"race_only": True}}}}}))
    c = Config(str(p))
    assert c.data["profiles"]["race"]["widgets"]["fuel"]["sessions"] == {
        "practice": False, "qualify": False, "warmup": False, "race": True}


def test_hotkeys_and_profile_cycle(oapp):
    oapp.config.data["hotkeys"]["widget:relative"] = "Ctrl+Shift+1"
    res = oapp.register_hotkeys()
    assert "edit" in res
    keys = list(oapp.config.data["profiles"])
    first = oapp.config.profile_key
    oapp.next_profile()
    assert oapp.config.profile_key == keys[(keys.index(first) + 1) % len(keys)]
    vis = bool(oapp.config.widget("relative").get("visible"))
    oapp.toggle_widget("relative")
    assert bool(oapp.config.widget("relative").get("visible")) != vis


def test_control_center_new_pages(oapp, qapp):
    oapp.config.data["onboarding_done"] = True
    oapp.open_control_center()
    cc = oapp.control
    for page in ("stream", "drivers", "telemetry", "hotkeys"):
        cc.go(page)
        qapp.processEvents()
        assert not cc.grab().isNull()
    dp = cc._pages["drivers"]
    dp.tag(123456, "Test Driver", "team")
    assert oapp.config.friends()[123456] == "#3DDC97"
    cc.hide()


def test_practice_standings_survive_garage_reset():
    """iRacing nuresetina CarIdxBestLapTime, kai mašina grįžta į garažą - vieta neturi pasikeisti."""
    sim = SimRace(n_cars=12, multiclass=False, max_cars=12, rain=False, events=False, record=False)
    sim.model.sessions[0].type = "practice"
    eng = TimingEngine()
    eng.set_session(sim.model)
    f = None
    for _ in range(60 * 300):
        f = sim.step()
        eng.update(f)
    eng._rows_cache = None
    before = {r.idx: (r.pos, r.best_lap) for r in eng.snapshot().cars}
    leader = min(before, key=lambda c: before[c][0])
    vals = dict(f.values)
    for k in ("CarIdxBestLapTime", "CarIdxLastLapTime", "CarIdxLapDistPct", "CarIdxLapCompleted"):
        arr = np.array(vals[k]).copy()
        arr[leader] = -1
        vals[k] = arr
    vals["SessionTime"] = float(vals["SessionTime"]) + 0.5
    from lth_timing.frame import Frame
    eng.update(Frame(vals))
    eng._rows_cache = None
    after = {r.idx: (r.pos, r.best_lap) for r in eng.snapshot().cars}
    assert after[leader] == before[leader]
    assert next(r for r in eng.snapshot().cars if r.idx == leader).status == "garage"


# ---------------------------------------------------------------- v0.6.1
def test_fuel_plan_matches_hand_calculation():
    from lth_overlays.widgets.car import fuel_plan
    a = fuel_plan(30, 2.5, 10.0, 100, 0.5, 5, 0.0)
    assert a["stops"] == 0 and a["spare"] == pytest.approx(2.0) and a["allowed"] == pytest.approx(30 / 10.5)
    b = fuel_plan(20, 2.5, 20.0, 40, 0.5, 5, 0.0)
    # vėliausiai lapo 11 pabaigoje (7 ratai = 17,5 l + 1,25 l atsarga <= 20 l), anksčiausiai 9 (po to 15,5 rato = 38,75 l <= 40 l)
    assert (b["stops"], b["latest_lap"], b["earliest_lap"]) == (1, 11, 9)
    assert b["deficit"] == pytest.approx(31.25) and not b["save_ok"]
    c = fuel_plan(24.5, 2.5, 10.0, 100, 0.5, 1, 0.5)
    assert c["save_ok"] and c["save_target"] == pytest.approx(24.5 / 10.5)
    d = fuel_plan(5, 2.5, 10.0, 60, 0.5, 7, 0.6)
    assert d["latest_lap"] == 8


def test_timed_race_laps_left_and_fuel_filter():
    from lth_timing.laps import clean_fuel_avg, laps_left_timed
    assert laps_left_timed(950, 0.0, 100) == pytest.approx(10.0)
    assert laps_left_timed(950, 0.5, 100) == pytest.approx(9.5)
    assert laps_left_timed(0, 0.3, 100) == pytest.approx(0.7)  # laikas baigėsi: tik šis ratas
    # greitesnis lyderis baigia anksčiau -> man mažiau ratų nei skaičiuojant savo tempu
    assert laps_left_timed(950, 0.2, 100, 0.8, 95) <= laps_left_timed(950, 0.2, 100)
    assert clean_fuel_avg([2.6, 2.62, 1.4, 2.58, 2.61]) == pytest.approx(2.6025)  # geltonas ratas atmestas


def test_relative_last_best_columns_and_titles_default(oapp, engine):
    from lth_overlays.registry import BY_NAME, defaults_for
    assert defaults_for(BY_NAME["relative"])["column_header"] is True
    assert defaults_for(BY_NAME["standings"])["column_header"] is True
    snap = engine.snapshot()
    oapp.config.widget("relative")["columns"].update(last=True, best=True)
    w = oapp.widgets["relative"]
    w.apply_settings()
    w.push(snap, force=True)
    assert "last" in w._cols and "best" in w._cols
    cells = {c[0]: c[1] for c in w._rows[0][1]}
    assert ":" in cells["last"] and ":" in cells["best"]


def test_fuel_strategy_widget_paints(oapp, engine):
    snap = engine.snapshot()
    w = oapp.widgets["fuel_strategy"]
    w.push(snap, force=True)
    w.resize(w.target_width(), w.final_height())
    assert w._view is not None and not w.grab().isNull()


def test_recorder_keeps_lap_on_session_info_update(engine):
    r = engine.recorder
    n = len(r.laps)
    buf = len(r._buf)
    r.set_session(dict(r.meta), r.track_m)  # tas pats trasa / mašina - einamasis ratas lieka
    assert len(r.laps) == n and len(r._buf) == buf


# ---------------------------------------------------------------- v0.6.2
def test_trace_decimation_is_stable_and_keeps_spikes():
    from lth_overlays.widgets.wheel import decimate
    sig = np.zeros(3000)
    sig[1500] = 1.0  # vieno mėginio pikas
    for seq in range(1500, 1700):
        win = sig[seq - 239:seq + 1]
        assert 1.0 in decimate(win, seq, 60)[1].tolist()
    a = set((decimate(sig[1000 - 239:1001], 1000, 60)[0] + 1000 - 239).tolist())
    b = set((decimate(sig[1001 - 239:1002], 1001, 60)[0] + 1001 - 239).tolist())
    assert len(a ^ b) <= 4  # kadras po kadro keičiasi tik kraštiniai taškai


def test_gt3_wheel_turns_the_right_way(qapp):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QImage, QPainter
    from lth_overlays.widgets.wheel import GT3Wheel

    def red_x(steer):
        img = QImage(200, 200, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        GT3Wheel().draw(p, QPointF(100, 100), 160, steer, 1.0)
        p.end()
        xs = [x for y in range(0, 100) for x in range(200)
              if (lambda c: c.red() > 180 and c.green() < 80 and c.blue() < 80)(img.pixelColor(x, y))]
        return sum(xs) / len(xs)

    assert abs(red_x(0.0) - 100) < 4  # žymė viršuje
    assert red_x(0.8) < 90  # iRacing: teigiamas = į kairę -> žymė pasislenka kairėn
    assert red_x(-0.8) > 110


def test_track_usage_text():
    from lth_overlays.widgets.weather import cardinal, track_usage_text
    assert track_usage_text("moderately low usage") == "Moderately low (2/5)"
    assert track_usage_text("high usage") == "High (5/5)"
    assert track_usage_text("carry over") == "Carried over"
    assert track_usage_text("") == ""
    import math
    assert cardinal(0) == "N" and cardinal(math.radians(90)) == "E" and cardinal(math.radians(225)) == "SW"


def test_sessions_saved_listed_and_loaded(engine, tmp_path):
    from lth_overlays.sessions import SessionStore
    st = SessionStore(str(tmp_path / "sessions"))
    n = st.observe(engine.recorder)
    assert n == len([x for x in engine.recorder.laps if x.has_trace])
    assert st.observe(engine.recorder) == 0  # tas pats - antrą kartą nerašo
    items = st.list()
    assert len(items) == 1 and items[0][1]["type"] == "race" and items[0][1]["best"]
    laps = SessionStore.load(items[0][0])
    assert len(laps) == n and "abs" in laps[0].data


def test_suggested_driver_lists_are_optional(oapp, qapp):
    from lth_overlays.control.drivers_page import SUGGESTED, suggested_drivers
    drivers = suggested_drivers()
    assert len(drivers) == 112 and len({d["id"] for d in drivers}) == 112
    oapp.config.data["onboarding_done"] = True
    assert not oapp.config.data.get("friends")  # numatytai niekas nepažymėtas
    oapp.open_control_center()
    oapp.control.go("drivers")
    qapp.processEvents()
    dp = oapp.control._pages["drivers"]
    dp.tag(1372638, "Audrius Bakutis", "team")  # pačio pažymėtas lieka
    dp._toggle_list("hub")
    f = oapp.config.data["friends"]
    assert f["1372638"]["tag"] == "team" and len(f) == 112
    dp._toggle_list("hub")
    assert list(oapp.config.data["friends"]) == ["1372638"]
    oapp.control.hide()


def test_setup_pack_import_is_safe(tmp_path):
    import zipfile
    from lth_overlays.setups import SetupLibrary
    z = tmp_path / "pack.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("LTH pack/bmwm4gt3/spa/race.sto", "x")
        f.writestr("../../evil.sto", "bad")
        f.writestr("porsche992rgt3/quali.sto", "q")
        f.writestr("virus.exe", "no")
    lib = SetupLibrary(str(tmp_path / "lib"))
    res = lib.import_files([str(z)], car_hint="ferrari296gt3")
    assert res.get("bmwm4gt3") == 1 and res.get("porsche992rgt3") == 1
    files = [os.path.relpath(os.path.join(r, n), lib.root) for r, _, fs in os.walk(lib.root) for n in fs]
    assert all(not f.startswith("..") for f in files) and not any(f.endswith(".exe") for f in files)
    assert os.path.isfile(os.path.join(lib.root, "bmwm4gt3", "spa", "race.sto"))


def test_dashboard_stats():
    import datetime
    from lth_overlays.sessions import stats
    items = [("a", {"started": "2026-10-29 20:50", "laps": {"1": [100, True, False], "2": [101, True, False]},
                    "car_name": "BMW", "type": "race"}),
             ("b", {"started": "2026-10-27 10:00", "laps": {"1": [90, True, False]}, "car_name": "Porsche"}),
             ("c", {"started": "2026-09-30 10:00", "laps": {"1": [90, True, False], "2": [1, 1, 1]}, "car_name": "BMW"})]
    s = stats(items, datetime.datetime(2026, 10, 29, 21, 0).timestamp())
    assert s["laps_month"] == 3 and s["time_month_s"] == pytest.approx(291)
    assert s["week"] == [0, 1, 0, 2, 0, 0, 0]  # 2026-10-27 antradienis, 10-29 ketvirtadienis
    assert s["top_car"][0] == "BMW" and s["top_car"][1] == 4


def test_new_control_center_pages(oapp, qapp, engine):
    oapp.config.data["onboarding_done"] = True
    oapp.engine.timing = engine
    oapp.sessions.observe(engine.recorder)
    oapp.open_control_center()
    cc = oapp.control
    for page in ("overview", "records", "setups", "telemetry", "drivers"):
        cc.go(page)
        qapp.processEvents()
        assert not cc.grab().isNull()
    oapp.notify("test toast")
    cc.hide()


def test_top_navigation_shell(oapp, qapp):
    """GoFast stiliaus apvalkalas: piliulės, nustatymų meniu, Overlays jungiklis, glaudinimas siauram langui."""
    from lth_overlays.control.center import NAV_MAIN, NAV_MORE
    oapp.config.data["onboarding_done"] = True
    oapp.open_control_center()
    cc = oapp.control
    assert set(cc._nav) == {k for k, _ in NAV_MAIN}
    acts = [a.text() for a in cc.b_settings.menu().actions() if a.text()]
    assert len(acts) == len(NAV_MORE) + 1 and acts[-1].startswith("Quit")
    cc.go("general")
    qapp.processEvents()
    assert not any(b.isChecked() for b in cc._nav.values())
    cc.go("telemetry")
    assert cc._nav["telemetry"].isChecked()
    # Overlays on jungiklis = Hide all
    was = oapp.hidden_all
    cc.t_overlays.click()
    assert oapp.hidden_all != was
    cc.t_overlays.click()
    assert oapp.hidden_all == was
    # siauriausias langas - juosta telpa
    cc.resize(1080, 760)
    qapp.processEvents()
    cc._fit_topnav()
    assert cc._topbar_w.layout().sizeHint().width() <= cc.width() - 44
    cc.resize(1700, 900)
    cc._fit_topnav()
    assert cc._compact == 0
    # pranešimų varpelis
    oapp.notify("hello")
    cc.tick(oapp.engine.latest)
    assert cc._notes_hot
    cc._fill_notes()
    assert not cc._notes_hot and any("hello" in a.text() for a in cc.notes_menu.actions())
    cc.hide()
