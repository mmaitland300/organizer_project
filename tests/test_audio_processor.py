"""
Unit tests for audio processing feature toggles.
"""

import unittest

from config.settings import ENABLE_ADVANCED_AUDIO_ANALYSIS


class TestAudioProcessing(unittest.TestCase):
    def test_feature_toggle_is_bool(self):
        self.assertIsInstance(ENABLE_ADVANCED_AUDIO_ANALYSIS, bool)


if __name__ == "__main__":
    unittest.main()
