# tests/test_waveform_plotter.py
import unittest
import tempfile
import numpy as np
import matplotlib.pyplot as plt
import soundfile as sf
from services.waveform_plotter import WaveformPlotter

class TestWaveformPlotter(unittest.TestCase):
    def create_sine(self, duration=1.0, sr=8000, freq=440):
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)
        y = 0.5 * np.sin(2 * np.pi * freq * t)
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        sf.write(tmp.name, y, sr)
        return tmp.name

    def test_plot_draws_line(self):
        wav = self.create_sine()
        fig, ax = plt.subplots()
        WaveformPlotter.plot(wav, ax, max_points=500)
        lines = ax.get_lines()
        # One line should be drawn, with non-empty data
        self.assertEqual(len(lines), 1)
        xs, ys = lines[0].get_data()
        self.assertGreater(len(xs), 0)
        self.assertGreater(len(ys), 0)

if __name__ == "__main__":
    unittest.main()
