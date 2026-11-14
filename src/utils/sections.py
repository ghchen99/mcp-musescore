"""Split a staff (typically drums) into groove sections for a chart-style layout.

A section starts with a groove bar. The bars after it are exact copies of the groove,
near copies (similar enough, e.g. one extra kick), or fills (bars that break the pattern).
A section ends where a new groove starts or after a fill that is not followed by the groove.

Within a section, `runs` are the stretches that can be collapsed: a phrase of 1, 2 or 4 bars repeated
back to back, where the copies are identical except for ghost notes and crashes on beat 1 (the core
fingerprint). Kicks, snares, open hats and articulations must match, so a groove whose open hat comes
every second bar is a 2-bar phrase, not a 1-bar groove with dropped differences.

Near copies are never proposed for replacement on their own: replacing them with a repeat
sign would delete their differences, so they are reported for the user to approve.
"""

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .repetition import (
    BEAT_ONE_CYMBALS,
    Fingerprint,
    core_fingerprint,
    staff_fingerprints,
)

PHRASE_LENGTHS = (1, 2, 4)

TICKS_PER_BEAT = 480

# General MIDI percussion names for the common kit pieces
DRUM_NAMES = {
    35: "kick", 36: "kick", 37: "side stick", 38: "snare", 39: "clap", 40: "snare",
    41: "low tom", 42: "closed hi-hat", 43: "low tom", 44: "pedal hi-hat", 45: "mid tom",
    46: "open hi-hat", 47: "mid tom", 48: "high tom", 49: "crash", 50: "high tom",
    51: "ride", 52: "china", 53: "ride bell", 54: "tambourine", 55: "splash", 56: "cowbell",
    57: "crash 2", 59: "ride 2",
}

Event = Tuple[int, int]

CRASH_PITCHES = {49, 57}  # crash cymbal 1 and 2


def bar_events(fingerprint: Fingerprint) -> Set[Event]:
    """(tick within the bar, pitch) for every note in a bar."""
    return {(item[0], pitch) for item in fingerprint if item[2] == "Chord" for pitch in item[4]}


def similarity(a: Set[Event], b: Set[Event]) -> float:
    """How alike two sets of hits are, from 0 to 1 (shared hits out of all hits)."""
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def describe(events: Set[Event]) -> List[str]:
    """Readable hits, e.g. "kick on beat 2.5"."""
    out = []
    for tick, pitch in sorted(events):
        beat = tick / TICKS_PER_BEAT + 1
        beat_text = f"{beat:g}"
        out.append(f"{DRUM_NAMES.get(pitch, f'pitch {pitch}')} on beat {beat_text}")
    return out


def _runs(numbers: List[int]) -> List[Tuple[int, int]]:
    runs: List[List[int]] = []
    for n in numbers:
        if runs and runs[-1][1] + 1 == n:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    return [(first, last) for first, last in runs]


def crash_pattern(has_crash: List[bool]) -> Dict[str, Any]:
    """Classify crashes on beat 1 over a groove run (index 0 = the groove bar).

    pattern: "none", "every_bar", "first_only", "every_n" (equispaced: every `every` bars, from
    run bar `from_bar`, 1-based) or "irregular" (with the run bars that have one).
    """
    hits = [i for i, crash in enumerate(has_crash) if crash]
    if not hits:
        return {"pattern": "none"}
    if len(hits) == len(has_crash):
        return {"pattern": "every_bar"}
    if hits == [0]:
        return {"pattern": "first_only"}
    if len(hits) >= 2:
        step = hits[1] - hits[0]
        if hits == list(range(hits[0], len(has_crash), step)):
            return {"pattern": "every_n", "every": step, "from_bar": hits[0] + 1}
    if len(hits) == 1:
        return {"pattern": "irregular", "run_bars": [hits[0] + 1],
                "description": f"crash on {_ordinal(hits[0] + 1)} time only"}
    return {"pattern": "irregular", "run_bars": [i + 1 for i in hits],
            "description": "crash on times " + ", ".join(str(i + 1) for i in hits)}


def crash_legend(pattern: Dict[str, Any], unit: str = "bar") -> Optional[Tuple[str, str]]:
    """(mark, legend text) for a crash pattern in a collapsed groove, or None if no mark is needed.

    unit: "bar" for a 1-bar groove, "time" for a longer phrase (crash every other time through it).
    """
    if pattern["pattern"] == "first_only":
        return "*", "crash on 1st time only"
    if pattern["pattern"] == "every_n":
        plural = "bars" if unit == "bar" else "times"
        every = f"every other {unit}" if pattern["every"] == 2 else f"every {pattern['every']} {plural}"
        if pattern["from_bar"] > 1:
            every += f", from the {_ordinal(pattern['from_bar'])} time"
        return "**", f"crash {every}"
    return None


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _crash_on_one(events: Set[Event]) -> bool:
    return any(tick == 0 and pitch in CRASH_PITCHES for tick, pitch in events)


def plan_runs(core: List[Fingerprint], start: int, end: int,
              phrase_starts: Iterable[int] = ()) -> List[Tuple[int, int, int]]:
    """(first bar index, phrase length, times) of the runs that leave the fewest bars on the page.

    A run is a phrase of 1, 2 or 4 bars repeated back to back (same core fingerprint); it takes the
    space of one phrase. A 2- or 4-bar run must start on the phrase grid: a whole number of phrases after
    the latest of `phrase_starts` (and `start`), so a chart reads 4 + 2 bars rather than 1 + 2x2 + 1.
    Among plans with as few bars, the one with fewer runs (repeat signs) wins, then the one whose runs start
    earlier (a section's first bar rather than the bar after it).
    """
    grid = sorted({start, *(b for b in phrase_starts if start <= b <= end)})

    def aligned(i: int, length: int) -> bool:
        origin = max(g for g in grid if g <= i)
        return (i - origin) % length == 0

    best: Dict[int, Tuple[int, int, List]] = {end + 1: (0, 0, [])}
    for i in range(end, start - 1, -1):
        bars, runs, plan = best[i + 1]
        choice = (bars + 1, runs, plan)
        written_out = True
        for length in PHRASE_LENGTHS:
            if not aligned(i, length):
                continue
            unit = core[i:i + length]
            times = 1
            while i + (times + 1) * length - 1 <= end and core[i + times * length:i + (times + 1) * length] == unit:
                times += 1
                after_bars, after_runs, after_plan = best[i + times * length]
                option = (length + after_bars, after_runs + 1, [(i, length, times)] + after_plan)
                if option[:2] < choice[:2] or (option[:2] == choice[:2] and written_out):
                    choice = option
                    written_out = False
        best[i] = choice
    return best[start][2]


def phrase_runs(core: List[Fingerprint], events: List[Set[Event]], numbers: List[int],
                start: int, end: int, phrase_starts: Iterable[int] = ()) -> List[Dict[str, Any]]:
    """The runs of `plan_runs` between bar indices start..end, with crash marks and dropped hits."""
    runs = []
    for i, length, times in plan_runs(core, start, end, phrase_starts):
        crashes = crash_pattern([_crash_on_one(events[i + r * length]) for r in range(times)])
        legend = crash_legend(crashes, "bar" if length == 1 else "time")
        if legend:
            crashes["mark"], crashes["legend"] = legend
        dropped = []
        for b in range(i + length, i + times * length):
            ref = i + (b - i) % length
            extra = {e for e in events[b] - events[ref] if not (e[0] == 0 and e[1] in BEAT_ONE_CYMBALS)}
            missing = {e for e in events[ref] - events[b] if not (e[0] == 0 and e[1] in BEAT_ONE_CYMBALS)}
            if extra or missing:
                dropped.append({"bar": numbers[b], "extra": describe(extra), "missing": describe(missing)})
        runs.append({
            "start": numbers[i],
            "end": numbers[i + times * length - 1],
            "phrase_bars": length,
            "play_count": times,
            "keep": [numbers[i], numbers[i + length - 1]],
            "crash_on_1": crashes,
            "dropped": dropped,
        })
    return runs


def find_sections(measures: Sequence[Dict[str, Any]], staff: str, tolerance: float = 0.85) -> List[Dict[str, Any]]:
    """Groove sections of one staff, with 1-based measure numbers."""
    fps, existing = staff_fingerprints(measures, staff)
    core, _ = staff_fingerprints(measures, staff, core_fingerprint)
    numbers = [m.get("measure", i + 1) for i, m in enumerate(measures)]
    events = [bar_events(fp) for fp in fps]
    n = len(fps)

    def kind(j: int, groove: int) -> str:
        if fps[j] == fps[groove]:
            return "exact"
        if events[j] and similarity(events[j], events[groove]) >= tolerance:
            return "near"
        return "other"

    # First the sections and their fills, which set the phrase grid of the runs
    spans = []
    i = 0
    while i < n:
        groove = i
        exact, near, fills = [], [], []
        j = i + 1
        next_start = n
        while j < n:
            k = kind(j, groove)
            if k == "exact":
                exact.append(j)
            elif k == "near":
                near.append(j)
            elif j + 1 < n and kind(j + 1, groove) != "other":
                fills.append(j)  # fill inside the section, the groove comes back
            elif j + 1 < n and (fps[j + 1] == fps[j] or similarity(events[j + 1], events[j]) >= tolerance):
                next_start = j  # bar j starts a new groove
                break
            else:
                fills.append(j)  # fill that ends the section
                next_start = j + 1
                break
            j += 1
        spans.append((groove, min(next_start, n) - 1, exact, near, fills))
        i = next_start

    # Phrases start with a section, after a fill and on a crash on beat 1. Runs are planned over the whole
    # staff (fewest bars on the page), then listed under the section they start in
    phrase_starts = {groove for groove, *_ in spans}
    phrase_starts |= {f + 1 for *_, fills in spans for f in fills}
    phrase_starts |= {b for b in range(n) if _crash_on_one(events[b])}
    all_runs = phrase_runs(core, events, numbers, 0, n - 1, phrase_starts) if n else []
    in_runs = {b for run in all_runs for b in range(run["start"], run["end"] + 1)}

    sections = []
    for groove, end, exact, near, fills in spans:
        # 1-bar repeat signs repeat the previous bar, so a bar qualifies only if it equals the bar before it
        signs = [b for b in exact if fps[b] == fps[b - 1] and b not in existing]

        section = {
            "start": numbers[groove],
            "end": numbers[end],
            "groove_bar": numbers[groove],
            "exact": [numbers[b] for b in exact],
            "near": [
                {
                    "bar": numbers[b],
                    "similarity": round(similarity(events[b], events[groove]), 2),
                    "extra": describe(events[b] - events[groove]),
                    "missing": describe(events[groove] - events[b]),
                }
                for b in near
            ],
            "fills": [numbers[b] for b in fills],
            "already_repeat_signs": [numbers[b] for b in sorted(existing) if groove < b <= end],
            "proposed_repeat_signs": [
                {"start": numbers[a], "end": numbers[b], "bars": 1} for a, b in _runs(signs)
            ],
        }
        section["runs"] = [run for run in all_runs if numbers[groove] <= run["start"] <= numbers[end]]
        section["fills"] = [b for b in section["fills"] if b not in in_runs]  # e.g. open-hat bars of a phrase
        sections.append(section)
    return sections


def played_times(measures: Sequence[Dict[str, Any]]) -> List[int]:
    """How many times each bar is played: repeat barlines with their play counts (voltas are not read)."""
    times = [1] * len(measures)
    start = 0
    for j, m in enumerate(measures):
        if m.get("repeatStart"):
            start = j
        if m.get("repeatEnd"):
            for k in range(start, j + 1):
                times[k] = int(m["repeatEnd"])
            start = j + 1
    return times


LEAD_IN_MIN = 2  # a single bar before the groove is part of the count ("2x4+2", not "1+2x4+1")


def _fours(n: int) -> str:
    k, r = divmod(n, 4)
    parts = ([f"{k}x4" if k > 1 else "4"] if k else []) + ([str(r)] if r else [])
    return "+".join(parts) or "0"


def count_label(bars: int, lead_in: int = 0, groups: Sequence[int] = ()) -> str:
    """A section's length the way drummers count it, in fours: 6 -> "4+2", 12 -> "3x4", 10 -> "2x4+2".

    A lead-in of LEAD_IN_MIN bars or more before the first groove bar (e.g. a rest bar and a pickup fill) is
    counted on its own: 8 with a 2-bar lead-in -> "2+4+2". `groups` are the sizes of the runs of equally long
    bars after the lead-in: a run in another time signature is counted on its own, e.g. 4 bars of 4/4, 2 of 3/4
    and 2 of 4/4 -> "4+2+2".
    """
    parts = []
    rest = bars
    if LEAD_IN_MIN <= lead_in < bars:
        parts.append(_fours(lead_in))
        rest -= lead_in
    sizes = [g for g in groups if g] if groups and sum(groups) == rest else [rest]
    parts += [_fours(n) for n in sizes]
    return "+".join(parts)


COUNT_IN_LABEL = re.compile(r"\s*\((\d[\dx+ ]*)\)\s*$")


def without_count(label: str) -> str:
    """A section label without a bar count in parentheses at its end: "Chorus 1 (2x4)" -> "Chorus 1"."""
    return COUNT_IN_LABEL.sub("", label).strip()


def count_in_label(label: str) -> Optional[str]:
    """The bar count written in a section label: "Chorus 1 (2x4)" -> "2x4"."""
    found = COUNT_IN_LABEL.search(label)
    return found.group(1).replace(" ", "") if found else None


def count_bars(label: object) -> Optional[int]:
    """Bars in a count label ("2x4+2" -> 10) or a plain number; None if it is neither."""
    if isinstance(label, int):
        return label
    total = 0
    for term in str(label).replace(" ", "").split("+"):
        factors = term.split("x")
        if not term or not all(f.isdigit() for f in factors):
            return None
        product = 1
        for f in factors:
            product *= int(f)
        total += product
    return total


def _drums(events: Set[Event]) -> List[str]:
    names = []
    for pitch in sorted({p for _, p in events if p >= 0}):
        name = DRUM_NAMES.get(pitch, f"pitch {pitch}")
        if name not in names:
            names.append(name)
    return names


# For naming grooves, a hi-hat is a hi-hat (closed, pedal, open) and a crash a crash: an open hat at the end of
# a bar or a crash on top is a variation of the groove, not another groove
SAME_SOUND = {44: 42, 46: 42, 57: 49, 55: 49, 52: 49, 53: 51, 59: 51}
GROOVE_MIN_HITS = 4  # onsets: a pickup or a single hit is never a groove


def song_structure(measures: Sequence[Dict[str, Any]], staff: str, tolerance: float = 0.8) -> Dict[str, Any]:
    """Sections (from rehearsal marks) with the bars they last as played, their grooves and their fills.

    Grooves are bars with at least GROOVE_MIN_HITS onsets whose hits, within `tolerance`, are played at least
    twice in a row (ghost notes, the cymbal on beat 1 and hi-hat openings aside); they are named Groove A, B...
    in order of appearance. Other bars with notes are fills (or one-off hits); empty bars are counted as rests.
    Bars excluded from the bar count (`irregular`, e.g. a count-in bar) are left out of the lengths. `count`
    is the section's length in fours: the count already written in its label ("Chorus 1 (4+2+2)", the user's
    phrasing) when it adds up to the bars played, else count_label's (lead-in, runs of other bar lengths).
    """
    core, _ = staff_fingerprints(measures, staff, core_fingerprint)
    events = [bar_events(fp) for fp in core]
    sounds = [{(tick, SAME_SOUND.get(pitch, pitch)) for tick, pitch in e} for e in events]
    numbers = [m.get("number", m.get("measure", i + 1)) for i, m in enumerate(measures)]
    times = played_times(measures)
    counted = [0 if m.get("irregular") else times[i] for i, m in enumerate(measures)]
    n = len(measures)

    clusters: List[List[int]] = []
    cluster_of: List[Optional[int]] = [None] * n
    for i in range(n):
        if len({tick for tick, _ in events[i]}) < GROOVE_MIN_HITS:
            continue
        for c, members in enumerate(clusters):
            if similarity(sounds[i], sounds[members[0]]) >= tolerance:
                members.append(i)
                cluster_of[i] = c
                break
        else:
            cluster_of[i] = len(clusters)
            clusters.append([i])
    # A groove is played at least twice in a row (consecutive bars or a repeat); a fill that comes back
    # later in the song is still a fill
    names: Dict[int, str] = {}
    for c, members in enumerate(clusters):
        if any(times[i] >= 2 or (i + 1 < n and cluster_of[i + 1] == c) for i in members):
            names[c] = f"Groove {chr(ord('A') + len(names))}" if len(names) < 26 else f"Groove {len(names) + 1}"

    marks = []
    for i, m in enumerate(measures):
        for marking in m.get("markings") or []:
            if marking.get("name") == "RehearsalMark" and marking.get("text"):
                marks.append((i, without_count(marking["text"]), count_in_label(marking["text"])))
                break
    if not marks or marks[0][0] > 0:
        marks.insert(0, (0, "Start", None))

    sections = []
    for k, (first, name, written) in enumerate(marks):
        last = (marks[k + 1][0] if k + 1 < len(marks) else n) - 1
        grooves: Dict[str, int] = {}
        fills, rests, not_counted = [], 0, []
        first_groove = None
        for i in range(first, last + 1):
            if not counted[i]:
                not_counted.append(i + 1)
                continue
            cluster = cluster_of[i]
            if not events[i]:
                rests += counted[i]
            elif cluster is not None and cluster in names:
                grooves[names[cluster]] = grooves.get(names[cluster], 0) + counted[i]
                if first_groove is None:
                    first_groove = i
            else:
                fills.append({"bar": numbers[i], "drums": _drums(events[i])})
        played = sum(counted[first:last + 1])
        lead_in = sum(counted[first:first_groove]) if first_groove is not None else 0
        lengths = [measures[i].get("durationTicks", 0) for i in range(first, last + 1) for _ in range(counted[i])]
        skip = lead_in if LEAD_IN_MIN <= lead_in < played else 0
        groups: List[int] = []
        for j, length in enumerate(lengths[skip:]):
            if j and length == lengths[skip + j - 1]:
                groups[-1] += 1
            else:
                groups.append(1)
        computed = count_label(played, lead_in, groups)
        section = {
            "section": name,
            "first_bar": first + 1,
            "last_bar": last + 1,
            "bars_played": played,
            "count": computed,
            "lead_in_bars": lead_in,
            "bars_on_page": last - first + 1,
            "grooves": [{"name": g, "bars_played": b} for g, b in grooves.items()],
            "fills": fills,
            "rest_bars": rests,
        }
        if not_counted:
            section["not_counted"] = not_counted  # positions of bars left out of the count
        if written and count_bars(written) == played:
            section["count"], section["count_source"] = written, "label"
            if written != computed:
                section["computed_count"] = computed
        elif written:
            section["label_count_outdated"] = written  # the label's count no longer adds up
        sections.append(section)
    legend = [{"name": names[c], "first_bar": numbers[clusters[c][0]], "drums": _drums(events[clusters[c][0]]),
               "bars_played": sum(times[i] for i in clusters[c])} for c in sorted(names)]
    return {"sections": sections, "grooves": legend, "total_bars_played": sum(counted)}
