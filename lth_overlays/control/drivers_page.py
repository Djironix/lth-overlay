"""Drivers puslapis: draugų / komandos draugų / „atsargiai“ žymos (paryškinami Standings ir Relative)."""
from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLineEdit

from .components import Card, ColorButton, Combo, button, clear_layout, label
from .pages import Page

TAGS = {"friend": ("Friend", "#ECBE58"), "team": ("Teammate", "#3DDC97"), "rival": ("Rival", "#FF8A1E"),
        "careful": ("Careful", "#FF4D5E"), "fast": ("Fast", "#B48CFF"), "lth": ("LTH", "#F2C94C"),
        "hub": ("iRacing Hub", "#5FD3C6")}  # ne mėlyna: mėlyna Relative reiškia lenkiamą mašiną
# Siūlomi sąrašai (neįjungti numatytai): raktas -> (pavadinimas, žyma, filtras)
SUGGESTED = (("lth", "LTH team", "lth", lambda d: d.get("team", "").strip().upper() == "LTH"),
             ("hub", "Lietuvos iRacing Hub", "hub", lambda d: True))


def suggested_drivers() -> list:
    """Patikrintas Lietuvos iRacing Hub narių sąrašas (iracing.lt) - [{id, name, team}]."""
    import json
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "drivers_lt.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return list(json.load(fh).get("drivers") or [])
    except (OSError, ValueError):
        return []


class DriversPage(Page):
    TITLE = "Drivers"
    SUBTITLE = "Tag friends, teammates and drivers to watch. Their names get your colour in Standings and Relative."

    def __init__(self, center):
        super().__init__(center)
        self.tagged = Card("Tagged drivers")
        self.tag_grid = QGridLayout()
        self.tag_grid.setHorizontalSpacing(10)
        self.tag_grid.setVerticalSpacing(6)
        self.tagged.add(self.tag_grid)
        add = QHBoxLayout()
        self.e_id = QLineEdit()
        self.e_id.setPlaceholderText("iRacing customer ID")
        self.e_id.setFixedWidth(170)
        self.e_name = QLineEdit()
        self.e_name.setPlaceholderText("Name (optional)")
        b_add = button("Add", None, "plus")
        b_add.clicked.connect(self._add_manual)
        add.addWidget(self.e_id)
        add.addWidget(self.e_name, 1)
        add.addWidget(b_add)
        self.tagged.add(add)
        self.content.addWidget(self.tagged)

        self.sugg = Card("Suggested lists", "Optional. Mark everyone from the LTH team or the whole Lithuanian "
                                            "iRacing Hub at once. Drivers you tagged yourself keep your tag.")
        self.sugg_grid = QGridLayout()
        self.sugg_grid.setHorizontalSpacing(12)
        self.sugg_grid.setVerticalSpacing(8)
        self.sugg.add(self.sugg_grid)
        self.content.addWidget(self.sugg)

        self.session = Card("In this session", "Click Tag to add a driver from the current session.")
        self.sess_grid = QGridLayout()
        self.sess_grid.setHorizontalSpacing(10)
        self.sess_grid.setVerticalSpacing(4)
        self.session.add(self.sess_grid)
        self.content.addWidget(self.session)
        self.content.addStretch(1)
        self._sess_key = None
        self._fill_suggested()
        self._fill_tagged()

    # ---- duomenys ----
    @property
    def friends(self) -> dict:
        return self.ctx.config.data.setdefault("friends", {})

    def _save(self):
        self.ctx.all_widgets_changed()

    def tag(self, uid: int, name: str, tag: str = "friend"):
        if not uid:
            return
        self.friends[str(uid)] = {"name": name, "tag": tag, "color": TAGS.get(tag, TAGS["friend"])[1]}
        self._save()
        self._fill_tagged()
        self._fill_session(force=True)

    def _add_manual(self):
        try:
            uid = int(self.e_id.text().strip())
        except ValueError:
            self.e_id.setFocus()
            return
        self.tag(uid, self.e_name.text().strip() or str(uid))
        self.e_id.clear()
        self.e_name.clear()

    def _remove(self, uid):
        self.friends.pop(str(uid), None)
        self._save()
        self._fill_tagged()
        self._fill_session(force=True)

    def _set(self, uid, key, value):
        d = self.friends.get(str(uid))
        if not isinstance(d, dict):
            return
        d[key] = value
        if key == "tag" and value in TAGS:
            d["color"] = TAGS[value][1]
            self._fill_tagged()
        self._save()

    # ---- UI ----
    # ---- siūlomi sąrašai ----
    def _list_count(self, key) -> int:
        return sum(1 for v in self.friends.values() if isinstance(v, dict) and v.get("src") == key)

    def _fill_suggested(self):
        clear_layout(self.sugg_grid)
        drivers = suggested_drivers()
        for r, (key, title, tag, flt) in enumerate(SUGGESTED):
            members = [d for d in drivers if flt(d)]
            on = self._list_count(key)
            self.sugg_grid.addWidget(label(title, "h3"), r, 0)
            self.sugg_grid.addWidget(label(f"{len(members)} drivers" + (f" · {on} marked" if on else ""), "faint"), r, 1)
            b = button("Remove" if on else "Add", "ghost" if on else None, "trash" if on else "plus")
            b.clicked.connect(lambda _=False, k=key: self._toggle_list(k))
            self.sugg_grid.addWidget(b, r, 2)
        self.sugg_grid.setColumnStretch(1, 1)

    def _toggle_list(self, key):
        spec = next(x for x in SUGGESTED if x[0] == key)
        if self._list_count(key):
            for uid in [u for u, v in self.friends.items() if isinstance(v, dict) and v.get("src") == key]:
                self.friends.pop(uid, None)
        else:
            _, _, tag, flt = spec
            for d in suggested_drivers():
                uid = str(d.get("id") or "")
                if not uid or not flt(d):
                    continue
                cur = self.friends.get(uid)
                if cur and not (isinstance(cur, dict) and cur.get("src")):
                    continue  # paties pažymėtas - nekeičiam
                if cur and isinstance(cur, dict) and cur.get("src") == "lth" and key == "hub":
                    continue  # LTH žyma svarbesnė už bendrą Hub
                self.friends[uid] = {"name": d.get("name", uid), "tag": tag, "color": TAGS[tag][1], "src": key}
        self._save()
        self._fill_suggested()
        self._fill_tagged()
        self._fill_session(force=True)

    def _fill_tagged(self):
        clear_layout(self.tag_grid)
        items = sorted(((u, v) for u, v in self.friends.items() if not (isinstance(v, dict) and v.get("src"))),
                       key=lambda kv: str((kv[1] or {}).get("name", "")).lower() if isinstance(kv[1], dict) else "")
        if not items:
            self.tag_grid.addWidget(label("Nobody tagged yet.", "faint"), 0, 0)
            return
        for r, (uid, d) in enumerate(items):
            d = d if isinstance(d, dict) else {"name": uid, "color": str(d), "tag": "friend"}
            tag = Combo({k: v[0] for k, v in TAGS.items()}, d.get("tag", "friend"), width=140)
            tag.changed.connect(lambda v, u=uid: self._set(u, "tag", v))
            col = ColorButton(d.get("color", "#ECBE58"))
            col.changed.connect(lambda v, u=uid: self._set(u, "color", v))
            rm = button("", "ghost", "trash", "Remove")
            rm.clicked.connect(lambda _=False, u=uid: self._remove(u))
            self.tag_grid.addWidget(label(d.get("name") or uid, "h3"), r, 0)
            self.tag_grid.addWidget(label(f"ID {uid}", "faint"), r, 1)
            self.tag_grid.addWidget(tag, r, 2)
            self.tag_grid.addWidget(col, r, 3)
            self.tag_grid.addWidget(rm, r, 4)
        self.tag_grid.setColumnStretch(0, 1)

    def _fill_session(self, force=False):
        snap = self.ctx.engine.latest
        live = snap.connected
        if not live:
            snap = self.ctx.preview_snapshot()
        cars = [r for r in snap.cars if r.user_id]
        key = (live, tuple((r.user_id, r.name) for r in cars), tuple(sorted(self.friends)))
        if key == self._sess_key and not force:
            return
        self._sess_key = key
        clear_layout(self.sess_grid)
        if not live:
            self.sess_grid.addWidget(label("Sample drivers - join a session in iRacing to tag real ones.", "faint"),
                                     0, 0, 1, 4)
        for i, r in enumerate(sorted(cars, key=lambda x: x.name.lower())):
            row = i + 1
            cur = self.friends.get(str(r.user_id))
            tagged = bool(cur) and not (isinstance(cur, dict) and cur.get("src"))
            b = button("Tagged" if tagged else "Tag", "ghost", "check" if tagged else "star")
            b.setEnabled(not tagged and live)
            b.clicked.connect(lambda _=False, u=r.user_id, n=r.name: self.tag(u, n))
            self.sess_grid.addWidget(label(r.name), row, 0)
            self.sess_grid.addWidget(label(r.class_name or "", "faint"), row, 1)
            self.sess_grid.addWidget(label(f"{r.irating} iR" if r.irating else "", "faint"), row, 2)
            self.sess_grid.addWidget(b, row, 3)
        self.sess_grid.setColumnStretch(0, 1)

    def on_show(self):
        self._fill_suggested()
        self._fill_tagged()
        self._fill_session()

    def tick(self, snap):
        if self.isVisible():
            self._fill_session()
