"""The passage grammar — parse, serialise, validate.

Shared by ``read_passage`` (serialise score into a passage string) and
``write_passage`` (parse a passage string and validate it before anything is
written).

The parser lives here, in Python, rather than in the QML plugin. Parsing is the
failure-prone half — durations, tuplets, ties, boundary ticks — and this side is
testable without MuseScore in the loop. The plugin keeps only the serialiser,
because that is where the score data already is.

Grammar (SPEC.md §1)::

    passage        := element (WS element)*
    element        := rest | chord | tuplet-group
    rest           := "r" "/" duration
    chord          := pitch ("+" pitch)* "/" duration
    pitch          := pitchclass accidental? octave "~"?
    pitchclass     := "C" | "D" | "E" | "F" | "G" | "A" | "B"
    accidental     := "#" | "##" | "b" | "bb" | "n" | ""
    octave         := "-1" … "9"
    duration       := symbol dots? | ticks
    symbol         := "w" | "h" | "q" | "e" | "s" | "t" | "x"
    dots           := "." | ".."
    ticks          := digit+
    tuplet-group   := "[" WS? element (WS element)* WS? "]" digit+ ":" digit+

Two properties the rest of the system leans on:

* **A bare number is always raw ticks.** Note values are letters, never digits,
  so ``8`` cannot mean both "eighth note" and "8 ticks". That ambiguity would be
  silent — the parser would accept it and write the wrong duration.
* **Ticks are sounding ticks.** For a tuplet group the written values are
  scaled by the ratio, so ``[q q q]3:2`` occupies 960 ticks, not 1440.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

DIVISION = 480
WHOLE = 4 * DIVISION  # 1920

#: Note-value symbols, in ticks. Deliberately letters: see module docstring.
SYMBOLS = {"w": 1920, "h": 960, "q": 480, "e": 240, "s": 120, "t": 60, "x": 30}

DOTS = {"": 1, ".": 3 / 2, "..": 7 / 4}

_PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

_ACCIDENTAL_OFFSET = {"": 0, "n": 0, "#": 1, "##": 2, "b": -1, "bb": -2}

#: Index is the MuseScore Tonal Pitch Class. Index 14 is C natural; each step is
#: a fifth upwards. Copied from the plugin's own table so both sides agree.
TPC_NAMES = [
    "Cbb", "Gbb", "Dbb", "Abb", "Ebb", "Bbb", "Fb",
    "Cb",  "Gb",  "Db",  "Ab",  "Eb",  "Bb",  "F",
    "C",   "G",   "D",   "A",   "E",   "B",   "F#",
    "C#",  "G#",  "D#",  "A#",  "E#",  "B#",  "F##",
    "C##", "G##", "D##", "A##", "E##", "B##", "F###",
]

_NAME_TO_TPC = {name: tpc for tpc, name in enumerate(TPC_NAMES)}
_NAME_TO_TPC["Fbb"] = -1  # the plugin special-cases -1 outside the table

MAX_TICKS = 10 ** 9  # a sanity ceiling, far beyond any legal span


class PassageError(ValueError):
    """A passage could not be parsed or is not legal to write.

    ``position`` is a character offset into the input, so an error can point at
    the offending token rather than describing the whole string.
    """

    def __init__(self, message: str, position: Optional[int] = None, text: str = ""):
        self.position = position
        self.text = text
        if position is not None and text:
            caret = " " * position + "^"
            message = f"{message}\n  {text}\n  {caret}"
        super().__init__(message)


@dataclass
class Pitch:
    name: str  # "Eb"
    octave: int  # 2
    midi: int  # 39
    tpc: int  # 11
    tie: bool = False

    def render(self) -> str:
        return f"{self.name}{self.octave}{'~' if self.tie else ''}"


@dataclass
class Element:
    """One chord, rest, or nested element inside a tuplet group.

    ``ticks`` is the **sounding** duration. For an element inside a tuplet that
    is the written value scaled by the ratio; ``written_ticks`` keeps the
    notated value, which is what MuseScore's ``setDuration`` needs.
    """

    pitches: List[Pitch] = field(default_factory=list)
    ticks: int = 0
    written_ticks: int = 0
    symbol: Optional[str] = None  # None when written as raw ticks
    is_rest: bool = False

    def render(self) -> str:
        if self.is_rest:
            body = "r"
        else:
            body = "+".join(p.render() for p in self.pitches)
        return f"{body}/{_render_duration(self.symbol, self.written_ticks)}"


@dataclass
class Tuplet:
    elements: List[Element]
    numerator: int
    denominator: int

    @property
    def written_ticks(self) -> int:
        return sum(e.written_ticks for e in self.elements)

    @property
    def ticks(self) -> int:
        """Sounding span: the written total scaled by the ratio."""
        return self.written_ticks * self.denominator // self.numerator

    def render(self) -> str:
        inner = " ".join(e.render() for e in self.elements)
        return f"[{inner}]{self.numerator}:{self.denominator}"


Node = object  # Element | Tuplet


# --------------------------------------------------------------------------
# pitch helpers
# --------------------------------------------------------------------------


def name_and_octave(midi: int, tpc: int) -> Tuple[str, int]:
    """Split a (pitch, tpc) pair into a spelled name and an octave.

    The octave comes from the note's **written** position, not its sounding
    pitch, so ``Cb4`` (which sounds as B3) keeps octave 4 — matching MuseScore,
    and making the pair round-trip.
    """
    name = TPC_NAMES[tpc] if tpc >= 0 else "Fbb"
    letter = name[0]
    accidental = name[1:]
    natural_midi = midi - _ACCIDENTAL_OFFSET[accidental]
    octave = (natural_midi - _PITCH_CLASS[letter]) // 12 - 1
    return name, octave


def midi_and_tpc(name: str, octave: int) -> Tuple[int, int]:
    """Inverse of :func:`name_and_octave`."""
    tpc = _NAME_TO_TPC.get(name)
    if tpc is None:
        raise PassageError(f"unknown pitch name: {name!r}")
    letter = name[0]
    accidental = name[1:]
    midi = (octave + 1) * 12 + _PITCH_CLASS[letter] + _ACCIDENTAL_OFFSET[accidental]
    if not 0 <= midi <= 127:
        raise PassageError(f"pitch out of MIDI range: {name}{octave}")
    return midi, tpc


def _render_duration(symbol: Optional[str], ticks: int) -> str:
    """Prefer the note symbol; fall back to raw ticks."""
    return symbol if symbol is not None else str(ticks)


def duration_ticks(symbol: str, dots: str) -> int:
    """Written ticks for a note symbol. Raises if the result is not integral."""
    try:
        base = SYMBOLS[symbol]
    except KeyError:
        raise PassageError(f"unknown duration symbol: {symbol!r}") from None
    value = base * DOTS[dots]
    if value != int(value):  # pragma: no cover - all current combos are integral
        raise PassageError(f"{symbol}{dots} is not an integral number of ticks")
    return int(value)


def ticks_to_symbol(ticks: int) -> Optional[Tuple[str, str]]:
    """Best (symbol, dots) for a tick count, or None if there is no exact one."""
    for symbol, base in SYMBOLS.items():
        for dots, factor in DOTS.items():
            if base * factor == ticks:
                return symbol, dots
    return None


def legal_tick_values() -> List[int]:
    """Every tick count a single plain note or rest can take, largest first."""
    values = set()
    for base in SYMBOLS.values():
        for factor in DOTS.values():
            value = base * factor
            if value == int(value):
                values.add(int(value))
    return sorted(values, reverse=True)


def decompose_ticks(ticks: int) -> Optional[List[int]]:
    """Split a tick total into plain note values, largest first.

    Returns None when no combination fits — a remainder of 160 ticks cannot be
    written as plain rests, because 160 is a triplet value and always needs a
    bracket. The caller must refuse rather than approximate.

    A greedy largest-first pass is NOT sufficient here: 1905 decomposes as
    1440 + 420 + 45, but grabbing 1680 first leaves 225 and then 15, and 15 is
    not a note value. Every legal value is a multiple of 15, so the search runs
    over units of 15 with a small DP.
    """
    if ticks < 0:
        raise PassageError("cannot decompose a negative span")
    if ticks == 0:
        return []
    if ticks % 15 != 0:
        return None

    units = ticks // 15
    # Descending, so the reconstruction prefers the fewest, largest rests.
    coins = sorted({v // 15 for v in legal_tick_values()}, reverse=True)
    if not coins:
        return None  # pragma: no cover - SYMBOLS is never empty

    # reachable[i] is the coin that reaches i, or None.
    reachable: List[Optional[int]] = [None] * (units + 1)
    reachable[0] = 0
    for i in range(1, units + 1):
        for coin in coins:
            if coin > i:
                continue
            if reachable[i - coin] is not None:
                reachable[i] = coin
                break

    if reachable[units] is None:
        return None

    out: List[int] = []
    i = units
    while i > 0:
        coin = reachable[i]
        out.append(coin * 15)
        i -= coin
    return sorted(out, reverse=True)


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------

_TOKEN = re.compile(
    r"""
    (?P<rest>r/(?:\d+|[whqestx]\.{0,2}))
  | (?P<tuplet_open>\[)
  | (?P<tuplet_close>\](?P<num>\d+):(?P<den>\d+))
  | (?P<chord>
        [A-G](?:\#\#|\#|bb|b|n)?
        -?\d
        ~?
        (?:\+[A-G](?:\#\#|\#|bb|b|n)?-?\d~?)*
        /(?:\d+|[whqestx]\.{0,2})
    )
  | (?P<space>\s+)
  | (?P<bad>\S+)
    """,
    re.VERBOSE,
)

_PITCH = re.compile(r"(?P<name>[A-G](?:\#\#|\#|bb|b|n)?)(?P<octave>-?\d)(?P<tie>~?)")


def _parse_pitches(text: str, position: int) -> List[Pitch]:
    pitches: List[Pitch] = []
    for chunk in text.split("+"):
        m = _PITCH.fullmatch(chunk)
        if not m:
            raise PassageError(f"malformed pitch: {chunk!r}", position, text)
        name = m.group("name")
        octave = int(m.group("octave"))
        if not -1 <= octave <= 9:
            raise PassageError(
                f"octave out of range (-1…9): {octave}", position, text
            )
        midi, tpc = midi_and_tpc(name, octave)
        pitches.append(Pitch(name, octave, midi, tpc, bool(m.group("tie"))))
    if len({p.midi for p in pitches}) != len(pitches):
        raise PassageError("a chord cannot repeat the same pitch", position, text)
    return pitches


def _parse_duration(text: str, position: int) -> Tuple[int, Optional[str]]:
    """Return (written ticks, symbol-or-None)."""
    if text.isdigit():
        ticks = int(text)
        if ticks <= 0:
            raise PassageError("raw ticks must be positive", position, text)
        if ticks > MAX_TICKS:
            raise PassageError(f"raw ticks implausibly large: {ticks}", position, text)
        return ticks, None
    m = re.fullmatch(r"([whqestx])(\.{0,2})", text)
    if not m:
        raise PassageError(f"malformed duration: {text!r}", position, text)
    return duration_ticks(m.group(1), m.group(2)), m.group(1) + m.group(2)


def _parse_element(tok: str, position: int) -> Element:
    if tok.startswith("r/"):
        ticks, symbol = _parse_duration(tok[2:], position)
        return Element(ticks=ticks, written_ticks=ticks, symbol=symbol, is_rest=True)
    body, _, dur = tok.rpartition("/")
    if not body or not dur:
        raise PassageError(f"malformed element: {tok!r}", position, tok)
    pitches = _parse_pitches(body, position)
    ticks, symbol = _parse_duration(dur, position)
    return Element(pitches=pitches, ticks=ticks, written_ticks=ticks, symbol=symbol)


def parse(text: str) -> List[Node]:
    """Parse a passage into a flat list of :class:`Element` and :class:`Tuplet`."""
    if not isinstance(text, str):
        raise PassageError("passage must be a string")
    nodes: List[Node] = []
    stack: List[Tuple[List[Node], int]] = []
    pos = 0
    saw_space = True  # leading space is tolerated
    length = len(text)

    while pos < length:
        m = _TOKEN.match(text, pos)
        if m is None:  # pragma: no cover - _TOKEN matches any non-space
            raise PassageError(f"unexpected character: {text[pos]!r}", pos, text)
        pos = m.end()

        if m.lastgroup == "space":
            saw_space = True
            continue

        if m.lastgroup == "bad":
            raise PassageError(
                f"unrecognised token: {m.group('bad')!r}", m.start(), text
            )

        if m.lastgroup == "tuplet_open":
            if not saw_space and nodes:
                raise PassageError("expected a space before '['", m.start(), text)
            stack.append((nodes, m.start()))
            nodes = []
            saw_space = True
            continue

        if m.lastgroup == "tuplet_close":
            if not stack:
                raise PassageError("']' without a matching '['", m.start(), text)
            inner, open_pos = stack.pop()
            numerator, denominator = int(m.group("num")), int(m.group("den"))
            if numerator <= 0 or denominator <= 0:
                raise PassageError("tuplet ratio must be positive", m.start(), text)
            if not nodes:
                raise PassageError("empty tuplet group", open_pos, text)
            for node in nodes:
                if isinstance(node, Tuplet):
                    raise PassageError(
                        "nested tuplets are not supported", open_pos, text
                    )
                if node.is_rest and node.symbol is None:
                    raise PassageError(
                        "raw ticks are not allowed inside a tuplet; use note symbols",
                        open_pos,
                        text,
                    )
            nodes = inner + [Tuplet(nodes, numerator, denominator)]
            saw_space = True
            continue

        # an element
        if not saw_space:
            raise PassageError("expected a space between elements", m.start(), text)
        element = _parse_element(m.group(m.lastgroup), m.start())
        if stack and element.symbol is None:
            raise PassageError(
                "raw ticks are not allowed inside a tuplet; use note symbols",
                m.start(),
                text,
            )
        nodes.append(element)
        saw_space = False

    if stack:
        _, open_pos = stack[-1]
        raise PassageError("unclosed '['", open_pos, text)
    if not nodes:
        raise PassageError("empty passage")
    return nodes


# --------------------------------------------------------------------------
# serialiser (reference implementation; the plugin mirrors this in QML)
# --------------------------------------------------------------------------


def serialise(nodes: Sequence[Node]) -> str:
    parts: List[str] = []
    for node in nodes:
        parts.append(node.render())
    return " ".join(parts)


# --------------------------------------------------------------------------
# arithmetic and validation
# --------------------------------------------------------------------------


def sounding_ticks(nodes: Sequence[Node]) -> int:
    return sum(node.ticks for node in nodes)


def collect_ties(nodes: Sequence[Node]) -> List[Pitch]:
    out: List[Pitch] = []
    for node in nodes:
        elements = node.elements if isinstance(node, Tuplet) else [node]
        for element in elements:
            out.extend(p for p in element.pitches if p.tie)
    return out


def collect_ambiguous_ticks(nodes: Sequence[Node]) -> List[Element]:
    """Elements written as raw ticks outside a tuplet.

    A raw duration that is not a plain note value almost always means a triplet
    or something stranger. Accepting it silently writes a note with no bracket,
    which is a lossy round trip — so ``write_passage`` refuses it.
    """
    out: List[Element] = []
    for node in nodes:
        if isinstance(node, Tuplet):
            continue
        if node.symbol is None:
            out.append(node)
    return out


@dataclass
class Span:
    """Where a passage is going, in ticks."""

    start_tick: int
    ticks: int
    measure_start: int
    measure_end: int
    measure: int

    @property
    def end_tick(self) -> int:
        return self.start_tick + self.ticks


def resolve_span(
    *,
    measure: Optional[int],
    start_tick: Optional[int],
    beat: int,
    ticks: int,
    measure_start: int,
    measure_end: int,
) -> Span:
    """Resolve measure/beat or an explicit tick into a span inside one measure.

    ``measure_start``/``measure_end`` come from the score; this function does not
    know the score's layout, which is why they are passed in.
    """
    if (measure is None) == (start_tick is None):
        raise PassageError("give exactly one of measure or start_tick")
    if ticks <= 0:
        raise PassageError("ticks must be positive")
    if not isinstance(beat, int) or isinstance(beat, bool):
        raise PassageError("beat must be an integer")
    if beat < 1:
        raise PassageError("beat is 1-based")

    if measure is not None:
        if measure < 1:
            raise PassageError("measure is 1-based")
        start = measure_start + (beat - 1) * DIVISION
    else:
        start = start_tick
        if beat != 1:
            raise PassageError("beat only applies when measure is given")

    span = Span(start, ticks, measure_start, measure_end, measure or 0)
    if span.end_tick > measure_end:
        raise PassageError(
            f"span runs past the end of the measure "
            f"({span.end_tick} > {measure_end}); call once per measure"
        )
    if start < measure_start:
        raise PassageError("span starts before the measure")
    return span


def validate(nodes: Sequence[Node], span: Span) -> int:
    """Check a passage is legal for ``span``. Returns the ticks to pad with.

    Everything is checked before anything is written — a passage that cannot be
    written legally must not be half-written.
    """
    ties = collect_ties(nodes)
    if ties:
        first = ties[0]
        raise PassageError(
            f"write_passage cannot express a tie (found {first.name}{first.octave}~). "
            "A tie is per-pitch, but the only working route - MuseScore's own `tie` "
            "action - acts on a tick RANGE and ties every note in it that has a "
            "same-pitch successor, so it cannot tie one pitch of a chord and leave "
            "another. Write the notes first, then call add_tie on the range. "
            "add_tie toggles: read the passage back and tie only what is not tied."
        )

    ambiguous = collect_ambiguous_ticks(nodes)
    if ambiguous:
        rendered = ", ".join(e.render() for e in ambiguous[:3])
        raise PassageError(
            f"raw ticks outside a tuplet: {rendered}. "
            "A raw duration that is not a plain note value is almost always a "
            "tuplet — write it as an explicit group, e.g. [c4/e d4/e e4/e]3:2."
        )

    total = sounding_ticks(nodes)
    if total > span.ticks:
        raise PassageError(
            f"passage is {total} ticks but the span is {span.ticks}; "
            f"either shorten the passage or widen ticks"
        )
    return span.ticks - total
