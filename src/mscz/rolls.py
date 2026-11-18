"""Rewrite a cymbal roll as one long note per bar, with a tremolo.

A roll is a run of repeated or tied cymbal notes. The new notes are tied across
barlines: fewer symbols for the same sound.

Notes of the first chord that are not part of the roll (e.g. a kick on beat 1)
move to voice 2 with their own length, followed by invisible rests, so the
tremolo only applies to the cymbals.

Only voice 1 of one staff is rewritten. The span starts in `start_measure` (at
its beginning, or `start_ticks` into it) and ends in `end_measure` (its end, or
`end_ticks` into it). If the cymbals at the start are tied from earlier notes (a
crash left ringing into the roll, as Guitar Pro imports write it), the roll
starts where that tie chain starts: one continuous roll, not a held crash and
then a roll. A length that no single note value can hold (e.g. five eighths) is
written as several tied notes. Every chord in the span must hold only roll
pitches, except the first one, whose other notes (e.g. a kick) are kept.
Anything that cannot be rewritten safely (other notes or rests in the span,
tuplets, a span that does not start or end where a note does) raises
ScoreFileError and nothing is changed.
"""

import copy
import xml.etree.ElementTree as ET
from fractions import Fraction
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .measure_repeats import measure_lengths
from .score_file import ScoreFile, ScoreFileError

WHOLE = 1920
DURATION_TICKS = {
    "whole": 1920,
    "half": 960,
    "quarter": 480,
    "eighth": 240,
    "16th": 120,
    "32nd": 60,
    "64th": 30,
}
DOT_FACTORS = {0: 1, 1: 1.5, 2: 1.75}
TREMOLO_SUBTYPES = {1: "r8", 2: "r16", 3: "r32", 4: "r64"}
CHORD_REST = {"Chord", "Rest"}


def fraction_ticks(text: str) -> int:
    """Convert a fraction of a whole note to ticks.

    Args:
        text (str): The fraction as "N/D", e.g. "3/4".

    Returns:
        ticks (int): The length in ticks, e.g. 1440 for "3/4".
    """
    num, den = text.split("/")
    return WHOLE * int(num) // int(den)


def element_ticks(element: ET.Element, measure_len: int) -> int:
    """Return how many ticks a chord or rest lasts.

    Args:
        element (ET.Element): The <Chord> or <Rest> element.
        measure_len (int): The measure's length in ticks, for a measure rest
            without a duration.

    Returns:
        ticks (int): The length in ticks, dots included.

    Raises:
        ScoreFileError: If its duration type is unknown.
    """
    kind = element.findtext("durationType")
    if kind == "measure":
        duration = element.findtext("duration")
        return fraction_ticks(duration) if duration else measure_len
    if kind not in DURATION_TICKS:
        raise ScoreFileError(f"Unknown duration {kind!r}")
    dots = int(element.findtext("dots") or 0)
    return int(DURATION_TICKS[kind] * DOT_FACTORS.get(dots, 1))


def note_value(ticks: int) -> Tuple[str, int]:
    """Find the single note value for a length in ticks.

    Args:
        ticks (int): The length in ticks.

    Returns:
        value (Tuple[str, int]): The durationType (e.g. "quarter") and the
            number of dots.

    Raises:
        ScoreFileError: If no single note value, with up to two dots, has that
            length.
    """
    for name, base in DURATION_TICKS.items():
        for dots, factor in DOT_FACTORS.items():
            if base * factor == ticks:
                return name, dots
    raise ScoreFileError(
        f"A length of {ticks} ticks cannot be written as one note value"
    )


def rest_values(ticks: int) -> List[Tuple[str, int]]:
    """Split a length in ticks into note values, longest first.

    Args:
        ticks (int): The length in ticks.

    Returns:
        values (List[Tuple[str, int]]): The (durationType, dots) of each value;
            together they add up to `ticks`.

    Raises:
        ScoreFileError: If the length cannot be filled with note values.
    """
    values = sorted(
        (
            (base * factor, name, dots)
            for name, base in DURATION_TICKS.items()
            for dots, factor in DOT_FACTORS.items()
        ),
        reverse=True,
    )
    out = []
    while ticks > 0:
        fit = next((v for v in values if v[0] <= ticks), None)
        if fit is None:
            raise ScoreFileError(f"{ticks} ticks cannot be filled with rests")
        out.append((fit[1], fit[2]))
        ticks -= int(fit[0])
    return out


def _duration(element: ET.Element, name: str, dots: int) -> ET.Element:
    """Give a chord or rest its note value.

    Args:
        element (ET.Element): The <Chord> or <Rest> element.
        name (str): The durationType, e.g. "quarter".
        dots (int): The number of dots.

    Returns:
        element (ET.Element): The same element, for chaining.
    """
    if dots:
        ET.SubElement(element, "dots").text = str(dots)
    ET.SubElement(element, "durationType").text = name
    return element


def _fraction(ticks: int) -> str:
    """Convert ticks to a fraction of a whole note.

    Args:
        ticks (int): The length in ticks.

    Returns:
        fraction (str): The fraction as "N/D", in lowest terms.
    """
    whole = Fraction(ticks, WHOLE)
    return f"{whole.numerator}/{whole.denominator}"


def _tie(direction: str, measures: int, ticks: int = 0) -> ET.Element:
    """Make one half of a tie: the link from a note to the next or previous one.

    The location of the other note is relative: whole measures, then a fraction
    within them.

    Args:
        direction (str): "next" or "prev".
        measures (int): The number of measures to the other note.
        ticks (int): The distance to the other note within the measure.

    Returns:
        spanner (ET.Element): The tie's <Spanner> element.
    """
    spanner = ET.Element("Spanner", {"type": "Tie"})
    if direction == "next":
        ET.SubElement(spanner, "Tie")
    location = ET.SubElement(ET.SubElement(spanner, direction), "location")
    if measures:
        ET.SubElement(location, "measures").text = str(measures)
    if ticks:
        ET.SubElement(location, "fractions").text = _fraction(ticks)
    return spanner


def _clean_note(note: ET.Element) -> ET.Element:
    """Copy a note without its id and ties.

    Args:
        note (ET.Element): The <Note> element.

    Returns:
        clean (ET.Element): A copy without its <eid> and <Spanner> children.
    """
    clean = copy.deepcopy(note)
    for child in list(clean):
        if child.tag in ("eid", "Spanner"):
            clean.remove(child)
    return clean


def _drop_ties(chord: ET.Element, direction: str, pitches: Set[str]) -> int:
    """Remove the ties of a chord's roll notes that go one way.

    Args:
        chord (ET.Element): The <Chord> element.
        direction (str): "next" or "prev".
        pitches (Set[str]): The roll pitches, as text.

    Returns:
        dropped (int): The number of ties removed.
    """
    dropped = 0
    for note in chord.findall("Note"):
        if note.findtext("pitch") not in pitches:
            continue
        for spanner in note.findall("Spanner"):
            if (
                spanner.get("type") == "Tie"
                and spanner.find(direction) is not None
            ):
                note.remove(spanner)
                dropped += 1
    return dropped


def _has_tie(chord: ET.Element, direction: str, pitches: Set[str]) -> bool:
    """Check whether one of a chord's roll notes is tied one way.

    Args:
        chord (ET.Element): The <Chord> element.
        direction (str): "next" or "prev".
        pitches (Set[str]): The roll pitches, as text.

    Returns:
        tied (bool): True if a roll note has a tie in that direction.
    """
    return any(
        spanner.get("type") == "Tie" and spanner.find(direction) is not None
        for note in chord.findall("Note")
        if note.findtext("pitch") in pitches
        for spanner in note.findall("Spanner")
    )


def _voice_one(
    measure: ET.Element, length: int
) -> Optional[List[Tuple[int, ET.Element]]]:
    """List the chords and rests of a measure's first voice, with their ticks.

    Args:
        measure (ET.Element): The <Measure> element.
        length (int): The measure's length in ticks, for measure rests.

    Returns:
        elements (Optional[List[Tuple[int, ET.Element]]]): The (tick, element)
            of each chord and rest, or None if the voice is missing or has
            tuplets or moved elements.
    """
    voice = measure.find("voice")
    if voice is None:
        return None
    out, tick = [], 0
    for child in voice:
        if child.tag in ("Tuplet", "location"):
            return None
        if child.tag in CHORD_REST:
            out.append((tick, child))
            tick += element_ticks(child, length)
    return out


def tie_chain_start(
    measures: List[ET.Element],
    lengths: List[int],
    start_measure: int,
    start_ticks: int,
    pitches: Set[str],
) -> Tuple[int, int]:
    """Find where the roll really starts, as (measure, ticks).

    Walks back while the roll cymbals are tied from the chord before, which must
    hold the roll cymbals too.

    Args:
        measures (List[ET.Element]): The staff's measures.
        lengths (List[int]): The length of each measure in ticks.
        start_measure (int): The requested start measure, 1-based.
        start_ticks (int): The requested start within that measure.
        pitches (Set[str]): The roll pitches, as text.

    Returns:
        start (Tuple[int, int]): The measure (1-based) and tick where the tie
            chain starts; the requested start if nothing is tied into it.
    """
    number, ticks = start_measure, start_ticks
    while True:
        elements = _voice_one(measures[number - 1], lengths[number - 1])
        if elements is None:
            return number, ticks
        index = next(
            (i for i, (t, _) in enumerate(elements) if t == ticks), None
        )
        if (
            index is None
            or elements[index][1].tag != "Chord"
            or not _has_tie(elements[index][1], "prev", pitches)
        ):
            return number, ticks
        if index > 0:
            previous_number, (previous_ticks, previous) = (
                number,
                elements[index - 1],
            )
        else:
            if number == 1:
                return number, ticks
            earlier = _voice_one(measures[number - 2], lengths[number - 2])
            if not earlier:
                return number, ticks
            previous_number, (previous_ticks, previous) = (
                number - 1,
                earlier[-1],
            )
        notes = {n.findtext("pitch") for n in previous.findall("Note")}
        if (
            previous.tag != "Chord"
            or not pitches <= notes
            or not _has_tie(previous, "next", pitches)
        ):
            return number, ticks
        number, ticks = previous_number, previous_ticks


def simplify_roll(
    score: ScoreFile,
    staff_index: int,
    start_measure: int,
    end_measure: int,
    end_ticks: Optional[int] = None,
    pitches: Sequence[int] = (49, 57),
    slashes: int = 3,
    start_ticks: int = 0,
) -> Dict:
    """Rewrite a cymbal roll as one long tremolo note per bar.

    See the module docstring for what is rewritten and what is refused.

    Args:
        score (ScoreFile): The score, changed in place.
        staff_index (int): The staff, 0-based.
        start_measure (int): The measure the roll starts in, 1-based.
        end_measure (int): The measure the roll ends in, 1-based.
        end_ticks (Optional[int]): Where the roll ends inside end_measure.
            Defaults to its end.
        pitches (Sequence[int]): The roll's MIDI pitches. Defaults to the two
            crash cymbals (49, 57).
        slashes (int): The tremolo strokes, 1-4 (eighths to 64ths).
        start_ticks (int): Where the roll starts inside start_measure. Defaults
            to its beginning.

    Returns:
        report (Dict): "measures", "replaced_chords",
            "ties_removed_at_the_edges", "new_notes", "starts_at_tick",
            "moved_to_voice_2" and "tremolo"; "start_moved_back" when the start
            moved back along a tie chain.

    Raises:
        ScoreFileError: If the staff, range or slashes are invalid, or the span
            cannot be rewritten safely.
    """
    staves = score.staves()
    if not 0 <= staff_index < len(staves):
        raise ScoreFileError(f"Staff {staff_index} does not exist")
    staff = staves[staff_index]
    measures = staff.findall("Measure")
    if not 1 <= start_measure <= end_measure <= len(measures):
        raise ScoreFileError(
            f"Invalid measure range {start_measure}-{end_measure}"
        )
    if slashes not in TREMOLO_SUBTYPES:
        raise ScoreFileError("slashes must be 1-4")
    lengths = [
        fraction_ticks(length) for length in measure_lengths(staff, staves[0])
    ]
    pitch_texts = {
        str(p) for p in pitches
    }  # the score file stores pitches as text
    requested = (start_measure, start_ticks)
    start_measure, start_ticks = tie_chain_start(
        measures, lengths, start_measure, start_ticks, pitch_texts
    )

    plans = []  # per measure: (number, voice, first index, last index, start tick, end tick, chords in span)
    for number in range(start_measure, end_measure + 1):
        measure = measures[number - 1]
        length = lengths[number - 1]
        begin = start_ticks if number == start_measure else 0
        stop = (
            end_ticks
            if number == end_measure and end_ticks is not None
            else length
        )
        if not 0 < stop <= length:
            raise ScoreFileError(f"The roll end is outside measure {number}")
        if not 0 <= begin < stop:
            raise ScoreFileError(
                f"The roll start is outside measure {number} or after its end"
            )
        for extra in measure.findall("voice")[1:]:
            if any(c.tag == "Chord" for c in extra):
                raise ScoreFileError(
                    f"Measure {number} has notes in other voices"
                )
        voice = measure.find("voice")
        if voice is None:
            raise ScoreFileError(f"Measure {number} is empty")

        tick, first, last, chords = 0, None, None, []
        for i, child in enumerate(voice):
            if child.tag in ("Tuplet", "location"):
                if tick < stop:
                    raise ScoreFileError(
                        f"Measure {number} has tuplets or moved elements inside the roll"
                    )
                continue
            if child.tag not in CHORD_REST:
                continue
            if tick >= stop:
                break
            if tick < begin:  # before the roll: left as it is
                tick += element_ticks(child, length)
                if tick > begin:
                    raise ScoreFileError(
                        f"No note starts where the roll starts in measure {number}"
                    )
                continue
            if child.tag == "Rest":
                raise ScoreFileError(
                    f"Measure {number} has a rest inside the roll"
                )
            notes = {n.findtext("pitch") for n in child.findall("Note")}
            is_first_chord = number == start_measure and not chords
            if not notes & pitch_texts or (
                not is_first_chord and not notes <= pitch_texts
            ):
                raise ScoreFileError(
                    f"Measure {number} has other notes inside the roll"
                )
            if first is None:
                first = i
            last = i
            chords.append(child)
            tick += element_ticks(child, length)
        if tick != stop:
            raise ScoreFileError(
                f"The roll does not end where a note ends in measure {number}"
            )
        if (
            first is None or last is None
        ):  # no roll chords (both are set when a chord is added)
            raise ScoreFileError(f"No roll notes in measure {number}")
        plans.append((number, voice, first, last, begin, stop, chords))

    # Ties from a note just before the roll, or into a note just after it, would point at removed notes
    dangling = 0
    number, voice, first, last, begin, stop, chords = plans[0]
    before = [c for c in list(voice)[:first] if c.tag == "Chord"]
    previous_voice = (
        measures[start_measure - 2].find("voice") if start_measure > 1 else None
    )
    if not before and previous_voice is not None:
        before = [c for c in previous_voice if c.tag == "Chord"]
    if before:
        dangling += _drop_ties(before[-1], "next", pitch_texts)
    number, voice, first, last, begin, stop, chords = plans[-1]
    after = [c for c in list(voice)[last + 1 :] if c.tag in CHORD_REST]
    if after and after[0].tag == "Chord":
        dangling += _drop_ties(after[0], "prev", pitch_texts)
    elif not after and end_measure < len(measures):
        following_voice = measures[end_measure].find(
            "voice"
        )  # None: an empty measure, so no tie into it
        following = (
            [c for c in following_voice if c.tag in CHORD_REST]
            if following_voice is not None
            else []
        )
        if following and following[0].tag == "Chord":
            dangling += _drop_ties(following[0], "prev", pitch_texts)

    first_chord = plans[0][6][0]
    roll_notes = [
        _clean_note(n)
        for n in first_chord.findall("Note")
        if n.findtext("pitch") in pitch_texts
    ]
    other_notes = [
        _clean_note(n)
        for n in first_chord.findall("Note")
        if n.findtext("pitch") not in pitch_texts
    ]

    # The new notes: one per bar, or several tied ones where no single value fits. (measure, tick, value)
    pieces = []
    for k, (number, voice, first, last, begin, stop, chords) in enumerate(
        plans
    ):
        tick = begin
        for name, dots in rest_values(stop - begin):
            pieces.append((k, tick, name, dots))
            tick += int(DURATION_TICKS[name] * DOT_FACTORS[dots])

    def piece_chord(i: int) -> ET.Element:
        """Make the chord of one new note, tied to its neighbours.

        Args:
            i (int): The index of the note in `pieces`.

        Returns:
            chord (ET.Element): The <Chord>, with the roll notes and a tremolo.
        """
        k, tick, name, dots = pieces[i]
        chord = _duration(ET.Element("Chord"), name, dots)
        for note in roll_notes:
            new = copy.deepcopy(note)
            ties = []
            if i < len(pieces) - 1:
                nk, ntick = pieces[i + 1][:2]
                ties.append(_tie("next", nk - k, ntick - tick))
            if i > 0:
                pk, ptick = pieces[i - 1][:2]
                ties.append(_tie("prev", pk - k, ptick - tick))
            for position, tie in enumerate(ties):
                new.insert(position, tie)
            chord.append(new)
        tremolo = ET.SubElement(chord, "TremoloSingleChord")
        ET.SubElement(tremolo, "subtype").text = TREMOLO_SUBTYPES[slashes]
        return chord

    replaced = 0
    for k, (number, voice, first, last, begin, stop, chords) in enumerate(
        plans
    ):
        new_chords = [
            piece_chord(i) for i, piece in enumerate(pieces) if piece[0] == k
        ]

        # Keep annotations that sat between the replaced chords (dynamics, texts): they move to the roll's start
        children = list(voice)
        between = [
            c
            for c in children[first : last + 1]
            if c.tag not in CHORD_REST and c.tag not in ("Beam",)
        ]
        for child in children[first : last + 1]:
            voice.remove(child)
        position = first
        for keep in between:
            voice.insert(position, keep)
            position += 1
        for chord in new_chords:
            voice.insert(position, chord)
            position += 1
        replaced += len(chords)

        if k == 0 and other_notes:
            measure = measures[number - 1]
            for extra in measure.findall("voice")[1:]:
                measure.remove(extra)
            second = ET.Element("voice")
            measure.insert(list(measure).index(voice) + 1, second)
            for name, dots in rest_values(begin):
                rest = ET.SubElement(second, "Rest")
                ET.SubElement(rest, "visible").text = "0"
                _duration(rest, name, dots)
            first_length = element_ticks(first_chord, lengths[number - 1])
            held = _duration(
                ET.SubElement(second, "Chord"), *note_value(first_length)
            )
            for note in other_notes:
                held.append(copy.deepcopy(note))
            for name, dots in rest_values(
                lengths[number - 1] - begin - first_length
            ):
                rest = ET.SubElement(second, "Rest")
                ET.SubElement(rest, "visible").text = "0"
                _duration(rest, name, dots)

    return {
        "measures": [start_measure, end_measure],
        "replaced_chords": replaced,
        "ties_removed_at_the_edges": dangling,
        "new_notes": len(pieces),
        "starts_at_tick": start_ticks,
        **(
            {
                "start_moved_back": {
                    "measure": start_measure,
                    "tick": start_ticks,
                    "reason": "the cymbals were tied into the roll from there",
                }
            }
            if (start_measure, start_ticks) != requested
            else {}
        ),
        "moved_to_voice_2": [n.findtext("pitch") for n in other_notes],
        "tremolo": TREMOLO_SUBTYPES[slashes],
    }
