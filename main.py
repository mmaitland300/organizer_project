__version__ = "1.4.1"

"""
Main entry point for Musicians Organizer.
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


from PyQt5 import QtWidgets

# --- Import necessary components ---
from config.settings import get_engine  # Import the engine factory
from services.database_manager import DatabaseManager
from ui.main_window import MainWindow


def main():
    app = QtWidgets.QApplication(sys.argv)
    # --- Create Engine and DB Manager Once ---
    try:
        engine = get_engine()
        db_manager = DatabaseManager(engine=engine)  # Pass engine
    except Exception as e:
        # Handle critical DB initialization error (e.g., show error message)
        print(f"FATAL: Failed to initialize database: {e}")
        # Consider showing a QtWidgets.QMessageBox.critical here
        sys.exit(1)  # Exit if DB cannot be initialized

    # --- Create and show MainWindow, passing the db_manager ---
    main_win = MainWindow(db_manager=db_manager)
    main_win.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
