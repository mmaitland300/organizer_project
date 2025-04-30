import unittest

# Assuming AutoTagService is importable, adjust path if needed
from services.auto_tagger import AutoTagService


class TestAutoTagService(unittest.TestCase):

    def test_auto_tag(self):
        # Input dictionary
        file_info = {
            "path": "C:/Music/Samples/Cool Kick C#m 120bpm.wav"
        }  # Example with key and BPM

        # Call the service (modifies file_info in-place)
        modified = AutoTagService.auto_tag(file_info)

        # Assert that the function reported modifications were made
        self.assertTrue(
            modified, "AutoTagService.auto_tag should return True for changes."
        )

        # Assert that the original dictionary was modified correctly
        # Check for 'key' extracted from filename
        self.assertIn("key", file_info, "'key' should be added to file_info")
        self.assertEqual(file_info["key"], "C#M", "Extracted key is incorrect")

        # Check for 'bpm' extracted from filename (if applicable based on your patterns)
        # Assuming your patterns extract BPM too:
        self.assertIn("bpm", file_info, "'bpm' should be added or updated in file_info")
        self.assertEqual(file_info["bpm"], 120, "Extracted BPM is incorrect")

        # You might also want a test case where no changes are expected:
        # file_info_no_change = {"path": "C:/Music/Samples/audio_no_metadata.wav", "key": "A", "bpm": 100}
        # modified_no_change = AutoTagService.auto_tag(file_info_no_change)
        # self.assertFalse(modified_no_change, "auto_tag should return False if no changes")
        # self.assertEqual(file_info_no_change["key"], "A") # Ensure existing value not changed
        # self.assertEqual(file_info_no_change["bpm"], 100)


# Add if __name__ == '__main__': block if needed for running file directly


if __name__ == "__main__":
    unittest.main()
