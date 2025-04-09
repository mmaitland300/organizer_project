import os
import pytest
from core.file_scanner import FileScanner

@pytest.fixture
def temp_audio_files(tmp_path):
    # Create a temporary directory with a few dummy audio files.
    dir_path = tmp_path / "audio_dir"
    dir_path.mkdir()
    file_paths = []
    for i in range(3):
        file = dir_path / f"audio{i}.mp3"
        file.write_text("dummy audio content")
        file_paths.append(str(file))
    return dir_path, file_paths

def test_file_scanner(qtbot, temp_audio_files):
    dir_path, file_paths = temp_audio_files
    # Create the scanner. Do NOT call qtbot.addWidget(scanner) because scanner is a QThread.
    scanner = FileScanner(str(dir_path), bpm_detection=False)
    # Use QSignalSpy to wait for the finished signal.
    from PyQt5.QtTest import QSignalSpy
    spy = QSignalSpy(scanner.finished)
    scanner.start()
    # Wait for the finished signal (timeout in milliseconds)
    assert spy.wait(5000)
    files_info = spy[0][0]
    # Check that the number of files scanned equals

