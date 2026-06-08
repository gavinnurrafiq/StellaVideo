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
OBS_GUIDE = ROOT / "OBS_WEBSOCKET_GUIDE.txt"


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


def pyside_collect_args() -> list[str]:
    """PyInstaller flags for the Qt modules Stella Video actually uses.

    Do not use ``--collect-all PySide6`` here. It bundles the full Qt tree
    (3D, WebEngine, Quick/QML tooling, designer tools, etc.), which makes the
    output huge and increases the chance that an unused Qt DLL/plugin fails to
    load on older Windows 10 systems.
    """
    args: list[str] = [
        "--collect-submodules", "shiboken6",
    ]
    for mod in (
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "shiboken6",
    ):
        args += ["--hidden-import", mod]
    return args


CHECK_INSTALL_BAT = r"""@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo === Pemeriksaan instalasi Stella Video ===
echo.
echo Folder: %CD%
echo.

set OK=1

if not exist "Stella Video.exe" (
  echo [GAGAL] Stella Video.exe tidak ada di folder ini.
  set OK=0
)

if not exist "_internal" (
  echo [GAGAL] Folder _internal tidak ada.
  echo         Jalankan dari folder lengkap hasil zip — jangan hanya menyalin .exe.
  set OK=0
) else (
  if not exist "_internal\PySide6\Qt6Core.dll" (
    echo [GAGAL] Qt6Core.dll hilang — instalasi tidak lengkap.
    echo         Coba ekstrak ulang zip; periksa apakah antivirus memblokir file.
    set OK=0
  ) else (
    echo [OK] Qt6Core.dll
  )
  if not exist "_internal\PySide6\plugins\platforms\qwindows.dll" (
    echo [GAGAL] Plugin Windows Qt ^(qwindows.dll^) hilang.
    set OK=0
  ) else (
    echo [OK] qwindows.dll
  )
  if not exist "_internal\PySide6\msvcp140.dll" (
    echo [GAGAL] msvcp140.dll hilang di bundle.
    set OK=0
  ) else (
    echo [OK] msvcp140.dll di bundle
  )
)

echo.
echo Arsitektur CPU/OS: %PROCESSOR_ARCHITECTURE%
if /i "%PROCESSOR_ARCHITECTURE%"=="x86" (
  echo [GAGAL] Windows 32-bit. Stella Video membutuhkan Windows 10/11 64-bit.
  set OK=0
)

if %OK%==1 (
  echo.
  echo Pemeriksaan dasar LULUS.
  echo Jika .exe tetap error, install Visual C++ 64-bit lalu restart:
  echo   https://aka.ms/vcredist/x64
) else (
  echo.
  echo Instalasi bermasalah. Minta zip lengkap dan ekstrak ke folder lokal
  echo ^(bukan OneDrive "online-only"^).
)
echo.
pause
"""


def write_dist_helpers(dist_dir: Path) -> None:
    """Drop a one-click checker next to the .exe for end-user troubleshooting."""
    checker = dist_dir / "Cek Instalasi.bat"
    checker.write_text(CHECK_INSTALL_BAT, encoding="utf-8")
    print(f"[dist] wrote {checker.name}")
    if OBS_GUIDE.is_file():
        shutil.copy2(OBS_GUIDE, dist_dir / OBS_GUIDE.name)
        print(f"[dist] copied {OBS_GUIDE.name}")


def verify_qt_bundle(dist_dir: Path) -> None:
    """Warn if Qt6Core.dll did not land in the output folder."""
    if sys.platform != "win32":
        return
    hits = list(dist_dir.rglob("Qt6Core.dll"))
    if hits:
        print(f"[verify] Qt6Core.dll -> {hits[0].relative_to(dist_dir)}")
        return
    print("[verify] WARNING: Qt6Core.dll not found under dist/. "
          "The .exe will fail with 'DLL load failed while importing QtCore'. "
          "Try: pip install -U pyinstaller PySide6, then rebuild.")


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
    for h in ("mpv", "websocket"):
        args += ["--hidden-import", h]

    args += pyside_collect_args()

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

    dist_dir = out_root / DIST_NAME
    exe = dist_dir / f"{DIST_NAME}.exe"
    if exe.is_file():
        verify_qt_bundle(dist_dir)
        write_dist_helpers(dist_dir)
        print()
        print(f"[build] DONE: {exe}")
        print(f"[build] distribute the ENTIRE folder (not just the .exe):")
        print(f"         {dist_dir}")
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
