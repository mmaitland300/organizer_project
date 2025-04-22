import datetime
import unittest

from PyQt5.QtCore import Qt

from models.file_model import FileFilterProxyModel, FileTableModel


class TestFileModel(unittest.TestCase):
    def setUp(self):
        self.file_info = [
            {
                "path": "/dummy/path/sample.wav",
                "size": 2048,
                "mod_time": datetime.datetime(2020, 1, 1, 12, 0, 0),
                "duration": 125,
                "bpm": 120,
                "key": "C#m",
                "used": False,
                "samplerate": 44100,
                "channels": 2,
                "tags": {"genre": ["ROCK"]},
            }
        ]
        self.model = FileTableModel(self.file_info, size_unit="KB")

    def test_row_column_count(self):
        self.assertEqual(self.model.rowCount(), 1)
        self.assertEqual(self.model.columnCount(), len(self.model.COLUMN_HEADERS))

    def test_data_display(self):
        # Column 1 is the file name.
        index = self.model.index(0, 1)
        self.assertEqual(self.model.data(index, role=Qt.DisplayRole), "sample.wav")

    def test_setData_edit(self):
        index = self.model.index(0, 6)  # Key column.
        result = self.model.setData(index, "Dm", role=Qt.EditRole)
        self.assertTrue(result)
        self.assertEqual(
            self.file_info[0]["key"], "DM"
        )  # Because the code converts input to uppercase.


class TestFileFilterProxyModel(unittest.TestCase):
    def setUp(self):
        self.file_info = [
            {"path": "/dummy/path/sample1.wav", "used": False},
            {"path": "/dummy/path/sample2.wav", "used": True},
        ]
        self.model = FileTableModel(self.file_info, size_unit="KB")
        self.proxy = FileFilterProxyModel()
        self.proxy.setSourceModel(self.model)

    def test_filter_only_unused(self):
        self.proxy.set_filter_unused(True)
        self.proxy.invalidateFilter()
        self.assertEqual(self.proxy.rowCount(), 1)


if __name__ == "__main__":
    unittest.main()
