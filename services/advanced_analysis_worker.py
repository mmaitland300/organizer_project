# services/advanced_analysis_worker.py

import os
import logging
import concurrent.futures
import threading
from typing import List, Dict, Any, Optional
from collections import OrderedDict
from PyQt5 import QtCore
import copy 

from services.database_manager import DatabaseManager
from services.analysis_engine import AnalysisEngine
from config.settings import AUDIO_EXTENSIONS, ALL_FEATURE_KEYS # Import ALL_FEATURE_KEYS
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# --- Corrected _analyze_and_update_file function ---
def _analyze_and_update_file(file_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Analyzes a single audio file using AnalysisEngine (which now includes BPM).
    Returns a DEEP COPY of the file_info dictionary containing extracted
    numerical features AND BPM in top-level keys if analysis succeeds.
    Also updates tags dictionary (e.g., filetype, BPM).
    Handles exceptions during analysis. Returns the original file_info on error/skip.

    Args:
        file_info: The original dictionary containing file metadata.

    Returns:
        An updated deep copy of file_info if analysis succeeded and modified data,
        otherwise returns the original file_info dictionary.
    """
    try:
        # Create a deep copy to avoid modifying the original dict in place
        output_file_info = copy.deepcopy(file_info)
    except Exception as e:
        logger.error(f"Failed to deep copy file_info for {file_info.get('path', 'Unknown Path')}: {e}")
        return file_info # Return original if deepcopy fails

    try:
        path = output_file_info.get("path")
        if not path:
            logger.warning("Skipping analysis: File info missing 'path'.")
            return file_info

        ext = os.path.splitext(path)[1].lower()
        supported_exts = {e.lower() for e in AUDIO_EXTENSIONS}
        if ext not in supported_exts:
             logger.debug(f"Skipping analysis for non-audio extension: {path}")
             return file_info

        # --- Call Analysis Engine ---

        adv_features = AnalysisEngine.analyze_audio_features(path, max_duration=60.0)

        if adv_features: # Check if AnalysisEngine returned a result dictionary
            logger.debug(f"Advanced analysis results obtained for {path}")

            # --- Update Numerical Features (from ALL_FEATURE_KEYS) ---
            for key in ALL_FEATURE_KEYS:
                # Update the output dict only if the key is present in the results
                # This handles cases where specific feature calculations might fail
                if key in adv_features:
                     output_file_info[key] = adv_features[key] # Handles None values correctly

            # --- Update BPM (handled separately as it's not in ALL_FEATURE_KEYS) ---
            if 'bpm' in adv_features:
                 output_file_info['bpm'] = adv_features['bpm'] # Handles None correctly

            # --- Update Tags Dictionary ---
            # Ensure 'tags' dictionary exists
            if "tags" not in output_file_info or not isinstance(output_file_info.get("tags"), dict):
                 output_file_info["tags"] = {}
            # Ensure filetype tag exists
            if "filetype" not in output_file_info["tags"]:
                 if ext: output_file_info["tags"]["filetype"] = [ext]

            # --- Add/Update/Remove BPM Tag based on calculated numerical value ---
            calculated_bpm = output_file_info.get('bpm') # Use .get() for safety
            current_bpm_tags = output_file_info["tags"].get("bpm", []) # Get current BPM tags list

            if calculated_bpm is not None:
                 try:
                      # Format BPM tag as integer string
                      bpm_tag_str = str(int(calculated_bpm))
                      # Update only if the tag list needs changing
                      if current_bpm_tags != [bpm_tag_str]:
                           output_file_info["tags"]["bpm"] = [bpm_tag_str]
                           logger.debug(f"Updated BPM tag for {path} to: {bpm_tag_str}")
                 except (ValueError, TypeError):
                      logger.warning(f"Could not format calculated BPM {calculated_bpm} as tag for {path}")
                      # If formatting fails and BPM tag exists, remove it
                      if "bpm" in output_file_info["tags"]:
                          del output_file_info["tags"]["bpm"]
            else:
                # If calculated BPM is None, ensure the BPM tag is removed if it exists
                if "bpm" in output_file_info["tags"]:
                    del output_file_info["tags"]["bpm"]
                    logger.debug(f"Removed BPM tag for {path} as calculated BPM is None.")
            # --- End BPM Tag ---

            # Optional: Reorder tags for consistent display (if needed)
            # current_tags = output_file_info.get("tags", {})
            # ordered_tags = OrderedDict()
            # if "filetype" in current_tags: ordered_tags["filetype"] = current_tags.pop("filetype")
            # if "bpm" in current_tags: ordered_tags["bpm"] = current_tags.pop("bpm")
            # ordered_tags.update(current_tags)
            # output_file_info["tags"] = dict(ordered_tags)

            # Check if anything actually changed compared to the original file_info
            if output_file_info != file_info:
                 return output_file_info # Return the updated copy
            else:
                 logger.debug(f"Analysis for {path} resulted in no changes to file_info.")
                 return file_info # Return original if no changes detected

        else:
            # AnalysisEngine returned None or empty dict, indicating failure/no features
            logger.debug(f"AnalysisEngine returned no results for {path}")
            return file_info # Return original

    except Exception as e:
        logger.error(f"Error during analysis processing for {output_file_info.get('path', 'Unknown Path')}: {e}", exc_info=True)
        return file_info # Return original on any unexpected error

# --- AdvancedAnalysisWorker class ---

class AdvancedAnalysisWorker(QtCore.QThread):
    """
    Worker thread that runs advanced DSP analysis in parallel... (docstring unchanged)
    """
    progress = QtCore.pyqtSignal(int, int)
    finished = QtCore.pyqtSignal(list)

    def __init__(self, files: List[Dict[str, Any]], parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self.files_to_process = list(files)
        self._cancelled = False
        self._lock = threading.Lock()

    def run(self) -> None:
        # It calls the updated _analyze_and_update_file helper,
        # compares original dict with result dict (using tags primarily),
        # and performs batch save of changed records.
        total_files = len(self.files_to_process)
        processed_count = 0
        results_list = []
        db_records_to_save = []

        max_workers = max(1, os.cpu_count() or 1)
        logger.info(f"Starting advanced analysis with up to {max_workers} workers.")

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        futures: List[concurrent.futures.Future] = []
        cancelled_during_submission = False

        try:
            # --- Submit tasks ---
            for file_info in self.files_to_process:
                future = executor.submit(_analyze_and_update_file, file_info)
                futures.append(future)

            # --- Process completed tasks ---
            logger.info(f"Submitted {len(futures)} analysis tasks. Waiting for results...")
            paths_successfully_processed = set() # Changed name for clarity

            for future in concurrent.futures.as_completed(futures):

                processed_successfully = False
                try:
                    updated_file_info_copy = future.result()
                    if updated_file_info_copy:
                        results_list.append(updated_file_info_copy)
                        # --- Logic to Check if Save is Needed ---
                        path = updated_file_info_copy.get('path')
                        if not path:
                             processed_successfully = True
                             continue

                        original_file_info = next((f for f in self.files_to_process if f.get('path') == path), None)

                        needs_save = False
                        if original_file_info:
                            # Compare tags
                            if original_file_info.get('tags') != updated_file_info_copy.get('tags'):
                                needs_save = True

                            # Compare new numerical features only if save not already needed
                            if not needs_save:
                                for key in ALL_FEATURE_KEYS:
                                    original_value = original_file_info.get(key)
                                    updated_value = updated_file_info_copy.get(key)

                                    # Check if the feature was added (original is None, new is not)
                                    # or if the feature value changed (both not None and different)
                                    if (original_value is None and updated_value is not None) or \
                                       (original_value is not None and updated_value is not None and original_value != updated_value):
                                        # Add tolerance for float comparison if strict equality isn't desired
                                        # e.g., not math.isclose(original_value, updated_value, rel_tol=1e-9)
                                        needs_save = True
                                        break # Found a difference

                        # Determine if save is needed ONLY if analysis returned features
                        # (If AnalysisEngine returned {}, updated_file_info_copy wouldn't have new feature keys)
                        has_new_features = any(key in updated_file_info_copy for key in ALL_FEATURE_KEYS if key not in original_file_info)

                        if needs_save or (has_new_features and not original_file_info): # Save if changed or if new file got features
                            # Check if any actual feature value was successfully added/changed
                             if any(updated_file_info_copy.get(key) is not None for key in ALL_FEATURE_KEYS):
                                db_records_to_save.append(updated_file_info_copy)
                                paths_successfully_processed.add(path) # Track success *and* change
                             else:
                                logger.debug(f"Skipping save for {path}: needs_save triggered but no valid features found in updated copy.")

                        processed_successfully = True

                except Exception as e:
                    logger.error(f"Error retrieving result from analysis future: {e}", exc_info=True)

                # --- Progress Update ---
                if processed_successfully:
                     processed_count += 1
                     self.progress.emit(processed_count, total_files)

            # --- Finalize ---
            with self._lock:
                was_cancelled = self._cancelled

            if not was_cancelled and db_records_to_save:
                logger.info(f"Analysis complete. Saving {len(db_records_to_save)} updated records to database...")
                # The safety filter is less critical now if 'needs_save' is accurate, but doesn't hurt
                final_records_to_save = [rec for rec in db_records_to_save if rec.get("path") in paths_successfully_processed]

                if final_records_to_save:
                     logger.info(f"Attempting to save {len(final_records_to_save)} records after final filtering...")
                     try:
                         DatabaseManager.instance().save_file_records(final_records_to_save)
                         logger.info("Database batch save successful.")
                     except Exception as e:
                         logger.error(f"Database batch save failed during analysis completion: {e}", exc_info=True)
                else:
                    logger.info("Analysis complete. No records identified for saving after final filtering.")
            # ... (rest of finalize block unchanged: cancellation logs, final list construction, emit finished) ...
            elif was_cancelled:
                 logger.info("Analysis cancelled. Skipping final database save.")
            else:
                 logger.info("Analysis complete. No records needed database updates based on comparison.")


            final_output_list = results_list
            processed_paths_in_results = {info.get('path') for info in results_list if info}
            for original_info in self.files_to_process:
                if original_info and original_info.get('path') not in processed_paths_in_results:
                    final_output_list.append(original_info)

            self.finished.emit(final_output_list)
            logger.info("AdvancedAnalysisWorker finished.")

        except Exception as e:
             logger.error(f"Unhandled exception in AdvancedAnalysisWorker run loop: {e}", exc_info=True)
             self.finished.emit(self.files_to_process)
        finally:
            logger.debug("Shutting down ThreadPoolExecutor.")
            executor.shutdown(wait=True)
            logger.debug("ThreadPoolExecutor shut down.")


    def cancel(self) -> None:
        with self._lock:
            if not self._cancelled:
                 logger.info("AdvancedAnalysisWorker cancellation requested.")
                 self._cancelled = True

