import unittest
from config import settings

class TestConfigSettings(unittest.TestCase):
    def test_constants(self):
        self.assertIsInstance(settings.MAX_HASH_FILE_SIZE, int)
        self.assertIsInstance(settings.HASH_TIMEOUT_SECONDS, int)
        self.assertIn(".wav", settings.AUDIO_EXTENSIONS)

    def test_dependency_flags(self):
        from config.settings import ENABLE_ADVANCED_AUDIO_ANALYSIS, ENABLE_WAVEFORM_PREVIEW
        self.assertIsInstance(ENABLE_ADVANCED_AUDIO_ANALYSIS, bool)
        self.assertIsInstance(ENABLE_WAVEFORM_PREVIEW, bool)

if __name__ == "__main__":
    unittest.main()
