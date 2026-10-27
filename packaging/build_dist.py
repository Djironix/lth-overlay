"""Builds the Windows distribution folder + zip.

Works on Windows or Linux (cross-download of Windows wheels).

    python packaging/build_dist.py [--python-url URL] [--sign]

Output: dist/LTH Overlays/ and dist/LTH-Overlays-<version>-win64.zip

Antivirus-friendly by design:
- no PyInstaller one-file / UPX packing (the most common false-positive trigger);
- plain portable Python + readable .py files + a tiny launcher with version info;
- nothing is written to the registry, no admin rights, no auto-download of code.
"""
from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lth_timing import VERSION  # noqa: E402

PY_URL = ("https://github.com/astral-sh/python-build-standalone/releases/download/20261026/"
          "cpython-3.13.18+20261026-x86_64-pc-windows-msvc-install_only_stripped.tar.gz")
PACKAGES = ["PySide6-Essentials==6.12.0", "numpy", "pyyaml"]

# Qt parts the overlays never load (Widgets + Gui + Core only)
PRUNE_GLOBS = [
    "PySide6/Qt6Qml*", "PySide6/Qt6Quick*", "PySide6/Qt6Pdf*", "PySide6/Qt6Designer*", "PySide6/Qt6Help*",
    "PySide6/Qt6Network*", "PySide6/Qt6OpenGL*", "PySide6/Qt6Sql*", "PySide6/Qt6Test*", "PySide6/Qt6Xml*",
    "PySide6/Qt6Concurrent*", "PySide6/Qt6DBus*", "PySide6/Qt6PrintSupport*", "PySide6/Qt6SvgWidgets*",
    "PySide6/Qt6UiTools*", "PySide6/Qt6VirtualKeyboard*", "PySide6/Qt6ShaderTools*", "PySide6/Qt6Labs*",
    "PySide6/QtQml*", "PySide6/QtQuick*", "PySide6/QtPdf*", "PySide6/QtDesigner*", "PySide6/QtHelp*",
    "PySide6/QtNetwork*", "PySide6/QtOpenGL*", "PySide6/QtSql*", "PySide6/QtTest*", "PySide6/QtXml*",
    "PySide6/QtConcurrent*", "PySide6/QtDBus*", "PySide6/QtPrintSupport*", "PySide6/QtSvgWidgets*", "PySide6/QtUiTools*",
    "PySide6/opengl32sw.dll", "PySide6/translations", "PySide6/qml", "PySide6/resources", "PySide6/metatypes",
    "PySide6/typesystems", "PySide6/include", "PySide6/glue", "PySide6/scripts", "PySide6/examples",
    "PySide6/*.exe", "PySide6/plugins/qmltooling", "PySide6/plugins/sqldrivers", "PySide6/plugins/networkinformation",
    "PySide6/plugins/tls", "PySide6/plugins/generic", "PySide6/plugins/platforminputcontexts",
    "PySide6/plugins/virtualkeyboard", "PySide6/plugins/designer", "PySide6/plugins/qmllint",
    "PySide6/plugins/platforms/qminimal.dll", "PySide6/plugins/platforms/qoffscreen.dll",
    "PySide6/plugins/platforms/qdirect2d.dll", "PySide6/plugins/iconengines", "PySide6/plugins/vectorimageformats",
    "PySide6/plugins/imageformats/qpdf.dll", "PySide6/plugins/imageformats/qsvg.dll",
    "numpy/tests", "numpy/*/tests", "numpy/_core/include", "numpy/f2py", "numpy/distutils", "numpy/typing",
    "*.pyi", "*/*.pyi", "*/*/*.pyi",
]
PRUNE_PY = ["Lib/test", "Lib/idlelib", "Lib/tkinter", "Lib/turtledemo", "Lib/ensurepip", "Lib/lib2to3",
            "tcl", "DLLs/_tkinter.pyd", "DLLs/tcl*.dll", "DLLs/tk*.dll", "Scripts"]
APP_ITEMS = ["run.py", "lth_timing", "lth_overlays", "tools/diagnose.py"]


def log(*a):
    print("[build]", *a, flush=True)


def fetch(url: str, cache: str) -> str:
    os.makedirs(cache, exist_ok=True)
    path = os.path.join(cache, url.rsplit("/", 1)[-1].replace("%2B", "+"))
    if not os.path.exists(path):
        log("downloading", url)
        urllib.request.urlretrieve(url, path + ".part")
        os.replace(path + ".part", path)
    return path


def rm(path):
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.exists(path):
        os.remove(path)


def size_mb(path):
    total = 0
    for dp, _, files in os.walk(path):
        for f in files:
            total += os.path.getsize(os.path.join(dp, f))
    return total / 1048576


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--python-url", default=PY_URL)
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    ap.add_argument("--sign", action="store_true", help="sign the .exe files with signtool (Windows)")
    args = ap.parse_args()

    cache = os.path.join(ROOT, "packaging", ".cache")
    target = os.path.join(args.out, "LTH Overlays")
    rm(target)
    os.makedirs(target)

    # 1) portable Python
    tgz = fetch(args.python_url, cache)
    log("extracting Python")
    with tarfile.open(tgz) as tf:
        tf.extractall(target, filter="data")  # creates python/
    py = os.path.join(target, "python")
    for pat in PRUNE_PY:
        for p in glob.glob(os.path.join(py, pat)):
            rm(p)

    # 2) Windows wheels into site-packages
    site = os.path.join(py, "Lib", "site-packages")
    log("installing", " ".join(PACKAGES))
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                           "--target", site, "--platform", "win_amd64", "--python-version", "3.13",
                           "--implementation", "cp", "--only-binary=:all:", "--no-compile", *PACKAGES])
    for pat in PRUNE_GLOBS:
        for p in glob.glob(os.path.join(site, pat)):
            rm(p)
    for p in glob.glob(os.path.join(site, "*", "__pycache__")) + glob.glob(os.path.join(site, "bin")):
        rm(p)

    # 3) app
    app = os.path.join(target, "app")
    for item in APP_ITEMS:
        src = os.path.join(ROOT, item)
        dst = os.path.join(app, item)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isdir(src):
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(src, dst)

    # 4) launchers + docs
    for exe in ("LTH Overlays.exe", "LTH Diagnostics.exe"):
        shutil.copy2(os.path.join(ROOT, "packaging", "launcher", exe), os.path.join(target, exe))
    shutil.copy2(os.path.join(ROOT, "packaging", "README.txt"), os.path.join(target, "README.txt"))

    if args.sign:
        sign(target)

    log(f"folder size {size_mb(target):.0f} MB")
    zpath = os.path.join(args.out, f"LTH-Overlays-{VERSION}-win64.zip")
    rm(zpath)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dp, _, files in os.walk(target):
            for f in files:
                full = os.path.join(dp, f)
                z.write(full, os.path.relpath(full, args.out))
    log(f"zip {os.path.getsize(zpath) / 1048576:.0f} MB -> {zpath}")


def sign(target):
    """Signs the launchers and the Python executables (Windows, signtool from the Windows SDK).

    Certificate: set LTH_SIGN_ARGS, e.g. '/n "LTH Racing"' for a certificate in the store
    or '/f cert.pfx /p password'. Timestamping keeps signatures valid after the cert expires."""
    sign_args = os.environ.get("LTH_SIGN_ARGS")
    if not sign_args:
        raise SystemExit("Set LTH_SIGN_ARGS (see README) to sign")
    files = glob.glob(os.path.join(target, "*.exe"))
    for f in files:
        cmd = f'signtool sign {sign_args} /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 "{f}"'
        log("signing", os.path.basename(f))
        subprocess.check_call(cmd, shell=True)


if __name__ == "__main__":
    main()
