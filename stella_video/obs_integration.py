"""OBS WebSocket integration and Live Studio panel."""
from __future__ import annotations

import base64
import hashlib
import json
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Callable

import websocket  # websocket-client
from PySide6.QtCore import QObject, QSettings, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QTextEdit, QGroupBox, QCheckBox, QMessageBox,
)


@dataclass(frozen=True)
class StreamingPreset:
    key: str
    label: str
    server: str
    note: str


PLATFORM_PRESETS: list[StreamingPreset] = [
    StreamingPreset(
        "shopee",
        "Shopee Live",
        "",
        "Copy Server URL and Stream Key from Shopee Live Center. Keys may change per session.",
    ),
    StreamingPreset(
        "tiktok",
        "TikTok Live",
        "",
        "Requires TikTok LIVE/RTMP access. Paste the RTMP URL and key shown by TikTok/Live Center.",
    ),
    StreamingPreset(
        "youtube",
        "YouTube Live",
        "rtmps://a.rtmps.youtube.com/live2",
        "Paste the Stream Key from YouTube Studio > Live Control Room. RTMPS is preferred.",
    ),
    StreamingPreset(
        "instagram",
        "Instagram Live",
        "",
        "Use Instagram Live Producer from a Professional account. RTMP credentials expire per session.",
    ),
    StreamingPreset(
        "custom",
        "Custom RTMP",
        "",
        "Use any RTMP/RTMPS server URL and stream key.",
    ),
]


class ObsWebSocketError(RuntimeError):
    pass


class ObsWebSocketClient:
    """Tiny obs-websocket 5.x JSON client.

    We keep this local instead of depending on a heavy OBS SDK. The protocol is
    simple: connect, receive Hello, Identify, then send Request messages.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 4455,
                 password: str = "", timeout: float = 5.0):
        self.host = host.strip() or "127.0.0.1"
        self.port = int(port)
        self.password = password
        self.timeout = timeout
        self.ws: websocket.WebSocket | None = None
        self.obs_version = ""
        self.websocket_version = ""

    def connect(self) -> None:
        url = f"ws://{self.host}:{self.port}"
        self.ws = websocket.create_connection(
            url,
            timeout=self.timeout,
            subprotocols=["obswebsocket.json"],
        )
        hello = self._recv()
        if hello.get("op") != 0:
            raise ObsWebSocketError("OBS did not send a Hello message.")

        data = hello.get("d", {})
        self.obs_version = str(data.get("obsStudioVersion", ""))
        self.websocket_version = str(data.get("obsWebSocketVersion", ""))
        rpc_version = int(data.get("rpcVersion", 1))

        identify: dict[str, Any] = {
            "rpcVersion": min(rpc_version, 1),
            "eventSubscriptions": 0,
        }
        auth = data.get("authentication")
        if auth:
            if not self.password:
                raise ObsWebSocketError("OBS WebSocket requires a password.")
            identify["authentication"] = self._auth_string(
                self.password,
                str(auth["salt"]),
                str(auth["challenge"]),
            )

        self._send({"op": 1, "d": identify})
        identified = self._recv()
        if identified.get("op") != 2:
            raise ObsWebSocketError("OBS authentication failed or protocol mismatch.")

    def close(self) -> None:
        if self.ws is not None:
            try:
                self.ws.close()
            finally:
                self.ws = None

    def request(self, request_type: str, request_data: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.ws is None:
            raise ObsWebSocketError("Not connected to OBS.")
        request_id = str(uuid.uuid4())
        payload = {
            "op": 6,
            "d": {
                "requestType": request_type,
                "requestId": request_id,
                "requestData": request_data or {},
            },
        }
        self._send(payload)
        while True:
            msg = self._recv()
            if msg.get("op") != 7:
                continue
            data = msg.get("d", {})
            if data.get("requestId") != request_id:
                continue
            status = data.get("requestStatus", {})
            if not status.get("result", False):
                comment = status.get("comment") or f"OBS request failed: {request_type}"
                raise ObsWebSocketError(str(comment))
            return data.get("responseData", {})

    def get_version(self) -> dict[str, Any]:
        return self.request("GetVersion")

    def get_stream_status(self) -> dict[str, Any]:
        return self.request("GetStreamStatus")

    def set_custom_rtmp(self, server: str, key: str) -> None:
        self.request(
            "SetStreamServiceSettings",
            {
                "streamServiceType": "rtmp_custom",
                "streamServiceSettings": {
                    "server": server,
                    "key": key,
                },
            },
        )

    def start_stream(self) -> None:
        self.request("StartStream")

    def stop_stream(self) -> None:
        self.request("StopStream")

    def _send(self, payload: dict[str, Any]) -> None:
        if self.ws is None:
            raise ObsWebSocketError("Not connected to OBS.")
        self.ws.send(json.dumps(payload))

    def _recv(self) -> dict[str, Any]:
        if self.ws is None:
            raise ObsWebSocketError("Not connected to OBS.")
        raw = self.ws.recv()
        return json.loads(raw)

    @staticmethod
    def _auth_string(password: str, salt: str, challenge: str) -> str:
        secret = base64.b64encode(
            hashlib.sha256((password + salt).encode("utf-8")).digest()
        ).decode("ascii")
        return base64.b64encode(
            hashlib.sha256((secret + challenge).encode("utf-8")).digest()
        ).decode("ascii")


class ObsTaskSignals(QObject):
    success = Signal(str, object)
    error = Signal(str)


class LiveStudioPanel(QWidget):
    """Dockable OBS streaming control surface."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LiveStudioPanel")
        self._settings = QSettings("StellaVideo", "Stella Video")
        self._client: ObsWebSocketClient | None = None
        self._signals = ObsTaskSignals()
        self._signals.success.connect(self._on_task_success)
        self._signals.error.connect(self._on_task_error)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(3000)
        self._poll_timer.timeout.connect(self.refresh_status)

        self._build_ui()
        self._load_settings()
        self._on_platform_changed()
        self._set_connected(False)

    def shutdown(self) -> None:
        self._poll_timer.stop()
        if self._client is not None:
            self._client.close()
            self._client = None

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title = QLabel("Live Studio")
        title.setObjectName("PanelTitle")
        subtitle = QLabel("Control OBS streaming from Stella Video.")
        subtitle.setObjectName("MutedLabel")
        root.addWidget(title)
        root.addWidget(subtitle)

        obs_box = QGroupBox("OBS WebSocket")
        obs_form = QFormLayout(obs_box)
        obs_form.setLabelAlignment(Qt.AlignRight)
        self.host_edit = QLineEdit("127.0.0.1")
        self.port_edit = QLineEdit("4455")
        self.port_edit.setMaximumWidth(82)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("OBS WebSocket password")
        obs_form.addRow("Host:", self.host_edit)
        obs_form.addRow("Port:", self.port_edit)
        obs_form.addRow("Password:", self.password_edit)
        row = QHBoxLayout()
        self.connect_btn = QPushButton("Connect")
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.setEnabled(False)
        self.connect_btn.clicked.connect(self.connect_obs)
        self.disconnect_btn.clicked.connect(self.disconnect_obs)
        row.addWidget(self.connect_btn)
        row.addWidget(self.disconnect_btn)
        obs_form.addRow("", row)
        root.addWidget(obs_box)

        dest_box = QGroupBox("Destination")
        dest_form = QFormLayout(dest_box)
        dest_form.setLabelAlignment(Qt.AlignRight)
        self.platform_combo = QComboBox()
        for preset in PLATFORM_PRESETS:
            self.platform_combo.addItem(preset.label, preset.key)
        self.platform_combo.currentIndexChanged.connect(self._on_platform_changed)
        self.server_edit = QLineEdit()
        self.server_edit.setPlaceholderText("rtmp:// or rtmps:// server URL")
        self.stream_key_edit = QLineEdit()
        self.stream_key_edit.setEchoMode(QLineEdit.Password)
        self.stream_key_edit.setPlaceholderText("Stream key")
        self.show_key_check = QCheckBox("show")
        self.show_key_check.toggled.connect(
            lambda checked: self.stream_key_edit.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        key_row = QHBoxLayout()
        key_row.addWidget(self.stream_key_edit, 1)
        key_row.addWidget(self.show_key_check)
        self.note_label = QLabel("")
        self.note_label.setWordWrap(True)
        self.note_label.setObjectName("MutedLabel")
        dest_form.addRow("Platform:", self.platform_combo)
        dest_form.addRow("Server:", self.server_edit)
        dest_form.addRow("Key:", key_row)
        dest_form.addRow("", self.note_label)
        root.addWidget(dest_box)

        status_box = QGroupBox("Stream Control")
        status_layout = QVBoxLayout(status_box)
        self.status_label = QLabel("OBS disconnected")
        self.status_label.setObjectName("LiveStatus")
        status_layout.addWidget(self.status_label)
        action_row = QHBoxLayout()
        self.apply_btn = QPushButton("Apply RTMP")
        self.start_btn = QPushButton("Start Live")
        self.stop_btn = QPushButton("Stop")
        self.refresh_btn = QPushButton("Refresh")
        self.apply_btn.clicked.connect(self.apply_destination)
        self.start_btn.clicked.connect(self.start_stream)
        self.stop_btn.clicked.connect(self.stop_stream)
        self.refresh_btn.clicked.connect(self.refresh_status)
        action_row.addWidget(self.apply_btn)
        action_row.addWidget(self.start_btn)
        action_row.addWidget(self.stop_btn)
        action_row.addWidget(self.refresh_btn)
        status_layout.addLayout(action_row)
        root.addWidget(status_box)

        capture_box = QGroupBox("OBS Capture Setup")
        capture_layout = QVBoxLayout(capture_box)
        self.capture_note = QTextEdit()
        self.capture_note.setReadOnly(True)
        self.capture_note.setFixedHeight(112)
        self.capture_note.setPlainText(
            "1. Open OBS > Tools > WebSocket Server Settings, enable the server, keep port 4455.\n"
            "2. In OBS, add a Window Capture source and choose the Stella Video window.\n"
            "3. Make sure OBS has an audio source: Desktop Audio, Application Audio Capture, or your mixer.\n"
            "4. OBS can stream to one destination at a time. For simultaneous Shopee/TikTok/YouTube/Instagram, use an OBS Multi-RTMP plugin or a restream service."
        )
        capture_layout.addWidget(self.capture_note)
        root.addWidget(capture_box)
        root.addStretch(1)

    def _load_settings(self) -> None:
        self.host_edit.setText(str(self._settings.value("obs/host", "127.0.0.1")))
        self.port_edit.setText(str(self._settings.value("obs/port", "4455")))
        platform = str(self._settings.value("obs/platform", "shopee"))
        index = self.platform_combo.findData(platform)
        if index >= 0:
            self.platform_combo.setCurrentIndex(index)
        self.server_edit.setText(str(self._settings.value("obs/server", "")))

    def _save_settings(self) -> None:
        self._settings.setValue("obs/host", self.host_edit.text().strip())
        self._settings.setValue("obs/port", self.port_edit.text().strip())
        self._settings.setValue("obs/platform", self.platform_combo.currentData())
        self._settings.setValue("obs/server", self.server_edit.text().strip())

    def _current_preset(self) -> StreamingPreset:
        key = self.platform_combo.currentData()
        return next((p for p in PLATFORM_PRESETS if p.key == key), PLATFORM_PRESETS[0])

    def _on_platform_changed(self) -> None:
        preset = self._current_preset()
        self.note_label.setText(preset.note)
        if preset.server and not self.server_edit.text().strip():
            self.server_edit.setText(preset.server)

    def connect_obs(self) -> None:
        self._save_settings()
        host = self.host_edit.text().strip() or "127.0.0.1"
        port = int(self.port_edit.text().strip() or "4455")
        password = self.password_edit.text()

        def connect_worker(_client: ObsWebSocketClient | None = None) -> dict[str, Any]:
            client = ObsWebSocketClient(host, port, password)
            client.connect()
            self._client = client
            return client.get_version()

        self._run_task("connect", connect_worker)

    def disconnect_obs(self) -> None:
        self._poll_timer.stop()
        if self._client is not None:
            self._client.close()
            self._client = None
        self._set_connected(False)
        self.status_label.setText("OBS disconnected")

    def apply_destination(self) -> None:
        server = self.server_edit.text().strip()
        key = self.stream_key_edit.text().strip()
        if not server or not key:
            QMessageBox.warning(self, "Missing RTMP Settings", "Isi Server URL dan Stream Key dulu.")
            return
        self._save_settings()
        self._run_task("apply", lambda client: client.set_custom_rtmp(server, key))

    def start_stream(self) -> None:
        server = self.server_edit.text().strip()
        key = self.stream_key_edit.text().strip()
        if not server or not key:
            QMessageBox.warning(self, "Missing RTMP Settings", "Isi Server URL dan Stream Key dulu.")
            return
        self._save_settings()

        def apply_and_start(client: ObsWebSocketClient) -> None:
            client.set_custom_rtmp(server, key)
            client.start_stream()

        self._run_task("start", apply_and_start)

    def stop_stream(self) -> None:
        self._run_task("stop", lambda client: client.stop_stream())

    def refresh_status(self) -> None:
        self._run_task("status", lambda client: client.get_stream_status())

    def _run_task(self, name: str, fn: Callable[[ObsWebSocketClient], Any]) -> None:
        def worker() -> None:
            try:
                if name != "connect":
                    if self._client is None:
                        raise ObsWebSocketError("Connect to OBS first.")
                    result = fn(self._client)
                else:
                    result = fn(None)  # type: ignore[arg-type]
                self._signals.success.emit(name, result)
            except Exception as exc:  # noqa: BLE001
                self._signals.error.emit(str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_task_success(self, name: str, result: object) -> None:
        if name == "connect":
            self._set_connected(True)
            data = result if isinstance(result, dict) else {}
            version = data.get("obsVersion") or data.get("obsStudioVersion") or "OBS"
            self.status_label.setText(f"Connected: {version}")
            self._poll_timer.start()
            self.refresh_status()
        elif name == "apply":
            self.status_label.setText(f"Destination ready: {self._current_preset().label}")
        elif name == "start":
            self.status_label.setText("Starting stream...")
            self.refresh_status()
        elif name == "stop":
            self.status_label.setText("Stopping stream...")
            self.refresh_status()
        elif name == "status" and isinstance(result, dict):
            active = bool(result.get("outputActive"))
            reconnecting = bool(result.get("outputReconnecting"))
            timecode = result.get("outputTimecode", "00:00:00")
            congestion = float(result.get("outputCongestion") or 0)
            if active:
                suffix = "reconnecting" if reconnecting else "live"
                self.status_label.setText(
                    f"OBS is {suffix} - {timecode} - congestion {congestion:.0%}"
                )
            else:
                self.status_label.setText("OBS connected - stream idle")

    def _on_task_error(self, message: str) -> None:
        self.status_label.setText(f"OBS error: {message}")
        if "Connect to OBS" in message or "refused" in message.lower():
            self._set_connected(False)

    def _set_connected(self, connected: bool) -> None:
        self.connect_btn.setEnabled(not connected)
        self.disconnect_btn.setEnabled(connected)
        for widget in (self.apply_btn, self.start_btn, self.stop_btn, self.refresh_btn):
            widget.setEnabled(connected)
