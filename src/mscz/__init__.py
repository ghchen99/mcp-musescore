"""Editing MuseScore score files directly, for changes the plugin API cannot make."""

from .measure_repeats import apply_measure_repeats
from .score_file import ScoreFile, ScoreFileError

__all__ = ["ScoreFile", "ScoreFileError", "apply_measure_repeats"]
