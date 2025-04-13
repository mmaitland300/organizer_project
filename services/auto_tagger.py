"""
AutoTagService – implements auto-tagging logic.

This service uses file name analysis (and optionally other signals) to assign tags like musical key.
"""

import logging
from typing import Dict, Any, List
from utils.helpers import detect_key_from_filename
import os

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class AutoTagService:
    """
    Service class for performing auto-tagging on file metadata.
    """
    @staticmethod
    def auto_tag(file_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update the file_info dictionary with auto-detected tags.
        
        Currently uses filename to detect musical key.
        """
        try:
            key = detect_key_from_filename(file_info['path'])
            file_info['key'] = key if key else "N/A"
        except Exception as e:
            logger.error(f"Auto-tagging failed for {file_info.get('path')}: {e}")
        return file_info
    
    @classmethod
    def auto_tag_files(cls, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process a list of files, applying auto-tagging to each.
        """
        return [cls.auto_tag(file_info) for file_info in files]
