"""Shared utilities."""
from __future__ import annotations

from pathlib import Path

VIDEO_EXTS = {
    ".mp4", ".mkv", ".webm", ".avi", ".mov", ".wmv", ".flv", ".m4v",
    ".mpg", ".mpeg", ".ts", ".m2ts", ".vob", ".ogv", ".3gp", ".rm", ".rmvb",
}
AUDIO_EXTS = {
    ".mp3", ".flac", ".wav", ".aac", ".ogg", ".opus", ".m4a", ".wma", ".ape",
}
SUBTITLE_EXTS = {".srt", ".ass", ".ssa", ".sub", ".vtt", ".idx", ".sup"}
MEDIA_EXTS = VIDEO_EXTS | AUDIO_EXTS


def is_media(path: str | Path) -> bool:
    return Path(path).suffix.lower() in MEDIA_EXTS


def is_subtitle(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUBTITLE_EXTS


def format_time(seconds: float | None, show_ms: bool = False) -> str:
    """Format seconds as H:MM:SS or M:SS (optionally with .mmm)."""
    if seconds is None or seconds < 0:
        return "--:--"
    total = float(seconds)
    h = int(total // 3600)
    m = int((total % 3600) // 60)
    s = int(total % 60)
    ms = int((total - int(total)) * 1000)
    if h > 0:
        base = f"{h}:{m:02d}:{s:02d}"
    else:
        base = f"{m:02d}:{s:02d}"
    if show_ms:
        base += f".{ms:03d}"
    return base


def media_file_filter() -> str:
    video = " ".join(f"*{e}" for e in sorted(VIDEO_EXTS))
    audio = " ".join(f"*{e}" for e in sorted(AUDIO_EXTS))
    all_media = " ".join(f"*{e}" for e in sorted(MEDIA_EXTS))
    return (
        f"Media Files ({all_media});;"
        f"Video Files ({video});;"
        f"Audio Files ({audio});;"
        "All Files (*)"
    )


def subtitle_file_filter() -> str:
    subs = " ".join(f"*{e}" for e in sorted(SUBTITLE_EXTS))
    return f"Subtitle Files ({subs});;All Files (*)"
