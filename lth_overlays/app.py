"""LTH Overlays programa.

Gijos:
- variklio gija: laukia iRacing kadrų, skaičiuoja (30 Hz), kas 0,1 s paskelbia
  momentinę būseną (Snapshot). Jokio UI darbo.
- UI gija: kas 0,1 s paima naujausią būseną ir išdalina valdikliams;
  valdiklis perpiešiamas tik jei pasikeitė rodomi skaičiai.

Paleidimas:
    python run.py              # iRacing
    python run.py --demo       # sintetinė lenktynė be iRacing
    python run.py --replay f.npz
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QGuiApplication, QIcon, QImage, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from lth_timing import VERSION
from lth_timing.engine import Snapshot, TimingEngine
from lth_timing.engineer import Engineer

from . import win32
from .config import Config, app_dir
from .registry import BY_NAME, CATEGORIES, WIDGETS

HOTKEY_EDIT = 0x4C54  # "LT"
HOTKEY_HIDE = 0x4C55
HOTKEY_RAIN = 0x4C56
HOTKEY_PROFILE = 0x4C57
HOTKEY_WIDGET0 = 0x4D00  # + valdiklio indeksas registre

# Valdiklio atnaujinimo dažnis: kas kiek UI „tikų“ (1 tikas = 0,1 s) - iš registro
RATES = {w.name: w.rate for w in WIDGETS}


# ----------------------------------------------------------------------
class EngineThread(threading.Thread):
    def __init__(self, make_source, config: Config):
        super().__init__(daemon=True, name="lth-engine")
        self.make_source = make_source
        self.config = config
        self.latest: Snapshot = Snapshot()
        self.stop_flag = threading.Event()
        self.update_us = 0.0
        self.fps = None
        self.error = None
        self.inputs_wanted = False
        self.timing = None  # UI įjungė Inputs valdiklį: reikia kiekvieno kadro (60 Hz)
        self.connected = False
        self.forget_map = False

    def run(self):
        """Gija nenutrūksta dėl klaidos: viską rašom į engine.log ir bandom iš naujo."""
        log = _EngineLog()
        log.write(f"start v{VERSION}")
        last_err, repeats = None, 0
        while not self.stop_flag.is_set():
            try:
                self._run_once(log)
                return
            except Exception:  # noqa: BLE001
                import traceback
                tb = traceback.format_exc()
                if tb != last_err:
                    log.write("ERROR\n" + tb)
                    last_err, repeats = tb, 0
                else:
                    repeats += 1
                    if repeats in (10, 100, 1000):
                        log.write(f"(same error repeated {repeats} times)")
                self.latest = Snapshot()
                time.sleep(2.0)

    def _run_once(self, log):
        try:
            src = self.make_source()
        except Exception as e:  # pvz. ne Windows
            self.error = str(e)
            log.write(f"source error: {e}")
            return
        hz = float(self.config.data.get("engine_hz", 20))
        eng = TimingEngine(rate_hz=hz, maps_dir=os.path.join(app_dir(), "maps"))
        self.timing = eng  # UI greitam keliui (Inputs / Dash 60 Hz)
        base_gap = max(0.0, 1.0 / hz - 0.006)
        engineer = Engineer()
        statelog = _StateLog()
        last_snap = last_eng = 0.0
        msgs = []
        idle = True
        announced = False
        driving = False
        self.cpu_s = 0.0
        tt = time.thread_time()
        while not self.stop_flag.is_set():
            now_tt = time.thread_time()
            self.cpu_s += now_tt - tt
            tt = now_tt
            inputs = self.inputs_wanted
            eng.player.inputs_enabled = inputs
            tel = self.config.data.get("telemetry") or {}
            eng.recorder.enabled = bool(tel.get("record", True))
            min_gap = 0.0 if inputs else base_gap
            if eng.recorder.enabled and driving:  # telemetrijai reikia tankesnių kadrų (30 arba 60 Hz)
                min_gap = min(min_gap, 0.0 if int(tel.get("hz", 30) or 30) >= 60 else 1 / 30 - 0.006)
            if self.forget_map:
                self.forget_map = False
                eng.trackmap.forget()
            f = src.wait_frame(200, min_gap) if hasattr(src, "min_interval_supported") else src.wait_frame(200)
            if f is None:
                if not getattr(src, "connected", False):
                    self.connected = False
                    if not idle or not announced:
                        self.latest = Snapshot()
                        idle = True
                        announced = True
                        log.write("iRacing not connected (waiting)")
                    time.sleep(0.8)  # miego režimas: iRacing neveikia
                continue
            if idle:
                announced = True
                log.write("iRacing connected, receiving frames")
            idle = False
            self.connected = True
            eng.set_session(src.session)
            driving = bool(f.IsOnTrack) and not bool(f.IsReplayPlaying)
            t0 = time.perf_counter()
            eng.update(f)
            dt = (time.perf_counter() - t0) * 1e6
            self.update_us = self.update_us * 0.98 + dt * 0.02
            now = time.monotonic()
            active = True
            period = 0.1 if active else 1.0  # garaže / meniu - 1 Hz
            if now - last_snap < period:
                continue
            last_snap = now
            snap = eng.snapshot()
            if now - last_eng >= 0.5:
                last_eng = now
                types = self.config.widget("engineer").get("types", {})
                engineer.enabled = {k for k, v in types.items() if v}
                msgs = engineer.update(snap, f)
            snap.messages = msgs
            self.fps = f.FrameRate
            self.latest = snap
            statelog.write(snap, f)
        src.close()


def _ui_log(text: str):
    """Sąsajos klaidos -> %APPDATA%\\LTH Overlays\\ui.log (pythonw neturi konsolės)."""
    try:
        with open(os.path.join(app_dir(), "ui.log"), "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}\n")
    except OSError:
        pass


def _install_excepthook():
    import traceback

    def hook(etype, value, tb):
        _ui_log("".join(traceback.format_exception(etype, value, tb)))
    sys.excepthook = hook


class _EngineLog:
    """%APPDATA%\\LTH Overlays\\engine.log - prisijungimo būsena ir klaidos."""

    def __init__(self):
        try:
            self.path = os.path.join(app_dir(), "engine.log")
            if os.path.exists(self.path) and os.path.getsize(self.path) > 200_000:
                os.replace(self.path, self.path + ".old")
        except OSError:
            self.path = None

    def write(self, text):
        if not self.path:
            return
        try:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}\n")
        except OSError:
            self.path = None


class _StateLog:
    """Rašo į %APPDATA%\\LTH Overlays\\visibility.log, kai pasikeičia iRacing būsena."""

    def __init__(self):
        self.last = None
        try:
            self.path = os.path.join(app_dir(), "visibility.log")
            if os.path.exists(self.path) and os.path.getsize(self.path) > 200_000:
                os.replace(self.path, self.path + ".old")
        except OSError:
            self.path = None

    def write(self, snap, f):
        if not self.path:
            return
        state = (bool(f.IsOnTrack), bool(f.IsReplayPlaying), f.CamCarIdx, f.PlayerCarIdx, snap.watching,
                 snap.session_type, len(snap.cars), f.IsInGarage, f.CamCameraState)
        if state == self.last:
            return
        self.last = state
        try:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%H:%M:%S')} on_track={state[0]} replay={state[1]} cam={state[2]} "
                         f"player={state[3]} watching={state[4]} session={state[5]} cars={state[6]} "
                         f"in_garage={state[7]} cam_state={state[8]}\n")
        except OSError:
            self.path = None


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callbacks: dict):
        super().__init__()
        self.callbacks = callbacks

    def nativeEventFilter(self, event_type, message):
        cb = self.callbacks.get(win32.hotkey_from_msg(message))
        if cb is not None:
            QTimer.singleShot(0, cb)
        return False, 0


# ----------------------------------------------------------------------
class OverlayApp(QObject):
    def __init__(self, app: QApplication, make_source, config: Config, virtual_screen: QRect | None = None):
        super().__init__()
        self.app = app
        self.config = config
        self.virtual_screen = virtual_screen
        self.theme = config.data.get("theme", "lth")
        self.perf = {}
        self.perf_hist = []  # (cpu, ram, fps) kas sekundę - Control Center grafikui
        self.editing = False
        self.idle = False
        self.hidden_all = False
        self.control = None  # ControlCenter (sukuriamas pirmą kartą atidarant)
        self._preview = None
        self._tick = 0
        self._proc = win32.ProcStats()
        self._hotkeys = {}
        self.widgets = {}
        for spec in WIDGETS:
            self.widgets[spec.name] = spec.load()(self)
        self.engine = EngineThread(make_source, config)
        self._install_gc()
        from .chat import ChatHub
        from .obs import ObsServer
        self.chat = ChatHub()
        from .pb import PersonalBests
        self.pbs = PersonalBests(os.path.join(os.path.dirname(config.path), "pb.json")
                                 if getattr(config, "path", None) else None)
        self.obs = ObsServer(self)

    def _install_gc(self):
        """Šiukšlių surinkimas tik UI gijoje. Automatinis Python GC gali pasileisti bet kurioje gijoje
        (variklis, OBS serveris, chat) ir ten sunaikinti Qt langus - tai nulaužia Qt. Todėl automatinis
        GC išjungiamas, o ciklai renkami laikmačiu UI gijoje (be to - jokių atsitiktinių pauzių piešiant)."""
        import gc
        gc.disable()
        self._gc_n = 0

        def collect():
            self._gc_n += 1
            gc.collect(2 if self._gc_n % 60 == 0 else (1 if self._gc_n % 10 == 0 else 0))
        self._gc_timer = QTimer(self)
        self._gc_timer.setTimerType(Qt.TimerType.CoarseTimer)
        self._gc_timer.timeout.connect(collect)
        self._gc_timer.start(1000)

    # ---- kontekstas valdikliams ----
    def screens(self) -> list:
        """Visi monitoriai: [(pavadinimas, QRect)] virtualaus darbalaukio koordinatėmis, pagrindinis - pirmas.

        Testams / peržiūrai galima perduoti virtual_screen (QRect arba QRect sąrašą)."""
        vs = self.virtual_screen
        if vs is not None:
            rects = vs if isinstance(vs, (list, tuple)) else [vs]
            return [(f"Display {i + 1}", QRect(r)) for i, r in enumerate(rects)]
        prim = QGuiApplication.primaryScreen()
        out = [(prim.name(), prim.geometry())] if prim is not None else []
        for s in QGuiApplication.screens():
            if s is not prim:
                out.append((s.name(), s.geometry()))
        return out or [("Display 1", QRect(0, 0, 1920, 1080))]

    def screen_rect(self) -> QRect:
        """Pagrindinis monitorius."""
        return self.screens()[0][1]

    def screen_for(self, x: int, y: int) -> QRect | None:
        """Monitorius, kuriame yra taškas (arba None - pvz. atjungtas monitorius)."""
        for _, r in self.screens():
            if r.contains(int(x), int(y)):
                return r
        return None

    def screen_for_rect(self, r: QRect) -> QRect | None:
        """Monitorius, kuriame yra didžiausia lango dalis (None - nė viename)."""
        best, area = None, 0
        for _, sr in self.screens():
            i = sr.intersected(r)
            a = i.width() * i.height() if not i.isEmpty() else 0
            if a > area:
                best, area = sr, a
        return best

    def desktop_rect(self) -> QRect:
        """Visų monitorių sąjunga."""
        rects = [r for _, r in self.screens()]
        u = QRect(rects[0])
        for r in rects[1:]:
            u = u.united(r)
        return u

    def save_config(self):
        try:
            self.config.save()
        except OSError:
            pass

    def save_config_soon(self):
        """Daug pakeitimų iš eilės (slankiklis) - į diską rašom vieną kartą."""
        t = getattr(self, "_save_timer", None)
        if t is None:
            t = self._save_timer = QTimer(self)
            t.setSingleShot(True)
            t.setInterval(600)
            t.timeout.connect(self.save_config)
        t.start()

    def widget_changed(self, name):
        self.widgets[name].apply_settings()
        ow = self.obs._inst.get(name)
        if ow is not None:
            ow.apply_settings()
        self.save_config_soon()
        self._update_inputs_flag()
        self._refresh_visibility(force=True)
        self._sync_tray()

    def all_widgets_changed(self):
        """Tema, šriftas, spalvos ar profilis pasikeitė - perpiešiam viską."""
        self.theme = self.config.data.get("theme", "lth")
        for w in self.widgets.values():
            w.apply_settings()
        self.obs.all_widgets_changed()
        self.save_config_soon()
        self._update_inputs_flag()
        self._refresh_visibility(force=True)
        self._sync_tray()

    theme_changed = all_widgets_changed

    def geometry_changed(self, name):
        """Valdiklis nutemptas / pakeistas dydis ekrane - Control Center atnaujina formą."""
        if self.control is not None:
            self.control.geometry_changed(name)

    def open_settings(self, name=None):
        self.open_control_center(page="widget" if name else None, widget=name)

    def open_control_center(self, page=None, widget=None):
        if self.control is None:
            from .control.center import ControlCenter
            self.control = ControlCenter(self)
        self.control.open(page, widget)

    def set_widget_visible(self, name, on: bool):
        self.config.widget(name)["visible"] = bool(on)
        self.widget_changed(name)

    def _update_inputs_flag(self):
        self.engine.inputs_wanted = any(
            spec.needs_inputs and self.config.widget(spec.name).get("visible") for spec in WIDGETS)

    # ---- paleidimas ----
    def start(self, tray=True):
        win32.lower_priority()
        self.engine.start()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.CoarseTimer)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(100)
        self.top_timer = QTimer(self)
        self.top_timer.setTimerType(Qt.TimerType.VeryCoarseTimer)
        self.top_timer.timeout.connect(self._keep_on_top)
        self.top_timer.start(2000)
        if tray:
            self._make_tray()
            self._first_run_autostart()
            QTimer.singleShot(5000, self._check_preview_flag)
        self._update_inputs_flag()
        # monitorius prijungtas / atjungtas / pakeista rezoliucija - perstatom valdiklius
        gapp = QGuiApplication.instance()
        gapp.screenAdded.connect(lambda *_: QTimer.singleShot(800, self._screens_changed))
        gapp.screenRemoved.connect(lambda *_: QTimer.singleShot(800, self._screens_changed))
        self._filter = HotkeyFilter({HOTKEY_EDIT: self.toggle_edit, HOTKEY_HIDE: self.toggle_hide_all,
                                     HOTKEY_RAIN: self.next_rain_tip,
                                     win32.SHOW_REQUEST: self._show_request})
        self.app.installNativeEventFilter(self._filter)
        self.register_hotkeys()
        self.app.aboutToQuit.connect(self._shutdown)
        self.obs.apply()

    def next_rain_tip(self):
        w = self.widgets.get("rain_master")
        if w is not None:
            w.next_tip()

    def _screens_changed(self):
        for w in self.widgets.values():
            w.apply_settings()
        if self.control is not None:
            lp = self.control._pages.get("layout")
            if lp is not None:
                lp.canvas.update()

    def _show_request(self):
        """Kitas paleidimas paprašė atidaryti Control Center (žinutė ateina kiekvienam langui - vieną kartą)."""
        now = time.monotonic()
        if now - getattr(self, "_last_show_req", 0.0) > 1.0:
            self._last_show_req = now
            self.open_control_center()

    def _hotkey_actions(self):
        """[(veiksmas, id, funkcija)] - bendri ir kiekvieno valdiklio rodymo / slėpimo."""
        out = [("edit", HOTKEY_EDIT, self.toggle_edit), ("toggle_all", HOTKEY_HIDE, self.toggle_hide_all),
               ("rain_next", HOTKEY_RAIN, self.next_rain_tip), ("next_profile", HOTKEY_PROFILE, self.next_profile)]
        for i, spec in enumerate(WIDGETS):
            out.append((f"widget:{spec.name}", HOTKEY_WIDGET0 + i, lambda n=spec.name: self.toggle_widget(n)))
        return out

    def register_hotkeys(self) -> dict:
        """(Per)registruoja karštuosius klavišus iš nustatymų. Grąžina {veiksmas: ar pavyko}."""
        for hid in getattr(self, "_hk_ids", ()):
            win32.unregister_hotkey(hid)
        hk = self.config.data.get("hotkeys") or {}
        out, ids, cbs = {}, [], {win32.SHOW_REQUEST: self._show_request}
        for action, hid, cb in self._hotkey_actions():
            parsed = win32.parse_hotkey(hk.get(action, ""))
            if not parsed:
                if not action.startswith("widget:"):
                    out[action] = False
                continue
            ok = win32.register_hotkey(hid, *parsed)
            out[action] = ok
            if ok:
                ids.append(hid)
                cbs[hid] = cb
        self._hk_ids = ids
        if hasattr(self, "_filter"):
            self._filter.callbacks = cbs
        self._hotkeys = out
        return out

    def next_profile(self):
        keys = list(self.config.data.get("profiles") or {})
        if len(keys) < 2:
            return
        cur = self.config.profile_key
        nxt = keys[(keys.index(cur) + 1) % len(keys)] if cur in keys else keys[0]
        self.set_profile(nxt, manual=True)

    def toggle_widget(self, name):
        if name in self.widgets:
            self.set_widget_visible(name, not self.config.widget(name).get("visible"))
            if self.control is not None:
                self.control.profile_changed()

    def quit(self):
        """Tikras išėjimas (tray / Control Center). Control Center tada nebesislepia į tray."""
        self.quitting = True
        if self.control is not None:
            self.control.hide()
        self.app.quit()

    def _shutdown(self):
        self.engine.stop_flag.set()
        self.obs.stop()
        self.chat.stop()
        for hid in getattr(self, "_hk_ids", ()):
            win32.unregister_hotkey(hid)
        self.save_config()

    def _keep_on_top(self):
        for w in self.widgets.values():
            w.keep_on_top()
        tb = getattr(self, "toolbar", None)
        if tb is not None and tb.isVisible():
            win32.keep_on_top(tb)

    # ---- pagrindinis ciklas (UI) ----
    def _on_tick(self):
        self._tick += 1
        snap = self.engine.latest
        if self._tick % 10 == 0:
            cpu, ram = self._proc.sample()
            self.perf.update(cpu=cpu, ram=ram, engine_us=self.engine.update_us, fps=self.engine.fps)
            self.perf_hist.append((cpu, ram, self.engine.fps))
            del self.perf_hist[:-120]
            if self.control is not None and self.control.isVisible():
                self.control.tick(snap)
        pl = snap.player
        # stovi garaže / boksuose / po finišo: greiti valdikliai (Inputs, žemėlapis) sulėtinami
        self.idle = bool(snap.connected and not snap.replay and not snap.watching and not self.editing
                         and (not snap.on_track or (pl is not None and pl.valid and pl.speed < 0.5)))
        if not snap.connected and self.editing:
            snap = self.preview_snapshot()
        if snap.connected:
            if self._tick % 10 == 5:
                self.pbs.observe(snap)
                if (self.config.data.get("telemetry") or {}).get("auto_save_best", True):
                    from .control.telemetry_page import autosave_best
                    tm = getattr(self.engine.timing, "trackmap", None)
                    autosave_best(getattr(self.engine.timing, "recorder", None), self.__dict__.setdefault("_tel_state", {}),
                                  tm.points if tm is not None else None)
            self._auto_profile(snap)
            self._apply_class_colors(snap)
        self._refresh_visibility(snap=snap)
        for name, w in self.widgets.items():
            if not w.isVisible():
                continue
            if self._tick % RATES.get(name, 1) == 0:
                w.push(snap)

    def _auto_profile(self, snap):
        cfg = self.config.data
        changed = False
        if cfg.get("auto_profile") and snap.session_type in cfg["profiles"] and snap.session_type != self.config.profile_key:
            self.config.set_profile(snap.session_type)
            changed = True
        theme = self.config.theme_for(snap.league_id, snap.series_id)
        if theme != self.theme:
            self.theme = theme
            changed = True
        if changed:
            for w in self.widgets.values():
                w.apply_settings()
            self._update_inputs_flag()
            self._sync_tray()

    def _apply_class_colors(self, snap):
        """Vartotojo klasių spalvos (Appearance) - pagal klasės pavadinimą."""
        cc = self.config.data.get("class_colors") or {}
        if not cc:
            return
        cache = {}
        for name, hexv in cc.items():
            try:
                cache[name] = int(str(hexv).lstrip("#")[:6], 16)
            except ValueError:
                pass
        for r in snap.cars:
            v = cache.get(r.class_name)
            if v is not None:
                r.class_color = v

    def _refresh_visibility(self, snap=None, force=False):
        snap = snap or self.engine.latest
        active = snap.connected and not self.hidden_all  # rodom, kai iRacing veikia (trasoje, garaže, stebint)
        for name, w in self.widgets.items():
            want = (active or self.editing) and w.wants_visible(snap)
            if want and not w.isVisible():
                w.show()
                w.push(snap, force=True)
            elif not want and w.isVisible():
                w.hide()

    def preview_snapshot(self, wait: bool = False):
        """Be iRacing (redagavimas, Control Center peržiūros) - sintetinės lenktynės duomenys.

        Skaičiuojama fone (~3-4 s vieną kartą); kol neparuošta, grąžinama tuščia būsena."""
        if self._preview is not None:
            return self._preview
        th = getattr(self, "_preview_thread", None)
        if th is None:
            th = self._preview_thread = threading.Thread(target=self._build_preview, daemon=True,
                                                         name="lth-preview")
            th.start()
        if wait:
            th.join()
            return self._preview
        if not hasattr(self, "_empty_preview"):
            self._empty_preview = Snapshot()
        return self._empty_preview

    def _build_preview(self):
        try:
            from .sources import DemoSource
            demo = DemoSource(fast_forward=200, realtime=False)
            eng = TimingEngine()
            eng.player.inputs_enabled = True
            eng.set_session(demo.session)
            for _ in range(60 * 200):
                eng.update(demo.wait_frame())
            snap = eng.snapshot()
            snap.connected = False
            self._preview = snap
        except Exception:  # noqa: BLE001
            import traceback
            _ui_log("preview failed\n" + traceback.format_exc())
            self._preview = Snapshot()

    def toggle_hide_all(self):
        """Karštasis klavišas: paslėpti / grąžinti visus valdiklius (pvz. transliacijai)."""
        self.hidden_all = not self.hidden_all
        self._refresh_visibility(force=True)
        if hasattr(self, "act_hide"):
            self.act_hide.blockSignals(True)
            self.act_hide.setChecked(self.hidden_all)
            self.act_hide.blockSignals(False)

    # ---- redagavimas ----
    def toggle_edit(self):
        self.editing = not self.editing
        for w in self.widgets.values():
            w.set_editing(self.editing)
        self._refresh_visibility(force=True)
        if hasattr(self, "act_edit"):
            self.act_edit.blockSignals(True)
            self.act_edit.setChecked(self.editing)
            self.act_edit.blockSignals(False)
        if self.control is not None:
            self.control.editing_changed(self.editing)
        self._show_toolbar(self.editing)

    def _show_toolbar(self, on: bool):
        tb = getattr(self, "toolbar", None)
        if on:
            if tb is None:
                from .edit_toolbar import EditToolbar
                tb = self.toolbar = EditToolbar(self)
            tb.place()
            tb.show()
            tb.raise_()
        elif tb is not None:
            tb.hide()

    # ---- tray ----
    def _make_tray(self):
        self.tray = QSystemTrayIcon(make_icon(), self.app)
        self.tray.setToolTip(f"LTH Overlays {VERSION}")
        self.tray.activated.connect(self._tray_activated)
        menu = QMenu()
        act_cc = QAction("Open Control Center", menu)
        act_cc.triggered.connect(lambda _=False: self.open_control_center())
        menu.addAction(act_cc)
        menu.setDefaultAction(act_cc)
        menu.addSeparator()
        hk = self.config.data.get("hotkeys") or {}
        self.act_edit = QAction(f"Edit layout ({hk.get('edit', '')})", menu, checkable=True)
        self.act_edit.triggered.connect(lambda _: self.toggle_edit())
        menu.addAction(self.act_edit)
        self.act_hide = QAction(f"Hide all overlays ({hk.get('toggle_all', '')})", menu, checkable=True)
        self.act_hide.triggered.connect(lambda _: self.toggle_hide_all())
        menu.addAction(self.act_hide)
        menu.addSeparator()
        self._widget_actions = {}
        wmenu = menu.addMenu("Widgets")
        for cat in CATEGORIES:
            sub = wmenu.addMenu(cat)
            for spec in [w for w in WIDGETS if w.category == cat]:
                act = QAction(spec.title, sub, checkable=True)
                act.setChecked(bool(self.config.widget(spec.name).get("visible")))
                act.toggled.connect(lambda v, n=spec.name: self.set_widget_visible(n, v))
                sub.addAction(act)
                self._widget_actions[spec.name] = act
        self._profile_menu = menu.addMenu("Profile")
        self._profile_menu.aboutToShow.connect(self._fill_profile_menu)
        menu.addSeparator()
        quit_act = QAction("Quit LTH Overlays", menu)
        quit_act.triggered.connect(self.quit)
        menu.addAction(quit_act)
        self.tray.setContextMenu(menu)
        self.tray.show()
        self._menu = menu

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.open_control_center()

    def _fill_profile_menu(self):
        m = self._profile_menu
        m.clear()
        for key, p in self.config.data["profiles"].items():
            a = QAction(p.get("name", key), m, checkable=True)
            a.setChecked(key == self.config.profile_key)
            a.triggered.connect(lambda _=False, k=key: self.set_profile(k))
            m.addAction(a)

    def _sync_tray(self):
        for name, act in getattr(self, "_widget_actions", {}).items():
            on = bool(self.config.widget(name).get("visible"))
            if act.isChecked() != on:
                act.blockSignals(True)
                act.setChecked(on)
                act.blockSignals(False)

    def _launcher_exe(self) -> str | None:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        exe = os.path.join(root, "LTH Overlays.exe")
        return exe if os.path.exists(exe) else None

    def set_autostart(self, on) -> bool:
        if win32.is_packaged():  # Store versija: paleidimą su Windows įjungia Windows nustatymuose
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl("ms-settings:startupapps"))
            return False
        exe = self._launcher_exe()
        ok = win32.set_autostart(bool(on), exe) if (exe or not on) else False
        self.config.data["autostart"] = bool(on) and ok
        self.save_config()
        return ok

    def autostart_enabled(self) -> bool:
        return win32.autostart_enabled()

    def _first_run_autostart(self):
        """Pirmą kartą paleidus - įsijungia automatinis paleidimas (galima išjungti meniu)."""
        d = self.config.data
        exe = self._launcher_exe()
        win32.migrate_autostart(exe)  # senas .vbs Startup aplanke -> registro Run įrašas
        # v0.6.1: įrašas į Windows paleidimą daromas tik vartotojui sutikus (tutorialo paskutinis žingsnis
        # arba General). Tylus „persistence“ pirmo paleidimo metu - viena iš antivirusų euristikų.
        return

    def save_preview(self):
        """Išsaugo visų valdiklių vaizdą (demo duomenys) į %APPDATA%\\LTH Overlays\\preview.png."""
        path = os.path.join(app_dir(), "preview.png")
        try:
            render_screenshot(self, path, sim_seconds=200)
        except Exception:  # noqa: BLE001
            import traceback
            _ui_log("preview failed\n" + traceback.format_exc())

    def _check_preview_flag(self):
        flag = os.path.join(app_dir(), "make_preview.flag")
        if os.path.exists(flag):
            try:
                os.remove(flag)
            except OSError:
                pass
            self.save_preview()

    def set_profile(self, key, manual=True):
        self.config.set_profile(key)
        if manual:
            self.config.data["auto_profile"] = False
        self.all_widgets_changed()
        if self.control is not None:
            self.control.profile_changed()

    _set_profile = set_profile


def make_icon() -> QIcon:
    from .brand import app_icon
    return app_icon()


# ----------------------------------------------------------------------
def render_screenshot(oapp: OverlayApp, path: str, sim_seconds: float = 300):
    """Nupiešia visus valdiklius ant ekrano dydžio fono (peržiūrai be iRacing)."""
    from .sources import DemoSource
    demo = DemoSource(fast_forward=0, realtime=False)
    eng = TimingEngine()
    eng.player.inputs_enabled = True
    eng.set_session(demo.session)
    ing = Engineer()
    snap = None
    for i in range(int(sim_seconds * 60)):
        f = demo.wait_frame()
        eng.update(f)
        if i % 30 == 0 and demo.sim.t > sim_seconds - 60:
            snap = eng.snapshot()
            snap.messages = ing.update(snap, f) or snap.messages
    snap = eng.snapshot()
    msgs = ing._active or []
    if not msgs:
        from lth_timing.engineer import Message
        rr = next((r for r in snap.relative if not r.is_me and r.gap > 0 and r.delta is not None), None)
        if rr is not None:
            txt = (f"Ahead #{rr.car.number}: {rr.gap:.1f}s, you are {-rr.delta:.1f}/lap faster" if rr.delta < 0
                   else f"Ahead #{rr.car.number}: {rr.gap:.1f}s, he is {rr.delta:.1f}/lap faster")
            msgs = [Message("ahead", txt, 0, snap.t, snap.t)]
    snap.messages = msgs
    oapp.perf.update(cpu=0.6, ram=88, engine_us=46, fps=144)
    vs = oapp.screen_rect()
    W, H = vs.width(), vs.height()
    img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    g = QLinearGradient(0, 0, 0, H)
    g.setColorAt(0.0, QColor(96, 120, 150))
    g.setColorAt(0.55, QColor(70, 78, 86))
    g.setColorAt(0.56, QColor(48, 50, 54))
    g.setColorAt(1.0, QColor(30, 30, 32))
    p.fillRect(img.rect(), g)
    p.setPen(QColor(255, 255, 255, 40))
    f = QFont()
    f.setPixelSize(28)
    p.setFont(f)
    p.drawText(QRect(0, H // 2 - 40, W, 40), Qt.AlignmentFlag.AlignCenter, "(iRacing view)")
    for name, w in oapp.widgets.items():
        if not w.wants_visible(snap):
            continue
        w.push(snap, force=True)
        w.resize(w.width(), w.desired_height())
        pm = w.grab()
        p.drawPixmap(w.pos(), pm)
    p.end()
    img.save(path)
    return snap


def main(argv=None):
    ap = argparse.ArgumentParser(description="LTH Overlays")
    ap.add_argument("--demo", action="store_true", help="synthetic race without iRacing")
    ap.add_argument("--replay", help="play back a diagnostics recording (.npz)")
    ap.add_argument("--config", help="settings file")
    ap.add_argument("--screenshot", help="(development) save a picture of the widgets and exit")
    ap.add_argument("--edit", action="store_true", help="start in edit mode")
    ap.add_argument("--autostart", action="store_true", help="started with Windows: stay in the tray")
    ap.add_argument("--control", action="store_true", help="open the Control Center")
    args = ap.parse_args(argv)

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("LTH Overlays")

    if not args.screenshot:
        lock = win32.single_instance("Local\\LTHOverlaysSingleInstance")
        if lock is None:
            if args.autostart or not win32.request_show_running_instance():
                if not args.autostart:
                    QMessageBox.information(None, "LTH Overlays",
                                            "LTH Overlays is already running (icon next to the clock).")
            return 0

    _install_excepthook()
    config = Config(args.config)
    if args.demo:
        from .sources import DemoSource
        make_source = DemoSource
    elif args.replay:
        from .sources import PacedReplay
        make_source = lambda: PacedReplay(args.replay)  # noqa: E731
    else:
        from lth_timing.irsdk import LiveSource
        make_source = LiveSource

    if args.screenshot:
        oapp = OverlayApp(app, make_source, config, virtual_screen=QRect(0, 0, 1920, 1080))
        for w in oapp.widgets.values():
            w.apply_settings()
        render_screenshot(oapp, args.screenshot)
        return 0

    oapp = OverlayApp(app, make_source, config)
    oapp.live = not (args.demo or args.replay)
    oapp.start()
    if args.edit:
        QTimer.singleShot(300, oapp.toggle_edit)
    if args.control or (not args.autostart and config.data.get("open_control_center", True)):
        QTimer.singleShot(200, oapp.open_control_center)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
