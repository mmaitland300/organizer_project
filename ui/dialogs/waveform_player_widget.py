# ui/dialogs/waveform_player_widget.py
"""
WaveformPlayerWidget - integrated waveform display and audio playback control.
"""

import os
from typing import Any, Optional

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import QUrl
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer

from config.settings import ENABLE_WAVEFORM_PREVIEW
from services.waveform_plotter import WaveformPlotter
from utils.helpers import format_time


class WaveformPlayerWidget(QtWidgets.QWidget):
    def __init__(
        self,
        file_path: str,
        theme: str = "light",
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.file_path = file_path
        self.theme = theme.lower()
        self.player: Optional[QMediaPlayer] = None
        self.cursor_line: Optional[Any] = None

        self.setup_ui()
        if ENABLE_WAVEFORM_PREVIEW:
            self.load_audio_and_plot()
        self.init_player()
        self.applyTheme(self.theme)

    def setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        self.figure, self.ax = plt.subplots(figsize=(6, 3))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

        slider_layout = QtWidgets.QHBoxLayout()
        self.currentTimeLabel = QtWidgets.QLabel("0:00", self)
        slider_layout.addWidget(self.currentTimeLabel)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
        self.slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        slider_layout.addWidget(self.slider)

        self.totalTimeLabel = QtWidgets.QLabel("0:00", self)
        slider_layout.addWidget(self.totalTimeLabel)
        layout.addLayout(slider_layout)

        controls_layout = QtWidgets.QHBoxLayout()
        self.playButton = QtWidgets.QPushButton("Play", self)
        self.playButton.clicked.connect(self.toggle_playback)
        controls_layout.addWidget(self.playButton)
        layout.addLayout(controls_layout)

        self.update_timer = QtCore.QTimer(self)
        self.update_timer.setInterval(100)
        self.update_timer.timeout.connect(self.update_cursor)
        self.canvas.mpl_connect("button_press_event", self.on_canvas_click)

    def load_audio_and_plot(self) -> None:
        # Unified plotting; desired resolution via max_points
        WaveformPlotter.plot(self.file_path, self.ax, max_points=1000)
        # Update total duration metadata
        self.total_duration_secs = (
            self.player.duration() / 1000.0 if self.player else 0.0
        )
        self.totalTimeLabel.setText(format_time(self.total_duration_secs))
        self.canvas.draw()

    def init_player(self) -> None:
        self.player = QMediaPlayer(self)
        url = QUrl.fromLocalFile(os.path.abspath(self.file_path))
        self.player.setMedia(QMediaContent(url))
        self.player.durationChanged.connect(self.on_duration_changed)
        self.player.positionChanged.connect(self.on_position_changed)
        self.slider.setMinimum(0)
        self.slider.setMaximum(0)
        self.slider.sliderMoved.connect(self.on_slider_moved)

    def applyTheme(self, theme: str) -> None:
        if theme == "dark":
            self.figure.patch.set_facecolor("#2B2B2B")
            self.ax.set_facecolor("#3A3F4B")
        else:
            self.figure.patch.set_facecolor("white")
            self.ax.set_facecolor("white")
        self.figure.tight_layout()
        self.canvas.draw()

    def toggle_playback(self) -> None:
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.playButton.setText("Play")
            self.update_timer.stop()
        else:
            self.player.play()
            self.playButton.setText("Pause")
            self.update_timer.start()

    def on_duration_changed(self, duration: int) -> None:
        if duration > 0:
            self.slider.setMaximum(duration)
            sec = duration / 1000.0
            self.totalTimeLabel.setText(format_time(sec))
            self.ax.set_xlim(0, sec)
            self.canvas.draw_idle()

    def on_position_changed(self, position: int) -> None:
        self.slider.setValue(position)
        self.currentTimeLabel.setText(format_time(position / 1000.0))

    def on_slider_moved(self, pos: int) -> None:
        if self.player:
            self.player.setPosition(pos)

    def update_cursor(self) -> None:
        if self.cursor_line:
            self.cursor_line.remove()
        pos_sec = self.player.position() / 1000.0 if self.player else 0.0
        self.cursor_line = self.ax.axvline(pos_sec)
        self.canvas.draw_idle()

    def on_canvas_click(self, event: Any) -> None:
        if event.xdata is not None and event.button == 1 and self.player:
            new_ms = int(max(0, event.xdata) * 1000)
            self.player.setPosition(new_ms)
            self.slider.setValue(new_ms)
            self.update_cursor()
