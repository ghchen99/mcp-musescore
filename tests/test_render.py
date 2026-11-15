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


def test_measures_are_cropped_with_a_margin_around_them():
    async def scenario(c, mock):
        result = await c.call_tool("render", {"measures": "2-3"})
        # Bars 2-3 span x 30-70 and y 10-30 sp; 2 sp of margin each side.
        assert image_of(result).size == (1100, 600)
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
        # x 30-74 and y 2-30 sp, plus 2 sp of margin each side.
        assert image_of(result).size == (1200, 800)

    run_with_mock(scenario, score)


def test_measures_across_two_systems_are_stacked():
    async def scenario(c, mock):
        result = await c.call_tool("render", {"measures": "3-6"})
        # Bars 3-4 above bars 5-6, each 44×24 sp with the margins.
        assert image_of(result).size == (1100, 1200)

    run_with_mock(scenario, two_systems_score())


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
