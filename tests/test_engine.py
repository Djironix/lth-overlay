"""Timing variklio testai su sintetinėmis lenktynėmis.

Kiekvienas testas lygina variklio rezultatą su tikra simuliacijos trajektorija.
"""
import math
import time

import numpy as np
import pytest

from lth_timing.engine import TimingEngine
from lth_timing.engineer import Engineer
from lth_timing.sessioninfo import build_model, parse_yaml
from lth_timing.sim import SimRace


def drive(sim, eng, secs, every=6, after=0.0, on_snap=None):
    for i in range(int(secs * 60)):
        f = sim.step()
        eng.update(f)
        if on_snap and i % every == 0 and sim.t >= after:
            on_snap(eng.snapshot())


def true_gap(sim, P, T, ahead, behind):
    return T[-1] - np.interp(P[-1, behind], P[:, ahead], T)


@pytest.mark.parametrize("max_cars,multiclass", [(None, False), (10, False), (10, True)])
def test_gaps_match_truth(max_cars, multiclass):
    sim = SimRace(n_cars=30, multiclass=multiclass, max_cars=max_cars, events=False)
    eng = TimingEngine()
    eng.set_session(sim.model)
    errors = []

    def check(s):
        P = np.array(sim.traj_p)
        T = np.array(sim.traj_t)
        leaders = {}
        for r in s.cars:
            leaders.setdefault(r.class_id, r.idx)
        for r in s.cars:
            if r.gap is not None:
                errors.append(abs(true_gap(sim, P, T, leaders[r.class_id], r.idx) - r.gap))

    drive(sim, eng, 300, every=60 * 20, after=150, on_snap=check)
    assert errors, "nėra palyginimų"
    # su Max Cars gap'as skaičiuojamas paskutinėje patikimoje vietoje (iki ~1 s senumo)
    limit = 0.10 if max_cars is None else 0.30
    assert max(errors) < limit, f"didžiausia paklaida {max(errors):.3f} s"


def test_gap_does_not_jump_with_unrendered_cars():
    """Pagrindinė LTH problema: +16 -> +8 s šuoliai. Su Max Cars = 10 gap'as
    tarp gretimų atnaujinimų neturi šokti daugiau nei 0,25 s, o nuo tikro
    gap'o nenukrypti daugiau nei 0,3 s."""
    sim = SimRace(n_cars=30, max_cars=10, events=False, seed=3)
    eng = TimingEngine()
    eng.set_session(sim.model)
    samples = []  # (traj indeksas, idx, lyderis, gap)

    def rec(s):
        leaders = {}
        for r in s.cars:
            leaders.setdefault(r.class_id, r.idx)
        for r in s.cars:
            if r.gap is not None:
                samples.append((len(sim.traj_t) - 1, r.idx, leaders[r.class_id], r.gap))

    drive(sim, eng, 400, every=6, after=200, on_snap=rec)
    P = np.array(sim.traj_p)
    T = np.array(sim.traj_t)
    last = {}
    worst_jump = worst_err = 0.0
    for k, c, L, g in samples:
        truth = T[k] - np.interp(P[k, c], P[: k + 1, L], T[: k + 1])
        worst_err = max(worst_err, abs(truth - g))
        prev = last.get(c)
        if prev is not None and prev[0] == L and k - prev[1] <= 6:
            worst_jump = max(worst_jump, abs(g - prev[2]))
        last[c] = (L, k, g)
    # Standings refresh at 2 Hz: one step covers 0.5 s of real change
    assert worst_jump < 0.25, f"jump {worst_jump:.3f} s"
    assert worst_err < 0.3, f"error {worst_err:.3f} s"


def test_naive_distance_method_breathes():
    """Įrodymas, kodėl NEnaudojam atstumas × rato laikas: tas pats gap'as
    posūkiuose ir tiesiosiose „kvėpuoja“ sekundėmis."""
    sim = SimRace(n_cars=10, events=False, seed=5)
    for _ in range(60 * 200):
        sim.step()
    P = np.array(sim.traj_p)
    T = np.array(sim.traj_t)
    a, b = 0, 5
    lap_time = sim.track_m / 45.0
    dev = []
    for i in range(len(T) - 60 * 90, len(T), 30):
        naive = (P[i, a] - P[i, b]) * lap_time
        real = T[i] - np.interp(P[i, b], P[: i + 1, a], T[: i + 1])
        dev.append(naive - real)
    assert max(dev) - min(dev) > 1.0


def test_relative_and_delta():
    sim = SimRace(n_cars=20, events=False, seed=11)
    eng = TimingEngine()
    eng.set_session(sim.model)
    drive(sim, eng, 360)
    s = eng.snapshot()
    P = np.array(sim.traj_p)
    T = np.array(sim.traj_t)
    me = s.me
    rel = [r for r in s.relative if not r.is_me]
    assert len(rel) == 6
    assert [r.gap > 0 for r in s.relative].count(True) == 3
    for r in rel:
        d = r.distance
        if d > 0:  # jis priekyje: kada jis buvo mano vietoje
            pa = P[-1, me] + (math.floor(P[-1, r.idx] - P[-1, me] - d + 0.5))
            truth = T[-1] - np.interp(pa, P[:, r.idx], T)
        else:  # jis už manęs: kada aš buvau jo vietoje
            pb = P[-1, r.idx] - math.floor(P[-1, r.idx] - P[-1, me] - d + 0.5)
            truth = -(T[-1] - np.interp(pb, P[:, me], T))
        assert abs(truth - r.gap) < 0.1, (r.idx, r.gap, truth)
        assert r.delta is not None and r.delta_exact
    # artėjimas: greitesnis priekyje -> delta > 0 (tolsta), lėtesnis -> < 0
    for r in rel:
        faster = sim.pace[r.idx] > sim.pace[me]
        if r.gap > 0 and r.lap_rel == 0 and abs(sim.pace[r.idx] - sim.pace[me]) > 0.004:
            assert (r.delta > 0) == faster


def test_delta_matches_true_closing_rate():
    sim = SimRace(n_cars=12, events=False, seed=2)
    eng = TimingEngine()
    eng.set_session(sim.model)
    drive(sim, eng, 420)
    s = eng.snapshot()
    P = np.array(sim.traj_p)
    T = np.array(sim.traj_t)
    me = s.me
    checked = 0
    for rr in s.relative:
        if rr.is_me or rr.gap <= 0 or rr.lap_rel != 0:
            continue
        x = P[-1, me]
        now = T[-1] - np.interp(x, P[:, rr.idx], T)
        ago = np.interp(x - 1, P[:, me], T) - np.interp(x - 1, P[:, rr.idx], T)
        assert rr.delta_exact
        assert abs((now - ago) - rr.delta) < 0.05, (rr.delta, now - ago)
        checked += 1
    assert checked >= 2


def test_stale_flag_only_for_unrendered():
    sim = SimRace(n_cars=30, max_cars=8, events=False)
    eng = TimingEngine()
    eng.set_session(sim.model)
    stale_counts = np.zeros(30)
    near_stale = []

    def rec(s):
        for r in s.cars:
            stale_counts[r.idx] += r.stale
        for rr in s.relative:
            if abs(rr.distance) < 0.01 and not rr.is_me:
                near_stale.append(rr.stale)

    drive(sim, eng, 300, every=6, after=120, on_snap=rec)
    assert stale_counts.sum() > 0
    assert stale_counts[sim.me] == 0
    # Artimos mašinos perduodamos; „~“ gali mirktelėti tik tą akimirką, kai mašina
    # ką tik priartėjo ir iRacing dar neatsiuntė naujos pozicijos.
    assert sum(near_stale) / max(len(near_stale), 1) < 0.05


def test_pit_stop_and_off_track():
    sim = SimRace(n_cars=16, events=True, seed=4)
    eng = TimingEngine()
    eng.set_session(sim.model)
    seen = {"pit": False, "off": False}

    def rec(s):
        for r in s.cars:
            if r.idx == sim.pit_car and r.status == "pit":
                seen["pit"] = True
            if r.idx == sim.off_car and r.status == "off":
                seen["off"] = True

    drive(sim, eng, 520, every=30, on_snap=rec)
    s = eng.snapshot()
    pit_row = next(r for r in s.cars if r.idx == sim.pit_car)
    assert seen["pit"] and seen["off"]
    assert pit_row.pit_stops == 1
    assert pit_row.laps_since_pit is not None and pit_row.laps_since_pit >= 1


def test_replay_jump_resets_history():
    sim = SimRace(n_cars=8, events=False)
    eng = TimingEngine()
    eng.set_session(sim.model)
    drive(sim, eng, 120)
    sim.t -= 60.0  # replay atgal
    f = sim.step()
    eng.update(f)
    assert eng.stats["resets"] == 1


def test_multiclass_positions_and_purple():
    sim = SimRace(n_cars=24, multiclass=True, events=False)
    eng = TimingEngine()
    eng.set_session(sim.model)
    drive(sim, eng, 400)
    s = eng.snapshot()
    by_class = {}
    for r in s.cars:
        by_class.setdefault(r.class_id, []).append(r)
    assert len(by_class) == 3
    for cid, rows in by_class.items():
        assert [r.class_pos for r in rows] == list(range(1, len(rows) + 1))
        assert rows[0].gap is None
        assert sum(r.best_is_fastest for r in rows) == 1


def test_weather_trend_rain():
    sim = SimRace(n_cars=6, rain=True, events=False)
    eng = TimingEngine()
    eng.set_session(sim.model)
    drive(sim, eng, 400)
    w = eng.snapshot().weather
    assert w.trend == "wetter"
    assert w.wetness >= 2
    assert w.track_temp_change < 0


def test_engineer_messages_on_straight():
    sim = SimRace(n_cars=16, events=False, seed=9)
    eng = TimingEngine()
    eng.set_session(sim.model)
    ing = Engineer()
    texts = []

    def rec(s):
        for m in ing.update(s, eng.frame):
            texts.append(m.text)

    drive(sim, eng, 420, every=30, after=100, on_snap=rec)
    assert any(t.startswith("Ahead") or t.startswith("Behind") for t in texts)


def test_session_yaml_with_tricky_names():
    raw = """---
WeekendInfo:
 TrackName: roadatlanta full
 TrackDisplayName: Michelin Raceway Road Atlanta
 TrackLength: 4.09 km
 LeagueID: 12345
 SeriesID: 0
 TeamRacing: 0
SessionInfo:
 Sessions:
 - SessionNum: 0
   SessionType: Race
   SessionName: RACE
   SessionLaps: unlimited
   ResultsPositions:
DriverInfo:
 DriverCarIdx: 1
 Drivers:
 - CarIdx: 0
   UserName: Pace Car
   AbbrevName: Pace, C
   CarIsPaceCar: 1
   IsSpectator: 0
   CarClassID: 11
 - CarIdx: 1
   UserName: Jonas "Žaibas": Petraitis
   AbbrevName: Petraitis, J
   TeamName: LTH: Racing #1
   CarNumber: "7"
   UserID: 555
   CarPath: bmwm4gt3
   CarScreenNameShort: BMW M4 GT3
   CarClassID: 2708
   CarClassShortName: GT3 Class
   CarClassColor: 0xffda59
   CarClassEstLapTime: 85.1234
   IRating: 2450
   LicString: A 3.45
   CarIsPaceCar: 0
   IsSpectator: 0
...
"""
    m = build_model(parse_yaml(raw))
    assert m.track_length_m == pytest.approx(4090)
    assert m.league_id == 12345
    d = m.drivers[1]
    assert d.name == 'Jonas "Žaibas": Petraitis'
    assert d.team == "LTH: Racing #1"
    assert d.brand["short"] == "BMW"
    assert d.class_color == 0xFFDA59
    assert list(m.classes) == [2708]
    assert m.session_type(0) == "race"


def test_performance_budget():
    """40 mašinų: kadras < 150 µs, snapshot < 2 ms (vidutiniškai, lėtam CI)."""
    sim = SimRace(n_cars=40, multiclass=True, max_cars=12, events=True)
    eng = TimingEngine()
    eng.set_session(sim.model)
    frames = [sim.step() for _ in range(60 * 150)]
    a = time.perf_counter()
    for f in frames:
        eng.update(f)
    per_frame = (time.perf_counter() - a) / len(frames)
    a = time.perf_counter()
    for _ in range(100):
        eng.snapshot()
    per_snap = (time.perf_counter() - a) / 100
    assert per_frame < 150e-6, per_frame
    assert per_snap < 2e-3, per_snap
