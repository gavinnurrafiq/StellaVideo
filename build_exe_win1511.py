"""Build Stella Video legacy package for Windows 10 1511.

This target uses PySide2/Qt5 instead of PySide6/Qt6. Build it from a
Python 3.9 environment installed with requirements-win1511.txt.

Usage:
    set STELLA_QT_BINDING=PySide2
    python build_exe_win1511.py

The output is written to dist-win1511/Stella Video/.
"""
from __future__ import annotations

import os
import json
import shutil
import subprocess
import sys
from pathlib import Path

from build_exe import ASSETS, DIST_NAME, OBS_GUIDE, ROOT, find_libmpv, generate_ico

DIST_ROOT = ROOT / "dist-win1511"
WORK_ROOT = ROOT / "build-win1511"
LEGACY_LIBS = ROOT / "libs" / "win1511"
BOOTSTRAP_BASE_MODULES = ("ipaddress",)


def find_legacy_libmpv() -> Path | None:
    for name in ("libmpv-2.dll", "mpv-2.dll", "mpv-1.dll"):
        candidate = LEGACY_LIBS / name
        if candidate.is_file():
            return candidate
    return find_libmpv()


def pyside2_collect_args() -> list[str]:
    args: list[str] = [
        "--collect-submodules", "shiboken2",
    ]
    for mod in (
        "PySide2.QtCore",
        "PySide2.QtGui",
        "PySide2.QtWidgets",
        "shiboken2",
    ):
        args += ["--hidden-import", mod]
    return args


CHECK_INSTALL_BAT = r"""@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo === Pemeriksaan instalasi Stella Video Legacy ===
echo.
echo Folder: %CD%
echo Target: Windows 10 1511 build 10586 atau lebih baru, 64-bit
echo.

set OK=1

if not exist "Stella Video.exe" (
  echo [GAGAL] Stella Video.exe tidak ada di folder ini.
  set OK=0
)

dir /s /b "Qt5Core.dll" >nul 2>nul
if errorlevel 1 (
  echo [GAGAL] Qt5Core.dll hilang - instalasi tidak lengkap.
  set OK=0
) else (
  echo [OK] Qt5Core.dll
)

dir /s /b "qwindows.dll" >nul 2>nul
if errorlevel 1 (
  echo [GAGAL] Plugin Windows Qt ^(qwindows.dll^) hilang.
  set OK=0
) else (
  echo [OK] qwindows.dll
)

dir /s /b "libmpv-2.dll" >nul 2>nul
if errorlevel 1 (
  dir /s /b "mpv-1.dll" >nul 2>nul
  if errorlevel 1 (
    echo [GAGAL] libmpv/mpv DLL hilang.
    set OK=0
  ) else (
    echo [OK] mpv-1.dll
  )
) else (
  echo [OK] libmpv-2.dll
)

echo.
echo Arsitektur CPU/OS: %PROCESSOR_ARCHITECTURE%
if /i "%PROCESSOR_ARCHITECTURE%"=="x86" (
  echo [GAGAL] Windows 32-bit. Stella Video membutuhkan Windows 64-bit.
  set OK=0
)

if %OK%==1 (
  echo.
  echo Pemeriksaan dasar LULUS.
  echo Jika .exe tetap error, install Visual C++ 64-bit lalu restart:
  echo   https://aka.ms/vcredist/x64
) else (
  echo.
  echo Instalasi bermasalah. Ekstrak ulang folder ZIP lengkap ke folder lokal.
)
echo.
pause
"""


def write_dist_helpers(dist_dir: Path) -> None:
    checker = dist_dir / "Cek Instalasi Legacy.bat"
    checker.write_text(CHECK_INSTALL_BAT, encoding="utf-8")
    print(f"[dist] wrote {checker.name}")
    if OBS_GUIDE.is_file():
        shutil.copy2(OBS_GUIDE, dist_dir / OBS_GUIDE.name)
        print(f"[dist] copied {OBS_GUIDE.name}")


def verify_qt5_bundle(dist_dir: Path) -> None:
    hits = list(dist_dir.rglob("Qt5Core.dll"))
    if hits:
        print(f"[verify] Qt5Core.dll -> {hits[0].relative_to(dist_dir)}")
        return
    print("[verify] WARNING: Qt5Core.dll not found under dist-win1511/.")


def run_pyinstaller_legacy(pyi_args: list[str]) -> int:
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    wrapper = WORK_ROOT / "_run_pyinstaller_win1511.py"
    wrapper.write_text(
        "\n".join([
            "import PyInstaller.__main__",
            "import PyInstaller.compat",
            f"base_modules = {BOOTSTRAP_BASE_MODULES!r}",
            "existing = list(PyInstaller.compat.PY3_BASE_MODULES)",
            "for name in base_modules:",
            "    if name not in existing:",
            "        existing.append(name)",
            "PyInstaller.compat.PY3_BASE_MODULES = existing",
            f"PyInstaller.__main__.run({json.dumps(pyi_args)})",
            "",
        ]),
        encoding="utf-8",
    )
    return subprocess.run([sys.executable, str(wrapper)], cwd=str(ROOT)).returncode


def ensure_legacy_environment() -> None:
    if sys.version_info[:2] != (3, 9):
        raise SystemExit(
            "Windows 10 1511 legacy build must use Python 3.9.\n"
            "Create an environment with Python 3.9 and install "
            "requirements-win1511.txt."
        )
    try:
        import PySide2  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "PySide2 is not installed. Run:\n"
            "  python -m pip install -r requirements-win1511.txt"
        ) from exc


def build(icon_path: Path) -> None:
    ensure_legacy_environment()
    os.environ["STELLA_QT_BINDING"] = "PySide2"

    libmpv = find_legacy_libmpv()
    if not libmpv:
        print("[warn] libmpv DLL not found in ./libs/. The bundled app will fail to start.")
    else:
        print(f"[libmpv] using {libmpv}")

    for d in (DIST_ROOT, WORK_ROOT):
        if d.exists():
            print(f"[clean] removing {d}")
            shutil.rmtree(d, ignore_errors=True)

    sep = ";" if sys.platform == "win32" else ":"
    args: list[str] = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name", DIST_NAME,
        "--windowed",
        "--icon", str(icon_path),
        "--distpath", str(DIST_ROOT),
        "--workpath", str(WORK_ROOT),
        "--specpath", str(ROOT),
        "--add-data", f"{ASSETS}{sep}stella_video/assets",
    ]
    if libmpv is not None:
        args += ["--add-binary", f"{libmpv}{sep}."]

    for h in ("mpv", "websocket"):
        args += ["--hidden-import", h]
    args += pyside2_collect_args()

    excludes = [
        "PySide6",
        "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
        "PySide2.QtWebEngineCore", "PySide2.QtWebEngineWidgets",
        "PySide2.QtWebChannel", "PySide2.QtWebSockets",
        "PySide2.QtQuick", "PySide2.QtQml", "PySide2.QtQuickWidgets",
        "PySide2.Qt3DCore", "PySide2.Qt3DRender", "PySide2.Qt3DInput",
        "PySide2.Qt3DLogic", "PySide2.Qt3DAnimation", "PySide2.Qt3DExtras",
        "PySide2.QtMultimedia", "PySide2.QtMultimediaWidgets",
        "PySide2.QtCharts", "PySide2.QtDataVisualization",
        "PySide2.QtPositioning", "PySide2.QtLocation", "PySide2.QtSensors",
        "PySide2.QtSerialPort", "PySide2.QtSql", "PySide2.QtBluetooth",
        "PySide2.QtNfc", "PySide2.QtRemoteObjects", "PySide2.QtScxml",
        "PySide2.QtTextToSpeech", "PySide2.QtTest", "PySide2.QtDesigner",
        "PySide2.QtUiTools", "tkinter", "matplotlib", "numpy", "scipy",
    ]
    for e in excludes:
        args += ["--exclude-module", e]

    args += [str(ROOT / "run.py")]

    print("[pyinstaller-win1511] " + " ".join(f'"{a}"' if " " in a else a for a in args[3:]))
    result_code = run_pyinstaller_legacy(args[3:])
    if result_code != 0:
        raise SystemExit(result_code)

    dist_dir = DIST_ROOT / DIST_NAME
    exe = dist_dir / f"{DIST_NAME}.exe"
    if not exe.is_file():
        print(f"[build] expected exe at {exe} - not found")
        raise SystemExit(1)
    verify_qt5_bundle(dist_dir)
    write_dist_helpers(dist_dir)
    print()
    print(f"[build] DONE: {exe}")
    print(f"[build] distribute the ENTIRE folder:")
    print(f"         {dist_dir}")


def main() -> int:
    print("Stella Video - Windows 10 1511 legacy build")
    print(f"Project root: {ROOT}")
    print()
    build(generate_ico())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
