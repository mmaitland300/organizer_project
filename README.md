# Musicians Organizer

**Musicians Organizer** is a tool designed for music producers, sound engineers, or music lovers with large, unmanageable music/sample libraries. It helps you clean up your folders, view detailed file information, detect duplicates, auto-tag audio samples, preview sounds, and even integrates with your DAW.

---

## What It Does

- **Scan Your Folders:**  
  Recursively scans directories and gathers file details such as size, name, modification date, and audio metadata (duration, sample rate, channels).

- **Filtering & Searching:**  
  Filter files by name or view only unused samples.

- **Duplicate Detection:**  
  Detects and groups duplicate files based on MD5 hashing. The duplicate search runs in the background with progress feedback so the UI stays responsive.

- **Audio Preview & Waveform Display:**  
  Preview audio samples and view an embedded waveform display for quick inspection of your sounds.

- **Auto-Tagging & Recommendations:**  
  Automatically tag audio files by detecting BPM and musical key, and receive recommendations for similar samples.

- **DAW Integration:**  
  Easily send your selected samples directly to your DAW for a smooth production workflow.

- **Customizable Themes:**  
  Switch between a modern light theme (default) and dark mode to suit your preferences.

- **Persistent Settings:**  
  User preferences (window size, last scanned folder, theme, etc.) are saved automatically between sessions.

---

## Project Structure

The project is now organized into multiple directories for better maintainability:

musicians_organizer/              # Project root  
├── main.py                       # Entry point script  
├── config/  
│   ├── __init__.py  
│   └── settings.py               # Global configuration & dependency checks  
├── core/  
│   ├── __init__.py  
│   └── file_scanner.py           # File scanning threads & duplicate finder  
├── models/  
│   ├── __init__.py  
│   └── file_model.py             # FileTableModel and FileFilterProxyModel  
├── ui/  
│   ├── __init__.py  
│   └── main_window.py            # MainWindow and related dialogs/widgets  
├── utils/  
│   ├── __init__.py  
│   ├── cache_manager.py          # CacheManager class for metadata caching  
│   └── helpers.py                # Utility functions (tag parsing, formatting, etc.)  
└── tests/                        # Unit tests (pytest)

---

## Getting Started

Follow these steps to get Musicians Organizer up and running on your machine.

### Prerequisites

- **Python 3.11+** is recommended to work with the latest libraries (e.g., librosa).
- [pip](https://pip.pypa.io/en/stable/) installed.
- (Optional) [virtualenv](https://virtualenv.pypa.io/en/latest/) or the built‑in venv module.

---

## Installation

#### Clone the Repository

Open your terminal and run:

    git clone https://github.com/mmaitland300/organizer_project.git
    cd organizer_project

Since the current repository contains the old single‑file version, we recommend creating a backup branch for it before integrating the new version. (See instructions in the Git guide below.)

#### Set Up the Virtual Environment and Install Dependencies

##### On Windows

    python3.11 -m venv venv
    .\venv\Scripts\Activate.ps1    # Use Activate.bat if using cmd.exe
    pip install -r requirements.txt

##### On Linux (Debian/Ubuntu)

    python3.11 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    # For audio-related dependencies, install additional libraries:
    sudo apt update
    sudo apt install libpulse-mainloop-glib0 libpulse-dev
    sudo apt install libqt5multimedia5-plugins \
                     gstreamer1.0-plugins-base \
                     gstreamer1.0-plugins-good \
                     gstreamer1.0-plugins-bad \
                     gstreamer1.0-plugins-ugly \
                     gstreamer1.0-libav \
                     ffmpeg

---

## Running the Application

simply run:

    python main.py

This launches the GUI for Musicians Organizer.

---

## Packaging the Application

To package the application into a standalone executable using PyInstaller:

1. Ensure you have installed PyInstaller:
   
       pip install pyinstaller

2. Run PyInstaller from the project root:

       pyinstaller --noconfirm --onefile --windowed main.py

This generates a standalone executable in the `dist/` folder.

---

## Running Tests

A comprehensive suite of unit tests using pytest is provided in the `tests/` folder. To run the tests:

1. Activate your virtual environment as described above.
2. Run:

       pytest --maxfail=1 --disable-warnings -q

This ensures that all core components and functionalities are working correctly.

---

## Future Improvements

- **Enhanced Audio Metadata Analysis:** Integrate additional libraries to extract more detailed audio metadata and allow in-app editing.
- **Extended Duplicate Detection:** Improve the asynchronous processing and add cancellation capabilities for long-running scans.
- **User Preferences:** Develop a dedicated settings/preferences dialog for fine-tuning parameters without modifying configuration files directly.
- **UI Enhancements:** Modernize the GUI and add in-app logging for better diagnostics.

