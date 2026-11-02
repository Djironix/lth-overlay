"""Atnaujinimai per GitHub Releases.

- Tikrina https://api.github.com/repos/<repo>/releases/latest paleidus programą ir kas 6 val.
  (tik kai nevažiuoji - trasoje nieko netikrina ir nesiunčia).
- Radus naujesnę versiją - pranešimas Control Center'yje. Parsiunčiama tik paspaudus „Update & restart“:
  LTH-Overlays-<v>-update.zip + .sha256, patikrinama SHA-256, o pritaikoma kitą kartą paleidžiant (lth_boot.py).
- Microsoft Store versija atsinaujina per Store - ten tikrinimas išjungtas.
Tinklo darbas - atskiroje gijoje; UI gauna rezultatą per QTimer (be Qt objektų kitose gijose).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

from lth_timing import VERSION

from .config import app_dir

CHECK_EVERY_S = 6 * 3600
FIRST_CHECK_S = 25


def parse_version(v: str) -> tuple:
    nums = re.findall(r"\d+", v or "")
    return tuple(int(x) for x in nums[:3]) + (0,) * (3 - len(nums[:3]))


def repo() -> str:
    try:
        with open(os.path.join(os.path.dirname(__file__), "data", "update.json"), encoding="utf-8") as fh:
            r = str(json.load(fh).get("repo") or "").strip().strip("/")
        return r if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", r) else ""
    except (OSError, ValueError):
        return ""


def runtime_id() -> str:
    """Python + Qt rinkinio žymė iš runtime.txt (šalia LTH Overlays.exe). Kūrimo aplinkoje - tuščia."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        with open(os.path.join(root, "runtime.txt"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _get(url: str, timeout: float = 15.0):
    req = urllib.request.Request(url, headers={"User-Agent": f"LTH-Overlays/{VERSION}",
                                               "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 - tik https://api.github.com / github.com


def check_release(rep: str) -> dict | None:
    """Naujausias išleidimas: {version, notes, page, zip_url, sha_url, runtime, full_url} arba None."""
    with _get(f"https://api.github.com/repos/{rep}/releases/latest") as r:
        data = json.loads(r.read().decode("utf-8"))
    ver = str(data.get("tag_name") or "").lstrip("vV")
    assets = {a.get("name", ""): a.get("browser_download_url", "") for a in data.get("assets") or []}
    zip_name = f"LTH-Overlays-{ver}-update.zip"
    body = str(data.get("body") or "")
    m = re.search(r"runtime:\s*([A-Za-z0-9_.-]+)", body)
    return {"version": ver, "notes": body.strip(), "page": data.get("html_url") or f"https://github.com/{rep}/releases",
            "zip_url": assets.get(zip_name), "sha_url": assets.get(zip_name + ".sha256"),
            "full_url": assets.get(f"LTH-Overlays-{ver}-win64.zip"), "runtime": m.group(1) if m else ""}


class Updater:
    """Valdo tikrinimą / parsiuntimą. Būsena: idle, checking, available, downloading, ready, error."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.repo = repo()
        self.state = "idle"
        self.info = None
        self.error = ""
        self.progress = 0.0
        self.last_check = 0.0
        self._result = None  # iš gijos: ("check"|"download", ok, duomenys)
        self._thread = None
        self._started = time.monotonic()

    # ---- ar galima ----
    def enabled(self) -> bool:
        from . import win32
        if not self.repo or win32.is_packaged():
            return False
        return bool((self.ctx.config.data.get("updates") or {}).get("auto", True))

    def _driving(self) -> bool:
        snap = self.ctx.engine.latest
        return bool(snap.connected and snap.on_track and not snap.replay)

    # ---- kviečiama iš UI laikmačio (~1 s) ----
    def tick(self):
        if self._result is not None:
            kind, ok, data = self._result
            self._result = None
            self._finish(kind, ok, data)
        if self._thread is not None and self._thread.is_alive():
            return
        if not self.enabled() or self.state in ("downloading", "ready"):
            return
        now = time.monotonic()
        due = (now - self._started > FIRST_CHECK_S and not self.last_check) or \
              (self.last_check and now - self.last_check > CHECK_EVERY_S)
        if due and not self._driving():
            self.check()

    def check(self, manual: bool = False):
        if not self.repo or (self._thread is not None and self._thread.is_alive()):
            return
        self.last_check = time.monotonic()
        self.state = "checking"
        self._manual = manual

        def work():
            try:
                self._result = ("check", True, check_release(self.repo))
            except urllib.error.HTTPError as e:
                # 404 = repo dar neturi nė vieno išleidimo - tai ne klaida
                self._result = ("check", True, None) if e.code == 404 else ("check", False, f"HTTP {e.code}")
            except Exception as e:  # noqa: BLE001
                self._result = ("check", False, str(e))
        self._thread = threading.Thread(target=work, daemon=True, name="lth-update-check")
        self._thread.start()

    def newer(self) -> bool:
        return bool(self.info and parse_version(self.info["version"]) > parse_version(VERSION))

    def needs_full(self) -> bool:
        """Naujai versijai reikia kito Python / Qt rinkinio - tada tik pilnas zip iš GitHub."""
        if not self.info:
            return False
        rt, mine = self.info.get("runtime") or "", runtime_id()
        return bool(rt and mine and rt != mine) or not self.info.get("zip_url") or not self.info.get("sha_url")

    def download(self):
        if not self.newer() or self.needs_full() or (self._thread is not None and self._thread.is_alive()):
            return
        self.state = "downloading"
        self.progress = 0.0
        info = dict(self.info)
        folder = os.path.join(app_dir(), "updates")

        def work():
            try:
                os.makedirs(folder, exist_ok=True)
                with _get(info["sha_url"]) as r:
                    sha = r.read().decode("utf-8", "replace").split()[0].strip().lower()
                if not re.fullmatch(r"[0-9a-f]{64}", sha):
                    raise ValueError("bad checksum file")
                path = os.path.join(folder, f"LTH-Overlays-{info['version']}-update.zip")
                h = hashlib.sha256()
                with _get(info["zip_url"], timeout=60) as r, open(path + ".part", "wb") as out:
                    total = int(r.headers.get("Content-Length") or 0)
                    done = 0
                    while True:
                        chunk = r.read(1 << 16)
                        if not chunk:
                            break
                        out.write(chunk)
                        h.update(chunk)
                        done += len(chunk)
                        if total:
                            self.progress = done / total
                if h.hexdigest() != sha:
                    os.remove(path + ".part")
                    raise ValueError("the download is damaged (checksum mismatch)")
                os.replace(path + ".part", path)
                with open(os.path.join(folder, "pending.json"), "w", encoding="utf-8") as fh:
                    json.dump({"zip": path, "sha256": sha, "version": info["version"]}, fh)
                self._result = ("download", True, path)
            except Exception as e:  # noqa: BLE001
                self._result = ("download", False, str(e))
        self._thread = threading.Thread(target=work, daemon=True, name="lth-update-download")
        self._thread.start()

    def _finish(self, kind, ok, data):
        if kind == "check":
            if not ok:
                self.state, self.error = "error", data
                if getattr(self, "_manual", False):
                    self.ctx.notify("Could not check for updates")
                return
            self.info = data
            if data is None:
                self.state = "idle"
                if getattr(self, "_manual", False):
                    self.ctx.notify(f"LTH Overlays {VERSION} is up to date")
                return
            if self.newer():
                announce = self.state != "available"
                self.state = "available"
                if announce:
                    self.ctx.notify(f"LTH Overlays {data['version']} is available - open the Control Center to update")
                    tray = getattr(self.ctx, "tray", None)
                    if tray is not None:
                        from PySide6.QtWidgets import QSystemTrayIcon
                        tray.showMessage("LTH Overlays update", f"Version {data['version']} is ready to install.",
                                         QSystemTrayIcon.MessageIcon.Information, 5000)
            else:
                self.state = "idle"
                if getattr(self, "_manual", False):
                    self.ctx.notify(f"LTH Overlays {VERSION} is up to date")
        else:
            if ok:
                self.state = "ready"
                self.ctx.notify(f"Update {self.info['version']} downloaded - restarting")
                self.restart()
            else:
                self.state, self.error = "available", data
                self.ctx.notify(f"Update failed: {data}")

    def restart(self):
        """Paleidžia programą iš naujo (naujas procesas palaukia, kol šis užsidarys)."""
        exe = self.ctx._launcher_exe()
        if not exe:
            self.ctx.notify("Update ready - restart LTH Overlays to install it")
            return
        from PySide6.QtCore import QProcess
        QProcess.startDetached(exe, ["--restarted", "--control"])
        self.ctx.quit()
