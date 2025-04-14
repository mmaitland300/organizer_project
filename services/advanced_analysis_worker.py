import os
import logging
from typing import List, Dict, Any, Optional
from collections import OrderedDict
from PyQt5 import QtCore

from services.database_manager import DatabaseManager
from services.analysis_engine import AnalysisEngine
from config.settings import AUDIO_EXTENSIONS

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class AdvancedAnalysisWorker(QtCore.QThread):
    """
    Worker thread that runs advanced DSP analysis on a list of files.
    
    Expects a list of file records (dictionaries) as input.
    For each file, it:
      - Ensures that the "filename" dimension remains as the first key in file_info["tags"].
      - Checks if the file is an audio file based on its "filetype" tag.
      - Runs advanced analysis via AnalysisEngine.
      - Stores each metric as its own tag dimension (e.g., "brightness", "loudness_rms", "stereo_width").
      - Updates the file record in the database.
    
    Emits:
       progress(current: int, total: int)
       finished(updated_files: List[Dict[str, Any]])
    """
    progress = QtCore.pyqtSignal(int, int)
    finished = QtCore.pyqtSignal(list)
    
    def __init__(self, files: List[Dict[str, Any]], parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self.files = files
        self._cancelled = False

    def run(self) -> None:
        total_files = len(self.files)
        updated_files = []
        current_count = 0

        for file_info in self.files:
            if self._cancelled:
                break

            # Ensure that we only analyze audio files based on the "filetype" in tags
            filetypes = file_info.get("tags", {}).get("filetype", [])
            if not filetypes or filetypes[0] not in [ext.lower() for ext in AUDIO_EXTENSIONS]:
                logger.debug(f"Skipping advanced analysis for non-audio file: {file_info.get('path', 'Unknown')}")
                updated_files.append(file_info)
                current_count += 1
                self.progress.emit(current_count, total_files)
                continue

            # Run advanced DSP analysis on this audio file
            adv_features = AnalysisEngine.analyze_audio_features(file_info["path"], max_duration=60.0)
            if adv_features:
                # For each computed metric, save it as its own tag dimension.
                file_info.setdefault("tags", {})
                for metric_name, metric_val in adv_features.items():
                    # Make sure we do not override "filetype"
                    if metric_name.lower() == "filetype":
                        continue
                    file_info["tags"].setdefault(metric_name, [])
                    file_info["tags"][metric_name] = [f"{metric_val:.3f}"]
                logger.debug(f"Advanced DSP updated for {file_info.get('path', 'Unknown')}")
                # Optionally, update BPM as a tag if available:
                if "bpm" in file_info and file_info["bpm"]:
                    file_info["tags"]["bpm"] = [str(file_info["bpm"])]
                DatabaseManager.instance().save_file_record(file_info)

            # Reorder the tags dictionary so that 'filetype' remains first.
            original_tags = file_info.get("tags", {})
            if "filetype" in original_tags:
                ordered_tags = OrderedDict()
                ordered_tags["filetype"] = original_tags["filetype"]
                # Append all other keys in the order they originally appear (or in sorted order if you prefer).
                for key, value in original_tags.items():
                    if key != "filetype":
                        ordered_tags[key] = value
                file_info["tags"] = ordered_tags

            updated_files.append(file_info)
            current_count += 1
            self.progress.emit(current_count, total_files)
        
        self.finished.emit(updated_files)

    def cancel(self) -> None:
        self._cancelled = True
