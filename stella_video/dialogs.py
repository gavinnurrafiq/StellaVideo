"""Dialogs — video adjustments, sub/audio sync, about."""
from __future__ import annotations

from .qt import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    Qt,
    Signal,
)

from . import __app_name__, __version__


class AdjustmentSlider(QSlider):
    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.setRange(-100, 100)
        self.setSingleStep(1)
        self.setPageStep(10)


class VideoAdjustmentsDialog(QDialog):
    """Brightness / contrast / saturation / gamma / hue."""

    valueChanged = Signal(str, int)   # name, value

    def __init__(self, parent=None, *, initial: dict[str, int] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Video Adjustments")
        self.setMinimumWidth(380)
        initial = initial or {}

        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self._sliders: dict[str, AdjustmentSlider] = {}
        self._value_labels: dict[str, QLabel] = {}
        for key, label in (
            ("brightness", "Brightness"),
            ("contrast", "Contrast"),
            ("saturation", "Saturation"),
            ("gamma", "Gamma"),
            ("hue", "Hue"),
        ):
            row = QHBoxLayout()
            slider = AdjustmentSlider()
            slider.setValue(int(initial.get(key, 0)))
            value_label = QLabel(str(slider.value()))
            value_label.setFixedWidth(36)
            value_label.setAlignment(Qt.AlignCenter)
            slider.valueChanged.connect(lambda v, k=key, lbl=value_label: self._on_changed(k, v, lbl))
            row.addWidget(slider, 1)
            row.addWidget(value_label)
            form.addRow(label + ":", row)
            self._sliders[key] = slider
            self._value_labels[key] = value_label

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        reset_btn = QPushButton("Reset All")
        reset_btn.clicked.connect(self.reset)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _on_changed(self, key: str, value: int, label: QLabel) -> None:
        label.setText(str(value))
        self.valueChanged.emit(key, value)

    def reset(self) -> None:
        for slider in self._sliders.values():
            slider.setValue(0)


class SyncDialog(QDialog):
    """Adjust subtitle / audio delay (in seconds)."""

    subDelayChanged = Signal(float)
    audioDelayChanged = Signal(float)

    def __init__(self, parent=None, *, sub_delay: float = 0.0, audio_delay: float = 0.0):
        super().__init__(parent)
        self.setWindowTitle("Audio / Subtitle Sync")
        self.setMinimumWidth(340)

        layout = QVBoxLayout(self)

        sub_box = QGroupBox("Subtitle delay (seconds)")
        sub_layout = QHBoxLayout(sub_box)
        self.sub_spin = QDoubleSpinBox()
        self.sub_spin.setRange(-60.0, 60.0)
        self.sub_spin.setSingleStep(0.1)
        self.sub_spin.setDecimals(2)
        self.sub_spin.setValue(sub_delay)
        self.sub_spin.valueChanged.connect(self.subDelayChanged)
        sub_layout.addWidget(self.sub_spin, 1)
        sub_reset = QPushButton("Reset")
        sub_reset.clicked.connect(lambda: self.sub_spin.setValue(0.0))
        sub_layout.addWidget(sub_reset)
        layout.addWidget(sub_box)

        aud_box = QGroupBox("Audio delay (seconds)")
        aud_layout = QHBoxLayout(aud_box)
        self.audio_spin = QDoubleSpinBox()
        self.audio_spin.setRange(-60.0, 60.0)
        self.audio_spin.setSingleStep(0.1)
        self.audio_spin.setDecimals(2)
        self.audio_spin.setValue(audio_delay)
        self.audio_spin.valueChanged.connect(self.audioDelayChanged)
        aud_layout.addWidget(self.audio_spin, 1)
        aud_reset = QPushButton("Reset")
        aud_reset.clicked.connect(lambda: self.audio_spin.setValue(0.0))
        aud_layout.addWidget(aud_reset)
        layout.addWidget(aud_box)

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        bb.button(QDialogButtonBox.Close).clicked.connect(self.accept)
        layout.addWidget(bb)


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {__app_name__}")
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        title = QLabel(f"<h2>{__app_name__}</h2>")
        title.setTextFormat(Qt.RichText)
        layout.addWidget(title)
        layout.addWidget(QLabel(f"Version {__version__}"))
        layout.addWidget(QLabel("A libmpv-powered media player built with Qt."))
        layout.addWidget(QLabel("Frame-accurate seeking enabled by default."))
        layout.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.accept)
        bb.button(QDialogButtonBox.Close).clicked.connect(self.accept)
        layout.addWidget(bb)
