<p align="center">
  <img src="resources/logo.png" alt="Stella Video Logo" width="220">
</p>

# Stella Video

Stella Video is a Windows desktop media player built around libmpv and PySide6.
It is designed for smooth playback, precise seeking, polished fullscreen viewing,
and OBS-based live streaming workflows.

## Download

Latest release:
[Stella Video 1.7.0](https://github.com/gavinnurrafiq/Stella-Video/releases/tag/Release5)

Recommended download:
[Stella.Video.1.7.0.Win10.1809-Plus.zip](https://github.com/gavinnurrafiq/Stella-Video/releases/download/Release5/Stella.Video.1.7.0.Win10.1809-Plus.zip)

Windows 10 1511 legacy download:
[Stella.Video.1.7.0.Win10.1511.Legacy.zip](https://github.com/gavinnurrafiq/Stella-Video/releases/download/Release5/Stella.Video.1.7.0.Win10.1511.Legacy.zip)

Portable usage:
1. Download the ZIP file for your Windows version.
2. Extract the full folder.
3. Open `Stella Video.exe`.

Do not run only the `.exe` after copying it out of the folder. The app needs the
bundled `_internal` runtime files.

## Windows Support

- Windows 11: supported.
- Windows 10 1809 or newer: supported.
- Windows 8/8.1: not supported by the current Qt 6/PySide6 runtime.
- 64-bit Windows is required.

The release build already includes the required app runtime and libmpv runtime.
Python is not required when using the installer or portable ZIP.

## Main Features

### Playback

- libmpv video backend with wide codec support.
- Audio and video playback.
- Frame-accurate seeking.
- Seekbar preview thumbnails while scrubbing.
- Resume playback per video.
- Watch History dialog with progress and last-played time.
- Remember per-video playback settings.
- Smart playlist from the current folder using natural file order.
- Mini Player Mode.
- Play, pause, stop, volume, speed control, next, previous, and folder ordering.
- A-B loop.
- Chapter markers and navigation.
- Screenshot support.
- Drag and drop media files.
- Open with Stella Video from Windows file context workflows.

### Video Canvas

- Dynamic canvas orientation from the control bar:
  - Horizontal / Landscape 16:9.
  - Vertical / Portrait 9:16.
- Video keeps its original aspect ratio.
- Landscape videos inside portrait canvas are letterboxed instead of stretched.
- Useful for TikTok, Shopee, Instagram, and other vertical live workflows.

### Interface

- Custom frameless UI.
- Dark/black visual theme.
- Animated video background when idle.
- Hybrid splash screen: static logo safety frame plus `loop.mp4` once the video renderer is ready.
- Auto-hide UI during playback.
- Fullscreen with `F11`.
- Playlist dock.
- OBS Live Studio dock.

### Streaming / OBS

Stella Video does not replace OBS. Stella Video controls OBS through WebSocket,
while OBS captures, encodes, and sends the live stream.

Supported streaming presets in Stella Video Live Studio:

- Shopee Live.
- TikTok Live.
- YouTube Live.
- Instagram Live.
- Custom RTMP / RTMPS.

OBS normally streams to one destination at a time. For simultaneous streaming to
Shopee, TikTok, YouTube, and Instagram, use an OBS Multi-RTMP plugin or a
restream service.

## OBS Download

Download OBS Studio from the official OBS website:
[https://obsproject.com/download](https://obsproject.com/download)

OBS is not bundled inside Stella Video. Keeping OBS separate is better because:

- OBS is a full streaming application with its own updates.
- Users may already have OBS installed.
- OBS plugins, scenes, encoders, and platform accounts are managed inside OBS.
- Bundling OBS would make the Stella Video installer much larger.

OBS Studio 28 and newer includes obs-websocket by default. No separate
obs-websocket download is needed for normal current OBS installs.

## How To Enable OBS WebSocket

1. Open OBS Studio.
2. Open `Tools`.
3. Click `WebSocket Server Settings`.
4. Enable `Enable WebSocket server`.
5. Keep the server port as `4455` unless you intentionally changed it.
6. Enable authentication if you want password protection.
7. Click `Show Connect Info`.
8. Copy or note:
   - Server IP.
   - Server Port.
   - Server Password.
9. Click `Apply` or `OK`.

Recommended Stella Video connection values when OBS is on the same PC:

```text
Host: 127.0.0.1
Port: 4455
Password: use the OBS WebSocket password, or leave blank if OBS authentication is disabled
```

## How To Connect Stella Video To OBS

1. Open OBS Studio.
2. Enable OBS WebSocket.
3. Open Stella Video.
4. Open `Live > OBS Live Studio`.
5. Enter host, port, and password.
6. Click `Connect`.
7. If connected, Stella Video will show OBS status and streaming controls.

## How To Capture Stella Video In OBS

1. In OBS, create or select a scene.
2. Add `Window Capture`.
3. Select the Stella Video window.
4. Add an audio source:
   - Desktop Audio, or
   - Application Audio Capture, or
   - your mixer/audio interface.
5. Play a video in Stella Video.
6. Confirm the video preview and audio meter are visible in OBS.

## How To Stream With RTMP

1. Open your platform live dashboard:
   - Shopee Live Center.
   - TikTok Live Center.
   - YouTube Studio Live Control Room.
   - Instagram Live Producer.
2. Create or prepare a live session.
3. Copy the RTMP/RTMPS server URL and stream key.
4. In Stella Video, open `Live > OBS Live Studio`.
5. Select the platform preset.
6. Paste the server URL.
7. Paste the stream key.
8. Click `Apply RTMP`.
9. Click `Start Live`.

Stream keys can expire. If streaming fails, copy a fresh key from the platform.

## Vertical Live Workflow

For TikTok, Shopee, Instagram, or other vertical formats:

1. In Stella Video, choose `Vertikal (Portrait - 9:16)` from the canvas dropdown.
2. In OBS, set your canvas/output layout for the live platform.
3. Capture Stella Video with `Window Capture`.
4. Fit or crop the captured source inside OBS as needed.
5. Use Stella Video Live Studio to apply the platform RTMP settings and start/stop the OBS stream.

## Included Help File

The release folder includes:

```text
OBS_WEBSOCKET_GUIDE.txt
```

Open that file for a step-by-step OBS WebSocket setup guide and troubleshooting
checklist.

## Troubleshooting

### Stella Video cannot connect to OBS

Check:

- OBS is open.
- OBS WebSocket server is enabled.
- Host is `127.0.0.1`.
- Port is `4455`, unless changed in OBS.
- Password matches OBS exactly.
- Windows Firewall is not blocking OBS.

### OBS connects but does not show Stella Video

Check:

- OBS has a `Window Capture` source.
- The source is capturing the Stella Video window.
- The source is visible in the active OBS scene.
- Stella Video is not minimized.

### Stream starts but audio is missing

Check:

- OBS has the correct audio capture source.
- The OBS audio meter moves while Stella Video plays.
- OBS streaming track/audio settings are enabled.

### TikTok, Shopee, or Instagram RTMP does not work

Check:

- Your account has live/RTMP access.
- The live session was created before starting the stream.
- The RTMP server URL is complete.
- The stream key is current and not expired.

## Keyboard Shortcuts

| Action | Shortcut |
|---|---|
| Play / Pause | `Space` |
| Seek 5 seconds | `Left` / `Right` |
| Seek 30 seconds | `Shift+Left` / `Shift+Right` |
| Seek 60 seconds | `Ctrl+Left` / `Ctrl+Right` |
| Speed down / up | `[` / `]` |
| Reset speed | `Backspace` |
| Volume up / down | `Up` / `Down` |
| Mute | `M` |
| A-B loop | `L` |
| Clear A-B loop | `Shift+L` |
| Previous / Next file or chapter | `PgUp` / `PgDown` |
| Fullscreen | `F11` |
| Toggle playlist | `Ctrl+L` |
| OBS Live Studio | `Ctrl+Shift+L` |
| Screenshot | `S` |
| Open file | `Ctrl+O` |
| Open URL | `Ctrl+U` |
| Open folder | `Ctrl+Shift+O` |
| Add subtitle | `Ctrl+T` |
| Preferences | `Ctrl+,` |

## Notes For Microsoft Store / Windows Trust

The current public build is an offline installer and portable ZIP. For Microsoft
Store or stronger Windows SmartScreen trust, the installer and executable should
be signed with a trusted code-signing certificate.

## License

Stella Video is released under the PolyForm Noncommercial License 1.0.0.

Third-party components keep their own licenses:

- libmpv.
- mpv.
- PySide6 / Qt for Python.
- FFmpeg where used for preview generation.
- OBS Studio if installed separately by the user.

## Credits

- [mpv](https://mpv.io/)
- [python-mpv](https://github.com/jaseg/python-mpv)
- [PySide6](https://doc.qt.io/qtforpython-6/)
- [FFmpeg](https://ffmpeg.org/)
- [OBS Studio](https://obsproject.com/)
