import unittest
from services.auto_tagger import AutoTagService

class TestAutoTagService(unittest.TestCase):
    def test_auto_tag(self):
        file_info = {
            'path': "C:/Music/C#m_sample.wav"
        }
        updated_info = AutoTagService.auto_tag(file_info)
        self.assertIn('key', updated_info)
        self.assertTrue(updated_info['key'].startswith("C#"))

if __name__ == "__main__":
    unittest.main()
