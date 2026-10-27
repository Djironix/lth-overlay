"""LTH diagnostika: įrašyti telemetriją ir patikrinti, kodėl gap'ai šokinėja.

Naudojimas (Windows, kol iRacing sesija vyksta):
    diagnose.py record --minutes 10
    diagnose.py report lth_irasas_....npz

Be iRacing (patikrinti patį įrankį):
    diagnose.py simulate --max-cars 10 --out sim.npz
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lth_timing.recording import Recorder, report  # noqa: E402


def cmd_record(args):
    from lth_timing.irsdk import LiveSource

    src = LiveSource()
    rec = Recorder(minutes=args.minutes)
    out = args.out or f"lth_recording_{dt.datetime.now():%Y%m%d_%H%M}.npz"
    print("Waiting for iRacing... (Ctrl+C to stop and save)")
    last_print = 0.0
    try:
        while not rec.full:
            f = src.wait_frame(200)
            if f is None:
                continue
            if not rec.session_yaml:
                rec.session_yaml = src.raw_session_yaml()
            rec.add(f)
            now = time.monotonic()
            if now - last_print > 5:
                last_print = now
                print(f"  recorded {rec.n / 30:.0f} s of {rec.n_max / 30:.0f} s")
    except KeyboardInterrupt:
        print("Stopped.")
    rec.session_yaml = src.raw_session_yaml() or rec.session_yaml  # naujausia versija su rezultatais
    rec.save(out)
    print(f"Saved: {os.path.abspath(out)}")
    txt = report(out)
    with open(out.replace(".npz", ".txt"), "w", encoding="utf-8") as fh:
        fh.write(txt)
    print(txt)


def cmd_report(args):
    print(report(args.file))


def cmd_simulate(args):
    from lth_timing.sim import SimRace

    sim = SimRace(n_cars=args.cars, multiclass=args.multiclass, max_cars=args.max_cars, events=True)
    rec = Recorder(minutes=args.minutes)
    rec.session_yaml = _sim_yaml(sim)
    while not rec.full:
        rec.add(sim.step())
    rec.save(args.out)
    print(report(args.out))


def _sim_yaml(sim) -> str:
    lines = ["---", "WeekendInfo:", " TrackDisplayName: Sim Raceway", f" TrackLength: {sim.track_m / 1000:.2f} km",
             " LeagueID: 0", "SessionInfo:", " Sessions:", " - SessionNum: 0", "   SessionType: Race",
             "DriverInfo:", f" DriverCarIdx: {sim.me}", " Drivers:"]
    for d in sim.model.drivers.values():
        lines += [f" - CarIdx: {d.idx}", f"   UserName: {d.name}", f"   AbbrevName: {d.abbrev}",
                  f"   CarNumber: \"{d.number}\"", f"   CarPath: {d.car_path}", f"   CarClassID: {d.class_id}",
                  f"   CarClassShortName: {d.class_name}", f"   CarClassColor: 0x{d.class_color:06x}",
                  f"   CarClassEstLapTime: {d.class_est_lap:.3f}", "   CarIsPaceCar: 0", "   IsSpectator: 0"]
    return "\n".join(lines) + "\n...\n"


def main():
    ap = argparse.ArgumentParser(description="LTH telemetry diagnostics")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record", help="record from iRacing")
    r.add_argument("--minutes", type=float, default=10)
    r.add_argument("--out")
    r.set_defaults(fn=cmd_record)
    p = sub.add_parser("report", help="report from a recording")
    p.add_argument("file")
    p.set_defaults(fn=cmd_report)
    s = sub.add_parser("simulate", help="synthetic recording without iRacing")
    s.add_argument("--cars", type=int, default=30)
    s.add_argument("--max-cars", type=int, default=10)
    s.add_argument("--multiclass", action="store_true")
    s.add_argument("--minutes", type=float, default=3)
    s.add_argument("--out", default="sim.npz")
    s.set_defaults(fn=cmd_simulate)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
