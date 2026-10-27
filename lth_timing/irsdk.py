"""iRacing shared memory skaitytuvas (tik Windows).

Efektyvumas:
- laukiame iRacing signalo „nauji duomenys“ (WaitForSingleObject), o ne sukam ciklo;
- kiekvieną kadrą nukopijuojame vieną buferį (kelis KB) į iš anksto paruoštą
  masyvą ir skaitome tik reikalingus kintamuosius per numpy vaizdus (be kopijų);
- sesijos YAML parsinamas tik kai pasikeičia, atskiroje gijoje.
"""
from __future__ import annotations

import ctypes
import mmap
import struct
import sys
import threading
import time

import numpy as np

from .frame import ALL_VARS, MAX_CARS, Frame
from .sessioninfo import build_model, parse_yaml

MEMMAP_NAME = "Local\\IRSDKMemMapFileName"
EVENT_NAME = "Local\\IRSDKDataValidEvent"
MEMMAP_SIZE = 1164 * 1024
STATUS_CONNECTED = 1

_HEADER = struct.Struct("<10i2i")  # ver..bufLen, pad[2]
_VARBUF = struct.Struct("<4i")  # tickCount, bufOffset, pad[2]
_VARHDR = struct.Struct("<3i?3x32s64s32s")
_NP_TYPES = {0: np.uint8, 1: np.bool_, 2: np.int32, 3: np.uint32, 4: np.float32, 5: np.float64}

SYNCHRONIZE = 0x00100000
FILE_MAP_READ = 0x0004
WAIT_OBJECT_0 = 0


# Reikšmė tuščioms vietoms, kai iRacing masyvas trumpesnis už MAX_CARS
_CAR_FILL = {"CarIdxLapDistPct": -1.0, "CarIdxLap": -1, "CarIdxLapCompleted": -1, "CarIdxTrackSurface": -1,
             "CarIdxLastLapTime": -1.0, "CarIdxBestLapTime": -1.0}


def fit_car_array(name: str, arr: np.ndarray) -> np.ndarray:
    """iRacing CarIdx masyvo ilgis keičiasi (64 -> 72 ...). Pritaikom prie MAX_CARS."""
    if len(arr) == MAX_CARS:
        return arr
    out = np.full(MAX_CARS, _CAR_FILL.get(name, 0), dtype=arr.dtype)
    n = min(len(arr), MAX_CARS)
    out[:n] = arr[:n]
    return out


class LiveSource:
    """Teikia telemetrijos kadrus iš veikiančio iRacing."""

    min_interval_supported = True

    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("iRacing telemetrija pasiekiama tik Windows")
        self._k32 = ctypes.windll.kernel32
        self._k32.OpenEventW.restype = ctypes.c_void_p
        self._k32.OpenFileMappingW.restype = ctypes.c_void_p
        self._k32.OpenFileMappingW.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p)
        self._k32.CloseHandle.argtypes = (ctypes.c_void_p,)
        self._k32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        self._mm = None
        self._event = None
        self._buf = None  # vietinė vieno kadro kopija
        self._views = {}
        self._layout_key = None
        self._session_update = -1
        self.session = None  # SessionModel
        self._parsing = False
        self._lock = threading.Lock()
        self._last_return = 0.0

    # ---- prisijungimas ----
    def _connect(self) -> bool:
        """Prisijungia TIK jei iRacing jau veikia.

        Svarbu: Python mmap su vardu, kai tokios atminties nėra, SUKURIA tuščią
        bloką tuo vardu. Jei overlay startuoja anksčiau už iRacing (paleidimas su
        Windows), tas tuščias blokas užimtų vardą: mes niekada negautume duomenų,
        o iRacing negalėtų normaliai paskelbti telemetrijos. Todėl pirmiausia
        tikriname, ar iRacing sukurti objektai egzistuoja."""
        if self._mm is not None and self._event is not None:
            return True
        if self._event is None:
            h = self._k32.OpenEventW(SYNCHRONIZE, False, EVENT_NAME)
            if not h:
                return False
            self._event = h
        if self._mm is None:
            probe = self._k32.OpenFileMappingW(FILE_MAP_READ, False, MEMMAP_NAME)
            if not probe:
                self._release()
                return False
            self._k32.CloseHandle(ctypes.c_void_p(probe))
            try:
                self._mm = mmap.mmap(-1, MEMMAP_SIZE, MEMMAP_NAME, access=mmap.ACCESS_READ)
            except OSError:
                self._release()
                return False
        return True

    def _release(self):
        """Paleidžia iRacing atminties rankenas, kad iRacing galėtų pasileisti iš naujo."""
        if self._mm is not None:
            try:
                self._mm.close()
            except (BufferError, ValueError):
                pass
            self._mm = None
        if self._event:
            self._k32.CloseHandle(ctypes.c_void_p(self._event))
            self._event = None
        self._layout_key = None
        self._session_update = -1
        self.session = None

    def close(self):
        self._release()

    @property
    def connected(self) -> bool:
        if self._mm is None:
            return False
        status = struct.unpack_from("<i", self._mm, 4)[0]
        return status & STATUS_CONNECTED == STATUS_CONNECTED

    # ---- kintamųjų išdėstymas ----
    def _build_layout(self, num_vars: int, var_offset: int, buf_len: int):
        self._buf = np.zeros(buf_len, dtype=np.uint8)
        self._views = {}
        wanted = {name: dt for name, dt in ALL_VARS}
        for i in range(num_vars):
            vtype, off, count, _, name, _, _ = _VARHDR.unpack_from(self._mm, var_offset + i * _VARHDR.size)
            name = name.split(b"\0", 1)[0].decode("latin-1")
            if name not in wanted:
                continue
            dt = _NP_TYPES.get(vtype)
            if dt is None:
                continue
            view = np.frombuffer(self._buf, dtype=dt, count=count, offset=off)
            self._views[name] = view if count > 1 else view  # skaliarai paimami [0]
        self._scalar = {n for n, _ in ALL_VARS if n in self._views and not n.startswith("CarIdx")}

    # ---- kadrai ----
    def wait_frame(self, timeout_ms: int = 100, min_interval_s: float = 0.0):
        """Grąžina Frame, kai iRacing paskelbia naujus duomenis, arba None.

        min_interval_s: miegam tiek nuo paskutinio kadro, kad nepabustume
        60 kartų per sekundę, kai variklis vis tiek skaičiuoja 20 Hz."""
        if not self._connect():
            time.sleep(1.0)  # iRacing neveikia - miego režimas
            return None
        rest = self._last_return + min_interval_s - time.perf_counter()
        if rest > 0.002:
            time.sleep(rest)
        self._k32.WaitForSingleObject(ctypes.c_void_p(self._event), timeout_ms)  # atleidžia GIL
        if not self.connected:
            self._release()  # iRacing užsidarė - atleidžiam, kad kitas paleidimas prisijungtų iš naujo
            return None
        mm = self._mm
        hdr = _HEADER.unpack_from(mm, 0)
        _, _, _, si_update, si_len, si_off, num_vars, var_off, num_buf, buf_len = hdr[:10]
        key = (num_vars, var_off, buf_len)
        if key != self._layout_key:
            self._build_layout(num_vars, var_off, buf_len)
            self._layout_key = key
        # Naujausias buferis
        bufs = [_VARBUF.unpack_from(mm, _HEADER.size + i * _VARBUF.size) for i in range(num_buf)]
        tick, off = max(bufs, key=lambda b: b[0])[:2]
        for _ in range(2):  # kopijuojam ir tikrinam, kad iRacing tuo metu neperrašė
            self._buf[:] = np.frombuffer(mm, dtype=np.uint8, count=buf_len, offset=off)
            idx = [b[0] for b in bufs].index(tick)
            if _VARBUF.unpack_from(mm, _HEADER.size + idx * _VARBUF.size)[0] == tick:
                break
        if si_update != self._session_update and not self._parsing:
            self._session_update = si_update
            raw = bytes(mm[si_off:si_off + si_len])
            self._parsing = True
            threading.Thread(target=self._parse_session, args=(raw, si_update), daemon=True).start()
        values = {}
        for name, view in self._views.items():
            values[name] = view[0].item() if name in self._scalar else fit_car_array(name, view.copy())
        self._last_return = time.perf_counter()
        return Frame(values)

    def _parse_session(self, raw: bytes, update: int):
        try:
            model = build_model(parse_yaml(raw.decode("cp1252", errors="replace")), update)
            with self._lock:
                self.session = model
        except Exception:  # sugadintas YAML - bandysim su kitu atnaujinimu
            self._session_update = -1
        finally:
            self._parsing = False

    def raw_session_yaml(self) -> str:
        if self._mm is None:
            return ""
        hdr = _HEADER.unpack_from(self._mm, 0)
        si_len, si_off = hdr[4], hdr[5]
        return bytes(self._mm[si_off:si_off + si_len]).decode("cp1252", errors="replace").rstrip("\x00")
