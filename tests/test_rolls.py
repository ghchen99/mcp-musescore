"""Tests for rewriting cymbal rolls as long tied notes (src/mscz/rolls.py)."""

import os
import subprocess

import pytest

from dev.plugin_harness import find_musescore
from src.mscz import ScoreFile, ScoreFileError
from src.mscz.rolls import note_value, rest_values, simplify_roll

TPC_BY_PITCH_CLASS = [14, 21, 16, 23, 18, 13, 20, 15, 22, 17, 24, 19]


def chord(duration, *pitches, tremolo=False):
    notes = "".join(
        f"<Note><pitch>{p}</pitch><tpc>{TPC_BY_PITCH_CLASS[p % 12]}</tpc></Note>"
        for p in pitches
    )
    trem = (
        "<TremoloSingleChord><subtype>r16</subtype></TremoloSingleChord>"
        if tremolo
        else ""
    )
    return (
        f"<Chord><durationType>{duration}</durationType>{notes}{trem}</Chord>"
    )


def write_score(tmp_path, bars):
    """Write a one-staff 4/4 drum score, one bar per voice-1 string."""
    measures = "".join(
        f"<Measure><voice>{'<TimeSig><sigN>4</sigN><sigD>4</sigD></TimeSig>' if i == 0 else ''}{b}<BarLine/></voice></Measure>"
        for i, b in enumerate(bars)
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><museScore version="4.70"><Score>'
        '<Part id="1"><Staff id="1"/><trackName>Drums</trackName></Part>'
        f'<Staff id="1">{measures}</Staff></Score></museScore>'
    )
    path = tmp_path / "roll.mscx"
    path.write_text(xml)
    return path


CRASH_ROLL = [
    chord("quarter", 35, 49) + chord("quarter", 49, tremolo=True) * 3,
    chord("quarter", 49, tremolo=True) * 2 + chord("quarter", 38) * 2,
]


def voices(measure):
    return [
        [
            (
                c.tag,
                c.findtext("durationType"),
                c.findtext("dots"),
                [n.findtext("pitch") for n in c.findall("Note")],
            )
            for c in v
            if c.tag in ("Chord", "Rest")
        ]
        for v in measure.findall("voice")
    ]


def test_note_values():
    assert (
        note_value(2880) == ("whole", 1)
        and note_value(1440) == ("half", 1)
        and note_value(480) == ("quarter", 0)
    )
    assert rest_values(2400) == [("whole", 0), ("quarter", 0)]
    with pytest.raises(ScoreFileError):
        note_value(1920 + 240)


def test_roll_becomes_one_tied_note_per_bar(tmp_path):
    path = write_score(tmp_path, CRASH_ROLL)
    score = ScoreFile(path)
    report = simplify_roll(
        score, 0, 1, 2, end_ticks=960, pitches=(49,), slashes=3
    )
    assert report["replaced_chords"] == 6 and report["moved_to_voice_2"] == [
        "35"
    ]
    score.save()

    first, second = ScoreFile(path).staves()[0].findall("Measure")
    assert voices(first) == [
        [("Chord", "whole", None, ["49"])],
        [("Chord", "quarter", None, ["35"]), ("Rest", "half", "1", [])],
    ]
    assert first.findtext("voice[2]/Rest/visible") == "0"
    assert voices(second) == [
        [
            ("Chord", "half", None, ["49"]),
            ("Chord", "quarter", None, ["38"]),
            ("Chord", "quarter", None, ["38"]),
        ]
    ]
    assert first.findtext("voice/Chord/TremoloSingleChord/subtype") == "r32"
    tie_out = first.findall("voice/Chord/Note/Spanner[@type='Tie']")[0]
    tie_in = second.findall("voice/Chord/Note/Spanner[@type='Tie']")[0]
    assert (
        tie_out.findtext("next/location/measures") == "1"
        and tie_in.findtext("prev/location/measures") == "-1"
    )


def test_roll_with_other_notes_inside_is_refused(tmp_path):
    path = write_score(
        tmp_path,
        [chord("quarter", 49) + chord("quarter", 38) + chord("half", 49)],
    )
    with pytest.raises(ScoreFileError, match="other notes"):
        simplify_roll(ScoreFile(path), 0, 1, 1, pitches=(49,))


def test_roll_must_end_where_a_note_ends(tmp_path):
    path = write_score(tmp_path, [chord("half", 49) * 2])
    with pytest.raises(ScoreFileError, match="does not end where a note ends"):
        simplify_roll(ScoreFile(path), 0, 1, 1, end_ticks=480, pitches=(49,))


MID_BAR_ROLL = [
    chord("quarter", 49) * 2
    + chord("quarter", 35, 49)
    + chord("quarter", 49, tremolo=True),
    chord("quarter", 49, tremolo=True) * 2
    + chord("eighth", 49)
    + chord("eighth", 38)
    + chord("quarter", 38),
]


def test_roll_can_start_mid_bar_and_end_on_an_odd_length(tmp_path):
    path = write_score(tmp_path, MID_BAR_ROLL)
    score = ScoreFile(path)
    report = simplify_roll(
        score, 0, 1, 2, start_ticks=960, end_ticks=1200, pitches=(49,)
    )
    assert report["replaced_chords"] == 5 and report["new_notes"] == 3
    score.save()

    first, second = ScoreFile(path).staves()[0].findall("Measure")
    # the hits before the roll stay; the kick on beat 3 moves to voice 2, after an invisible half rest
    assert voices(first) == [
        [("Chord", "quarter", None, ["49"])] * 2
        + [("Chord", "half", None, ["49"])],
        [
            ("Rest", "half", None, []),
            ("Chord", "quarter", None, ["35"]),
            ("Rest", "quarter", None, []),
        ],
    ]
    # five eighths: a half tied to an eighth
    assert voices(second)[0][:2] == [
        ("Chord", "half", None, ["49"]),
        ("Chord", "eighth", None, ["49"]),
    ]

    def location(chord, direction):
        tie = next(
            s for s in chord.iter("Spanner") if s.find(direction) is not None
        )
        return tie.findtext(f"{direction}/location/measures"), tie.findtext(
            f"{direction}/location/fractions"
        )

    roll_start = first.findall("voice/Chord")[2]
    half, eighth = second.findall("voice/Chord")[:2]
    assert roll_start.find("Note/Spanner/prev") is None
    assert location(roll_start, "next") == ("1", "-1/2")
    assert location(half, "prev") == ("-1", "1/2") and location(
        half, "next"
    ) == (None, "1/2")
    assert (
        location(eighth, "prev") == (None, "-1/2")
        and eighth.find("Note/Spanner/next") is None
    )


def test_roll_before_a_measure_without_voice(tmp_path):
    """A roll before a measure without a voice is rewritten.

    A measure without <voice> after the roll has no notes, so there is no tie into it to drop.
    """
    path = write_score(tmp_path, [chord("whole", 49), chord("whole", 38)])
    score = ScoreFile(path)
    second = score.staves()[0].findall("Measure")[1]
    second.remove(second.findall("voice")[0])
    report = simplify_roll(score, 0, 1, 1, pitches=(49,))
    assert report["replaced_chords"] == 1 and second.find("voice") is None


def test_roll_must_start_where_a_note_starts(tmp_path):
    path = write_score(tmp_path, [chord("half", 49) * 2])
    with pytest.raises(
        ScoreFileError, match="No note starts where the roll starts"
    ):
        simplify_roll(ScoreFile(path), 0, 1, 1, start_ticks=480, pitches=(49,))


def musescore_roundtrip(tmp_path, path):
    out_dir = tmp_path / "out"  # the CLI clears the folder it writes .mscx into
    out_dir.mkdir()
    out = out_dir / "roundtrip.mscx"
    musescore = find_musescore()
    assert musescore is not None
    subprocess.run(
        [musescore, "-o", str(out), str(path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        timeout=300,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return ScoreFile(out).staves()[0].findall("Measure")


def tied_chord(duration, *pitches, back=None, ahead=None, tremolo=False):
    """Make a chord whose notes are tied back and ahead.

    Tied from `back` and to `ahead` (fractions of a whole, e.g. "1/4").
    """
    ties = ""
    if ahead:
        ties += f'<Spanner type="Tie"><Tie/><next><location><fractions>{ahead}</fractions></location></next></Spanner>'
    if back:
        ties += f'<Spanner type="Tie"><prev><location><fractions>-{back}</fractions></location></prev></Spanner>'
    notes = "".join(
        f"<Note>{ties if p in (49, 57) else ''}<pitch>{p}</pitch><tpc>{TPC_BY_PITCH_CLASS[p % 12]}</tpc></Note>"
        for p in pitches
    )
    trem = (
        "<TremoloSingleChord><subtype>r16</subtype></TremoloSingleChord>"
        if tremolo
        else ""
    )
    return (
        f"<Chord><durationType>{duration}</durationType>{notes}{trem}</Chord>"
    )


def test_roll_starts_where_the_tied_cymbals_start(tmp_path):
    """The roll starts where the tied cymbals start.

    As Guitar Pro imports write it: crash + crash 2 hit with the kick on beat 1, left ringing (tied) into a
    tremolo from beat 3. The roll covers it all, from beat 1.
    """
    path = write_score(
        tmp_path,
        [
            tied_chord("quarter", 35, 49, 57, ahead="1/4")
            + tied_chord("quarter", 49, 57, back="1/4", ahead="1/4")
            + tied_chord("half", 49, 57, back="1/4", tremolo=True),
            chord("half", 49, 57, tremolo=True) + chord("half", 38),
        ],
    )
    score = ScoreFile(path)
    report = simplify_roll(score, 0, 1, 2, end_ticks=960, start_ticks=960)
    assert (
        report["start_moved_back"]["tick"] == 0
        and report["replaced_chords"] == 4
    )
    assert report["moved_to_voice_2"] == ["35"]
    first = score.staves()[0].findall("Measure")[0]
    assert voices(first)[0] == [("Chord", "whole", None, ["49", "57"])]


def test_roll_start_stays_without_a_tie_into_it(tmp_path):
    path = write_score(
        tmp_path,
        [
            chord("quarter", 35, 49, 57)
            + chord("quarter", 49, 57)
            + chord("half", 49, 57)
        ],
    )
    report = simplify_roll(ScoreFile(path), 0, 1, 1, start_ticks=480)
    assert "start_moved_back" not in report and report["starts_at_tick"] == 480


@pytest.mark.skipif(find_musescore() is None, reason="MuseScore not installed")
def test_musescore_reads_a_mid_bar_roll_back(tmp_path):
    path = write_score(tmp_path, MID_BAR_ROLL)
    score = ScoreFile(path)
    simplify_roll(
        score, 0, 1, 2, start_ticks=960, end_ticks=1200, pitches=(49,)
    )
    score.save()
    first, second = musescore_roundtrip(tmp_path, path)
    roll_start = first.findall("voice/Chord")[2]
    half, eighth = second.findall("voice/Chord")[:2]
    assert roll_start.find("Note/Spanner[@type='Tie']/next") is not None
    assert half.find("Note/Spanner[@type='Tie']/prev") is not None
    assert half.find("Note/Spanner[@type='Tie']/next") is not None
    assert eighth.find("Note/Spanner[@type='Tie']/prev") is not None
    assert eighth.findtext("TremoloSingleChord/subtype") == "r32"


@pytest.mark.skipif(find_musescore() is None, reason="MuseScore not installed")
def test_musescore_reads_the_roll_back(tmp_path):
    path = write_score(tmp_path, CRASH_ROLL)
    score = ScoreFile(path)
    simplify_roll(score, 0, 1, 2, end_ticks=960, pitches=(49,))
    score.save()
    out_dir = tmp_path / "out"  # the CLI clears the folder it writes .mscx into
    out_dir.mkdir()
    out = out_dir / "roundtrip.mscx"
    musescore = find_musescore()
    assert musescore is not None
    subprocess.run(
        [musescore, "-o", str(out), str(path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        timeout=300,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    first, second = ScoreFile(out).staves()[0].findall("Measure")
    assert voices(first)[0] == [("Chord", "whole", None, ["49"])]
    assert first.find("voice/Chord/Note/Spanner[@type='Tie']/next") is not None
    assert voices(second)[0][0] == ("Chord", "half", None, ["49"])
