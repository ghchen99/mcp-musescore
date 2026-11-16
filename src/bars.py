"""Bar numbers as printed in the score, the way users name bars.

The plugin addresses measures by position (1-based, in score order); users go by
the numbers printed in the score, which differ after a pickup bar, an "add to
measure number" offset or a bar left out of the count. Tools take and give the
printed numbers and turn them into positions here, so positions never reach the
user.

A pickup (a first measure left out of the count) is bar 0. A number printed on
more than one bar (a split bar, a section that counts from 1 again) is told
apart with letters in score order: 12a, 12b.
"""

import re
from string import ascii_lowercase
from typing import (
    Any,
    Dict,
    List,
    NoReturn,
    Optional,
    Tuple,
    TypeVar,
    Union,
    cast,
)

from fastmcp.exceptions import ToolError

from .client import MuseScoreClient

Reply = TypeVar("Reply")
"""A plugin reply, or a part of one."""

Bar = Union[int, str]
"""A bar as users name it: 12, or "12b" for the second bar printed as 12."""

BAR_HELP = (
    "as printed in the score (a pickup bar is 0; a number printed twice is "
    '"12a"/"12b")'
)
"""Help text for a bar parameter, to follow e.g. "First bar to read, "."""


class BarNumbers:
    """The score's printed bar numbers, by position."""

    def __init__(self, numbers: List[int], excluded: List[bool]) -> None:
        """Name each measure as printed.

        Args:
            numbers (List[int]): The number MuseScore prints on each measure, by
                position.
            excluded (List[bool]): Whether each measure is left out of the
                count; a first measure that is, is a pickup: bar 0.
        """
        printed = list(numbers)
        if printed and excluded and excluded[0]:
            printed[0] = 0
        counts: Dict[int, int] = {}
        for number in printed:
            counts[number] = counts.get(number, 0) + 1
        seen: Dict[int, int] = {}
        self.labels: List[str] = []
        for number in printed:
            if counts[number] == 1:
                self.labels.append(str(number))
            else:
                self.labels.append(
                    f"{number}{ascii_lowercase[seen.get(number, 0)]}"
                )
                seen[number] = seen.get(number, 0) + 1
        self._printed = printed
        self._positions = {
            label: position
            for position, label in enumerate(self.labels, start=1)
        }

    def label(self, position: int) -> str:
        """Return the printed name of the measure at a position (1-based)."""
        return self.labels[position - 1]

    def span(self, first: int, last: int) -> str:
        """Name positions first..last as printed: "12-15", or "12" for one bar."""
        if first == last:
            return self.label(first)
        return f"{self.label(first)}-{self.label(last)}"

    def position(self, bar: Bar) -> int:
        """Return the position (1-based) of a bar named as printed.

        Args:
            bar (Bar): 12, "12" or "12b".

        Returns:
            position (int): The measure's position in the score.

        Raises:
            ToolError: If no bar is printed so, or the number is printed on more
                than one bar and no letter says which.
        """
        name = str(bar).strip().lower()
        if name in self._positions:
            return self._positions[name]
        match = re.fullmatch(r"-?\d+", name)
        if match:
            twins = [
                label
                for label in self.labels
                if re.fullmatch(rf"{name}[a-z]", label)
            ]
            if twins:
                self._ambiguous(name, twins)
        raise ToolError(f"There is no bar {bar}: {self._range()}")

    def _ambiguous(self, name: str, twins: List[str]) -> NoReturn:
        listed = ", ".join(twins[:-1]) + f" and {twins[-1]}"
        times = "twice" if len(twins) == 2 else f"{len(twins)} times"
        raise ToolError(
            f"Bar {name} is printed {times} in the score: say {listed} (in score "
            "order) to tell them apart, or ask the user which one they mean"
        )

    def describe(self, first: int = 1, last: int = 0) -> str:
        """Name positions first..last as printed, gaps in the numbering shown.

        Args:
            first (int): The first position. Defaults to the first measure.
            last (int): The last position. Defaults to the last measure.

        Returns:
            bars (str): e.g. "0-8" or, for a score numbered as played, "1-2,
                5-6".
        """
        last = last or len(self.labels)
        runs: List[List[int]] = []
        for position in range(first, last + 1):
            number = self._printed[position - 1]
            previous = self._printed[position - 2] if runs else None
            if previous is not None and number in (previous, previous + 1):
                runs[-1].append(position)
            else:
                runs.append([position])
        return ", ".join(self.span(run[0], run[-1]) for run in runs)

    def _range(self) -> str:
        return f"the score's bars are {self.describe()}"

    def bounds(
        self, start: Optional[Bar], end: Optional[Bar], to_end: bool = False
    ) -> Tuple[int, int]:
        """Return the positions of a tool's start and end bars.

        Args:
            start (Optional[Bar]): The first bar. Defaults to the first bar of
                the score.
            end (Optional[Bar]): The last bar, inclusive. Defaults to start, or
                with to_end to the last bar of the score.
            to_end (bool): Whether a missing end means the end of the score.

        Returns:
            positions (Tuple[int, int]): The first and last measure's position.

        Raises:
            ToolError: If a bar is not printed so, or the range runs backwards.
        """
        first = 1 if start is None else self.position(start)
        if end is not None:
            last = self.position(end)
        else:
            last = len(self.labels) if to_end else first
        if last < first:
            raise ToolError(
                f"Bars {start}-{end} run backwards: bar {self.label(last)} "
                f"comes before bar {self.label(first)} in the score"
            )
        return first, last

    def relabel_text(self, text: str) -> str:
        """Rename the measures in a plugin message as printed.

        "measures 5-8" and "Measure 5" become "bars 49-52" and "Bar 49".
        """

        def bar(match: re.Match) -> str:
            first = int(match.group(3))
            last = int(match.group(4) or first)
            if not 1 <= first <= last <= len(self.labels):
                return match.group(0)
            word = "Bar" if match.group(1) == "M" else "bar"
            return f"{word}{match.group(2)} {self.span(first, last)}"

        return MEASURES_IN_TEXT.sub(bar, text)

    def relabel(self, value: Reply) -> Reply:
        """Rename the measures in a plugin reply as printed.

        Position fields (measure, startMeasure, ...) become printed names, and
        so do the measures named in its texts.
        """
        if isinstance(value, dict):
            return cast(
                Reply,
                {
                    key: self.label(item)
                    if key in POSITION_FIELDS
                    and isinstance(item, int)
                    and not isinstance(item, bool)
                    and 1 <= item <= len(self.labels)
                    else self.relabel(item)
                    for key, item in value.items()
                },
            )
        if isinstance(value, list):
            return cast(Reply, [self.relabel(item) for item in value])
        if isinstance(value, str):
            return cast(Reply, self.relabel_text(value))
        return value


MEASURES_IN_TEXT = re.compile(r"\b([Mm])easure(s?) (\d+)(?:-(\d+))?\b")
"""A measure (or range) named by position in a plugin message."""

POSITION_FIELDS = {
    "measure",
    "startMeasure",
    "endMeasure",
    "firstMeasure",
    "lastMeasure",
}
"""Fields of a plugin reply that hold a measure's position."""


async def bar_numbers(client: MuseScoreClient) -> BarNumbers:
    """Fetch the open score's printed bar numbers from the plugin."""
    reply = await client.request("barNumbers")
    return BarNumbers(reply["numbers"], reply["excluded"])


async def send(
    client: MuseScoreClient,
    bars: BarNumbers,
    action: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run a plugin command and give its reply and errors in printed bars.

    Args:
        client (MuseScoreClient): The client to send the command through.
        bars (BarNumbers): The score's printed bar numbers.
        action (str): The plugin action.
        params (Optional[Dict[str, Any]]): Its parameters, measures by position.

    Returns:
        result (Dict[str, Any]): The plugin's result, measures as printed.

    Raises:
        ToolError: If the plugin reports an error, measures as printed.
    """
    try:
        result = await client.request(action, params)
    except ToolError as error:
        raise ToolError(bars.relabel_text(str(error))) from error
    return bars.relabel(result)
