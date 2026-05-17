"""Download libmpv-2.dll for Windows into ./libs/.

Pulls the latest mpv-dev-x86_64 archive from SourceForge, extracts
libmpv-2.dll into the local libs/ folder. Requires py7zr (auto-installed)
on first run.

Usage:
    python setup_libmpv.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


RSS_URL = "https://sourceforge.net/projects/mpv-player-windows/rss?path=/libmpv"
LIBS_DIR = Path(__file__).resolve().parent / "libs"
TARGET_DLL = "libmpv-2.dll"


def fetch_latest_archive_url() -> str:
    print(f"Fetching SourceForge index: {RSS_URL}")
    req = urllib.request.Request(RSS_URL, headers={"User-Agent": "stella-video/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read().decode("utf-8", errors="replace")
    root = ET.fromstring(data)
    # RSS 2.0: rss/channel/item/link  — first item is the newest
    for item in root.iterfind(".//item"):
        link = item.findtext("link") or ""
        title = item.findtext("title") or ""
        if "mpv-dev-x86_64" in title and title.endswith(".7z"):
            print(f"Latest:  {title.strip()}")
            print(f"Link:    {link}")
            return link
    raise RuntimeError("Could not find a recent mpv-dev-x86_64 .7z in the SF feed.")


def download(url: str, dest: Path) -> Path:
    print("Downloading… (this is ~30–40 MB)")
    # SourceForge redirects to a CDN mirror; urllib handles redirects.
    req = urllib.request.Request(url, headers={"User-Agent": "stella-video/0.1"})
    dest.parent.mkdir(exist_ok=True)
    with urllib.request.urlopen(req, timeout=180) as resp, open(dest, "wb") as f:
        total = 0
        while True:
            buf = resp.read(1024 * 256)
            if not buf:
                break
            f.write(buf)
            total += len(buf)
            print(f"  {total / 1_048_576:6.1f} MB", end="\r", flush=True)
    print()
    return dest


def _find_7z_exe() -> str | None:
    """Locate a usable 7-Zip command-line tool."""
    for candidate in ("7z", "7z.exe", "7zz"):
        path = shutil.which(candidate)
        if path:
            return path
    for fixed in (
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        r"C:\Windows\System32\7z.exe",
    ):
        if Path(fixed).is_file():
            return fixed
    return None


def _extract_with_7z(seven_zip: str, archive_path: Path, stage: Path) -> Path:
    print(f"Extracting with: {seven_zip}")
    # `e` = extract without paths (flatten), `-y` = assume yes
    result = subprocess.run(
        [seven_zip, "e", str(archive_path), f"-o{stage}", TARGET_DLL, "-r", "-y"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"7z extraction failed (exit {result.returncode}):\n"
            f"{result.stdout}\n{result.stderr}"
        )
    extracted = stage / TARGET_DLL
    if not extracted.is_file():
        raise RuntimeError(
            f"7z extracted ok but {TARGET_DLL} not found at {extracted}. "
            f"Output:\n{result.stdout}"
        )
    return extracted


def _extract_with_py7zr(archive_path: Path, stage: Path) -> Path:
    try:
        import py7zr  # type: ignore
    except ImportError:
        print("Installing py7zr (for .7z extraction)…")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "py7zr"])
        import py7zr  # type: ignore

    with py7zr.SevenZipFile(str(archive_path), mode="r") as z:
        names = z.getnames()
        matches = [n for n in names if n.lower().endswith(TARGET_DLL.lower())]
        if not matches:
            raise RuntimeError(
                f"{TARGET_DLL} not found inside the archive. "
                f"Contents:\n  " + "\n  ".join(names[:30])
            )
        wanted = matches[0]
        print(f"Extracting (py7zr): {wanted}")
        z.extract(path=str(stage), targets=[wanted])
    src = stage / wanted
    if not src.is_file():
        raise RuntimeError(f"py7zr extraction produced no file at {src}")
    return src


def extract_dll(archive_path: Path) -> None:
    LIBS_DIR.mkdir(exist_ok=True)
    target = LIBS_DIR / TARGET_DLL
    stage = LIBS_DIR / "_stage"
    if stage.exists():
        shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir()

    seven_zip = _find_7z_exe()
    try:
        if seven_zip:
            src = _extract_with_7z(seven_zip, archive_path, stage)
        else:
            print("7-Zip not found; falling back to py7zr (may fail on BCJ2 archives).")
            src = _extract_with_py7zr(archive_path, stage)

        if target.exists():
            target.unlink()
        src.replace(target)
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    size_mb = target.stat().st_size / 1_048_576
    print(f"Wrote: {target}  ({size_mb:.1f} MB)")


def main() -> int:
    print("Stella Video — libmpv setup")
    print("=" * 40)
    if (LIBS_DIR / TARGET_DLL).is_file():
        print(f"{TARGET_DLL} already present at {LIBS_DIR}.")
        try:
            ans = input("Re-download anyway? [y/N] ").strip().lower()
        except EOFError:
            ans = "n"
        if ans != "y":
            return 0
    archive_path = LIBS_DIR / "_libmpv_archive.7z"
    try:
        if not archive_path.is_file() or archive_path.stat().st_size < 1_000_000:
            url = fetch_latest_archive_url()
            download(url, archive_path)
        else:
            print(f"Using cached archive: {archive_path}")
        extract_dll(archive_path)
    except Exception as e:  # noqa: BLE001
        print()
        print(f"Setup failed: {e}")
        print()
        print("You can also install manually:")
        print("  1. Open https://sourceforge.net/projects/mpv-player-windows/files/libmpv/")
        print("  2. Download the newest 'mpv-dev-x86_64-*.7z'")
        print(f"  3. Extract libmpv-2.dll into: {LIBS_DIR}")
        return 1
    # Optionally clean the archive
    try:
        archive_path.unlink()
    except OSError:
        pass
    print()
    print("Done. You can now run:  python run.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
