"""Build Stella Video into a standalone Windows .exe via PyInstaller.

Steps:
  1. Convert logo.png -> logo.ico (multi-resolution) so Windows shows it
     in Explorer, taskbar, alt-tab, etc.
  2. Invoke PyInstaller with everything bundled — assets, libmpv DLL.
  3. Print where the result lives.

Usage:
    python build_exe.py

After the build, distribute the entire `dist/Stella Video/` folder.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PKG = ROOT / "stella_video"
ASSETS = PKG / "assets"
LIBS = ROOT / "libs"
DIST_NAME = "Stella Video"


def generate_ico() -> Path:
    """Build a multi-resolution .ico next to the PNG so Windows can pick
    the right size for each context (16x16 tray, 256x256 alt-tab, etc.)."""
    png = ASSETS / "logo.png"
    ico = ASSETS / "logo.ico"
    if not png.is_file():
        raise FileNotFoundError(f"logo.png not found at {png}")
    if ico.is_file() and ico.stat().st_mtime >= png.stat().st_mtime:
        print(f"[icon] up to date: {ico}")
        return ico
    try:
        from PIL import Image
    except ImportError:
        print("[icon] Pillow not installed — install with: pip install pillow")
        raise SystemExit(1)
    print(f"[icon] converting {png.name} -> {ico.name}")
    img = Image.open(png)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    img.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                         (64, 64), (128, 128), (256, 256)])
    print(f"[icon] wrote {ico} ({ico.stat().st_size / 1024:.1f} KB)")
    return ico


def find_libmpv() -> Path | None:
    for name in ("libmpv-2.dll", "mpv-2.dll", "mpv-1.dll"):
        p = LIBS / name
        if p.is_file():
            return p
    return None


def build(icon_path: Path) -> None:
    libmpv = find_libmpv()
    if not libmpv:
        print("[warn] libmpv DLL not found in ./libs/. The bundled app will "
              "fail to start until you run setup_libmpv.py or copy it in.")
    out_root = ROOT / "dist"
    work_root = ROOT / "build"

    # Clean previous build to avoid mixing artefacts.
    for d in (out_root, work_root):
        if d.exists():
            print(f"[clean] removing {d}")
            shutil.rmtree(d, ignore_errors=True)

    # --add-data uses ';' separator on Windows, ':' elsewhere.
    sep = ";" if sys.platform == "win32" else ":"
    add_data = [
        f"{ASSETS}{sep}stella_video/assets",
    ]

    binaries: list[str] = []
    if libmpv is not None:
        # Bundle libmpv-2.dll next to the .exe so Windows can locate it.
        binaries.append(f"{libmpv}{sep}.")

    args: list[str] = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name", DIST_NAME,
        "--windowed",                     # no console window
        "--icon", str(icon_path),
        "--distpath", str(out_root),
        "--workpath", str(work_root),
        "--specpath", str(ROOT),
    ]
    for d in add_data:
        args += ["--add-data", d]
    for b in binaries:
        args += ["--add-binary", b]

    # Hidden imports — most are auto-detected, listed defensively.
    for h in ("mpv",):
        args += ["--hidden-import", h]

    # Strip Qt modules we don't use — PySide6 ships >700 MB of plugins
    # by default (WebEngine, 3D, Quick, etc.). Excluding them drops the
    # bundle to roughly a third.
    excludes = [
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
        "PySide6.QtWebSockets", "PySide6.QtQuick", "PySide6.QtQml",
        "PySide6.QtQuick3D", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
        "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation",
        "PySide6.Qt3DExtras", "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets", "PySide6.QtCharts",
        "PySide6.QtDataVisualization", "PySide6.QtPositioning",
        "PySide6.QtLocation", "PySide6.QtSensors", "PySide6.QtSerialPort",
        "PySide6.QtSql", "PySide6.QtBluetooth", "PySide6.QtNfc",
        "PySide6.QtPdf", "PySide6.QtPdfWidgets",
        "PySide6.QtRemoteObjects", "PySide6.QtScxml",
        "PySide6.QtStateMachine", "PySide6.QtTextToSpeech",
        "PySide6.QtSpatialAudio", "PySide6.QtHttpServer",
        "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtUiTools",
        "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
        "tkinter", "matplotlib", "numpy", "scipy",
    ]
    for e in excludes:
        args += ["--exclude-module", e]

    args += [str(ROOT / "run.py")]

    print("[pyinstaller] " + " ".join(f'"{a}"' if " " in a else a for a in args[3:]))
    result = subprocess.run(args, cwd=str(ROOT))
    if result.returncode != 0:
        print(f"\n[build] FAILED with exit code {result.returncode}")
        raise SystemExit(result.returncode)

    exe = out_root / DIST_NAME / f"{DIST_NAME}.exe"
    if exe.is_file():
        print()
        print(f"[build] DONE: {exe}")
        print(f"[build] distribute the folder: {out_root / DIST_NAME}")
    else:
        print(f"[build] expected exe at {exe} — not found, check PyInstaller output above")


def main() -> int:
    print(f"Stella Video — build_exe.py")
    print(f"Project root: {ROOT}")
    print()
    icon = generate_ico()
    build(icon)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
