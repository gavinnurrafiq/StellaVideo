# Stella Video

A libmpv-powered desktop media player built with Qt. The modern build uses
PySide6/Qt6, while the Windows 10 1511 legacy build uses PySide2/Qt5. Frame-accurate
seeking, animated UI, scrubbing thumbnails, and a backdrop that adapts
to whatever is on screen.

![Stella Video logo](stella_video/assets/logo.png)

---

## Features

### Playback
- **libmpv backend** — wide codec support, hardware decoding, network streams (mpv handles `http://`, `https://`, `rtsp://`, plus yt-dlp URLs)
- **Frame-accurate seeking** with `hr-seek=yes` enabled by default
- **Scrub thumbnail preview** — hover the seek bar to see the frame at any position (rendered via ffmpeg hybrid seek)
- **A-B loop** to repeat a section
- **Chapter navigation** with marks on the seek bar
- **Playback speed** 0.25× – 4×, A-B loop, frame-by-frame stepping (`,` / `.`)
- **Folder-based next/previous** with natural-numeric ordering (`Episode 02` before `Episode 10`)

### Audio & Subtitles
- Audio + subtitle track switching from the menu
- Audio / subtitle delay sync (live, finer than mpv defaults)
- Drag-and-drop subtitle files
- Subtitle styling (font, size, color, outline, bold/italic) from Preferences

### Interface
- **Custom frameless title bar** with an animated gradient that reacts to the video — a sunset shot tints it orange, an underwater scene tints it blue
- **Animated backdrop** when no video is loaded (uses `assets/background.mp4` looped + zoom-to-fill)
- **Auto-hide UI** during playback (returns on mouse move)
- **Splash screen** with looping video on launch
- Black overlay around the playing video for cinema-style viewing comfort

### Convenience
- Recent files list, drag-and-drop, "Open Folder" auto-queues a directory
- Playlist dock with drag-to-reorder
- Screenshots (with or without subtitles)
- Settings persisted via QSettings

---

## Requirements

- **Python 3.10+** for the modern PySide6 build
- **Python 3.9** for the Windows 10 1511 PySide2 legacy build
- **libmpv DLL** (Windows) — placed in `libs/` for modern builds or `libs/win1511/` for legacy builds
- **ffmpeg.exe** on `PATH` — required for the scrub thumbnail preview and reactive title-bar color sampling
- Modern build: Windows 10 1809+ / Windows 11
- Legacy build: Windows 10 1511 build 10586+ 64-bit

### Python packages
```
pip install -r requirements-win10.txt
pip install -r requirements-win1511.txt
```

---

## Quick Start

### Run from source

```powershell
git clone https://github.com/USER/Stella-Video.git
cd Stella-Video

# Recommended: virtualenv
python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt

# Download libmpv-2.dll automatically (one-time, ~30 MB)
python setup_libmpv.py

python run.py
```

> **Note:** `libs/libmpv-2.dll` is not in git (115 MB, over GitHub's
> file-size limit). The `setup_libmpv.py` script downloads it from
> the official SourceForge build.

For Windows 10 1511 legacy builds:

```powershell
python setup_libmpv_win1511.py
python build_exe_win1511.py
```

### Open a file
- Drag a video onto the window
- Or `File → Open File…` (`Ctrl+O`)
- Or `python run.py "path\to\video.mp4"`

---

## Keyboard Shortcuts

| Action | Shortcut |
|---|---|
| Play / Pause | `Space` |
| Seek ±5s | `←` / `→` |
| Seek ±30s | `Shift+←` / `Shift+→` |
| Seek ±60s | `Ctrl+←` / `Ctrl+→` |
| Speed −/+ | `[` / `]` |
| Reset speed | `Backspace` |
| Volume +/− | `↑` / `↓` |
| Mute | `M` |
| Toggle subtitles | `V` |
| Subtitle delay −/+ | `Z` / `X` |
| A-B loop set / clear | `L` / `Shift+L` |
| Previous / Next chapter | `PgUp` / `PgDown` |
| Fullscreen | `F11` (or double-click) |
| Toggle playlist | `Ctrl+L` |
| Screenshot | `S` (or `Shift+S` to save-as) |
| Video adjustments | `Ctrl+E` |
| Open file / URL / folder | `Ctrl+O` / `Ctrl+U` / `Ctrl+Shift+O` |
| Add subtitle file | `Ctrl+T` |
| Preferences | `Ctrl+,` |
| Resize to video | `Ctrl+R` |
| Always on top | `Ctrl+Shift+T` |
| Show shortcuts list | `F1` |

---

## Project Layout

```
Stella Video/
├── libs/                          libmpv-2.dll lives here
├── stella_video/
│   ├── assets/
│   │   ├── background.mp4         animated welcome backdrop
│   │   ├── loop.mp4               splash screen loop
│   │   ├── logo.png               app icon
│   │   └── icons/                 playback control icons
│   ├── app.py                     QApplication + main()
│   ├── main_window.py             QMainWindow, menus, layout
│   ├── player.py                  libmpv wrapper with Qt signals
│   ├── qt.py                      PySide6/PySide2 compatibility layer
│   ├── video_widget.py            native widget hosting mpv output
│   ├── video_stack.py             foreground video + backdrop stack
│   ├── controls.py                seek bar, play controls, volume
│   ├── playlist.py                playlist dock panel
│   ├── thumbnail.py               ffmpeg-based scrub preview
│   ├── color_sampler.py           frame averaging for reactive title bar
│   ├── custom_title_bar.py        frameless title bar with animated gradient
│   ├── splash.py                  startup splash with looping video
│   ├── preferences.py             AppSettings + PreferencesDialog
│   ├── dialogs.py                 video adjust / sync / about
│   ├── styles.py                  dark theme QSS
│   ├── utils.py                   time format, file filters
│   └── __init__.py
├── requirements.txt
├── requirements-win10.txt
├── requirements-win1511.txt
├── run.py                         entry point
├── setup_libmpv.py                auto-download libmpv-2.dll
├── setup_libmpv_win1511.py        auto-download legacy mpv-1.dll
├── build_exe.py                   PyInstaller modern build script
└── build_exe_win1511.py           PyInstaller Windows 10 1511 legacy build script
```

---

## Building a Standalone .exe

```powershell
pip install pyinstaller pillow
python build_exe.py
```

Output: `dist/Stella Video/Stella Video.exe` (along with required DLLs and assets).

For Windows 10 1511:

```powershell
python setup_libmpv_win1511.py
python build_exe_win1511.py
```

Output: `dist-win1511/Stella Video/Stella Video.exe`.

To distribute, zip the entire `dist/Stella Video/` folder for modern Windows, or the entire `dist-win1511/Stella Video/` folder for Windows 10 1511. The user does **not** need Python or any DLL installed — but should still install **ffmpeg** separately for thumbnail previews to work.

---

## Architecture Notes

- **mpv embedding** — `VideoFrame.winId()` is passed to mpv via the `wid` option. mpv renders into that native window via its D3D11 swapchain.
- **Why two mpv instances** — one for the user's video (the main `Player` class), one for the looping idle backdrop (`BackgroundPlayer`). They run independently.
- **Why ffmpeg, not mpv, for thumbnails** — `screenshot-raw` requires an active video output. Spawning a short-lived ffmpeg process per scrub gives reliable frame extraction without VO complications.
- **UI bars outside the mpv widget** — menu bar, control bar, status bar all live in QMainWindow slots (not inside the mpv-painted area), so mpv's destructive swapchain repaint can never erase them.
- **Reactive title bar** — every 1.5 s the `ColorSampler` spawns ffmpeg to extract a 32×32 frame at the current playback position, averages the pixels, and tweens the title bar's gradient base toward that color.

---

## License

**PolyForm Noncommercial License 1.0.0** — see [LICENSE](LICENSE).

You may use, copy, modify, and redistribute Stella Video freely for
**non-commercial** purposes: personal use, research, education,
hobby projects, religious/charitable/government use, fair use under
applicable law.

You **may not** use it for any commercial purpose without a separate
license from the author. "Commercial" includes selling the software,
selling a service that incorporates it, bundling it with a paid product,
or using it in revenue-generating internal operations of a for-profit
business.

Third-party components keep their own licenses:

- libmpv — LGPL 2.1+
- ffmpeg — LGPL or GPL depending on build options
- PySide6 — LGPL 3 (with a commercial option from Qt Company)

---

## Contributing

Pull requests welcome. By submitting a PR you agree to license your
contribution under the same PolyForm Noncommercial License as the rest
of the project.

If you want a commercial license, open an issue.

---

## Credits

- [mpv](https://mpv.io/) — the video engine
- [python-mpv](https://github.com/jaseg/python-mpv) — Python bindings
- [PySide6](https://doc.qt.io/qtforpython-6/) — Qt for Python
- [ffmpeg](https://ffmpeg.org/) — frame extraction for thumbnails
