"""Passage reading and writing.

The compact passage format is specified in ``SPEC.md`` §1 and implemented in
``src/passage.py``. This module is the MCP surface over it.

Why a separate format at all: reading a score through ``getScore`` costs 134 KB
(~33,000 tokens) on a 117-measure score, and trimming redundant fields only gets
that to 63%. The passage form gets to 7%, because it changes the payload's
*shape* rather than its spelling.
"""

from typing import Any, Dict, List, Optional

from ..client import MuseScoreClient
from .. import passage as P
from ..utils.envelope import unwrap
from ..utils.score_context import measure_bounds, score_context, score_end_tick


def setup_passage_tools(mcp, client: MuseScoreClient):
    """Setup passage read/write tools."""

    async def _context() -> Dict[str, Any]:
        return await score_context(client)

    async def _span(params: Dict[str, Any]) -> tuple:
        """Resolve measure/beat or start_tick into a Span. Raises PassageError."""
        ctx = await _context()
        starts = list(ctx.get("measureStarts") or [])
        if not starts:
            raise P.PassageError("cannot read the score's measure layout")

        # Refuse anything past the end of the score. This is the guard whose
        # absence took MuseScore down: a passage aimed at measure 40 of a
        # 32-measure score left curScore unusable, and every command after it
        # reported no score at all.
        end_of_score = score_end_tick(ctx)
        target_tick = params.get("startTick")
        if target_tick is not None and end_of_score is not None \
                and target_tick >= end_of_score:
            raise P.PassageError(
                f"start_tick {target_tick} is past the end of the score "
                f"(it ends at {end_of_score}); nothing was written"
            )

        measure = params.get("measure")
        start_tick = params.get("startTick")
        beat = params.get("beat", 1)
        ticks = params.get("ticks")

        if measure is not None:
            bounds = measure_bounds(ctx, measure)
            if bounds is None:
                raise P.PassageError(
                    f"measure out of range (1..{len(starts)})"
                )
            m_start, m_end = bounds
            if m_end is None:
                # Last measure: its length is not knowable from the next start
                # tick, so take it from the caller's span.
                if ticks is None:
                    raise P.PassageError(
                        "the last measure has no following barline to measure "
                        "against; pass ticks explicitly"
                    )
                m_end = m_start + ticks
        else:
            if start_tick is None:
                raise P.PassageError("give measure or start_tick")
            idx, _ = _locate(starts, start_tick)
            m_start = starts[idx - 1]
            m_end = starts[idx] if idx < len(starts) else start_tick + (ticks or 0)

        span = P.resolve_span(
            measure=measure,
            start_tick=start_tick,
            beat=beat,
            ticks=ticks,
            measure_start=m_start,
            measure_end=m_end,
        )
        if end_of_score is not None and span.end_tick > end_of_score:
            raise P.PassageError(
                f"the span runs past the end of the score "
                f"({span.end_tick} > {end_of_score}); nothing was written"
            )
        return span

    def _locate(starts, tick):
        from ..utils.score_context import locate_tick
        return locate_tick({"measureStarts": starts}, tick)

    @mcp.tool()
    async def read_passage(
        measure: Optional[int] = None,
        start_tick: Optional[int] = None,
        measures: int = 1,
        staves: Optional[List[int]] = None,
        include_context: bool = True,
    ):
        """Read a span of the score as compact passage strings.

        One call replaces reading the whole score. Each measure comes back with
        one string per staff:

            {"measures": [{"m": 35, "tick": 56640,
                           "s0": "Eb2/h.",
                           "s1": "r/q Eb4+G4+Bb4/q Eb4+G4+Bb4/q"}],
             "context": {"key": [{"m": 1, "value": "Eb"}],
                         "time_sig": [{"m": 1, "value": "3/4"}]}}

        Passage syntax: notes are `name + octave` (MIDI 60 = C4), durations are
        `w h q e s t x` with `.` and `..` for dots, `r` is a rest, `+` stacks a
        chord, `~` marks a tie, and `[c4/e d4/e e4/e]3:2` is a tuplet. A bare
        number is raw ticks.

        Args:
            measure: 1-based measure to start at. Give this or start_tick.
            start_tick: tick to start at, as an alternative to measure.
            measures: how many measures to read.
            staves: 0-based staff indices. Defaults to staff 0 only.
            include_context: include key and time-signature changes.
        """
        if (measure is None) == (start_tick is None):
            return {"error": "give exactly one of measure or start_tick"}

        params: Dict[str, Any] = {
            "measures": measures,
            "staves": staves if staves is not None else [0],
            "includeContext": include_context,
        }
        if measure is not None:
            params["measure"] = measure
        else:
            params["startTick"] = start_tick

        res = unwrap(await client.send_command("readPassage", params))
        if not (isinstance(res, dict) and res.get("success")):
            return res
        return res.get("passage", res)

    @mcp.tool()
    async def write_passage(
        staff: int,
        notes: str,
        ticks: int,
        measure: Optional[int] = None,
        start_tick: Optional[int] = None,
        beat: int = 1,
        voice: int = 0,
        dry_run: bool = False,
    ):
        """Write a passage onto one staff, replacing the span it claims.

        The caller declares how much space it is claiming with `ticks`. That is
        not optional: without it a shortened passage leaves stale content behind
        and produces a measure that sums to exactly the right number of ticks
        with the wrong music in it — a failure this project has already had.

        Everything is validated before anything is written. A span that crosses
        a barline is refused rather than extended; call once per measure.

        Args:
            staff: 0-based staff index.
            notes: the passage string, e.g. "Eb4/h. r/q Eb4+G4+Bb4/q".
            ticks: the span being claimed, in ticks (480 per quarter note).
            measure: 1-based measure to start at. Give this or start_tick.
            start_tick: tick to start at, as an alternative to measure.
            beat: 1-based beat within the measure. Quarter notes, not the time
                signature's beat unit. Only used with measure.
            voice: target voice. Reserved — polyphony is not implemented yet.
            dry_run: validate and report what would happen, without writing.

        Raises a PassageError (as an error dict) for ties, ambiguous raw ticks,
        barline crossings, and passages longer than the span.
        """
        if (measure is None) == (start_tick is None):
            return {"error": "give exactly one of measure or start_tick"}

        try:
            nodes = P.parse(notes)
            span = await _span({
                "measure": measure, "startTick": start_tick,
                "beat": beat, "ticks": ticks,
            })
            padding = P.validate(nodes, span)
        except P.PassageError as exc:
            return {"error": str(exc)}

        # The padding rests are computed HERE, not in the plugin: this is plain
        # arithmetic and it is testable without MuseScore in the loop. Writing a
        # remainder that has no note value (a triplet fragment, say) is refused
        # rather than approximated.
        pad_pieces = P.decompose_ticks(padding)
        if pad_pieces is None:
            return {"error": (
                f"the passage leaves {padding} ticks to fill, and no combination "
                "of plain rests adds up to that. A remainder that is not a "
                "multiple of 30 ticks is almost always a tuplet fragment — either "
                "give the span a length the passage can pad, or write the tuplet "
                "explicitly."
            )}

        plan = {
            "staff": staff,
            "voice": voice,
            "start_tick": span.start_tick,
            "measure": span.measure,
            "ticks": span.ticks,
            "written_ticks": P.sounding_ticks(nodes),
            "padding_ticks": padding,
            "padding_rests": pad_pieces,
            "elements": len(nodes),
            "canonical": P.serialise(nodes),
        }

        if dry_run:
            return {"dry_run": True, "valid": True, "plan": plan}

        elements = [_element_payload(n) for n in nodes]
        elements += [_rest_payload(t) for t in pad_pieces]

        payload = {
            "staff": staff,
            "voice": voice,
            "startTick": span.start_tick,
            "ticks": span.ticks,
            # The plugin receives a structure, not the string: parsing happens
            # here, where it can be tested without MuseScore in the loop.
            "elements": elements,
        }
        res = unwrap(await client.send_command("writePassage", payload))
        if not (isinstance(res, dict) and res.get("success")):
            return res

        # Verify by comparison, not by the tool's own success flag. The padding
        # rests are part of what should now be on the staff, so the expected
        # string includes them.
        expected = _expected_readback(nodes, pad_pieces)
        actual = res.get("actual")
        verified = (actual == expected)

        out = {
            "plan": plan,
            "verified": verified,
            "expected": expected,
            "actual": actual,
            "neighbour_staff": res.get("neighbour_staff"),
            "neighbour": res.get("neighbour"),
        }
        if not verified:
            out["warning"] = (
                "the read-back does not match what was asked for. Do not assume "
                "the write landed — check the score before continuing."
            )
        return out

    @mcp.tool()
    async def write_score(
        staff: int,
        notes: str,
        start_measure: int = 1,
        voice: int = 0,
        dry_run: bool = False,
    ):
        """Write many bars in one call: one bar per `|`-separated group.

        `write_passage` handles one bar, so a fifty-bar piece is fifty tool calls
        and fifty round trips of JSON envelope around them. This splits the same
        grammar on `|` and writes each group as its own bar, so the piece is one
        call. Nothing about the per-bar rules changes: each bar is still
        validated, written and read back on its own, and any bar that fails is
        reported with its measure number.

        Bar lengths are read from the score rather than supplied, so a passage
        may cross a time-signature change. A bar whose length cannot be
        determined is refused rather than guessed.

        Bars are written in order and the run STOPS at the first failure, so a
        partial write is possible — the report says exactly which bars landed.

        Args:
            staff: 0-based staff index.
            notes: the passage, one group per bar, e.g.
                "Eb4/w | Eb4/h G4/h | Bb3/w". Each group is exactly what
                write_passage accepts.
            start_measure: 1-based measure the first group is written to.
            voice: target voice.
            dry_run: validate every bar and report, writing nothing.
        """
        groups = [g.strip() for g in notes.split("|")]
        if not groups or all(g == "" for g in groups):
            return {"error": "the passage is empty"}
        empty = [i + 1 for i, g in enumerate(groups) if g == ""]
        if empty:
            # A missing group is almost always a stray `|`, and silently
            # skipping it would shift every following bar by one — the exact
            # class of quiet misplacement this format exists to prevent.
            return {"error": (
                f"bar group(s) {empty} are empty (check for a stray '|'). "
                "To clear a bar, write a rest: 'r/w'."
            )}

        ctx = await score_context(client)
        starts = list(ctx.get("measureStarts") or [])
        if not starts:
            return {"error": "cannot read the score's measure layout"}
        end_of_score = score_end_tick(ctx)

        # Resolve every span before writing anything, so a passage that runs off
        # the end of the score is refused whole rather than half-written.
        spans = []
        for i in range(len(groups)):
            measure = start_measure + i
            bounds = measure_bounds(ctx, measure)
            if bounds is None:
                return {"error": (
                    f"bar group {i + 1} is measure {measure}, which is outside "
                    f"the score (1..{len(starts)})"
                )}
            start, end = bounds
            if end is None:
                end = end_of_score
            if end is None:
                return {"error": (
                    f"cannot determine the length of measure {measure}, the last "
                    "bar of the score"
                )}
            spans.append((measure, end - start))

        results, verified_all = [], True
        for group, (measure, ticks) in zip(groups, spans):
            res = await write_passage(
                staff=staff, notes=group, ticks=ticks, measure=measure,
                voice=voice, dry_run=dry_run,
            )
            if "error" in res:
                results.append({"measure": measure, "error": res["error"]})
                verified_all = False
                break
            results.append({
                "measure": measure,
                "ticks": ticks,
                "verified": res.get("verified"),
                "actual": res.get("actual"),
            })
            if res.get("verified") is not True:
                verified_all = False
                break

        written = [r["measure"] for r in results if "error" not in r]
        out = {
            "bars": len(groups),
            "written": len(written),
            "measures": written,
            "verified": verified_all,
            "results": results,
        }
        if dry_run:
            out["dry_run"] = True
        if len(written) < len(groups):
            out["stopped_at"] = f"bar group {len(written) + 1} of {len(groups)}"
        return out

def _expected_readback(nodes, pad_pieces) -> str:
    """What the staff should read as once the passage and its padding land."""
    parts = [P.serialise(nodes)] if nodes else []
    for ticks in pad_pieces:
        symbol = P.ticks_to_symbol(ticks)
        parts.append(P.Element(
            ticks=ticks,
            written_ticks=ticks,
            symbol=(symbol[0] + symbol[1]) if symbol else None,
            is_rest=True,
        ).render())
    return " ".join(p for p in parts if p)


def _rest_payload(ticks: int) -> Dict[str, Any]:
    """A padding rest. Always a plain value — decompose_ticks guarantees it."""
    return {"rest": True, "ticks": ticks, "pitches": []}


def _element_payload(node) -> Dict[str, Any]:
    """One parsed node in the structured form the plugin writes from."""
    if isinstance(node, P.Tuplet):
        return {
            "tuplet": {"numerator": node.numerator, "denominator": node.denominator},
            "elements": [_element_payload(e) for e in node.elements],
        }
    return {
        "rest": node.is_rest,
        "ticks": node.written_ticks,
        "pitches": [{"midi": p.midi, "tpc": p.tpc} for p in node.pitches],
    }
