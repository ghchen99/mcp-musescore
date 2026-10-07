"""Cheap score metadata.

``getScore``/``getCursorInfo`` return the entire score — 134 KB, roughly 33,000
tokens, on a 117-measure score. Most callers do not want the music; they want to
know how many measures there are, where measure N starts, or what a staff is
called. That is a few hundred bytes.

Everything here is a thin wrapper over the plugin's ``scoreContext`` command.
"""

from typing import Any, Dict, List, Optional

from ..client import MuseScoreClient
from .envelope import unwrap


async def score_context(client: MuseScoreClient) -> Dict[str, Any]:
    """Title, staff names, measure count, and every measure's start tick."""
    res = unwrap(await client.send_command("scoreContext"))
    if isinstance(res, dict) and res.get("success") and isinstance(res.get("context"), dict):
        return res["context"]
    return {}


def score_end_tick(context: Dict[str, Any]) -> Optional[int]:
    """Total length of the score in ticks, or None when it cannot be read."""
    end = context.get("endTick")
    if isinstance(end, int) and end > 0:
        return end
    starts = list(context.get("measureStarts") or [])
    if not starts:
        return None
    # We cannot know the last measure's length from a following barline, so this
    # is a lower bound only. Good enough to reject a start beyond the score.
    return starts[-1]


def measure_bounds(context: Dict[str, Any], measure: int) -> Optional[tuple]:
    """``(start_tick, end_tick)`` for a 1-based measure number, or None.

    The last measure has no following start tick to read, so its end is taken
    from the score's own measure count when possible and is otherwise open.
    """
    starts: List[int] = list(context.get("measureStarts") or [])
    if not starts or measure < 1 or measure > len(starts):
        return None
    start = starts[measure - 1]
    end = starts[measure] if measure < len(starts) else None
    return start, end


def locate_tick(context: Dict[str, Any], tick: int) -> tuple:
    """``(measure, beat)`` for a tick. Both 1-based, beat = a quarter note.

    Beat is a quarter regardless of time signature, matching the score's
    Division. Deriving the measure from ``tick // 1920`` — the old fallback — is
    simply wrong in anything but 4/4.
    """
    starts: List[int] = list(context.get("measureStarts") or [])
    if not starts:
        return (tick // 1920) + 1, ((tick % 1920) // 480) + 1
    idx = 0
    for i, start in enumerate(starts):
        if start <= tick:
            idx = i
        else:
            break
    return idx + 1, ((tick - starts[idx]) // 480) + 1


def span_ticks(
    context: Dict[str, Any],
    *,
    measure: Optional[int] = None,
    start_tick: Optional[int] = None,
    measures: int = 1,
) -> tuple:
    """``(start_tick, ticks)`` for a range that may cross barlines.

    Unlike ``write_passage``, which is confined to one measure on purpose, a
    transposition is expected to span a whole passage.

    Raises ``ValueError`` when the range cannot be resolved — most often because
    it reaches the final measure, whose length is not knowable from a following
    barline. Callers that need that should pass an explicit span instead.
    """
    starts: List[int] = list(context.get("measureStarts") or [])
    if not starts:
        raise ValueError("cannot read the score's measure layout")
    if (measure is None) == (start_tick is None):
        raise ValueError("give exactly one of measure or start_tick")
    if measures < 1:
        raise ValueError("measures must be at least 1")

    end_of_score = score_end_tick(context)
    if end_of_score is not None:
        if start_tick is not None and start_tick >= end_of_score:
            raise ValueError(
                f"start_tick {start_tick} is past the end of the score "
                f"(it ends at {end_of_score})"
            )
        if measure is not None and starts and measure > len(starts):
            raise ValueError(f"measure out of range (1..{len(starts)})")

    if measure is not None:
        if measure < 1 or measure > len(starts):
            raise ValueError(f"measure out of range (1..{len(starts)})")
        first = measure - 1
        start = starts[first]
    else:
        first = 0
        for i, s in enumerate(starts):
            if s <= start_tick:
                first = i
        start = start_tick

    last = min(first + measures - 1, len(starts) - 1)
    if last + 1 >= len(starts):
        raise ValueError(
            "the range reaches the final measure, which has no following barline "
            "to measure against; transpose it separately or use an explicit range"
        )
    span = starts[last + 1] - start
    if end_of_score is not None and start + span > end_of_score:
        raise ValueError(
            f"the range runs past the end of the score "
            f"({start + span} > {end_of_score})"
        )
    return start, span

