"""The render tool: the score as MuseScore engraves it, as an image."""

import re
import tempfile
from pathlib import Path
from typing import Annotated, Optional

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import ToolResult
from fastmcp.utilities.types import Image as McpImage

from ..bars import BAR_HELP, BarNumbers, bar_numbers
from ..client import MuseScoreClient
from ..render import boxes_from, png_bytes, render_measures, render_whole_page


def parse_bars(measures: str, bars: BarNumbers) -> tuple[int, int]:
    """Turn bars "X-Y" (or "X"), as printed, into their positions.

    Args:
        measures (str): The range, inclusive, e.g. "49-62", "0-4" or "12b-14".
        bars (BarNumbers): The score's printed bar numbers.

    Returns:
        range (tuple[int, int]): The first and last measure's position.

    Raises:
        ToolError: If the range is malformed, names a bar the score does not
            print, or runs backwards.
    """
    match = re.fullmatch(r"\s*(\w+)\s*(?:-\s*(\w+)\s*)?", measures)
    if not match:
        raise ToolError(
            f'measures must look like "5-8" or "5", not {measures!r}'
        )
    first = bars.position(match.group(1))
    last = bars.position(match.group(2) or match.group(1))
    if last < first:
        raise ToolError(
            f"Bars {measures} run backwards: bar {bars.label(last)} comes "
            f"before bar {bars.label(first)} in the score"
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
            "Bars are named as printed in the score, as the user sees them. "
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
            f'Bars to show instead of a page, e.g. "5-8" or "5", {BAR_HELP}',
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
                bars = await bar_numbers(client)
                first, last = parse_bars(measures, bars)
                for n in range(first, last + 1):
                    if boxes[n - 1] is None:
                        raise ToolError(
                            f"Bar {bars.label(n)} is inside a multi-measure rest, so it has no place of "
                            "its own on the page. Render its page instead, or turn multi-measure rests "
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
                caption = f"Bars {bars.span(first, last)} ({where} of {pages})"
        return ToolResult(
            content=[
                caption,
                McpImage(
                    data=png_bytes(image), format="png"
                ).to_image_content(),
            ]
        )
