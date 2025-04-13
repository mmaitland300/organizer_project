"""
WaveformPlayerWidget - provides an integrated waveform display and audio playback control.
"""

import os
from typing import Optional, Any
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtCore import QUrl
from config.settings import ENABLE_WAVEFORM_PREVIEW, librosa, plt, np, FigureCanvas
from utils.helpers import format_time

class WaveformPlayerWidget(QtWidgets.QWidget):
    def __init__(self, file_path: str, theme: str = "light", parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.file_path = file_path
        self.theme = theme.lower()
        self.figure: Optional[Any] = None
        self.ax: Optional[Any] = None
        self.canvas: Optional[Any] = None
        self.cursor_line: Optional[Any] = None
        self.duration_ms: int = 0
        self.total_duration_secs: float = 0.0
        self.setup_ui()
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
        try:
            y, sr = librosa.load(self.file_path, sr=None, mono=True)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Could not load audio:\n{e}")
            return
        desired_points = 1000
        factor = max(1, int(len(y) / desired_points))
        y_downsampled = y[::factor]
        times = np.linspace(0, len(y) / sr, num=len(y_downsampled))
        self.ax.clear()
        self.ax.plot(times, y_downsampled)
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Amplitude")
        self.ax.set_title("Waveform Player")
        self.duration_ms = int(len(y) / sr * 1000)
        self.total_duration_secs = len(y) / sr
        self.totalTimeLabel.setText(format_time(self.total_duration_secs))
        self.canvas.draw()
    
    def init_player(self) -> None:
        self.player = QMediaPlayer(self)
        url = QUrl.fromLocalFile(os.path.abspath(self.file_path))
        media = QMediaContent(url)
        self.player.setMedia(media)
        self.player.durationChanged.connect(self.on_duration_changed)
        self.player.positionChanged.connect(self.on_position_changed)
        self.slider.setMinimum(0)
        self.slider.setMaximum(self.duration_ms)
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
            self.totalTimeLabel.setText(format_time(duration / 1000.0))
            self.ax.set_xlim(0, duration / 1000.0)
            self.canvas.draw_idle()
    
    def on_position_changed(self, position: int) -> None:
        self.slider.setValue(position)
        current_sec = position / 1000.0
        self.currentTimeLabel.setText(format_time(current_sec))
    
    def on_slider_moved(self, pos: int) -> None:
        self.player.setPosition(pos)
    
    def update_cursor(self) -> None:
        pos_sec = self.player.position() / 1000.0
        if self.cursor_line is not None:
            self.cursor_line.remove()
        self.cursor_line = self.ax.axvline(pos_sec, color="red")
        self.canvas.draw_idle()
    
    def on_canvas_click(self, event: Any) -> None:
        if event.xdata is not None and event.button == 1:
            new_pos_sec = max(0, event.xdata)
            new_pos_ms = int(new_pos_sec * 1000)
            self.player.setPosition(new_pos_ms)
            self.slider.setValue(new_pos_ms)
            self.update_cursor()
