"""Download the older libmpv DLL used by the Windows 10 1511 legacy build."""
from __future__ import annotations

import shutil
import subprocess
import urllib.request
from pathlib import Path


URL = (
    "https://sourceforge.net/projects/mpv-player-windows/files/libmpv/"
    "mpv-dev-x86_64-20211017-git-e13fe12.7z/download"
)
ROOT = Path(__file__).resolve().parent
LEGACY_LIBS = ROOT / "libs" / "win1511"
ARCHIVE = LEGACY_LIBS / "_libmpv_win1511_20211017.7z"
TARGET_DLL = "mpv-1.dll"
SEVEN_Z_MAGIC = b"7z\xbc\xaf\x27\x1c"


def _find_7z_exe() -> str | None:
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


def download() -> None:
    LEGACY_LIBS.mkdir(parents=True, exist_ok=True)
    print(f"Downloading legacy libmpv archive:\n  {URL}")
    req = urllib.request.Request(URL, headers={"User-Agent": "stella-video/legacy"})
    with urllib.request.urlopen(req, timeout=180) as resp, open(ARCHIVE, "wb") as f:
        total = 0
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
            print(f"  {total / 1_048_576:6.1f} MB", end="\r", flush=True)
    print()
    with open(ARCHIVE, "rb") as f:
        if f.read(len(SEVEN_Z_MAGIC)) != SEVEN_Z_MAGIC:
            raise RuntimeError(f"Downloaded file is not a 7z archive: {ARCHIVE}")


def extract() -> None:
    seven_zip = _find_7z_exe()
    if not seven_zip:
        raise RuntimeError("7-Zip is required. Install 7-Zip or place 7z.exe on PATH.")
    print(f"Extracting {TARGET_DLL} with {seven_zip}")
    result = subprocess.run(
        [seven_zip, "e", str(ARCHIVE), TARGET_DLL, f"-o{LEGACY_LIBS}", "-r", "-y"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout + "\n" + result.stderr)
    target = LEGACY_LIBS / TARGET_DLL
    if not target.is_file():
        raise RuntimeError(f"{TARGET_DLL} not found after extraction.")
    print(f"Wrote: {target} ({target.stat().st_size / 1_048_576:.1f} MB)")


def main() -> int:
    target = LEGACY_LIBS / TARGET_DLL
    if target.is_file():
        print(f"{TARGET_DLL} already exists at {target}")
        return 0
    download()
    extract()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
