"""Tests of the render tool against the mock plugin.

The mock writes the score as a PDF of blank pages and reports each measure's box
in spatium units (staff spaces), as the plugin does. The layouts below are in
spatium units, so the expected image sizes follow from them by hand: a page view
fits in 1568 px, and cropped measures are drawn at 25 px per staff space before
that limit applies.
"""

import base64
import io

from mock_musescore import MockScore
from PIL import Image
from test_integration import run_with_mock


def two_systems_score():
    """Eight bars on one 100×140 sp page: bars 1-4 and 5-8, 20 sp each.

    System 1 spans y 10-30 and system 2 y 50-70.
    """
    score = MockScore(staves=1, measures=8)
    score.page_size = (100, 140)
    score.measure_boxes = [
        (0, 10 + 20 * (i % 4), 10 if i < 4 else 50, 20, 20) for i in range(8)
    ]
    return score


def image_of(result):
    """Return the tool result's image as a Pillow image."""
    (image,) = [c for c in result.content if c.type == "image"]
    return Image.open(io.BytesIO(base64.b64decode(image.data)))


def text_of(result):
    return " ".join(c.text for c in result.content if c.type == "text")


def test_a_page_is_scaled_to_fit_the_image_limit():
    score = MockScore(staves=1, measures=4)
    score.page_size = (100, 200)
    score.measure_boxes = [(0, 10 + 20 * i, 20, 20, 20) for i in range(4)]

    async def scenario(c, mock):
        result = await c.call_tool("render", {})
        assert image_of(result).size == (784, 1568)
        assert "Page 1 of 1" in text_of(result)

    run_with_mock(scenario, score)


def colour_at(image, x, y, top):
    """Return "grey" or "white": the colour at (x, y) staff spaces.

    The image is a crop of two_systems_score's systems, which span x 8-92 with
    their margins, from y top, fitted from 25 px per staff space; the mock draws
    each measure's box grey.
    """
    scale = image.width / (84 * 25)
    r, g, b = image.convert("RGB").getpixel(
        (int((x - 8) * 25 * scale), int((y - top) * 25 * scale))
    )
    return "white" if min(r, g, b) > 250 else "grey"


def test_measures_are_cropped_in_place_with_the_rest_of_their_system_blank():
    async def scenario(c, mock):
        result = await c.call_tool("render", {"measures": "2-3"})
        image = image_of(result)
        # System x 10-90 and y 10-30 sp with 2 sp margins: 2100×600 px, fitted.
        assert image.size == (1568, 448)
        # Bars 2-3 where they stand on the system; bars 1 and 4 left blank.
        assert [colour_at(image, x, 20, top=8) for x in (20, 40, 60, 80)] == [
            "white",
            "grey",
            "grey",
            "white",
        ]
        assert "Measures 2-3 (page 1 of 1)" in text_of(result)

    run_with_mock(scenario, two_systems_score())


def test_a_crop_takes_in_everything_attached_to_its_measures():
    score = two_systems_score()
    score.content_boxes = {
        0: (12, 0, 4, 2),  # bar 1, not shown: no effect
        1: (32, 4, 6, 3),  # a chord symbol above bar 2
        2: (66, 2, 8, 4),  # a To Coda sign past the end of bar 3
    }

    async def scenario(c, mock):
        result = await c.call_tool("render", {"measures": "2-3"})
        # y 2-30 sp plus the margins: 84×32 sp, 2100×800 px, fitted.
        assert image_of(result).size == (1568, 597)

    run_with_mock(scenario, score)


def test_measures_across_two_systems_are_cropped_as_they_stand_on_the_page():
    async def scenario(c, mock):
        result = await c.call_tool("render", {"measures": "3-6"})
        image = image_of(result)
        # y 8-72 sp: both systems and the space between them, 2100×1600 px.
        assert image.size == (1568, 1194)
        assert [colour_at(image, x, 20, top=8) for x in (20, 60)] == [
            "white",
            "grey",
        ]
        assert [colour_at(image, x, 60, top=8) for x in (20, 60)] == [
            "grey",
            "white",
        ]

    run_with_mock(scenario, two_systems_score())


def test_what_stands_between_two_systems_is_shown_once():
    score = two_systems_score()
    score.content_boxes = {
        3: (70, 10, 20, 35),  # lyrics below bar 4, down to y 45
        4: (10, 35, 20, 35),  # a chord symbol above bar 5, from y 35
    }

    async def scenario(c, mock):
        result = await c.call_tool("render", {"measures": "3-6"})
        # Still y 8-72 sp: the space between the systems is not repeated.
        assert image_of(result).size == (1568, 1194)

    run_with_mock(scenario, score)


def test_a_crop_stops_at_the_notes_of_the_system_above():
    score = two_systems_score()
    score.content_boxes = {4: (10, 20, 20, 50)}  # reaches up into system 1

    async def scenario(c, mock):
        result = await c.call_tool("render", {"measures": "5-6"})
        # From system 1's bottom (y 30) to y 72: 84×42 sp, 2100×1050 px.
        assert image_of(result).size == (1568, 784)

    run_with_mock(scenario, score)


def test_a_page_that_does_not_exist_is_refused():
    async def scenario(c, mock):
        result = await c.call_tool("render", {"page": 3}, raise_on_error=False)
        assert result.is_error
        assert "Page 3 does not exist: the score has 1 page" in (
            result.content[0].text
        )

    run_with_mock(scenario, two_systems_score())


def test_measures_hidden_in_a_multi_measure_rest_are_refused():
    score = two_systems_score()
    score.measure_boxes[2] = None  # inside a multi-measure rest: not laid out

    async def scenario(c, mock):
        result = await c.call_tool(
            "render", {"measures": "2-3"}, raise_on_error=False
        )
        assert result.is_error
        assert "Measure 3 is inside a multi-measure rest" in (
            result.content[0].text
        )

    run_with_mock(scenario, score)


def test_the_caption_gives_printed_bar_numbers_when_they_differ():
    score = two_systems_score()
    score.irregular = {1}  # a pickup bar: bar 2 is printed as bar 1

    async def scenario(c, mock):
        result = await c.call_tool("render", {"measures": "3-6"})
        assert "Measures 3-6 (printed bars 2-5, page 1 of 1)" in text_of(result)

    run_with_mock(scenario, score)
