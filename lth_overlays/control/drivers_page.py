"""Drivers puslapis: draugų / komandos draugų / „atsargiai“ žymos (paryškinami Standings ir Relative)."""
from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLineEdit

from .components import Card, ColorButton, Combo, button, clear_layout, label
from .pages import Page

TAGS = {"friend": ("Friend", "#ECBE58"), "team": ("Teammate", "#3DDC97"), "rival": ("Rival", "#FF8A1E"),
        "careful": ("Careful", "#FF4D5E"), "fast": ("Fast", "#B48CFF")}


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

        self.session = Card("In this session", "Click Tag to add a driver from the current session.")
        self.sess_grid = QGridLayout()
        self.sess_grid.setHorizontalSpacing(10)
        self.sess_grid.setVerticalSpacing(4)
        self.session.add(self.sess_grid)
        self.content.addWidget(self.session)
        self.content.addStretch(1)
        self._sess_key = None
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
    def _fill_tagged(self):
        clear_layout(self.tag_grid)
        items = sorted(self.friends.items(), key=lambda kv: str((kv[1] or {}).get("name", "")).lower()
                       if isinstance(kv[1], dict) else "")
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
            tagged = str(r.user_id) in self.friends
            b = button("Tagged" if tagged else "Tag", "ghost", "check" if tagged else "star")
            b.setEnabled(not tagged and live)
            b.clicked.connect(lambda _=False, u=r.user_id, n=r.name: self.tag(u, n))
            self.sess_grid.addWidget(label(r.name), row, 0)
            self.sess_grid.addWidget(label(r.class_name or "", "faint"), row, 1)
            self.sess_grid.addWidget(label(f"{r.irating} iR" if r.irating else "", "faint"), row, 2)
            self.sess_grid.addWidget(b, row, 3)
        self.sess_grid.setColumnStretch(0, 1)

    def on_show(self):
        self._fill_tagged()
        self._fill_session()

    def tick(self, snap):
        if self.isVisible():
            self._fill_session()
