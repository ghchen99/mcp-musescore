"""Unit tests for the LilyPond conversion (src/utils/lilypond_converter.py)."""

import pytest

from src.utils.lilypond_converter import (
    midi_to_lilypond_pitch,
    process_element,
    score_to_lilypond,
    ticks_to_lilypond_duration,
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


def test_triplet_notes_are_two_thirds_of_the_note_they_are_written_as():
    # A triplet eighth lasts 160 ticks: two thirds of an eighth (240)
    assert ticks_to_lilypond_duration(640) == "2*2/3"
    assert ticks_to_lilypond_duration(320) == "4*2/3"
    assert ticks_to_lilypond_duration(160) == "8*2/3"
    assert ticks_to_lilypond_duration(80) == "16*2/3"


def test_a_tuplet_note_is_its_written_value_times_the_ratio():
    # Five 16ths in the time of four: each a 16th (120 ticks) times 4/5
    quintuplet = {"actual": 5, "normal": 4, "writtenTicks": 120}
    note = {**chord(C, ticks=96), "tuplet": quintuplet}
    assert process_element(note) == "c'16*4/5"
    rest = {"name": "Rest", "durationTicks": 96, "tuplet": quintuplet}
    assert process_element(rest) == "r16*4/5"
    # Seven 16ths in a quarter: 480/7 ticks, which no tick table can name
    septuplet = {"actual": 7, "normal": 4, "writtenTicks": 120}
    assert process_element({**chord(C, ticks=68), "tuplet": septuplet}) == (
        "c'16*4/7"
    )


@pytest.mark.parametrize(
    "tuplet, ticks, expected",
    [
        # A triplet inside a triplet: 9 16ths in the time of 4
        ({"actual": 9, "normal": 4, "writtenTicks": 120}, 53, "c'16*4/9"),
        # A quintuplet inside a triplet, or the other way round: 15 in 8
        ({"actual": 15, "normal": 8, "writtenTicks": 120}, 64, "c'16*8/15"),
        # Three triplets inside each other: 27 in 8
        ({"actual": 27, "normal": 8, "writtenTicks": 120}, 36, "c'16*8/27"),
        # A duplet: two eighths in the time of three, so longer than written
        ({"actual": 2, "normal": 3, "writtenTicks": 240}, 360, "c'8*3/2"),
        # A dotted written value in a triplet
        ({"actual": 3, "normal": 2, "writtenTicks": 360}, 240, "c'8.*2/3"),
    ],
)
def test_nested_and_unusual_tuplets_use_their_whole_ratio(
    tuplet, ticks, expected
):
    assert process_element({**chord(C, ticks=ticks), "tuplet": tuplet}) == (
        expected
    )


def test_a_tuplet_without_its_written_value_falls_back_to_the_length():
    # An older plugin, or one that could not read the written value
    tuplet = {"actual": 3, "normal": 2, "writtenTicks": 0}
    assert process_element({**chord(C, ticks=160), "tuplet": tuplet}) == (
        "c'8*2/3"
    )
