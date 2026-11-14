"""Unit tests for the score JSON to LilyPond conversion (src/utils/lilypond_converter.py)."""

from src.utils.lilypond_converter import process_element, score_to_lilypond

C, E, G = 60, 64, 67


def chord(*notes, ticks=480):
    """A Chord element; each note is a pitch or a (pitch, {"tieForward": True, ...}) pair."""
    note_data = []
    for note in notes:
        pitch, extra = note if isinstance(note, tuple) else (note, {})
        note_data.append({"pitchMidi": pitch, **extra})
    return {"name": "Chord", "durationTicks": ticks, "notes": note_data}


TIED = {"tieForward": True}


def test_untied_notes_have_no_tie():
    assert process_element(chord(C)) == "c'4"
    assert process_element(chord(C, E, G)) == "<c' e' g'>4"


def test_tied_single_note():
    assert process_element(chord((C, TIED))) == "c'4~"


def test_fully_tied_chord_gets_one_tie_after_the_chord():
    assert process_element(chord((C, TIED), (E, TIED))) == "<c' e'>4~"


def test_partially_tied_chord_ties_each_tied_pitch():
    assert process_element(chord((C, TIED), (E, TIED), G)) == "<c'~ e'~ g'>4"


def test_tie_comes_before_lyrics():
    element = {**chord((C, TIED)), "lyrics": [{"text": "la"}]}
    assert process_element(element) == 'c\'4~^"la"'


def test_tie_back_alone_adds_nothing():
    # The tie is written once, on the note it starts from
    assert process_element(chord((C, {"tieBack": True}))) == "c'4"


def test_tie_across_a_barline():
    def bar(number, *elements):
        start = (number - 1) * 1920
        return {
            "measure": number,
            "startTick": start,
            "durationTicks": 1920,
            "elements": {
                "staff0": [
                    {**e, "startTick": start + 480 * i}
                    for i, e in enumerate(elements)
                ]
            },
        }

    score = {
        "measures": [
            bar(1, chord(C), chord(C), chord(C), chord((C, TIED))),
            bar(2, chord((C, {"tieBack": True}), ticks=1920)),
        ]
    }
    text = score_to_lilypond(score)
    assert "c'4 c'4 c'4 c'4~ | % m.1" in text
    assert "c'1 | % m.2" in text
