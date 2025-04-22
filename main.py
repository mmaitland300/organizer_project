__version__ = "1.3.0"

"""
Main entry point for Musicians Organizer.
"""

import sys

from PyQt5 import QtWidgets

from services.database_manager import DatabaseManager
from ui.main_window import MainWindow


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
