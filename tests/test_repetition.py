"""Unit tests for the repeated-material analysis.

They need neither MuseScore nor the mock plugin.
"""

from src.utils.repetition import (
    find_repeats,
    measure_fingerprint,
    staff_fingerprints,
)
from src.utils.sections import find_sections

BAR = 1920
PITCHES = {letter: 60 + i for i, letter in enumerate("ABCDEFGH")}


def bar_elements(number, letter):
    """Four quarter notes of one pitch per letter; "-" is a whole-bar rest."""
    start = (number - 1) * BAR
    if letter == "-":
        return [
            {
                "name": "Rest",
                "startTick": start,
                "durationTicks": BAR,
                "voice": 0,
            }
        ]
    return [
        {
            "name": "Chord",
            "startTick": start + i * 480,
            "durationTicks": 480,
            "voice": 0,
            "notes": [{"pitchMidi": PITCHES[letter]}],
        }
        for i in range(4)
    ]


def measures(*staff_patterns):
    """Make getScore-style measures from patterns.

    Each pattern string gives one staff, one letter per bar.
    """
    return [
        {
            "measure": i + 1,
            "startTick": i * BAR,
            "durationTicks": BAR,
            "elements": {
                f"staff{s}": bar_elements(i + 1, p[i])
                for s, p in enumerate(staff_patterns)
            },
        }
        for i in range(len(staff_patterns[0]))
    ]


def test_fingerprint_ignores_position_in_score_and_lyrics():
    first = bar_elements(1, "A")
    later = bar_elements(5, "A")
    later[0]["lyrics"] = [{"text": "la"}]
    assert measure_fingerprint(first, 0) == measure_fingerprint(later, 4 * BAR)
    assert measure_fingerprint(first, 0) != measure_fingerprint(
        bar_elements(1, "B"), 0
    )


def test_one_bar_repeat_on_one_staff_only():
    result = find_repeats(measures("ABBC", "EFGH"))
    assert result["measure_repeats"] == [
        {"bars": 1, "from": 3, "to": 3, "staves": [0]}
    ]
    assert result["passages"] == []


def test_two_and_four_bar_measure_repeats():
    two = find_repeats(measures("ABAB"))["measure_repeats"]
    four = find_repeats(measures("ABCDABCD"))["measure_repeats"]
    assert two == [{"bars": 2, "from": 3, "to": 4, "staves": [0]}]
    assert four == [{"bars": 4, "from": 5, "to": 8, "staves": [0]}]


def test_rest_bars_are_not_measure_repeats():
    assert find_repeats(measures("A--B"))["measure_repeats"] == []


def test_staves_with_the_same_repeats_are_grouped():
    result = find_repeats(measures("AAB", "CCD", "EFG"))
    assert result["measure_repeats"] == [
        {"bars": 1, "from": 2, "to": 2, "staves": [0, 1]}
    ]


def test_passage_repeated_on_all_staves():
    (passage,) = find_repeats(measures("EABCABC", "EDEFDEF"))["passages"]
    assert passage["type"] == "repeat"
    assert (passage["start"], passage["end"], passage["times"]) == (2, 4, 2)
    assert passage["duplicate_measures"] == [5, 7]
    assert passage["saves_measures"] == 3


def test_repeat_count_prefers_the_biggest_saving():
    (passage,) = find_repeats(measures("AAAA"))["passages"]
    assert (passage["start"], passage["end"], passage["times"]) == (1, 1, 4)
    assert passage["saves_measures"] == 3


def test_passage_with_first_and_second_endings():
    (passage,) = find_repeats(measures("ABCDABCE"))["passages"]
    assert passage["type"] == "repeat_with_endings"
    assert (passage["start"], passage["end"]) == (1, 3)
    assert passage["first_ending"] == [4, 4]
    assert passage["second_ending"] == [8, 8]
    assert passage["duplicate_measures"] == [5, 7]


def test_passage_needs_every_staff_to_repeat():
    assert find_repeats(measures("ABCABC", "DDDEEE"))["passages"] == []


def test_measure_numbers_follow_the_input_range():
    ms = measures("CABAB")[1:]  # analyse measures 2-5 only
    (passage,) = find_repeats(ms)["passages"]
    assert (
        passage["start"],
        passage["end"],
        passage["duplicate_measures"],
    ) == (2, 3, [4, 5])


def sign_bar(number, size=1):
    """A bar holding a measure-repeat sign, as the plugin reports it."""
    return [
        {
            "name": "MeasureRepeat",
            "numMeasures": size,
            "startTick": (number - 1) * BAR,
            "durationTicks": BAR,
            "voice": 0,
        }
    ]


def test_existing_repeat_signs_count_as_copies():
    ms = measures("ABCD")
    ms[1]["elements"]["staff0"] = sign_bar(
        2
    )  # bar 2 is a repeat sign of bar 1: A A C D
    fps, existing = staff_fingerprints(ms, "staff0")
    assert fps[1] == fps[0] and existing == {1}
    result = find_repeats(ms)
    assert result["measure_repeats"] == []  # bar 2 is already a sign
    assert (
        result["passages"][0]["start"] == 1
    )  # A A is still seen as a repeated passage


def test_two_bar_sign_resolves_both_bars():
    ms = measures("ABAB")
    ms[2]["elements"]["staff0"] = sign_bar(3, size=2)
    ms[3]["elements"]["staff0"] = [
        {"name": "Rest", "startTick": 3 * BAR, "durationTicks": BAR, "voice": 0}
    ]
    fps, existing = staff_fingerprints(ms, "staff0")
    assert fps[2:] == fps[:2] and existing == {2, 3}


def groove_bar(
    number, kick_beats=(1, 3), snare_beats=(2, 4), extra=(), cymbal=42
):
    """Make a groove bar of kick, snare and cymbal.

    Kick and snare on the given beats, eighth notes on the cymbal (closed hi-hat by default).
    """
    start = (number - 1) * BAR
    hits = (
        [(b, 36) for b in kick_beats]
        + [(b, 38) for b in snare_beats]
        + list(extra)
    )
    hits += [(b + h / 2, cymbal) for b in range(1, 5) for h in range(2)]
    by_tick = {}
    for beat, pitch in hits:
        by_tick.setdefault(int((beat - 1) * 480), []).append(pitch)
    return [
        {
            "name": "Chord",
            "startTick": start + t,
            "durationTicks": 240,
            "voice": 0,
            "notes": [{"pitchMidi": p} for p in sorted(ps)],
        }
        for t, ps in sorted(by_tick.items())
    ]


def fill_bar(number):
    start = (number - 1) * BAR
    return [
        {
            "name": "Chord",
            "startTick": start + i * 240,
            "durationTicks": 240,
            "voice": 0,
            "notes": [{"pitchMidi": 45 + (i % 4)}],
        }
        for i in range(8)
    ]


def drum_measures(bars):
    return [
        {
            "measure": i + 1,
            "startTick": i * BAR,
            "durationTicks": BAR,
            "elements": {"staff0": b},
        }
        for i, b in enumerate(bars)
    ]


def test_sections_split_groove_near_copies_and_fills():
    bars = [groove_bar(n) for n in range(1, 5)]  # 1-4 groove
    bars.append(groove_bar(5, extra=[(2.5, 36)]))  # 5 near: extra kick
    bars += [groove_bar(n) for n in (6, 7)]  # 6-7 groove
    bars.append(fill_bar(8))  # 8 fill, section ends
    bars += [
        groove_bar(n, cymbal=51) for n in range(9, 13)
    ]  # 9-12 new groove on the ride

    first, second = find_sections(drum_measures(bars), "staff0")
    assert (first["start"], first["end"], first["groove_bar"]) == (1, 8, 1)
    assert first["exact"] == [2, 3, 4, 6, 7] and first["fills"] == [8]
    (near,) = first["near"]
    assert (
        near["bar"] == 5
        and near["extra"] == ["kick on beat 2.5"]
        and near["missing"] == []
    )
    # bar 6 follows the near bar 5, so a 1-bar sign there would repeat bar 5: not proposed
    assert first["proposed_repeat_signs"] == [
        {"start": 2, "end": 4, "bars": 1},
        {"start": 7, "end": 7, "bars": 1},
    ]
    # the extra kick in bar 5 matters, so it stays written out between two runs
    assert [
        (r["start"], r["end"], r["phrase_bars"], r["play_count"])
        for r in first["runs"]
    ] == [(1, 4, 1, 4), (6, 7, 1, 2)]
    assert (second["start"], second["end"], second["exact"]) == (
        9,
        12,
        [10, 11, 12],
    )
    assert [
        (r["start"], r["end"], r["play_count"]) for r in second["runs"]
    ] == [(9, 12, 4)]


def test_new_groove_without_fill_starts_a_section():
    bars = [groove_bar(n) for n in (1, 2)] + [
        groove_bar(n, cymbal=51) for n in (3, 4)
    ]
    first, second = find_sections(drum_measures(bars), "staff0")
    assert (first["end"], first["fills"]) == (2, [])
    assert (second["start"], second["groove_bar"]) == (3, 3)


def test_mid_section_fill_keeps_the_section():
    bars = [groove_bar(1), groove_bar(2), fill_bar(3), groove_bar(4)]
    (section,) = find_sections(drum_measures(bars), "staff0")
    assert section["fills"] == [3] and section["exact"] == [2, 4]
    assert section["proposed_repeat_signs"] == [
        {"start": 2, "end": 2, "bars": 1}
    ]


def test_two_extra_kicks_still_count_as_near():
    bars = [groove_bar(1), groove_bar(2, kick_beats=(1, 2, 3, 4))]
    (section,) = find_sections(drum_measures(bars), "staff0")
    assert section["near"][0]["extra"] == ["kick on beat 2", "kick on beat 4"]


def crash_groove(number, crash):
    bar = groove_bar(number)
    if crash:
        bar[0]["notes"].append({"pitchMidi": 57})
    return bar


def test_crash_patterns():
    from src.utils.sections import crash_legend, crash_pattern

    assert crash_pattern([True, False, False]) == {"pattern": "first_only"}
    assert crash_pattern([True, False, True, False]) == {
        "pattern": "every_n",
        "every": 2,
        "from_bar": 1,
    }
    assert crash_pattern(
        [True, False, False, False, True, False, False, False]
    ) == {"pattern": "every_n", "every": 4, "from_bar": 1}
    assert crash_pattern([False, True, False, True]) == {
        "pattern": "every_n",
        "every": 2,
        "from_bar": 2,
    }
    assert crash_pattern([True, True]) == {"pattern": "every_bar"}
    assert crash_pattern([False, False]) == {"pattern": "none"}
    assert crash_pattern([True, True, False, True]) == {
        "pattern": "irregular",
        "run_bars": [1, 2, 4],
        "description": "crash on times 1, 2, 4",
    }
    assert crash_pattern([False, True]) == {
        "pattern": "irregular",
        "run_bars": [2],
        "description": "crash on 2nd time only",
    }

    assert crash_legend({"pattern": "first_only"}) == (
        "*",
        "crash on 1st time only",
    )
    assert crash_legend({"pattern": "every_n", "every": 2, "from_bar": 1}) == (
        "**",
        "crash every other bar",
    )
    assert crash_legend({"pattern": "every_n", "every": 4, "from_bar": 1}) == (
        "**",
        "crash every 4 bars",
    )
    assert crash_legend({"pattern": "every_n", "every": 2, "from_bar": 2}) == (
        "**",
        "crash every other bar, from the 2nd time",
    )
    assert crash_legend({"pattern": "every_bar"}) is None


def test_sections_report_the_crash_pattern_of_the_groove_run():
    # bars 1-6: crash on 1 every other bar (near copies of each other), bar 7 fill
    bars = [crash_groove(n, crash=(n % 2 == 1)) for n in range(1, 7)] + [
        fill_bar(7)
    ]
    (section,) = find_sections(drum_measures(bars), "staff0")
    (run,) = section["runs"]
    assert (
        run["start"],
        run["end"],
        run["phrase_bars"],
        run["play_count"],
    ) == (1, 6, 1, 6)
    assert run["crash_on_1"] == {
        "pattern": "every_n",
        "every": 2,
        "from_bar": 1,
        "mark": "**",
        "legend": "crash every other bar",
    }
    assert (
        run["dropped"] == []
    )  # crashes on 1 are described by the mark, not dropped


def open_hat_bar(number, crash=False):
    """The groove with the last hi-hat eighth opened."""
    bar = crash_groove(number, crash)
    bar[-1]["notes"] = [
        {"pitchMidi": 46} if n["pitchMidi"] == 42 else n
        for n in bar[-1]["notes"]
    ]
    return bar


def test_open_hat_every_second_bar_makes_a_two_bar_phrase():
    bars = []
    for n in range(1, 9):
        bars.append(open_hat_bar(n) if n % 2 == 0 else groove_bar(n))
    bars.append(fill_bar(9))
    section = find_sections(drum_measures(bars), "staff0")[0]
    (run,) = section["runs"]
    assert (
        run["start"],
        run["end"],
        run["phrase_bars"],
        run["play_count"],
        run["keep"],
    ) == (1, 8, 2, 4, [1, 2])
    assert run["dropped"] == []
    assert (
        section["fills"] == []
    )  # the open-hat bars are part of the phrase, not fills


def test_ghost_notes_do_not_block_collapsing_but_are_reported():
    bars = [groove_bar(n) for n in range(1, 5)]
    bars[2][1]["notes"].append(
        {"pitchMidi": 38, "ghost": True}
    )  # a ghost snare on the "and" of 1 in bar 3
    (section,) = find_sections(drum_measures(bars), "staff0")
    (run,) = section["runs"]
    assert (run["start"], run["end"], run["play_count"]) == (1, 4, 4)
    assert run["dropped"] == [
        {"bar": 3, "extra": ["snare on beat 1.5"], "missing": []}
    ]


def test_phrase_crash_legend_counts_times():
    bars = []
    for n in range(1, 9):
        bars.append(
            open_hat_bar(n)
            if n % 2 == 0
            else crash_groove(n, crash=n in (1, 5))
        )
    (section,) = find_sections(drum_measures(bars), "staff0")
    (run,) = section["runs"]
    assert (
        run["phrase_bars"] == 2
        and run["crash_on_1"]["legend"] == "crash every other time"
    )


def crash_instead_of_hat(bar):
    bar[0]["notes"] = [
        {"pitchMidi": 49} if n["pitchMidi"] == 42 else n
        for n in bar[0]["notes"]
    ]
    return bar


def test_phrases_start_on_the_crash_bars():
    """Phrases start on the crash bars.

    The intro of "Hold the Line": crash bar 1 (no hi-hat on the 2nd eighth), open hat at the end of bars 2
    and 4, crash again on bar 5, bar 6 different. 1 + [2-3]x2 + 1 leaves as few bars as 4 + 2 but starts a
    2-bar phrase on the bar after the crash; the chart should read 4 + 2.
    """
    first = crash_instead_of_hat(groove_bar(1))
    first[1]["notes"] = [n for n in first[1]["notes"] if n["pitchMidi"] != 42]
    bars = [
        first,
        open_hat_bar(2),
        groove_bar(3),
        open_hat_bar(4),
        crash_instead_of_hat(groove_bar(5)),
        groove_bar(6, kick_beats=(1, 2.5, 3)),
    ]
    runs = [
        (r["start"], r["end"], r["phrase_bars"])
        for s in find_sections(drum_measures(bars), "staff0")
        for r in s["runs"]
    ]
    assert (2, 5, 2) not in runs
    assert all(
        length == 1 or (start - 1) % length == 0 for start, _, length in runs
    )


def test_song_structure_counts_bars_as_played_and_names_grooves():
    from src.utils.sections import song_structure

    bars = [
        groove_bar(1),
        open_hat_bar(2),
        groove_bar(3, cymbal=51),
        fill_bar(4),
        groove_bar(5, cymbal=51),
        groove_bar(6, kick_beats=(1, 2.5, 3), cymbal=51),
        fill_bar(7),
    ]
    ms = drum_measures(bars)
    ms[0]["markings"] = [{"name": "RehearsalMark", "text": "Intro"}]
    ms[2]["markings"] = [{"name": "RehearsalMark", "text": "Verse"}]
    ms[4]["repeatStart"], ms[5]["repeatEnd"] = (
        True,
        4,
    )  # bars 5-6 played 4 times
    result = song_structure(ms, "staff0")
    intro, verse = result["sections"]
    assert (intro["section"], intro["bars_played"], intro["fills"]) == (
        "Intro",
        2,
        [],
    )
    assert intro["grooves"] == [
        {"name": "Groove A", "bars_played": 2}
    ]  # the open-hat bar is the same groove
    assert (verse["section"], verse["bars_played"], verse["bars_on_page"]) == (
        "Verse",
        1 + 1 + 8 + 1,
        5,
    )
    assert verse["grooves"] == [
        {"name": "Groove B", "bars_played": 9}
    ]  # the extra kick in bar 6 is a variation
    assert [f["bar"] for f in verse["fills"]] == [4, 7] and result[
        "total_bars_played"
    ] == 13  # same fill twice


def test_count_labels_are_in_fours():
    from src.utils.sections import count_bars, count_label

    assert [count_label(n) for n in (2, 4, 6, 8, 10, 12, 14, 16)] == [
        "2",
        "4",
        "4+2",
        "2x4",
        "2x4+2",
        "3x4",
        "3x4+2",
        "4x4",
    ]
    assert (
        count_label(8, lead_in=2) == "2+4+2"
        and count_label(2, lead_in=2) == "2"
    )
    assert [count_bars(x) for x in ("2+4+2", "3x4+2", "4x4", 9, "Intro")] == [
        8,
        14,
        16,
        9,
        None,
    ]


def test_counts_follow_the_phrasing():
    from src.utils.sections import count_label

    assert (
        count_label(10, lead_in=1) == "2x4+2"
    )  # a single bar before the groove is part of the count
    assert count_label(7, lead_in=1) == "4+3"
    assert (
        count_label(8, groups=[4, 2, 2]) == "4+2+2"
    )  # 2 bars in another time signature in the middle
    assert count_label(8, lead_in=2, groups=[6]) == "2+4+2"


def test_song_structure_keeps_the_count_written_in_the_label():
    from src.utils.sections import song_structure

    bars = [groove_bar(n) for n in range(1, 7)] + [fill_bar(7), groove_bar(8)]
    ms = drum_measures(bars)
    ms[0]["markings"] = [
        {"name": "RehearsalMark", "text": "Verse (2+4)"}
    ]  # the user's phrasing
    ms[6]["markings"] = [{"name": "RehearsalMark", "text": "Chorus (5)"}]
    ms[4]["durationTicks"] = ms[5]["durationTicks"] = 1440  # bars 5-6 in 3/4
    verse, chorus = song_structure(ms, "staff0")["sections"]
    assert (
        verse["section"],
        verse["count"],
        verse["count_source"],
        verse["computed_count"],
    ) == (
        "Verse",
        "2+4",
        "label",
        "4+2",
    )  # computed: 4 bars of 4/4, then 2 of 3/4
    assert (
        chorus["section"],
        chorus["count"],
        chorus["label_count_outdated"],
    ) == ("Chorus", "2", "5")
