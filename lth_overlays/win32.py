"""Windows specifika: langas virš iRacing, pelė kiaurai, be fokuso, prioritetas.

Ne Windows sistemose (testai, peržiūra) visos funkcijos nieko nedaro.

Antivirusams draugiškas sprendimas: jokių žemo lygio klaviatūros „hook'ų“
(dažnas klaidingo pavojaus šaltinis) - karštas klavišas registruojamas
standartiniu RegisterHotKey.
"""
from __future__ import annotations

import ctypes
import os
import sys

IS_WIN = sys.platform == "win32"

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_NOOWNERZORDER = 0x0001, 0x0002, 0x0010, 0x0200
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x4000

if IS_WIN:
    from ctypes import wintypes

    _u32 = ctypes.windll.user32
    _k32 = ctypes.windll.kernel32
    _GetLong = getattr(_u32, "GetWindowLongPtrW", _u32.GetWindowLongW)
    _SetLong = getattr(_u32, "SetWindowLongPtrW", _u32.SetWindowLongW)
    _GetLong.restype = ctypes.c_ssize_t
    _GetLong.argtypes = (wintypes.HWND, ctypes.c_int)
    _SetLong.restype = ctypes.c_ssize_t
    _SetLong.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
    _u32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_uint)


def _hwnd(widget) -> int:
    return int(widget.winId())


def make_overlay(widget, click_through: bool = True):
    """Langas: be fokuso, ne užduočių juostoje, visada viršuje, (ne)praleidžia pelę."""
    if not IS_WIN:
        return
    h = _hwnd(widget)
    ex = _GetLong(h, GWL_EXSTYLE)
    ex |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_LAYERED
    if click_through:
        ex |= WS_EX_TRANSPARENT
    else:
        ex &= ~WS_EX_TRANSPARENT
    _SetLong(h, GWL_EXSTYLE, ex)
    keep_on_top(widget)


def set_click_through(widget, enabled: bool):
    if not IS_WIN:
        return
    h = _hwnd(widget)
    ex = _GetLong(h, GWL_EXSTYLE)
    ex = (ex | WS_EX_TRANSPARENT) if enabled else (ex & ~WS_EX_TRANSPARENT)
    _SetLong(h, GWL_EXSTYLE, ex)


def keep_on_top(widget):
    """Pigus kvietimas: grąžina langą į viršų, jei iRacing jį uždengė."""
    if not IS_WIN:
        return
    _u32.SetWindowPos(_hwnd(widget), HWND_TOPMOST, 0, 0, 0, 0,
                      SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER)


def lower_priority():
    """Procesas „Below normal“: iRacing visada gauna procesorių pirmas."""
    if not IS_WIN:
        try:
            import os
            os.nice(5)
        except (AttributeError, OSError):
            pass
        return
    _k32.SetPriorityClass(_k32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)


def register_hotkey(hotkey_id: int, mods: int, vk: int) -> bool:
    if not IS_WIN:
        return False
    return bool(_u32.RegisterHotKey(None, hotkey_id, mods | MOD_NOREPEAT, vk))


def unregister_hotkey(hotkey_id: int):
    if IS_WIN:
        _u32.UnregisterHotKey(None, hotkey_id)


def hotkey_from_msg(message) -> int | None:
    """Iš Qt native įvykio ištraukia WM_HOTKEY id."""
    if not IS_WIN:
        return None
    try:
        msg = wintypes.MSG.from_address(int(message))
    except (TypeError, ValueError):
        return None
    if msg.message == WM_HOTKEY:
        return int(msg.wParam)
    return None


def single_instance(name: str):
    """Grąžina rankenėlę, jei tai vienintelė programa; None - jei jau veikia."""
    if not IS_WIN:
        return object()
    _k32.CreateMutexW.restype = wintypes.HANDLE
    h = _k32.CreateMutexW(None, False, name)
    if _k32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return None
    return h


# ---- paleidimas kartu su Windows (Startup aplankas, be registro) ----
def _startup_file() -> str | None:
    base = os.environ.get("APPDATA")
    if not IS_WIN or not base:
        return None
    return os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "LTH Overlays.vbs")


def autostart_enabled() -> bool:
    p = _startup_file()
    return bool(p and os.path.exists(p))


def set_autostart(enabled: bool, exe: str) -> bool:
    """Įrašo/ištrina mažą .vbs Startup aplanke. Programa pati laukia iRacing."""
    p = _startup_file()
    if not p:
        return False
    try:
        if enabled:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            folder = os.path.dirname(exe)
            with open(p, "w", encoding="utf-8") as f:
                f.write('Set sh = CreateObject("WScript.Shell")\r\n'
                        f'sh.CurrentDirectory = "{folder}"\r\n'
                        f'sh.Run Chr(34) & "{exe}" & Chr(34), 0, False\r\n')
        elif os.path.exists(p):
            os.remove(p)
        return True
    except OSError:
        return False


# ---- našumo matavimas (be psutil) ----
class ProcStats:
    def __init__(self):
        import time
        self._time = time
        self._last = None

    def sample(self):
        """(CPU % vieno branduolio, RAM MB) nuo paskutinio kvietimo."""
        t = self._time.perf_counter()
        cpu = self._cpu_seconds()
        out_cpu = 0.0
        if self._last is not None:
            dt = t - self._last[0]
            if dt > 0:
                out_cpu = (cpu - self._last[1]) / dt * 100.0
        self._last = (t, cpu)
        return out_cpu, self._rss_mb()

    @staticmethod
    def _cpu_seconds():
        import os
        tms = os.times()
        return tms.user + tms.system

    @staticmethod
    def _rss_mb():
        if IS_WIN:
            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t), ("PrivateUsage", ctypes.c_size_t)]
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            psapi = ctypes.windll.psapi
            if psapi.GetProcessMemoryInfo(_k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
                return pmc.PrivateUsage / 1048576
            return 0.0
        try:
            with open("/proc/self/statm") as f:
                import os
                return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1048576
        except OSError:
            return 0.0
