"""Turn MuseScore's engraved pages into images for Claude.

The plugin writes the score as a PDF with writeScore and reports each measure's
box in staff spaces (the plugin API's unit for positions). Only the pages needed
are rasterised, at a size chosen here; MuseScore's own PNG export would write
every page at its export resolution, 1200 DPI by default.
"""

import io
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import pypdfium2 as pdfium
from PIL import Image

IMAGE_LIMIT = 1568
"""Longest side of an image handed to Claude; larger images are scaled down."""

CROP_PIXELS_PER_SPACE = 25
"""Detail of cropped measures: a staff is 100 px high."""

CROP_MARGIN = 2
"""Staff spaces added around cropped measures, which shows the barline before."""


@dataclass(frozen=True)
class Box:
    """A measure's box on its page, in staff spaces from the page's top left.

    The box is as high as the measure's whole system (all its staves). content
    also takes in what is attached to the measure and may stick out of it: chord
    symbols, texts, lyrics, markers and jumps, notes on ledger lines.
    """

    page: int
    x: float
    y: float
    width: float
    height: float
    content: Optional["Box"] = None

    @property
    def bottom(self) -> float:
        """The y of the box's lower edge, in staff spaces."""
        return self.y + self.height


def boxes_from(measures: List[Optional[dict]]) -> List[Optional[Box]]:
    """Build the measure boxes from the plugin's reply.

    Args:
        measures (List[Optional[dict]]): One {"page", "x", "y", "width",
            "height", "content"} per measure, content being {"x", "y", "width",
            "height"}; None for a measure that is not laid out (inside a multi-
            measure rest).

    Returns:
        boxes (List[Optional[Box]]): The boxes, in score order.
    """
    boxes: List[Optional[Box]] = []
    for m in measures:
        if not m:
            boxes.append(None)
            continue
        fields = {k: m[k] for k in ("page", "x", "y", "width", "height")}
        content = m.get("content")
        boxes.append(
            Box(
                **fields,
                content=Box(page=m["page"], **content) if content else None,
            )
        )
    return boxes


def render_page(pdf: Path, page: int, scale: float) -> Image.Image:
    """Rasterise one page of the PDF on white.

    Args:
        pdf (Path): The PDF the plugin wrote.
        page (int): The page, 0-based.
        scale (float): Pixels per PDF point.

    Returns:
        image (Image.Image): The page, RGB.
    """
    document = pdfium.PdfDocument(pdf)
    try:
        bitmap = document[page].render(
            scale=scale, fill_color=(255, 255, 255, 255)
        )
        return bitmap.to_pil().convert("RGB")
    finally:
        document.close()


def page_points(pdf: Path) -> tuple[float, float]:
    """Return the size of the PDF's first page, in points."""
    document = pdfium.PdfDocument(pdf)
    try:
        return document[0].get_size()
    finally:
        document.close()


def fit(image: Image.Image, limit: int = IMAGE_LIMIT) -> Image.Image:
    """Scale the image down so its longest side is at most limit pixels."""
    scale = limit / max(image.size)
    if scale >= 1:
        return image
    size = (
        max(1, int(image.width * scale)),
        max(1, int(image.height * scale)),
    )
    return image.resize(size, Image.Resampling.LANCZOS)


def render_whole_page(pdf: Path, page: int) -> Image.Image:
    """Render a page so that its longest side fills IMAGE_LIMIT pixels.

    Args:
        pdf (Path): The PDF the plugin wrote.
        page (int): The page, 0-based.

    Returns:
        image (Image.Image): The page.
    """
    width, height = page_points(pdf)
    return fit(render_page(pdf, page, IMAGE_LIMIT / max(width, height)))


def bands(
    boxes: Sequence[Optional[Box]], first: int, last: int
) -> List[tuple[int, Box]]:
    """Return the region to crop on each system that holds measures first..last.

    A band takes in the chosen measures of the system and everything attached to
    them, with CROP_MARGIN staff spaces around, so that nothing of theirs is cut
    off (a To Coda sign past the barline, a chord symbol high above).

    Args:
        boxes (Sequence[Optional[Box]]): Every measure's box, in score order;
            None for a measure that is not laid out, which is skipped.
        first (int): The first measure, 1-based.
        last (int): The last measure, 1-based and inclusive.

    Returns:
        bands (List[tuple[int, Box]]): (page, region) per system, top to bottom,
            in staff spaces.
    """
    systems: List[List[Box]] = []  # the chosen measures, per system
    for box in boxes[first - 1 : last]:
        if box is None:
            continue
        prev = systems[-1][0] if systems else None
        if prev and (prev.page, prev.y) == (box.page, box.y):
            systems[-1].append(box)
        else:
            systems.append([box])

    result = []
    for system in systems:
        parts = system + [b.content for b in system if b.content]
        left = min(b.x for b in parts) - CROP_MARGIN
        top = min(b.y for b in parts) - CROP_MARGIN
        right = max(b.x + b.width for b in parts) + CROP_MARGIN
        bottom = max(b.bottom for b in parts) + CROP_MARGIN
        page = system[0].page
        result.append(
            (
                page,
                Box(
                    page=page,
                    x=left,
                    y=top,
                    width=right - left,
                    height=bottom - top,
                ),
            )
        )
    return result


def render_measures(
    pdf: Path,
    page_width: float,
    boxes: Sequence[Optional[Box]],
    first: int,
    last: int,
) -> Image.Image:
    """Crop measures first..last from their pages, one band per system, stacked.

    Args:
        pdf (Path): The PDF the plugin wrote.
        page_width (float): The page width, in staff spaces.
        boxes (Sequence[Optional[Box]]): Every measure's box, in score order;
            None for a measure that is not laid out.
        first (int): The first measure, 1-based.
        last (int): The last measure, 1-based and inclusive.

    Returns:
        image (Image.Image): The bands, fitted to IMAGE_LIMIT.
    """
    width_points, _ = page_points(pdf)
    scale = CROP_PIXELS_PER_SPACE * page_width / width_points
    pages: dict[int, Image.Image] = {}
    crops = []
    for page, region in bands(boxes, first, last):
        if page not in pages:
            pages[page] = render_page(pdf, page, scale)
        image = pages[page]
        px = image.width / page_width  # pixels per staff space
        crops.append(
            image.crop(
                (
                    max(0, round(region.x * px)),
                    max(0, round(region.y * px)),
                    min(image.width, round((region.x + region.width) * px)),
                    min(image.height, round(region.bottom * px)),
                )
            )
        )
    stacked = Image.new(
        "RGB",
        (max(c.width for c in crops), sum(c.height for c in crops)),
        "white",
    )
    y = 0
    for crop in crops:
        stacked.paste(crop, (0, y))
        y += crop.height
    return fit(stacked)


def png_bytes(image: Image.Image) -> bytes:
    """Encode the image as PNG."""
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()
