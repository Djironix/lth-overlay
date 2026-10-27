"""Valdiklių peržiūros vaizdai Control Center'iui.

Kiekvienam valdikliui laikoma atskira (niekada nerodoma) to paties tipo
kopija: ji skaito tuos pačius nustatymus, bet nekeičia tikro overlay lango.
Vaizdas = grab() su dabartiniu momentiniu vaizdu (iRacing arba demo).
"""
from __future__ import annotations

from PySide6.QtGui import QPixmap

from ..registry import BY_NAME


class PreviewRenderer:
    def __init__(self, ctx):
        self.ctx = ctx
        self._inst = {}
        self._cache = {}  # name -> (raktas, QPixmap)

    def _widget(self, name):
        w = self._inst.get(name)
        if w is None:
            w = BY_NAME[name].load()(self.ctx)
            w.preview_mode = True
            w.editing = True  # parodo vietos rezervavimo turinį (pvz. vėliavai be vėliavos)
            self._inst[name] = w
        return w

    def snapshot(self):
        snap = self.ctx.engine.latest
        if not snap.connected:
            snap = self.ctx.preview_snapshot()
        return snap

    def render(self, name: str, snap=None, force: bool = False) -> QPixmap:
        snap = snap or self.snapshot()
        w = self._widget(name)
        cfg = self.ctx.config.widget(name)
        key = (id(snap), snap.t, repr(sorted((k, repr(v)) for k, v in cfg.items())), self.ctx.theme,
               self.ctx.config.data.get("font"), repr(self.ctx.config.data.get("custom_colors")))
        hit = self._cache.get(name)
        if hit is not None and hit[0] == key and not force:
            return hit[1]
        w.apply_settings()
        w.push(snap, force=True)
        w.resize(w.width(), w.final_height())
        pm = w.grab()
        self._cache[name] = (key, pm)
        return pm

    def invalidate(self, name=None):
        if name is None:
            self._cache.clear()
        else:
            self._cache.pop(name, None)
