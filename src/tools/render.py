"""The render tool: the score as MuseScore engraves it, as an image."""

import re
import tempfile
from pathlib import Path
from typing import Annotated, Optional

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import ToolResult
from fastmcp.utilities.types import Image as McpImage

from ..client import MuseScoreClient
from ..render import boxes_from, png_bytes, render_measures, render_whole_page


def parse_measures(measures: str, num_measures: int) -> tuple[int, int]:
    """Parse "X-Y" (or "X") into a measure range within the score.

    Args:
        measures (str): The range, 1-based and inclusive.
        num_measures (int): The number of measures in the score.

    Returns:
        range (tuple[int, int]): The first and last measure.

    Raises:
        ToolError: If the range is malformed or outside the score.
    """
    match = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+)\s*)?", measures)
    if not match:
        raise ToolError(
            f'measures must look like "5-8" or "5", not {measures!r}'
        )
    first = int(match.group(1))
    last = int(match.group(2) or first)
    if not 1 <= first <= last <= num_measures:
        raise ToolError(
            f"Measures {measures} are outside the score, which has "
            f"{num_measures} measures"
        )
    return first, last


def setup_render_tools(mcp: FastMCP, client: MuseScoreClient) -> None:
    """Register the render tool.

    Args:
        mcp (FastMCP): The server to register the tools on.
        client (MuseScoreClient): The client the tools send their commands
            through.
    """

    @mcp.tool(
        description=(
            "Show the score as MuseScore engraves it, as an image: what get_score's text cannot show, such as "
            "overlapping chord symbols, marker placement, system and page breaks and spacing. "
            "page=N gives a whole page (for layout); measures='X-Y' crops those bars from their page at higher "
            "detail, with everything attached to them (chord symbols, texts, lyrics, markers), as they stand on their "
            "systems: the other bars of those systems are left blank, so a blank space before the first bar means "
            "the system starts earlier. "
            "Measures are positions in the score, as in get_score's '% m.N', not printed bar numbers: with a "
            "pickup bar, printed bar 49 is measure 50. The caption gives the printed numbers when they differ. "
            "Render again after a change to check it."
        ),
        tags={"score", "layout"},
    )
    async def render(
        page: Annotated[
            Optional[int], "Page to show (1-based). Defaults to page 1"
        ] = None,
        measures: Annotated[
            Optional[str],
            'Measures to show instead of a page, by position (as in get_score\'s "% m.N"), e.g. "5-8" or "5"',
        ] = None,
    ) -> ToolResult:
        if page is not None and measures is not None:
            raise ToolError("Give either page or measures, not both")
        with tempfile.TemporaryDirectory(prefix="mcp-musescore-") as tmp:
            base = Path(tmp) / "score"
            result = await client.request(
                "renderScore", {"path": base.as_posix()}
            )
            pdf = base.with_name(base.name + ".pdf")
            pages = result["pages"]
            if measures is None:
                number = page or 1
                if not 1 <= number <= pages:
                    raise ToolError(
                        f"Page {number} does not exist: the score has {pages} "
                        f"page{'s' if pages != 1 else ''}"
                    )
                image = render_whole_page(pdf, number - 1)
                caption = f"Page {number} of {pages}"
            else:
                boxes = boxes_from(result["measures"])
                first, last = parse_measures(measures, len(boxes))
                for n in range(first, last + 1):
                    if boxes[n - 1] is None:
                        raise ToolError(
                            f"Measure {n} is inside a multi-measure rest, so it has no place of its "
                            "own on the page. Render its page instead, or turn multi-measure rests "
                            'off with set_style({"createMultiMeasureRests": false}).'
                        )
                image = render_measures(
                    pdf, result["pageWidth"], boxes, first, last
                )
                shown = sorted(
                    {b.page + 1 for b in boxes[first - 1 : last] if b}
                )
                where = (
                    f"page {shown[0]}"
                    if len(shown) == 1
                    else f"pages {shown[0]}-{shown[-1]}"
                )
                span = f"{first}-{last}" if last != first else str(first)
                numbers = result.get("numbers") or []
                printed = ""
                if len(numbers) >= last and (
                    numbers[first - 1] != first or numbers[last - 1] != last
                ):
                    low, high = numbers[first - 1], numbers[last - 1]
                    printed = (
                        f"printed bars {low}-{high}, "
                        if high != low
                        else f"printed bar {low}, "
                    )
                caption = f"Measures {span} ({printed}{where} of {pages})"
        return ToolResult(
            content=[
                caption,
                McpImage(
                    data=png_bytes(image), format="png"
                ).to_image_content(),
            ]
        )
