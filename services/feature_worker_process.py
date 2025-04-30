"""
Small helper that is *only* imported by multiprocessing.
Computes features for a single file and returns a serialisable dict.
"""

from services.analysis_engine import AnalysisEngine


def compute(path: str, max_duration: float = 30.0):
    return AnalysisEngine.analyze_audio_features(path, max_duration=max_duration)
