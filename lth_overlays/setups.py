"""Setupų biblioteka ir automatinis įdiegimas į iRacing aplanką.

Biblioteka: %APPDATA%\\LTH Overlays\\setups\\<mašinos aplankas>\\... (.sto failai iš LTH paketų).
Įdiegimas:  Documents\\iRacing\\setups\\<mašinos aplankas>\\LTH\\...

Mašinos aplankas = iRacing CarPath (pvz. bmwm4gt3) - toks pat, kokį iRacing naudoja setups aplanke.
Kopijuojami tik .sto (ir greta esantys .htm / .txt aprašai), keliai tikrinami, kad niekas neišeitų už aplanko.
"""
from __future__ import annotations

import os
import re
import shutil
import zipfile

ALLOWED = (".sto", ".htm", ".html", ".txt")
SUBFOLDER = "LTH"


def iracing_setups_dir() -> str | None:
    """Documents\\iRacing\\setups (Documents gali būti perkeltas į OneDrive - Qt žino tikrą vietą)."""
    try:
        from PySide6.QtCore import QStandardPaths
        docs = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    except Exception:  # noqa: BLE001
        docs = os.path.join(os.path.expanduser("~"), "Documents")
    path = os.path.join(docs, "iRacing", "setups")
    return path if os.path.isdir(os.path.dirname(path)) else None


def _safe_parts(name: str) -> list:
    parts = [p for p in re.split(r"[\\/]+", name) if p and p not in (".", "..")]
    return [re.sub(r'[<>:"|?*\x00-\x1f]', "_", p) for p in parts]


class SetupLibrary:
    def __init__(self, root: str):
        self.root = root

    # ---- importas ----
    def import_files(self, paths, car_hint: str = "") -> dict:
        """.zip paketai ir / ar pavieniai .sto. Grąžina {mašina: kiek failų}. car_hint - dabartinė mašina,
        kai faile nėra mašinos aplanko."""
        known = set(self.known_cars())
        out = {}
        for path in paths:
            if path.lower().endswith(".zip"):
                with zipfile.ZipFile(path) as z:
                    for info in z.infolist():
                        if info.is_dir() or info.file_size > 5_000_000:
                            continue
                        parts = _safe_parts(info.filename)
                        if not parts or not parts[-1].lower().endswith(ALLOWED):
                            continue
                        car, rest = self._split(parts, known, car_hint)
                        if not car:
                            continue
                        dst = os.path.join(self.root, car, *rest)
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        with z.open(info) as src, open(dst, "wb") as fh:
                            shutil.copyfileobj(src, fh)
                        out[car] = out.get(car, 0) + 1
            elif path.lower().endswith(ALLOWED) and car_hint:
                dst = os.path.join(self.root, car_hint, os.path.basename(path))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(path, dst)
                out[car_hint] = out.get(car_hint, 0) + 1
        return out

    @staticmethod
    def known_cars() -> list:
        """Mašinų aplankai, kuriuos iRacing jau sukūrė (tavo mašinos)."""
        d = iracing_setups_dir()
        try:
            return [n for n in os.listdir(d) if os.path.isdir(os.path.join(d, n))] if d else []
        except OSError:
            return []

    @staticmethod
    def _split(parts, known, car_hint):
        """Kelias pakete -> (mašinos aplankas, likęs kelias).
        Paketas gali būti „bmwm4gt3/spa/race.sto“ arba „LTH pack/bmwm4gt3/race.sto“."""
        dirs = parts[:-1]
        lower = {k.lower(): k for k in known}
        for i, p in enumerate(dirs[:2]):
            if p.lower() in lower:
                return lower[p.lower()], parts[i + 1:]
        if not known:  # iRacing aplanko nėra (pvz. kitas kompiuteris) - pasitikim paketo struktūra
            for i, p in enumerate(dirs[:2]):
                if re.fullmatch(r"[a-z0-9_]{3,40}", p):
                    return p, parts[i + 1:]
        if car_hint:
            return car_hint, parts[-1:]
        return "", []

    # ---- biblioteka ----
    def cars(self) -> dict:
        """{mašina: setupų (.sto) skaičius}."""
        out = {}
        try:
            names = os.listdir(self.root)
        except OSError:
            return out
        for car in names:
            base = os.path.join(self.root, car)
            if not os.path.isdir(base):
                continue
            n = sum(1 for _, _, fs in os.walk(base) for f in fs if f.lower().endswith(".sto"))
            if n:
                out[car] = n
        return out

    def remove(self, car: str):
        shutil.rmtree(os.path.join(self.root, car), ignore_errors=True)

    # ---- įdiegimas ----
    def install(self, car: str) -> int:
        """Nukopijuoja bibliotekos setupus į iRacing\\setups\\<car>\\LTH. Grąžina, kiek failų nauji / pakeisti."""
        dst_root = iracing_setups_dir()
        src_root = os.path.join(self.root, car)
        if not dst_root or not car or not os.path.isdir(src_root):
            return 0
        n = 0
        for dirpath, _, files in os.walk(src_root):
            rel = os.path.relpath(dirpath, src_root)
            for f in files:
                if not f.lower().endswith(ALLOWED):
                    continue
                src = os.path.join(dirpath, f)
                dst = os.path.normpath(os.path.join(dst_root, car, SUBFOLDER, rel, f))
                if not dst.startswith(os.path.normpath(dst_root)):
                    continue
                try:
                    if os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src) and \
                            os.path.getmtime(dst) >= os.path.getmtime(src):
                        continue
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
                    if f.lower().endswith(".sto"):
                        n += 1
                except OSError:
                    continue
        return n
