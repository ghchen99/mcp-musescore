"""Edit MuseScore score files directly, for what the plugin API can't do."""

from .measure_repeats import apply_measure_repeats
from .score_file import ScoreFile, ScoreFileError

__all__ = ["ScoreFile", "ScoreFileError", "apply_measure_repeats"]
