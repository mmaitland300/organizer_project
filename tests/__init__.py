import os
import sys

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Create a QApplication instance if one doesn't exist.
if QApplication.instance() is None:
    app = QApplication(sys.argv)

app.setFont(QFont("Arial", 10))
