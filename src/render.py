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
from PIL import Image, ImageDraw

IMAGE_LIMIT = 1568
"""Longest side of an image handed to Claude; larger images are scaled down."""

CROP_PIXELS_PER_SPACE = 25
"""Detail of cropped measures: a staff is 100 px high."""

CROP_MARGIN = 2
"""Staff spaces added around cropped measures."""

BARLINE_ROOM = 0.5
"""Staff spaces left unblanked before the first chosen measure: its barline."""


@dataclass(frozen=True)
class Box:
    """A measure's box on its page, in staff spaces from the page's top left.

    The box is as high as the measure's whole system (all its staves). notes
    also takes in its notes, rests and stems, which may stick out of the staves;
    content also what is attached to it: chord symbols, texts, lyrics, markers
    and jumps.
    """

    page: int
    x: float
    y: float
    width: float
    height: float
    content: Optional["Box"] = None
    notes: Optional["Box"] = None

    @property
    def bottom(self) -> float:
        """The y of the box's lower edge, in staff spaces."""
        return self.y + self.height


def boxes_from(measures: List[Optional[dict]]) -> List[Optional[Box]]:
    """Build the measure boxes from the plugin's reply.

    Args:
        measures (List[Optional[dict]]): One {"page", "x", "y", "width",
            "height", "content", "notes"} per measure, content and notes being
            {"x", "y", "width", "height"}; None for a measure that is not laid
            out (inside a multi-measure rest).

    Returns:
        boxes (List[Optional[Box]]): The boxes, in score order.
    """
    boxes: List[Optional[Box]] = []
    for m in measures:
        if not m:
            boxes.append(None)
            continue
        fields = {k: m[k] for k in ("page", "x", "y", "width", "height")}
        content, notes = m.get("content"), m.get("notes")
        boxes.append(
            Box(
                **fields,
                content=Box(page=m["page"], **content) if content else None,
                notes=Box(page=m["page"], **notes) if notes else None,
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


@dataclass(frozen=True)
class Crop:
    """What to cut from one page to show the chosen measures on it.

    region is the chosen measures' systems, whole and as they stand on the page,
    with what is attached to the measures. The other measures of the first and
    last system are blanked out (blanks), except where the chosen measures'
    attachments reach into them (keep).
    """

    page: int
    region: Box
    blanks: List[Box]
    keep: List[Box]


def _span(x0: float, y0: float, x1: float, y1: float, page: int) -> Box:
    return Box(page=page, x=x0, y=y0, width=x1 - x0, height=y1 - y0)


def _systems(boxes: Sequence[Optional[Box]]) -> List[List[tuple[int, Box]]]:
    """Group the laid-out measures into systems: [(measure, box)], 1-based."""
    systems: List[List[tuple[int, Box]]] = []
    for number, box in enumerate(boxes, start=1):
        if box is None:
            continue
        prev = systems[-1][0][1] if systems else None
        if prev and (prev.page, prev.y) == (box.page, box.y):
            systems[-1].append((number, box))
        else:
            systems.append([(number, box)])
    return systems


def _notes(system: List[tuple[int, Box]]) -> tuple[float, float]:
    """Return the top and bottom of a system's staves and notes."""
    parts = [b.notes or b for _, b in system]
    return min(b.y for b in parts), max(b.bottom for b in parts)


def crops(boxes: Sequence[Optional[Box]], first: int, last: int) -> List[Crop]:
    """Return what to cut from each page that holds measures first..last.

    The chosen systems are cut in one piece per page, so what stands between two
    of them shows once, and with CROP_MARGIN staff spaces around them and what
    is attached to the chosen measures (a To Coda sign past the barline, a chord
    symbol high above), but never into the staves and notes of the systems above
    and below. The measures before first and after last are left blank, so the
    chosen ones stand where they do on their system.

    Args:
        boxes (Sequence[Optional[Box]]): Every measure's box, in score order;
            None for a measure that is not laid out, which is skipped.
        first (int): The first measure, 1-based.
        last (int): The last measure, 1-based and inclusive.

    Returns:
        crops (List[Crop]): One per page, in page order, in staff spaces.
    """
    systems = _systems(boxes)
    result = []
    for page in sorted({b.page for b in boxes[first - 1 : last] if b}):
        on_page = [s for s in systems if s[0][1].page == page]
        shown = [
            k
            for k, s in enumerate(on_page)
            if any(first <= n <= last for n, _ in s)
        ]
        chosen_systems = on_page[shown[0] : shown[-1] + 1]
        everything = [b for s in chosen_systems for _, b in s]
        chosen = [b for s in chosen_systems for n, b in s if first <= n <= last]
        parts = everything + [b.content for b in chosen if b.content]
        top = min(b.y for b in parts) - CROP_MARGIN
        bottom = max(b.bottom for b in parts) + CROP_MARGIN
        if shown[0] > 0:
            top = max(top, _notes(on_page[shown[0] - 1])[1])
        if shown[-1] + 1 < len(on_page):
            bottom = min(bottom, _notes(on_page[shown[-1] + 1])[0])
        left = min(b.x for b in parts) - CROP_MARGIN
        right = max(b.x + b.width for b in parts) + CROP_MARGIN

        # Where one chosen system's rows end and the next one's begin.
        cuts = [top]
        for upper, lower in zip(chosen_systems, chosen_systems[1:]):
            cuts.append((_notes(upper)[1] + _notes(lower)[0]) / 2)
        cuts.append(bottom)

        blanks = []
        head = [b for n, b in chosen_systems[0] if n >= first]
        if chosen_systems[0][0][0] < first:
            blanks.append(
                _span(left, cuts[0], head[0].x - BARLINE_ROOM, cuts[1], page)
            )
        tail = [b for n, b in chosen_systems[-1] if n <= last]
        if chosen_systems[-1][-1][0] > last:
            end = tail[-1].x + tail[-1].width
            blanks.append(_span(end, cuts[-2], right, cuts[-1], page))

        result.append(
            Crop(
                page=page,
                region=_span(left, top, right, bottom, page),
                blanks=blanks,
                keep=[b.content for b in chosen if b.content],
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
    """Crop measures first..last from their pages, one piece per page, stacked.

    Each piece keeps its place across the page, so a bar in the middle of its
    system stands in the middle of the image.

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
    pieces = []  # (left edge in page pixels, image)
    for crop in crops(boxes, first, last):
        page = render_page(pdf, crop.page, scale)
        px = page.width / page_width  # pixels per staff space

        def pixels(box: Box) -> tuple[int, int, int, int]:
            return (
                max(0, round(box.x * px)),
                max(0, round(box.y * px)),
                min(page.width, round((box.x + box.width) * px)),
                min(page.height, round(box.bottom * px)),
            )

        shown = page.copy()
        draw = ImageDraw.Draw(shown)
        for blank in crop.blanks:
            x0, y0, x1, y1 = pixels(blank)
            if x1 > x0 and y1 > y0:
                draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill="white")
        for keep in crop.keep:
            area = pixels(keep)
            shown.paste(page.crop(area), area[:2])
        area = pixels(crop.region)
        pieces.append((area[0], shown.crop(area)))

    left = min(x for x, _ in pieces)
    stacked = Image.new(
        "RGB",
        (
            max(x - left + p.width for x, p in pieces),
            sum(p.height for _, p in pieces),
        ),
        "white",
    )
    y = 0
    for x, piece in pieces:
        stacked.paste(piece, (x - left, y))
        y += piece.height
    return fit(stacked)


def png_bytes(image: Image.Image) -> bytes:
    """Encode the image as PNG."""
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()
