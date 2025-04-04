# Musicians Organizer

Here is **Musicians Organizer** a tool for music producers, sound engineers or just fans of music with large unmanageable collections, to help manage their music or sample libraries. Whether you’re looking to clean up your folders, get detailed file info, detect duplicates, or auto-tag audio samples, this application can provide.

## What It Does

- **Scan Your Folders:**  
  Recursively scans directories to gather file details like size, name, modification date, and audio metadata (duration, sample rate, channels).

- **Filtering & Searching:**
  Use filters to quickly find samples by name or see only unused samples.

- **Duplicate Detection:**  
  Finds and groups duplicate files using MD5 hashing and allows you to selectively delete them with recyle bin toggle.

- **Audio Preview & Waveform Display:**  
  Quickly preview your samples and view an embedded waveform preview to better view your sounds.

- **Auto-Tagging & Recommendations:**  
  Automatically tags files based on BPM and musical key detection, plus recommends similar samples based on your selections.

- **DAW Integration:**  
  Easily send your favorite samples directly to your DAW of choices library for a smooth production workflow.

- **Customizable Themes:**  
  Modern light theme by default, with the option to switch to dark mode if you prefer a different look.

- **Persistent Settings:**  
  Preferences (like window size, last scanned folder, theme, etc.) are saved automatically.

## Getting Started
Follow these steps to get Musicians Organizer up and running on your machine!
### Prerequisites

- **Python 3.7+** (Recommend Python 3.11 to work with the librosa library)
- [pip](https://pip.pypa.io/en/stable/) installed

## Installation

 #### Clone the Repository:

    git clone https://github.com/mmaitland300/organizer_project.git
    cd organizer_project
  

### Install Virtual Environment and requirements

#### On Windows:
 
    python3.11 -m venv venv
    .\venv\Scripts\Activate.ps1
    pip install -r requirements.txt


#### On Linux(Debian/Unbuntu) (Had to install some aditional libararies):

    python3.11 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    sudo apt update
    sudo apt install libpulse-mainloop-glib0 libpulse-dev
    sudo apt install libqt5multimedia5-plugins \
                 gstreamer1.0-plugins-base \
                 gstreamer1.0-plugins-good \
                 gstreamer1.0-plugins-bad \
                 gstreamer1.0-plugins-ugly \
                 gstreamer1.0-libav \
                 ffmpeg

## Running the application

    python -m organizer.organizer

## Packaging the application

    pip install pyinstaller
    pyinstaller --noconfirm --onefile --windowed organizer/organizer.py
 

## Running Tests

To ensure everything is working correctly, you can run the tests provided in the repository.

**Activate the virtual environment:**

#### On Windows:
    
    .\venv\Scripts\Activate.ps1
  

#### On macOS/Linux:
  
    source venv/bin/activate
   

**Run the tests using pytest:**
  
    python -m pytest
   



