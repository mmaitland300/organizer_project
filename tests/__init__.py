import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Create a QApplication instance if one doesn't exist.
if QApplication.instance() is None:
    app = QApplication(sys.argv)

app.setFont(QFont("Arial", 10))
