"""Keep only some instruments of a score, editing the file.

MuseScore can remove instruments itself (Score.removeParts, 4.7+), but only in an open score, and a
score with a damaged bar in another instrument (e.g. a Guitar Pro import with an incomplete measure)
cannot be opened by a plugin at all. Removing the other parts in the file first avoids both problems.

Things that belong to the whole system are stored on the first staff only: frames (title frame),
measure-level settings (repeat barlines, layout breaks, jumps, markers, bar numbering) and system
texts (tempo, rehearsal marks, system text, voltas). When the first staff is removed, they move to
the first staff that is kept.
"""

import copy
import os
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from .measure_repeats import measure_lengths
from .rolls import element_ticks, fraction_ticks
from .score_file import ScoreFile, ScoreFileError

FRAMES = {"VBox", "TBox", "HBox", "FBox"}
# Measure children that describe one staff, not the whole system
PER_STAFF_MEASURE_TAGS = {
    "voice",
    "measureRepeatCount",
    "vspacerUp",
    "vspacerDown",
    "vspacerFixed",
    "visible",
    "slashStyle",
    "stemless",
    "StaffTypeChange",
    "MeasureNumber",
    "MMRestRange",
}
SYSTEM_TEXTS = {
    "Tempo",
    "RehearsalMark",
    "SystemText",
    "Jump",
    "Marker",
    "TempoChangeRanged",
    "GradualTempoChange",
}
SYSTEM_SPANNERS = {"Volta", "TempoChangeRanged", "GradualTempoChange"}


def _part_staves(score: ScoreFile) -> List[Tuple[ET.Element, List[int]]]:
    """Each <Part> with the body staff indices it owns (its <Staff> children are positional)."""
    out, index = [], 0
    for part in score.score.findall("Part"):
        count = max(len(part.findall("Staff")), 1)
        out.append((part, list(range(index, index + count))))
        index += count
    return out


def _is_system(element: ET.Element) -> bool:
    if element.tag == "Spanner":
        return element.get("type") in SYSTEM_SPANNERS
    return element.tag in SYSTEM_TEXTS


def _voice_positions(
    voice: ET.Element, measure_len: int
) -> List[Tuple[int, int]]:
    """(child index, tick) for every child of a voice; tuplets scale the durations inside them."""
    positions, tick, scale = [], 0, []
    for i, child in enumerate(voice):
        positions.append((i, tick))
        if child.tag == "Tuplet":
            normal = int(child.findtext("normalNotes") or 1)
            actual = int(child.findtext("actualNotes") or 1)
            scale.append((normal, actual))
        elif child.tag == "endTuplet":
            if scale:
                scale.pop()
        elif child.tag == "location":
            fractions = child.findtext("fractions")
            if fractions:
                tick += fraction_ticks(fractions)
        elif child.tag in ("Chord", "Rest", "MeasureRepeat"):
            ticks = element_ticks(child, measure_len)
            for normal, actual in scale:
                ticks = ticks * normal // actual
            tick += ticks
    return positions


def _insert_at_tick(
    voice: ET.Element, element: ET.Element, tick: int, measure_len: int
) -> bool:
    """Insert `element` before the first chord/rest starting at `tick`; False if no chord/rest starts there."""
    for index, position in _voice_positions(voice, measure_len):
        child = voice[index]
        if position == tick and child.tag in (
            "Chord",
            "Rest",
            "MeasureRepeat",
            "Tuplet",
        ):
            voice.insert(index, element)
            return True
        if position > tick:
            break
    return False


def _merge_measure(
    system_measure: ET.Element,
    kept_measure: ET.Element,
    measure_len: int,
    number: int,
    report: Dict,
) -> ET.Element:
    """The kept staff's measure, with the system-level content of the old first staff's measure."""
    merged = copy.deepcopy(kept_measure)
    for key, value in system_measure.attrib.items():
        merged.attrib.setdefault(key, value)
    system_tags = [
        copy.deepcopy(c)
        for c in system_measure
        if c.tag not in PER_STAFF_MEASURE_TAGS
    ]
    for position, child in enumerate(system_tags):
        merged.insert(position, child)

    source_voice = system_measure.find("voice")
    target_voice = merged.find("voice")
    if source_voice is None:
        return merged
    if target_voice is None:
        target_voice = ET.SubElement(merged, "voice")
    for index, tick in _voice_positions(source_voice, measure_len):
        child = source_voice[index]
        if not _is_system(child):
            continue
        moved = copy.deepcopy(child)
        if not _insert_at_tick(target_voice, moved, tick, measure_len):
            # No note starts there on the kept staff: put it on the nearest earlier note
            positions = [
                (i, t)
                for i, t in _voice_positions(target_voice, measure_len)
                if target_voice[i].tag in ("Chord", "Rest", "MeasureRepeat")
                and t <= tick
            ]
            target_voice.insert(positions[-1][0] if positions else 0, moved)
            report["moved_earlier"].append(
                {"measure": number, "element": child.tag}
            )
        report["system_texts"] += 1
    return merged


def keep_parts(score: ScoreFile, keep_staves: Sequence[int]) -> Dict:
    """Remove every part that has none of `keep_staves` (0-based body staff indices). Returns a report."""
    parts = _part_staves(score)
    staves = score.staves()
    keep = set(keep_staves)
    if not keep or not keep <= set(range(len(staves))):
        raise ScoreFileError(
            f"Staves {sorted(keep_staves)} do not all exist (score has {len(staves)})"
        )
    kept_parts = [(part, owned) for part, owned in parts if keep & set(owned)]
    kept_indices = sorted(
        i for _, owned in kept_parts for i in owned if i < len(staves)
    )
    report = {
        "kept_parts": [p.findtext("trackName") or "" for p, _ in kept_parts],
        "removed_parts": len(parts) - len(kept_parts),
        "staves": len(kept_indices),
        "system_texts": 0,
        "moved_earlier": [],
        "dropped": [],
    }

    first_old = staves[0]
    new_staves = []
    if kept_indices[0] == 0:
        new_staves = [staves[i] for i in kept_indices]
    else:
        # Rebuild the first kept staff on the old first staff's frame/measure sequence
        lengths = [
            fraction_ticks(length)
            for length in measure_lengths(first_old, first_old)
        ]
        kept_first = staves[kept_indices[0]].findall("Measure")
        first = ET.Element("Staff")
        number = 0
        for child in first_old:
            if child.tag == "Measure":
                if number >= len(kept_first):
                    raise ScoreFileError(
                        "The kept staff has fewer measures than the first staff"
                    )
                first.append(
                    _merge_measure(
                        child,
                        kept_first[number],
                        lengths[number],
                        number + 1,
                        report,
                    )
                )
                number += 1
            else:
                first.append(
                    child
                )  # frames (title frame...) live on the first staff only
        new_staves = [first] + [staves[i] for i in kept_indices[1:]]

    body = score.score
    for staff in staves:
        body.remove(staff)
    for part, _ in parts:
        if not any(part is p for p, _ in kept_parts):
            body.remove(part)
    for number, staff in enumerate(new_staves, 1):
        staff.set("id", str(number))
        body.append(staff)
    number = 1
    for part, _ in kept_parts:
        for staff_def in part.findall("Staff"):
            if staff_def.get("id") is not None:
                staff_def.set("id", str(number))
            number += 1

    # Settings that refer to the removed instruments: MuseScore rebuilds sensible defaults without them
    for tag in ("SystemObjects", "Order"):
        for element in body.findall(tag):
            body.remove(element)
            report["dropped"].append(tag)
    if score.drop_entries("Excerpts/"):
        report["dropped"].append("part scores (Excerpts)")
    return report


def part_name(path: Path, entry: str) -> str:
    """The name of a part stored in a score file (its Score <name>)."""
    with zipfile.ZipFile(path) as z:
        name = ET.fromstring(z.read(entry)).findtext("Score/name")
    return name or Path(entry).stem


def detach_part(path: Path, entry: str, target: Path) -> Path:
    """Write the part `entry` (Excerpts/...mscx) of the score file `path` as a score file of its own.

    A part is stored as a complete score whose elements point at the full score's (<linkedTo>); without
    those links MuseScore opens it as an ordinary score with just the part's staves.
    """
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        data = z.read(entry).decode("utf-8")
        folder = entry.rsplit("/", 1)[0] + "/"
        style = next(
            (n for n in names if n.startswith(folder) and n.endswith(".mss")),
            None,
        )
        style = style or next(
            (n for n in names if n.endswith(".mss") and "/" not in n), None
        )
        style_data = z.read(style) if style else None
    data = re.sub(r"\s*<linkedTo>[^<]*</linkedTo>", "", data)
    main = f"{target.stem}.mscx"
    rootfiles = f'<rootfile full-path="{main}"/>'
    container = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<container><rootfiles>'
        + rootfiles
        + "</rootfiles></container>\n"
    )

    fd, tmp = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    os.close(fd)
    umask = os.umask(0)
    os.umask(umask)
    os.chmod(tmp, 0o666 & ~umask)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
            out.writestr("META-INF/container.xml", container)
            out.writestr(main, data)
            if style_data is not None:
                out.writestr("score_style.mss", style_data)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return target
