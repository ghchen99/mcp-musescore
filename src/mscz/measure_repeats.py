"""Write measure-repeat signs into a score's XML the way MuseScore's palette does.

Layout of a group of N repeated measures on one staff (MuseScore 4.x, see
Score::cmdAddMeasureRepeat and the vtest/engraving test scores):
- every measure gets <measureRepeatCount>k</measureRepeatCount>, k = 1..N;
- the sign (<MeasureRepeat><subtype>N</subtype>...) sits in measure 1 for N = 1 or 2 and in
  measure 2 for N = 4; the other measures hold a full-measure rest, which playback needs;
- voices 2-4 are emptied;
- every measure but the last gets a "nobreak" layout break (stored on the first staff) and loses
  its end barline on this staff.
"""

import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Sequence, Tuple

from .score_file import ScoreFile, ScoreFileError

SIGN_POSITION = {1: 0, 2: 0, 4: 1}

# Elements that start the musical content of a voice; anything from the first of them up to the
# last of BODY_END_TAGS is replaced by the sign.
BODY_START_TAGS = {"Chord", "Rest", "MeasureRepeat", "Tuplet", "Beam", "location"}
BODY_END_TAGS = {"Chord", "Rest", "MeasureRepeat", "Tuplet", "endTuplet", "location"}
# Spanners anchored to chords or notes cannot outlive the chords they start or end on.
CHORD_SPANNERS = {"Tie", "Slur", "Glissando", "GuitarBend", "HammerOnPullOff", "PartialTie", "LaissezVib"}
# Measure-level tags that MuseScore writes before the per-staff ones.
MEASURE_HEAD_TAGS = {"eid", "startRepeat", "endRepeat", "irregular", "breakMultiMeasureRest",
                     "stretch", "noOffset", "measureNumberMode"}
# Body tags that are just notation plumbing, not worth reporting when dropped.
SILENT_TAGS = {"Chord", "Rest", "MeasureRepeat", "Tuplet", "endTuplet", "Beam", "location", "Spanner"}


def _crosses_barline(spanner: ET.Element) -> bool:
    for link in ("next", "prev"):
        measures = spanner.findtext(f"{link}/location/measures")
        if measures and measures.strip() not in ("", "0"):
            return True
    return False


def _repeat_count(measure: ET.Element) -> int:
    text = measure.findtext("measureRepeatCount")
    return int(text) if text and text.strip().isdigit() else 0


def _existing_groups(measures: Sequence[ET.Element]) -> List[Tuple[int, int]]:
    """(first index, size) of the measure-repeat groups already on a staff."""
    groups = []
    i = 0
    while i < len(measures):
        if _repeat_count(measures[i]) == 1:
            j = i + 1
            while j < len(measures) and _repeat_count(measures[j]) == j - i + 1:
                j += 1
            groups.append((i, j - i))
            i = j
        else:
            i += 1
    return groups


def measure_lengths(staff: ET.Element, first_staff: ET.Element) -> List[str]:
    """Actual length of each measure as "N/D": the irregular-measure len, else the time signature."""
    lengths = []
    signature = "4/4"
    first_measures = first_staff.findall("Measure")
    for i, measure in enumerate(staff.findall("Measure")):
        timesig = measure.find("voice/TimeSig")
        if timesig is not None and timesig.findtext("sigN") and timesig.findtext("sigD"):
            signature = f"{timesig.findtext('sigN').strip()}/{timesig.findtext('sigD').strip()}"
        length = measure.get("len")
        if not length and i < len(first_measures):
            length = first_measures[i].get("len")
        lengths.append(length or signature)
    return lengths


def _split_voice(voice: ET.Element):
    """(leading, body, trailing) children of a voice; leading/trailing sit at the measure's edges."""
    children = list(voice)
    starts = [i for i, c in enumerate(children) if c.tag in BODY_START_TAGS]
    if not starts:
        return children, [], []
    first = starts[0]
    last = max(i for i, c in enumerate(children) if c.tag in BODY_END_TAGS)
    return children[:first], children[first:last + 1], children[last + 1:]


def _check_measure(measure: ET.Element) -> Tuple[Optional[str], List[str]]:
    """(reason it can't be replaced or None, list of content that replacing would drop)."""
    dropped = []
    voices = measure.findall("voice")
    for v, voice in enumerate(voices):
        leading, body, trailing = _split_voice(voice) if v == 0 else ([], list(voice), [])
        for edge in leading + trailing:
            if edge.tag == "Spanner" and edge.get("type") in CHORD_SPANNERS:
                body.append(edge)
        for element in body:
            for spanner in element.iter("Spanner"):
                if _crosses_barline(spanner):
                    return f"a {spanner.get('type', 'spanner').lower()} crosses its barline", []
            if element.tag not in SILENT_TAGS:
                dropped.append(element.tag)
            if element.tag == "Chord" and element.find("Lyrics") is not None:
                dropped.append("Lyrics")
        if v > 0 and any(e.tag in ("Chord", "Rest") for e in body):
            dropped.append(f"voice {v + 1}")
    return None, sorted(set(dropped))


def _sign_or_rest(size: int, holds_sign: bool, length: str) -> ET.Element:
    element = ET.Element("MeasureRepeat" if holds_sign else "Rest")
    if holds_sign:
        ET.SubElement(element, "subtype").text = str(size)
    ET.SubElement(element, "durationType").text = "measure"
    ET.SubElement(element, "duration").text = length
    return element


def _set_repeat_count(measure: ET.Element, count: int) -> None:
    for old in measure.findall("measureRepeatCount"):
        measure.remove(old)
    position = 0
    for i, child in enumerate(measure):
        if child.tag in MEASURE_HEAD_TAGS:
            position = i + 1
        else:
            break
    tag = ET.Element("measureRepeatCount")
    tag.text = str(count)
    measure.insert(position, tag)


def _add_nobreak(first_staff_measure: ET.Element) -> bool:
    """Add a nobreak layout break unless the measure already has a layout break; True if added."""
    if first_staff_measure.find("LayoutBreak") is not None:
        return False
    voices = [i for i, c in enumerate(first_staff_measure) if c.tag == "voice"]
    position = voices[0] if voices else len(first_staff_measure)
    brk = ET.Element("LayoutBreak")
    ET.SubElement(brk, "subtype").text = "nobreak"
    first_staff_measure.insert(position, brk)
    return True


def _rewrite_measure(measure: ET.Element, count: int, size: int, holds_sign: bool,
                     length: str, keep_barline: bool) -> None:
    voices = measure.findall("voice")
    if not voices:
        voices = [ET.SubElement(measure, "voice")]
    for extra in voices[1:]:
        measure.remove(extra)

    voice = voices[0]
    leading, _, trailing = _split_voice(voice)
    leading = [e for e in leading if not (e.tag == "Spanner" and e.get("type") in CHORD_SPANNERS)]
    trailing = [
        e for e in trailing
        if not (e.tag == "Spanner" and e.get("type") in CHORD_SPANNERS)
        and (keep_barline or e.tag != "BarLine")
    ]
    for child in list(voice):
        voice.remove(child)
    for child in leading + [_sign_or_rest(size, holds_sign, length)] + trailing:
        voice.append(child)
    _set_repeat_count(measure, count)


def apply_measure_repeats(score: ScoreFile, staff_index: int, groups: Sequence[Tuple[int, int]]) -> Dict:
    """Turn measures into measure-repeat signs on one staff.

    groups: (first measure, size) pairs, 1-based measures and size 1, 2 or 4. A group repeats the
    `size` measures before it. Groups that cannot be applied safely are skipped and reported.
    """
    staves = score.staves()
    if not 0 <= staff_index < len(staves):
        raise ScoreFileError(f"Staff {staff_index} does not exist (score has {len(staves)} staves)")
    staff = staves[staff_index]
    first_measures = staves[0].findall("Measure")
    measures = staff.findall("Measure")
    lengths = measure_lengths(staff, staves[0])
    existing = _existing_groups(measures)

    report = {"applied": [], "unchanged": [], "skipped": [], "dropped": [], "kept_layout_breaks": []}

    # First pass: basic validity. Existing groups only count as replaced when the valid requests
    # together cover them completely.
    valid = []
    claimed = set()
    for start, size in sorted(groups):
        entry = {"start": start, "end": start + size - 1, "bars": size}
        first = start - 1
        indices = list(range(first, first + size))
        reason = None
        if size not in SIGN_POSITION:
            reason = "size must be 1, 2 or 4 bars"
        elif first - size < 0:
            reason = f"needs {size} bar(s) before it to repeat"
        elif indices[-1] >= len(measures):
            reason = f"the staff has only {len(measures)} measures"
        elif claimed.intersection(indices):
            reason = "overlaps another requested group"
        if reason:
            report["skipped"].append({**entry, "reason": reason})
            continue
        claimed.update(indices)
        valid.append((entry, first, size, indices))

    for entry, first, size, indices in valid:
        overlapping = [g for g in existing if set(range(g[0], g[0] + g[1])) & set(indices)]
        if overlapping == [(first, size)]:
            report["unchanged"].append(entry)
            continue
        partial = [g for g in overlapping if not set(range(g[0], g[0] + g[1])) <= claimed]
        if partial:
            g_first, g_size = partial[0]
            reason = f"overlaps an existing {g_size}-bar repeat at bars {g_first + 1}-{g_first + g_size}"
            report["skipped"].append({**entry, "reason": reason})
            continue

        problems = []
        dropped = {}
        for i in indices:
            problem, lost = _check_measure(measures[i])
            if problem:
                problems.append(f"bar {i + 1}: {problem}")
            if lost:
                dropped[i + 1] = lost
        if problems:
            report["skipped"].append({**entry, "reason": "; ".join(problems)})
            continue

        for k, i in enumerate(indices):
            _rewrite_measure(
                measures[i], count=k + 1, size=size, holds_sign=(k == SIGN_POSITION[size]),
                length=lengths[i], keep_barline=(k == size - 1),
            )
            if k < size - 1 and i < len(first_measures) and not _add_nobreak(first_measures[i]):
                report["kept_layout_breaks"].append(i + 1)
        report["applied"].append(entry)
        report["dropped"].extend({"measure": m, "items": items} for m, items in dropped.items())

    return report
