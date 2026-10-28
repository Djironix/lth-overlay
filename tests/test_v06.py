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
