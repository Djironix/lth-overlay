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
from .widgets.engineer import EngineerWidget, PerfWidget
from .widgets.relative import RelativeWidget
from .widgets.standings import StandingsWidget
from .widgets.weather import WeatherWidget

HOTKEY_ID = 0x4C54  # "LT"
VK_E = 0x45

# Valdiklio atnaujinimo dažnis: kas kiek UI „tikų“ (1 tikas = 0,1 s)
RATES = {"relative": 1, "standings": 5, "engineer": 2, "weather": 10, "perf": 10}


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
        eng = TimingEngine(rate_hz=hz)
        min_gap = max(0.0, 1.0 / hz - 0.006)
        engineer = Engineer()
        statelog = _StateLog()
        last_snap = last_eng = 0.0
        msgs = []
        idle = True
        announced = False
        self.cpu_s = 0.0
        tt = time.thread_time()
        while not self.stop_flag.is_set():
            now_tt = time.thread_time()
            self.cpu_s += now_tt - tt
            tt = now_tt
            f = src.wait_frame(200, min_gap) if hasattr(src, "min_interval_supported") else src.wait_frame(200)
            if f is None:
                if not getattr(src, "connected", False):
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
            eng.set_session(src.session)
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
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        if win32.hotkey_from_msg(message) == HOTKEY_ID:
            QTimer.singleShot(0, self.callback)
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
        self.editing = False
        self._dialogs = {}
        self._preview = None
        self._tick = 0
        self._proc = win32.ProcStats()
        self.widgets = {}
        for cls in (StandingsWidget, RelativeWidget, WeatherWidget, EngineerWidget, PerfWidget):
            self.widgets[cls.NAME] = cls(self)
        self.engine = EngineThread(make_source, config)

    # ---- kontekstas valdikliams ----
    def screen_rect(self) -> QRect:
        if self.virtual_screen is not None:
            return self.virtual_screen
        return QGuiApplication.primaryScreen().availableGeometry()

    def save_config(self):
        try:
            self.config.save()
        except OSError:
            pass

    def widget_changed(self, name):
        self.widgets[name].apply_settings()
        self.save_config()
        self._refresh_visibility(force=True)

    def theme_changed(self):
        self.theme = self.config.data.get("theme", "lth")
        for w in self.widgets.values():
            w.apply_settings()
        self.save_config()

    def open_settings(self, name):
        from .settings import SettingsDialog
        dlg = self._dialogs.get(name)
        if dlg is None:
            dlg = SettingsDialog(self, name)
            self._dialogs[name] = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

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
        hk = self.config.data.get("hotkey", "Ctrl+Shift+E")
        self._hotkey_ok = win32.register_hotkey(HOTKEY_ID, win32.MOD_CONTROL | win32.MOD_SHIFT, VK_E) \
            if hk == "Ctrl+Shift+E" else False
        if self._hotkey_ok:
            self._filter = HotkeyFilter(self.toggle_edit)
            self.app.installNativeEventFilter(self._filter)
        self.app.aboutToQuit.connect(self._shutdown)

    def _shutdown(self):
        self.engine.stop_flag.set()
        win32.unregister_hotkey(HOTKEY_ID)
        self.save_config()

    def _keep_on_top(self):
        for w in self.widgets.values():
            w.keep_on_top()

    # ---- pagrindinis ciklas (UI) ----
    def _on_tick(self):
        self._tick += 1
        snap = self.engine.latest
        if self._tick % 10 == 0:
            cpu, ram = self._proc.sample()
            self.perf.update(cpu=cpu, ram=ram, engine_us=self.engine.update_us, fps=self.engine.fps)
        if not snap.connected and self.editing:
            snap = self.preview_snapshot()
        if snap.connected:
            self._auto_profile(snap)
        self._refresh_visibility(snap=snap)
        for name, w in self.widgets.items():
            if not w.isVisible():
                continue
            if self._tick % RATES.get(name, 1) == 0 or self.editing:
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

    def _refresh_visibility(self, snap=None, force=False):
        snap = snap or self.engine.latest
        active = snap.connected  # visada rodom, kai iRacing veikia (trasoje, garaže, stebint)
        for name, w in self.widgets.items():
            want = (active or self.editing) and w.wants_visible(snap)
            if want and not w.isVisible():
                w.show()
                w.push(snap, force=True)
            elif not want and w.isVisible():
                w.hide()

    def preview_snapshot(self):
        """Redaguojant be iRacing - rodom sintetinės lenktynės duomenis."""
        if self._preview is None:
            from .sources import DemoSource
            demo = DemoSource(fast_forward=200, realtime=False)
            eng = TimingEngine()
            eng.set_session(demo.session)
            for _ in range(60 * 200):
                eng.update(demo.wait_frame())
            self._preview = eng.snapshot()
        return self._preview

    # ---- redagavimas ----
    def toggle_edit(self):
        self.editing = not self.editing
        for w in self.widgets.values():
            w.set_editing(self.editing)
        self._refresh_visibility(force=True)
        if hasattr(self, "act_edit"):
            self.act_edit.setChecked(self.editing)

    # ---- tray ----
    def _make_tray(self):
        self.tray = QSystemTrayIcon(make_icon(), self.app)
        self.tray.setToolTip(f"LTH Overlays {VERSION}")
        menu = QMenu()
        self.act_edit = QAction("Edit layout (Ctrl+Shift+E)", menu, checkable=True)
        self.act_edit.triggered.connect(lambda _: self.toggle_edit())
        menu.addAction(self.act_edit)
        menu.addSeparator()
        for name, w in self.widgets.items():
            act = QAction(w.TITLE, menu, checkable=True)
            act.setChecked(bool(w.cfg.get("visible")))

            def toggle(v, n=name):
                self.config.widget(n)["visible"] = bool(v)
                self.widget_changed(n)
            act.toggled.connect(toggle)
            menu.addAction(act)
        menu.addSeparator()
        prof = menu.addMenu("Profile")
        for key, p in self.config.data["profiles"].items():
            a = QAction(p.get("name", key), prof)
            a.triggered.connect(lambda _=False, k=key: self._set_profile(k))
            prof.addAction(a)
        settings = menu.addMenu("Settings")
        for name, w in self.widgets.items():
            a = QAction(w.TITLE, settings)
            a.triggered.connect(lambda _=False, n=name: self.open_settings(n))
            settings.addAction(a)
        menu.addSeparator()
        act_prev = QAction("Save preview image", menu)
        act_prev.triggered.connect(lambda _=False: self.save_preview())
        menu.addAction(act_prev)
        self.act_auto = QAction("Start with Windows (waits for iRacing)", menu, checkable=True)
        self.act_auto.setChecked(win32.autostart_enabled())
        self.act_auto.toggled.connect(self._toggle_autostart)
        menu.addAction(self.act_auto)
        quit_act = QAction("Quit", menu)
        quit_act.triggered.connect(self.app.quit)
        menu.addAction(quit_act)
        self.tray.setContextMenu(menu)
        self.tray.show()
        self._menu = menu

    def _launcher_exe(self) -> str | None:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        exe = os.path.join(root, "LTH Overlays.exe")
        return exe if os.path.exists(exe) else None

    def _toggle_autostart(self, on):
        exe = self._launcher_exe()
        ok = bool(exe) and win32.set_autostart(bool(on), exe)
        self.config.data["autostart"] = bool(on) and ok
        self.save_config()
        if on and not ok:
            self.act_auto.blockSignals(True)
            self.act_auto.setChecked(False)
            self.act_auto.blockSignals(False)

    def _first_run_autostart(self):
        """Pirmą kartą paleidus - įsijungia automatinis paleidimas (galima išjungti meniu)."""
        d = self.config.data
        if d.get("autostart_done") or not getattr(self, "live", True):
            return
        d["autostart_done"] = True
        exe = self._launcher_exe()
        if d.get("autostart", True) and exe and win32.set_autostart(True, exe):
            if hasattr(self, "act_auto"):
                self.act_auto.blockSignals(True)
                self.act_auto.setChecked(True)
                self.act_auto.blockSignals(False)
        self.save_config()

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

    def _set_profile(self, key):
        self.config.set_profile(key)
        self.config.data["auto_profile"] = False
        for w in self.widgets.values():
            w.apply_settings()
        self.save_config()


def make_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(14, 14, 16))
    p.setPen(QColor(226, 177, 60))
    p.drawRoundedRect(2, 2, 60, 60, 12, 12)
    f = QFont()
    f.setPixelSize(40)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "L")
    p.end()
    return QIcon(pm)


# ----------------------------------------------------------------------
def render_screenshot(oapp: OverlayApp, path: str, sim_seconds: float = 300):
    """Nupiešia visus valdiklius ant ekrano dydžio fono (peržiūrai be iRacing)."""
    from .sources import DemoSource
    demo = DemoSource(fast_forward=0, realtime=False)
    eng = TimingEngine()
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
    vs = oapp.virtual_screen or QGuiApplication.primaryScreen().geometry()
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
    args = ap.parse_args(argv)

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("LTH Overlays")

    if not args.screenshot:
        lock = win32.single_instance("Local\\LTHOverlaysSingleInstance")
        if lock is None:
            QMessageBox.information(None, "LTH Overlays", "LTH Overlays is already running (icon next to the clock).")
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
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
