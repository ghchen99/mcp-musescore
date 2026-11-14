"""Find repeated material in a getScore analysis.

Measures are compared by a fingerprint of their notes and rests (position within the
measure, voice, duration, pitches, tuplet and tie flags; lyrics are ignored). Two kinds
of suggestions come out of it:

- per staff: bars that repeat the previous 1, 2 or 4 bars (measure-repeat signs);
- all staves: passages played again right after themselves (repeat barlines), and
  passages whose repeat differs only in its last bars (1st/2nd endings).

Bars that already hold a measure-repeat sign count as copies of the bars they repeat.
"""

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

Fingerprint = Tuple[Tuple[Any, ...], ...]

MEASURE_REPEAT_SIZES = (1, 2, 4)
# Which bar of an N-bar measure-repeat group holds the sign (MuseScore's layout)
SIGN_POSITION = {1: 0, 2: 0, 4: 1}


CRASH_PITCHES = {49, 57}  # crash cymbal 1 and 2
# On beat 1 a crash usually replaces the closed hi-hat, so for collapsing they count as the same "cymbal on 1"
BEAT_ONE_CYMBALS = CRASH_PITCHES | {42}


def measure_fingerprint(
    elements: Sequence[Dict[str, Any]], measure_start_tick: int
) -> Fingerprint:
    """Summarize one staff's content in one measure, for comparing bars.

    Each chord or rest counts with its position in the measure, voice,
    duration, pitches, tuplet and tie flags, articulations and ghost notes.

    Args:
        elements (Sequence[Dict[str, Any]]): The staff's elements in the
            measure, from the plugin's analysis.
        measure_start_tick (int): The tick at which the measure starts.

    Returns:
        fingerprint (Fingerprint): A hashable summary; equal for bars with
            the same content.
    """
    items = []
    for e in elements:
        notes = [
            n for n in e.get("notes", []) if n.get("pitchMidi") is not None
        ]
        items.append(
            (
                e.get("startTick", measure_start_tick) - measure_start_tick,
                e.get("voice", 0),
                e.get("name", ""),
                e.get("durationTicks", 0),
                tuple(sorted(n["pitchMidi"] for n in notes)),
                bool(e.get("isTuplet")),
                bool(e.get("isTie")),
                tuple(sorted(e.get("articulations") or [])),
                tuple(sorted(n["pitchMidi"] for n in notes if n.get("ghost"))),
            )
        )
    return tuple(sorted(items))


def core_fingerprint(
    elements: Sequence[Dict[str, Any]], measure_start_tick: int
) -> Fingerprint:
    """Summarize a bar like measure_fingerprint, but more loosely.

    Ghost notes are ignored, and a crash and a closed hi-hat on beat 1 both
    count as "a cymbal on 1". Bars with the same core can be collapsed into
    one: their only differences are things a chart shows with a mark (crash
    pattern) or leaves out (ghost notes).

    Args:
        elements (Sequence[Dict[str, Any]]): The staff's elements in the
            measure, from the plugin's analysis.
        measure_start_tick (int): The tick at which the measure starts.

    Returns:
        fingerprint (Fingerprint): A hashable summary of the bar's core.
    """
    items = []
    for e in elements:
        tick = e.get("startTick", measure_start_tick) - measure_start_tick
        notes = [
            n["pitchMidi"]
            for n in e.get("notes", [])
            if n.get("pitchMidi") is not None and not n.get("ghost")
        ]
        if tick == 0 and any(p in BEAT_ONE_CYMBALS for p in notes):
            notes = [p for p in notes if p not in BEAT_ONE_CYMBALS] + [
                -1
            ]  # -1: a cymbal on beat 1
        name = e.get("name", "")
        if name == "Chord" and not notes:
            name = "Rest"
        items.append(
            (
                tick,
                e.get("voice", 0),
                name,
                e.get("durationTicks", 0),
                tuple(sorted(notes)),
                bool(e.get("isTuplet")),
                tuple(sorted(e.get("articulations") or [])) if notes else (),
            )
        )
    return tuple(sorted(items))


def staff_fingerprints(
    measures: Sequence[Dict[str, Any]],
    staff: str,
    fingerprint: Callable[
        [Sequence[Dict[str, Any]], int], Fingerprint
    ] = measure_fingerprint,
) -> Tuple[List[Fingerprint], set]:
    """Fingerprint each measure of one staff.

    A bar covered by an existing measure-repeat sign gets the fingerprint of
    the bar it repeats.

    Args:
        measures (Sequence[Dict[str, Any]]): The measures from the plugin's
            analysis.
        staff (str): The staff name, e.g. "staff0".
        fingerprint (Callable[[Sequence[Dict[str, Any]], int], Fingerprint]):
            The function that summarizes a bar. Defaults to
            measure_fingerprint.

    Returns:
        result (Tuple[List[Fingerprint], set]): The fingerprint of each
            measure, and the 0-based indices of the bars covered by an
            existing measure-repeat group.
    """
    fps = []
    groups = []
    for i, m in enumerate(measures):
        elements = (m.get("elements") or {}).get(staff, [])
        fps.append(fingerprint(elements, m.get("startTick", 0)))
        sign = next(
            (e for e in elements if e.get("name") == "MeasureRepeat"), None
        )
        if sign is not None:
            size = int(sign.get("numMeasures") or 1)
            first = i - SIGN_POSITION.get(size, 0)
            groups.append((first, size))

    covered = {}
    for first, size in groups:
        for b in range(max(first, 0), min(first + size, len(fps))):
            covered[b] = size
    for b in sorted(covered):
        if b - covered[b] >= 0:
            fps[b] = fps[b - covered[b]]
    return fps, set(covered)


def _has_notes(fingerprint: Fingerprint) -> bool:
    """Check whether a bar holds anything but rests.

    Args:
        fingerprint (Fingerprint): The bar's fingerprint.

    Returns:
        has_notes (bool): True if it has a chord or other non-rest element.
    """
    return any(item[2] != "Rest" for item in fingerprint)


def _staff_index(name: str) -> int:
    """Return the number of a staff name such as "staff2".

    Args:
        name (str): The staff name.

    Returns:
        index (int): The staff number, or -1 if the name has none.
    """
    try:
        return int(name.replace("staff", ""))
    except ValueError:
        return -1


def _measure_repeats_for_staff(
    fps: List[Fingerprint], existing: Optional[set] = None
) -> List[Tuple[int, int]]:
    """Find where measure-repeat signs fit on one staff, left to right.

    Smaller sizes win, so four identical bars give three 1-bar repeats, and an
    "A B A B" pattern gives one 2-bar repeat. Bars already shown as repeat signs
    (existing) are not suggested again.

    Args:
        fps (List[Fingerprint]): The fingerprint of each measure.
        existing (Optional[set]): Indices of bars already shown as repeat
            signs.

    Returns:
        placements (List[Tuple[int, int]]): The (index, size) of each sign,
            with 0-based indices.
    """
    existing = existing or set()
    placements = []
    i = 1
    while i < len(fps):
        for size in MEASURE_REPEAT_SIZES:
            if i - size < 0 or i + size > len(fps):
                continue
            source = fps[i - size : i]
            if fps[i : i + size] == source and any(
                _has_notes(fp) for fp in source
            ):
                if not set(range(i, i + size)) <= existing:
                    placements.append((i, size))
                i += size
                break
        else:
            i += 1
    return placements


def _merge_runs(
    placements: List[Tuple[int, int]],
) -> List[Tuple[int, int, int]]:
    """Merge back-to-back measure-repeat placements of the same size.

    Args:
        placements (List[Tuple[int, int]]): The (index, size) of each sign.

    Returns:
        runs (List[Tuple[int, int, int]]): The (first index, last index,
            size) of each run of signs.
    """
    runs: List[List[int]] = []
    for index, size in placements:
        if runs and runs[-1][2] == size and runs[-1][1] + 1 == index:
            runs[-1][1] = index + size - 1
        else:
            runs.append([index, index + size - 1, size])
    return [(first, last, size) for first, last, size in runs]


def _best_passage(
    ids: List[int],
    content: List[bool],
    i: int,
    max_passage: int,
    max_ending: int,
) -> Optional[Tuple[int, Dict[str, Any]]]:
    """Find the best repeat structure that starts at a bar.

    A plain repeat (A A ...) saves the bars of every repeat after the first;
    a repeat with endings (A B A C) saves the length of A.

    Args:
        ids (List[int]): An id per bar; bars with the same content on all
            staves have the same id.
        content (List[bool]): Whether each bar holds anything but rests.
        i (int): The index of the bar to start at.
        max_passage (int): The longest passage to consider, in bars.
        max_ending (int): The longest ending to consider, in bars.

    Returns:
        best (Optional[Tuple[int, Dict[str, Any]]]): The bars saved and the
            structure ("kind", "length", and "times" or "ending"), or None if
            no repeat starts there.
    """
    n = len(ids)
    best = None

    # Plain repeat: A A (A A ...). Longest passage first, so ties keep the longer passage.
    for length in range(min(max_passage, (n - i) // 2), 0, -1):
        block = ids[i : i + length]
        if ids[i + length : i + 2 * length] != block or not any(
            content[i : i + length]
        ):
            continue
        times = 2
        while ids[i + times * length : i + (times + 1) * length] == block:
            times += 1
        saved = length * (times - 1)
        if best is None or saved > best[0]:
            best = (saved, {"kind": "repeat", "length": length, "times": times})

    # Repeat with endings: A B A C, with B != C
    for length in range(min(max_passage, (n - i) // 2), 1, -1):
        if best is not None and length <= best[0]:
            break
        block = ids[i : i + length]
        if not any(content[i : i + length]):
            continue
        for ending in range(1, min(max_ending, length) + 1):
            second = i + length + ending
            if second + length + ending > n:
                break
            if ids[second : second + length] != block:
                continue
            if (
                ids[i + length : second]
                == ids[second + length : second + length + ending]
            ):
                continue
            best = (
                length,
                {"kind": "endings", "length": length, "ending": ending},
            )
            break
        if best is not None and best[1]["kind"] == "endings":
            break

    return best


def find_repeats(
    measures: List[Dict[str, Any]],
    staff_names: Optional[List[str]] = None,
    max_passage: int = 32,
    max_ending: int = 4,
) -> Dict[str, Any]:
    """Analyse measures (as returned by getScore) for repeated material.

    Args:
        measures (List[Dict[str, Any]]): The measures from the plugin's
            analysis.
        staff_names (Optional[List[str]]): The staves to compare, e.g.
            ["staff0"]. Defaults to every staff in the measures.
        max_passage (int): The longest repeated passage to look for, in bars.
        max_ending (int): The longest 1st/2nd ending to look for, in bars.

    Returns:
        repeats (Dict[str, Any]): "measure_repeats" (runs of bars that repeat
            the bars before them, per staff) and "passages" (repeats and
            repeats with endings), with 1-based measure numbers and 0-based
            staff indices.
    """
    if staff_names is None:
        names = {name for m in measures for name in (m.get("elements") or {})}
        staff_names = sorted(names, key=_staff_index)
    numbers = [m.get("measure", i + 1) for i, m in enumerate(measures)]

    fps: Dict[str, List[Fingerprint]] = {}
    existing: Dict[str, set] = {}
    for staff in staff_names:
        fps[staff], existing[staff] = staff_fingerprints(measures, staff)

    # Per-staff measure repeats, grouped across staves that share the same run
    grouped: Dict[Tuple[int, int, int], List[int]] = {}
    for staff in staff_names:
        for first, last, size in _merge_runs(
            _measure_repeats_for_staff(fps[staff], existing[staff])
        ):
            grouped.setdefault((first, last, size), []).append(
                _staff_index(staff)
            )
    measure_repeats = [
        {
            "bars": size,
            "from": numbers[first],
            "to": numbers[last],
            "staves": staves,
        }
        for (first, last, size), staves in sorted(grouped.items())
    ]

    # Whole-score passages
    combined = [
        tuple(fps[staff][i] for staff in staff_names)
        for i in range(len(measures))
    ]
    ids_by_bar: Dict[Tuple[Fingerprint, ...], int] = {}
    ids = [ids_by_bar.setdefault(bar, len(ids_by_bar)) for bar in combined]
    content = [any(_has_notes(fp) for fp in bar) for bar in combined]

    passages = []
    i = 0
    while i < len(ids):
        found = _best_passage(ids, content, i, max_passage, max_ending)
        if found is None:
            i += 1
            continue
        saved, shape = found
        length = shape["length"]
        if shape["kind"] == "repeat":
            times = shape["times"]
            passages.append(
                {
                    "type": "repeat",
                    "start": numbers[i],
                    "end": numbers[i + length - 1],
                    "times": times,
                    "duplicate_measures": [
                        numbers[i + length],
                        numbers[i + length * times - 1],
                    ],
                    "saves_measures": saved,
                }
            )
            i += length * times
        else:
            ending = shape["ending"]
            second = i + length + ending
            passages.append(
                {
                    "type": "repeat_with_endings",
                    "start": numbers[i],
                    "end": numbers[i + length - 1],
                    "first_ending": [numbers[i + length], numbers[second - 1]],
                    "second_ending": [
                        numbers[second + length],
                        numbers[second + length + ending - 1],
                    ],
                    "duplicate_measures": [
                        numbers[second],
                        numbers[second + length - 1],
                    ],
                    "saves_measures": saved,
                }
            )
            i = second + length + ending

    return {"measure_repeats": measure_repeats, "passages": passages}
