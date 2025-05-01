# Musicians Organizer v1.5.0

**Musicians Organizer** is a desktop tool designed for music producers, sound engineers, or anyone with large music or audio sample libraries. It helps scan, organize, analyze, and manage your audio files efficiently. Features include detailed metadata viewing, advanced filtering, duplicate detection, audio feature analysis, similarity-based recommendations, audio previewing, and basic DAW integration.

---

## Features

* **Efficient Folder Scanning:** Recursively scans directories using background threads, gathering file details (path, size, modification date) and basic audio metadata (duration, sample rate, channels via TinyTag). Syncs metadata with a persistent database.
* **Persistent Metadata Storage:** Uses an SQLite database (managed via SQLAlchemy) to store file paths, metadata, tags, and extracted audio features, allowing for quick reloading and analysis.
* **Advanced Filtering & Searching:** Filter files dynamically by:
    * Filename substring
    * Musical Key (e.g., "Cm", "F#")
    * BPM range
    * Tag text (substring search across all tags)
    * "Used" status
    * LUFS loudness range
    * Bit Depth
    * Pitch (Hz) range
    * Attack Time (ms) range
* **Duplicate Detection:** Identifies potential duplicate audio files based on file size and MD5 hash comparison (hashing performed in background). Provides a dialog to manage and delete duplicates.
* **Advanced Audio Analysis:** Extracts a range of audio features using Librosa in a background process:
    * Core features: Brightness (Spectral Centroid), Loudness (RMS)
    * Spectral features: Zero-Crossing Rate, Spectral Contrast
    * MFCCs (1-13)
    * Additional features: Bit Depth, Loudness (LUFS), Pitch (Hz), Attack Time
* **Similarity Recommendations:** Finds samples similar to a selected file based on the calculated advanced audio features using a Z-score scaled Euclidean distance.
* **Audio Preview & Waveform Display:** Preview audio files directly within the application. View interactive waveform plots with playback controls.
* **Multi-Dimensional Tagging:** Organise files using tags with dimensions (e.g., `instrument:KICK`, `mood:DARK`) or general tags. Includes an editor for managing tags. Auto-tags key/bpm based on filename patterns.
* **DAW Integration:** Simple "Send to Cubase" feature copies selected files to a predefined folder.
* **Customizable Themes:** Switch between light (default) and dark themes.
* **Persistent Settings:** Remembers window geometry, last scanned folder, theme preference, and other settings between sessions.

---

## Project Structure
```text
MUSICIANS_ORGANIZER/
├── alembic.ini
├── README.md
├── config/
│   ├── __init__.py
│   └── settings.py
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── __init__.py
│       ├── 60ec2f724e78_check_schema_sync.py
│       ├── 5663b07ada03_add_bit_depth_lufs_columns.py
│       ├── a970f5188eb3_add_audio_feature_columns.py
│       ├── a39924643879_create_files_table.py
│       └── c09c5f22a86d_add_indexes_to_feature_columns.py
├── models/
│   ├── __init__.py
│   └── file_model.py
├── services/
│   ├── __init__.py
│   ├── advanced_analysis_worker.py
│   ├── analysis_engine.py
│   ├── auto_tagger.py
│   ├── cache_manager.py
│   ├── database_manager.py
│   ├── duplicate_finder.py
│   ├── file_scanner.py
│   ├── hash_worker.py
│   ├── schema.py
│   └── spectrogram_plotter.py
│   └── spectrogram_service.py
│   └── waveform_plotter.py
├── ui/
│   ├── __init__.py
│   ├── controllers.py
│   ├── main_window.py
│   └── dialogs/
│       ├── __init__.py
│       ├── duplicate_manager_dialog.py
│       ├── feature_view_dialog.py
│       ├── multi_dim_tag_editor_dialog.py
│       ├── spectrogram_dialog.py
│       ├── waveform_dialog.py
│       └── waveform_player_widget.py
├── utils/
│   ├── __init__.py
│   └── helpers.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── pytest.ini
    ├── __pycache__/
    ├── pytest_cache/
    ├── test_advanced_analysis.py
    ├── test_audio_processor.py
    ├── test_auto_tagger.py
    ├── test_cache_manager.py
    ├── test_config_settings.py
    ├── test_database_manager.py
    ├── test_db_schema_sync.py
    ├── test_duplicate_finder.py
    ├── test_file_filter_proxy.py
    ├── test_file_model.py
    ├── test_file_scanner.py
    ├── test_helpers.py
    ├── test_ui_main_window.py
    └── test_waveform_plotter.py
```
---

## Getting Started

Follow these steps to get Musicians Organizer up and running on your machine.

### Prerequisites

* **Python 3.11+** is recommended.
* [pip](https://pip.pypa.io/en/stable/) (Python package installer).
* Git version control system.

### Installation

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/mmaitland300/organizer_project musicians_organizer
    cd musicians_organizer
    ```

2.  **Set Up Virtual Environment & Install Dependencies**
    It's highly recommended to use a virtual environment. From the project root (`musicians_organizer/`):

    * **Windows (PowerShell):**
        ```bash
        python3.11 -m venv venv
        .\venv\Scripts\Activate.ps1
        pip install -r requirements.txt
        ```
    * **Windows (Command Prompt):**
        ```bash
        python3.11 -m venv venv
        .\venv\Scripts\activate.bat
        pip install -r requirements.txt
        ```
    * **macOS / Linux (Bash/Zsh):**
        ```bash
        python3.11 -m venv venv
        source venv/bin/activate
        pip install -r requirements.txt
        ```

3.  **Linux Additional Dependencies (Example for Debian/Ubuntu):**
    Audio playback and some analysis features might require extra system libraries.
    ```bash
    sudo apt update
    sudo apt install -y libsndfile1 # For soundfile/librosa audio loading
    ```

    ```bash
    sudo apt install -y libqt5multimedia5-plugins gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav ffmpeg libpulse-dev
    ```
    (Note: Specific libraries might vary slightly based on Linux distribution and version).

4.  **Database Setup:**
    The application uses Alembic for database migrations. The first time you run the application, the database file (`~/.musicians_organizer.db` by default) should be created. To ensure the schema is up-to-date, you can optionally run migrations manually (ensure `alembic.ini` points to the correct database URL if not using the default):
    ```bash
    # While venv is active
    alembic upgrade head
    ```

---

### Running the Application

Ensure your virtual environment is activated, then run:

```bash
python main.py
```
### Packaging the Application
To create a standalone executable using PyInstaller (make sure it's installed: pip install pyinstaller):

Bash

### Run from the project root directory

```bash
pyinstaller --noconfirm --onefile --windowed main.py
```

The executable will be located in the dist/ folder. Note that packaging applications with complex dependencies like audio libraries and Qt can sometimes require adjustments to the PyInstaller spec file.

Running Tests
The project uses pytest. To run the test suite:

Activate your virtual environment.
Run pytest from the project root directory:
```Bash
pytest
```
Or use the command you ran successfully:
```Bash
pytest --maxfail=1 --disable-warnings -q
```
Future Improvements / Ideas
Refine UI/UX, potentially add more visual feedback during long operations.
Optimize performance for scanning and analysis on very large libraries.
Expand auto-tagging capabilities (e.g., genre detection based on audio features).
More sophisticated similarity search options (e.g., feature weighting).
Allow editing of more metadata fields directly in the table.
Add support for different database backends (e.g., PostgreSQL).
Improve packaging process for easier distribution.

**Summary of Key Updates:**

* Added version number.
* Updated the "Features" section to accurately reflect current capabilities, including advanced filtering, detailed audio analysis (LUFS, Pitch, etc.), similarity search based on features, and the underlying database.
* Corrected the "Project Structure" section based on the directory layout you provided.
* Updated the "Installation" section to use a generic repository URL placeholder and reflect standard venv setup. Added database setup step using Alembic.
* Updated the "Running Tests" section command.
* Refreshed the "Future Improvements" section.
