"""Savo mašinos sektorių laikai ir iRating prognozė."""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class SectorState:
    bounds: tuple = ()  # sektorių pradžios 0..1
    current: tuple = ()  # šio rato sektorių laikai (None - dar nevažiuotas)
    last: tuple = ()  # paskutinio užbaigto rato
    best: tuple = ()  # geriausi šios sesijos (mano)
    index: int = -1  # dabartinis sektorius
    elapsed: float = 0.0  # kiek laiko dabartiniame sektoriuje
    improved: tuple = ()  # kurie šio rato sektoriai pagerino geriausią
    last_improved: tuple = ()
    lap_done_age: float = 1e9  # prieš kiek sekundžių baigtas ratas

    @property
    def optimal(self) -> float | None:
        if self.best and all(b is not None for b in self.best):
            return sum(self.best)
        return None


class SectorTracker:
    """Sektorių kirtimai iš LapDistPct (interpoliuojant tarp kadrų). Ratas, kuriame
    buvai boksuose ar „teleportavaisi“ (tow / reset), sektoriams negalioja."""

    MAX_STEP = 0.03  # didesnis šuolis per kadrą = teleportas

    def __init__(self):
        self.reset(())

    def reset(self, bounds):
        self.bounds = tuple(bounds)
        n = len(self.bounds)
        self.cur = [None] * n
        self.cur_improved = [False] * n
        self.last = [None] * n
        self.last_improved = [False] * n
        self.best = [None] * n
        self.idx = -1
        self.sec_start = None  # sektoriaus pradžios laikas (None = nežinoma -> negalioja)
        self.sec_valid = False
        self.prev = None  # (t, pct)
        self.lap_done_t = -1e9
        self.t = 0.0

    def _sector_of(self, pct: float) -> int:
        k = 0
        for i, b in enumerate(self.bounds):
            if pct >= b:
                k = i
        return k

    def update(self, t: float, pct: float, on_pit: bool, bounds):
        if tuple(bounds) != self.bounds:
            self.reset(bounds)
        self.t = t
        if not self.bounds or pct is None or not math.isfinite(pct) or pct < 0:
            self.prev = None
            self.sec_start = None
            return
        if self.prev is None:
            self.prev = (t, pct)
            self.idx = self._sector_of(pct)
            self.sec_start = None
            return
        t0, p0 = self.prev
        self.prev = (t, pct)
        d = pct - p0
        wrapped = d < -0.5
        if wrapped:
            d += 1.0
        if d < 0 or d > self.MAX_STEP:  # atgal arba teleportas
            self.sec_start = None
            self.idx = self._sector_of(pct)
            return
        if on_pit:
            self.sec_valid = False
        if d == 0:
            return
        # perėjom ribas: kirtimo laikas interpoliuojamas tarp kadrų
        n = len(self.bounds)
        p1 = p0 + d  # be apsukimo (gali būti > 1)
        cross = []
        for lap_off in (0.0, 1.0):
            for j in range(n):
                x = self.bounds[j] + lap_off
                if j == 0 and lap_off == 0.0:
                    continue  # linija 0.0 kertama tik kaip 1.0
                if p0 < x <= p1:
                    cross.append((x, j))
        cross.sort()
        for x, j in cross:
            tc = t0 + (x - p0) / d * (t - t0)
            self._finish_sector((j - 1) % n, tc)
            if j == 0:
                self._finish_lap(tc)
            self._start_sector(j, tc, on_pit)
        self.idx = self._sector_of(pct)

    def _finish_sector(self, k, tc):
        if self.sec_start is None or not self.sec_valid or not (0 <= k < len(self.cur)):
            return
        dt = tc - self.sec_start
        if dt <= 0:
            return
        dt = float(dt)
        self.cur[k] = dt
        if self.best[k] is None or dt < self.best[k]:
            self.best[k] = dt
            self.cur_improved[k] = True

    def _start_sector(self, k, tc, on_pit):
        self.sec_start = tc
        self.sec_valid = not on_pit

    def _finish_lap(self, tc):
        self.last = list(self.cur)
        self.last_improved = list(self.cur_improved)
        n = len(self.bounds)
        self.cur = [None] * n
        self.cur_improved = [False] * n
        self.lap_done_t = tc

    def state(self) -> SectorState:
        el = (self.t - self.sec_start) if self.sec_start is not None else 0.0
        return SectorState(bounds=self.bounds, current=tuple(self.cur), last=tuple(self.last),
                           best=tuple(self.best), index=self.idx, elapsed=el, improved=tuple(self.cur_improved),
                           last_improved=tuple(self.last_improved), lap_done_age=self.t - self.lap_done_t)


# ---------------------------------------------------------------- iRating
BR1 = 1600.0 / math.log(2.0)


def _chance(a: float, b: float) -> float:
    """Tikimybė, kad a aplenks b (bendruomenės iRating skaičiuoklės formulė)."""
    ea, eb = math.exp(-a / BR1), math.exp(-b / BR1)
    num = (1 - ea) * eb
    den = (1 - eb) * ea + num
    return num / den if den > 0 else 0.5


def irating_changes(field_: list) -> dict:
    """[(idx, irating, finish_pos 1..n)] vienos klasės -> {idx: prognozuojamas pokytis}.

    Visi laikomi startavusiais. Tikslumas ~±1–3 iR (oficiali formulė neskelbiama)."""
    n = len(field_)
    if n < 2:
        return {}
    rs = [max(1.0, float(r or 1350)) for _, r, _ in field_]
    out = {}
    for i, (idx, _, pos) in enumerate(field_):
        expected = sum(_chance(rs[i], rs[j]) for j in range(n)) - 0.5
        fudge = (n / 2.0 - pos) / 100.0
        out[idx] = (n - pos - expected - fudge) * 200.0 / n
    return out


def project_irating(cars) -> dict:
    """Snapshot.cars -> {idx: iR pokytis} pagal dabartines klasės pozicijas."""
    by_class = {}
    for r in cars:
        if r.class_pos and r.irating > 0:
            by_class.setdefault(r.class_id, []).append((r.idx, r.irating, r.class_pos))
    out = {}
    for rows in by_class.values():
        rows.sort(key=lambda x: x[2])
        rows = [(idx, ir, i + 1) for i, (idx, ir, _) in enumerate(rows)]
        out.update(irating_changes(rows))
    return out


# ---------------------------------------------------------------- likę ratai lenktynėse
def laps_left_timed(time_remain: float, my_pct: float, my_lap: float,
                    leader_pct: float | None = None, leader_lap: float | None = None) -> float | None:
    """Kiek ratų (su dalimi) dar nuvažiuosiu laiko lenktynėse.

    Lenktynės baigiasi, kai bendras lyderis kerta liniją pasibaigus laikui; aš baigiu, kai po to
    pirmą kartą kertu liniją. Kai lyderio duomenų nėra (arba lyderis - aš), skaičiuojama mano tempu."""
    if not (my_lap and my_lap > 0) or time_remain is None or time_remain > 1e6:
        return None
    t = max(0.0, float(time_remain))
    p = float(my_pct) % 1.0
    if leader_lap and leader_lap > 0 and leader_pct is not None:
        pl = float(leader_pct) % 1.0
        k_l = max(1, math.ceil(t / leader_lap + pl - 1e-9))
        t_end = (k_l - pl) * leader_lap  # kada lyderis gaus finišo vėliavą
    else:
        t_end = t
    k = max(1, math.ceil(t_end / my_lap + p - 1e-9))
    return k - p


def clean_fuel_avg(hist) -> float | None:
    """Vidutinės kuro sąnaudos per ratą be „geltonų“ / lėtų ratų (jie gerokai mažesni už medianą)."""
    vals = [float(x) for x in hist if x and x > 0]
    if not vals:
        return None
    med = sorted(vals)[len(vals) // 2]
    keep = [v for v in vals if v >= 0.85 * med]
    return sum(keep) / len(keep) if keep else None
