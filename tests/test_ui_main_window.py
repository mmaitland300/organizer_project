import unittest
import sys
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow
import sys, os
from PyQt5.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if QApplication.instance() is None:
    app = QApplication(sys.argv)


class TestMainWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure that a QApplication instance exists.
        cls.app = QApplication(sys.argv)
    
    def test_main_window_instantiation(self):
        window = MainWindow()
        self.assertIsNotNone(window)
    
    @classmethod
    def tearDownClass(cls):
        cls.app.quit()

if __name__ == "__main__":
    unittest.main()
