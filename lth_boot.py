"""Atnaujinimo pritaikymas paleidžiant (prieš įkeliant programą).

LTH Overlays.exe paleidžia python\\pythonw.exe app\\run.py. run.py pirmiausia iškviečia apply_pending():
jei Control Center'yje buvo paspausta „Update & restart“, %APPDATA%\\LTH Overlays\\updates\\pending.json
nurodo parsiųstą ir patikrintą (SHA-256) zip. Jo turinys pakeičia programos aplanką (lth_overlays,
lth_timing ...), sena versija lieka app\\_prev. Jei nauja versija nepasileidžia - rollback() grąžina seną.
Tik standartinė biblioteka: šis failas turi veikti net jei kita programos dalis sugadinta.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import zipfile

APP = os.path.dirname(os.path.abspath(__file__))
ITEMS = ("lth_overlays", "lth_timing", "lth_boot.py", "tools")


def data_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "LTH Overlays")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _log(text: str):
    try:
        os.makedirs(os.path.join(data_dir(), "updates"), exist_ok=True)
        with open(os.path.join(data_dir(), "updates", "update.log"), "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    except OSError:
        pass


def _rm(path):
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def apply_pending(app: str = APP) -> str | None:
    """Pritaiko laukiantį atnaujinimą. Grąžina naują versiją arba None."""
    pend = os.path.join(data_dir(), "updates", "pending.json")
    if not os.path.isfile(pend):
        return None
    try:
        with open(pend, encoding="utf-8") as fh:
            info = json.load(fh)
        zpath, sha, ver = info["zip"], info["sha256"].lower(), info["version"]
    except (OSError, ValueError, KeyError):
        _rm(pend)
        return None
    _rm(pend)  # vieną kartą - net jei nepavyks, nesisuksim ratu
    if not os.path.isfile(zpath) or _sha256(zpath) != sha:
        _log(f"update {ver}: file missing or checksum mismatch - skipped")
        return None
    new = os.path.join(app, "_new")
    prev = os.path.join(app, "_prev")
    _rm(new)
    try:
        with zipfile.ZipFile(zpath) as z:
            for m in z.infolist():
                name = m.filename.replace("\\", "/")
                if not name.startswith("app/") or ".." in name.split("/"):
                    continue  # tik app/ aplankas, jokių kelių už jo ribų
                rel = name[4:]
                if not rel or name.endswith("/"):
                    continue
                dst = os.path.join(new, *rel.split("/"))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with z.open(m) as src, open(dst, "wb") as out:
                    shutil.copyfileobj(src, out)
        for need in ("lth_overlays/__init__.py", "lth_timing/__init__.py"):
            if not os.path.isfile(os.path.join(new, *need.split("/"))):
                raise ValueError(f"{need} missing in the update")
        _rm(prev)
        os.makedirs(prev, exist_ok=True)
        for item in ITEMS:
            cur = os.path.join(app, item)
            if os.path.exists(cur):
                if item == "lth_boot.py":
                    shutil.copy2(cur, os.path.join(prev, item))
                else:
                    os.replace(cur, os.path.join(prev, item))
        for item in os.listdir(new):
            if item == "run.py":
                continue  # run.py vykdomas dabar - jo nekeičiam (jis paprastas ir stabilus)
            dst = os.path.join(app, item)
            if os.path.isdir(dst):
                _rm(dst)
            os.replace(os.path.join(new, item), dst)
        _rm(new)
        _rm(zpath)
        _log(f"updated to {ver}")
        return ver
    except Exception as e:  # noqa: BLE001
        _log(f"update {ver} failed: {e!r} - restoring")
        rollback(app)
        _rm(new)
        return None


def rollback(app: str = APP) -> bool:
    """Grąžina ankstesnę versiją iš app\\_prev."""
    prev = os.path.join(app, "_prev")
    if not os.path.isdir(prev) or not os.listdir(prev):
        return False
    for item in os.listdir(prev):
        dst = os.path.join(app, item)
        _rm(dst)
        os.replace(os.path.join(prev, item), dst)
    _log("rolled back to the previous version")
    return True
