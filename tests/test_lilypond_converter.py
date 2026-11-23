"""Unit tests for the LilyPond conversion (src/utils/lilypond_converter.py)."""

from src.utils.lilypond_converter import (
    midi_to_lilypond_pitch,
    process_element,
    score_to_lilypond,
)

C, E, G = 60, 64, 67


def chord(*notes, ticks=480):
    """Make a Chord element from pitches.

    Each note is a pitch or a (pitch, {"tieForward": True, ...}) pair.
    """
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
    assert "c'4 c'4 c'4 c'4~ | % bar 1" in text
    assert "c'1 | % bar 2" in text


def test_octave_follows_the_written_note_across_the_octave_boundary():
    # C flat sounds as the B below it and B sharp as the C above it, so their
    # written octave differs from the octave of the MIDI pitch.
    # B5 written as C flat 6, B flat 4 as C double flat 5
    assert midi_to_lilypond_pitch(83, tpc=7) == "ces'''"
    assert midi_to_lilypond_pitch(70, tpc=0) == "ceses''"
    # C4 written as B sharp 3, C sharp 4 as B double sharp 3
    assert midi_to_lilypond_pitch(60, tpc=26) == "bis"
    assert midi_to_lilypond_pitch(61, tpc=33) == "bisis"
    # A plain B4 and middle C are unchanged
    assert midi_to_lilypond_pitch(71, tpc=19) == "b'"
    assert midi_to_lilypond_pitch(60, tpc=14) == "c'"


def test_transposing_staff_takes_the_octave_of_the_written_pitch():
    # A B flat instrument's written C5 sounds as B flat 4: the plugin names it
    # C (tpc 14) and reports the written pitch next to the sounding one
    written_c = (70, {"pitchWritten": 72, "tpc": 14})
    assert process_element(chord(written_c)) == "c''4"
