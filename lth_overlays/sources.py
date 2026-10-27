"""Duomenų šaltiniai programai: iRacing, demo (sintetinė lenktynė), įrašas."""
from __future__ import annotations

import time

from lth_timing.recording import ReplaySource
from lth_timing.sim import SimRace


class DemoSource:
    """Sintetinė multiklasės lenktynė realiu laiku - overlay'ų peržiūrai be iRacing."""

    def __init__(self, fast_forward: float = 240.0, realtime: bool = True):
        self.sim = SimRace(n_cars=28, multiclass=True, max_cars=12, rain=True, events=True, record=False)
        self.session = self.sim.model
        self.realtime = realtime
        for _ in range(int(fast_forward * 60)):
            self.sim.step()
        self._t0 = time.perf_counter()
        self._sim_t0 = self.sim.t
        self.connected = True

    def wait_frame(self, timeout_ms: int = 100):
        if self.realtime:
            target = self._t0 + (self.sim.t + self.sim.dt - self._sim_t0)
            delay = target - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
        return self.sim.step()

    def close(self):
        pass


class PacedReplay:
    """Įrašo atkūrimas realiu laiku (pagal SessionTime)."""

    def __init__(self, path: str):
        self.rep = ReplaySource(path)
        self.session = self.rep.session
        self.i = 0
        self._t0 = None
        self.connected = True

    def wait_frame(self, timeout_ms: int = 100):
        if self.i >= self.rep.n:
            time.sleep(timeout_ms / 1000)
            return None
        f = self.rep.frame(self.i)
        self.i += 1
        if self._t0 is None:
            self._t0 = (time.perf_counter(), f.SessionTime)
        delay = self._t0[0] + (f.SessionTime - self._t0[1]) - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        return f

    def close(self):
        pass
