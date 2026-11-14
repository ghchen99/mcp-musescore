"""Edit the texts of a score's frames.

The title frame at the top, a notes frame at the end and a song structure page after it (a text frame that
starts a new page: the frame or bar before it carries a page break).

Frames (VBox, TBox) live only in the first staff's body, between its measures. The plugin API
cannot reach them (measure navigation skips frames, Score.addText only adds), so they are edited
in the file.
"""

import textwrap
import xml.etree.ElementTree as ET
from itertools import zip_longest
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..utils.sections import count_bars, count_label
from .score_file import ScoreFile

# Tool field -> MuseScore text style of the title frame text
HEADER_STYLES = {
    "title": "title",
    "subtitle": "subtitle",
    "composer": "composer",
    "lyricist": "lyricist",
    "part_name": "instrument_excerpt",
}
NOTES_STYLE = "frame"
TABLE_FONT = "DejaVu Sans Mono"  # columns line up only in a monospaced font
TABLE_WIDTH = 84  # characters per line at 10 pt across an A4/Letter page
NBSP = "\u00a0"  # padding that MuseScore never collapses


def _first_staff(score: ScoreFile) -> ET.Element:
    """Return the first staff of the score, where the frames live.

    Args:
        score (ScoreFile): The score.

    Returns:
        staff (ET.Element): The first <Staff> of the score body.
    """
    return score.staves()[0]


def title_frame(score: ScoreFile, create: bool = True) -> Optional[ET.Element]:
    """Return the title frame: the vertical frame before the first measure.

    Args:
        score (ScoreFile): The score.
        create (bool): Whether to create the frame if the score has none.

    Returns:
        vbox (Optional[ET.Element]): The <VBox> element, or None if there is
            none and `create` is False.
    """
    staff = _first_staff(score)
    first = next(iter(staff), None)
    if first is not None and first.tag == "VBox":
        return first
    if not create:
        return None
    vbox = ET.Element("VBox")
    ET.SubElement(vbox, "height").text = "10"
    staff.insert(0, vbox)
    return vbox


def header_texts(score: ScoreFile) -> Dict[str, str]:
    """Return the current title frame texts, by tool field name.

    Args:
        score (ScoreFile): The score.

    Returns:
        texts (Dict[str, str]): Plain text (markup removed) per field, e.g.
            {"title": ..., "composer": ...}; fields without a text are left out.
    """
    vbox = title_frame(score, create=False)
    found = {}
    if vbox is not None:
        by_style = {style: field for field, style in HEADER_STYLES.items()}
        for text in vbox.findall("Text"):
            style = text.findtext("style")
            field = by_style.get(style) if style is not None else None
            if field:
                found[field] = plain_text(text.find("text"))
    return found


def set_header(score: ScoreFile, **fields: Optional[str]) -> Dict[str, str]:
    """Set texts of the title frame.

    The frame is created when a text is added to a score without one.

    Args:
        score (ScoreFile): The score.
        **fields (Optional[str]): The new text per field (title, subtitle,
            composer, lyricist, part_name). None keeps a text, "" removes it.

    Returns:
        changes (Dict[str, str]): "set", "added" or "removed" per field that
            changed.
    """
    changes = {}
    for field, value in fields.items():
        if value is None:
            continue
        style = HEADER_STYLES[field]
        vbox = title_frame(score, create=bool(value))
        if vbox is None:
            continue
        existing = [
            t for t in vbox.findall("Text") if t.findtext("style") == style
        ]
        if value == "":
            for text in existing:
                vbox.remove(text)
            if existing:
                changes[field] = "removed"
            continue
        if existing:
            for extra in existing[1:]:
                vbox.remove(extra)
            node = existing[0].find("text")
            if node is None:
                node = ET.SubElement(existing[0], "text")
            for child in list(node):
                node.remove(child)
            node.text = value
            changes[field] = "set"
        else:
            text = ET.SubElement(vbox, "Text")
            ET.SubElement(text, "style").text = style
            ET.SubElement(text, "text").text = value
            changes[field] = "added"
    return changes


def plain_text(node: Optional[ET.Element]) -> str:
    """Return the text of a <text> element, without its markup.

    Args:
        node (Optional[ET.Element]): The <text> element, or None.

    Returns:
        text (str): The text, with <br/> as newlines; "" for None.
    """
    if node is None:
        return ""
    parts = [node.text or ""]
    for child in node:
        parts.append("\n" if child.tag == "br" else plain_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def _is_page_break(element: ET.Element) -> bool:
    """Check whether a measure or frame carries a page break.

    Args:
        element (ET.Element): The measure or frame.

    Returns:
        has_break (bool): True if it has a page <LayoutBreak>.
    """
    return any(
        b.findtext("subtype") == "page" for b in element.findall("LayoutBreak")
    )


def _set_page_break(element: ET.Element, on: bool) -> None:
    """Add or remove the page break of a measure or frame.

    Args:
        element (ET.Element): The measure or frame.
        on (bool): True to give it a page break, False to remove it.
    """
    for brk in [
        b
        for b in element.findall("LayoutBreak")
        if b.findtext("subtype") == "page"
    ]:
        element.remove(brk)
    if on:
        brk = ET.Element("LayoutBreak")
        ET.SubElement(brk, "subtype").text = "page"
        if element.tag == "Measure":
            element.insert(0, brk)
        else:
            element.append(brk)


def _end(
    staff: ET.Element,
) -> Tuple[List[ET.Element], int, Optional[ET.Element]]:
    """Return the parts of the first staff that matter at its end.

    The structure frame is a text frame that ends the staff, after a frame or
    bar with a page break.

    Args:
        staff (ET.Element): The first staff.

    Returns:
        end (Tuple[List[ET.Element], int, Optional[ET.Element]]): The staff's
            children, the index of its last measure (-1 if none), and the
            structure frame or None.
    """
    children = list(staff)
    last_measure = max(
        (i for i, c in enumerate(children) if c.tag == "Measure"), default=-1
    )
    structure = None
    if (
        len(children) - 1 > last_measure >= 0
        and children[-1].tag == "TBox"
        and _is_page_break(children[-2])
    ):
        structure = children[-1]
    return children, last_measure, structure


def _trailing_notes_frames(staff: ET.Element) -> List[ET.Element]:
    """Return the text frames after the last measure, except the structure page.

    Args:
        staff (ET.Element): The first staff.

    Returns:
        frames (List[ET.Element]): The notes frames (<TBox>), in order.
    """
    children, last_measure, structure = _end(staff)
    return [
        c
        for c in children[last_measure + 1 :]
        if c.tag == "TBox" and c is not structure
    ]


def _place_structure_break(staff: ET.Element) -> None:
    """Keep the page break only right before the structure page.

    Removes the page breaks from the last measure up to the structure page,
    except on the bar or frame right before it. Does nothing without a
    structure page.

    Args:
        staff (ET.Element): The first staff.
    """
    children, last_measure, structure = _end(staff)
    if structure is None:
        return
    for child in children[last_measure:-2]:
        _set_page_break(child, False)


class _Rich:
    """Builds MuseScore rich text (mixed XML content) inside a <text> element.

    Attributes:
        node (ET.Element): The <text> element being built.
        last (Optional[ET.Element]): The last element added, whose tail takes
            the next text; None before the first one.
    """

    def __init__(self, node: ET.Element) -> None:
        """Start building rich text in an element.

        Args:
            node (ET.Element): The <text> element to build in.
        """
        self.node, self.last = node, None

    def text(self, value: str) -> None:
        """Append plain text after what was added so far.

        Args:
            value (str): The text; an empty string adds nothing.
        """
        if not value:
            return
        if self.last is None:
            self.node.text = (self.node.text or "") + value
        else:
            self.last.tail = (self.last.tail or "") + value

    def tag(self, name: str, value: str = "", **attrib: str) -> None:
        """Append an element, such as <b>, <br/> or <font>.

        Args:
            name (str): The element's tag.
            value (str): The element's text. Defaults to no text.
            **attrib (str): The element's attributes, e.g. size="12".
        """
        self.last = ET.SubElement(self.node, name, attrib)
        if value:
            self.last.text = value


def end_notes(score: ScoreFile) -> List[str]:
    """Return the lines of the notes frames after the last measure.

    Args:
        score (ScoreFile): The score.

    Returns:
        lines (List[str]): The non-empty lines as plain text, headings
            included.
    """
    lines = []
    for frame in _trailing_notes_frames(_first_staff(score)):
        lines += [
            line
            for line in plain_text(frame.find("Text/text")).split("\n")
            if line.strip()
        ]
    return lines


def set_end_notes(
    score: ScoreFile, heading: str, lines: List[str], append: bool = False
) -> Dict[str, Any]:
    """Put a notes frame after the last measure: a bold heading and lines.

    Text frames already after the last measure are replaced (the structure page stays after them), so
    running it again updates the notes; `previous` in the report lists what they said. With `append`, their
    lines (except the old heading) are kept before the new ones. An empty heading and no lines removes them.

    Args:
        score (ScoreFile): The score.
        heading (str): The bold heading, or "" for none.
        lines (List[str]): The lines below the heading, one per item.
        append (bool): Whether to keep the lines of the existing notes before
            the new ones.

    Returns:
        report (Dict[str, Any]): "replaced" (the number of frames replaced),
            "lines" (the number of lines written) and "previous" (the lines
            the old frames held).
    """
    staff = _first_staff(score)
    old = _trailing_notes_frames(staff)
    printed = end_notes(score)
    if append:
        old_lines = (
            printed[1:]
            if printed and old and old[0].find("Text/text/b") is not None
            else printed
        )
        lines = old_lines + [line for line in lines if line not in old_lines]
    structure = _end(staff)[2]
    for frame in old:
        staff.remove(frame)
    if not heading and not lines:
        if structure is not None:
            _set_page_break(list(staff)[-2], True)
        _place_structure_break(staff)
        return {"replaced": len(old), "lines": 0, "previous": printed}

    frame = ET.Element("TBox")
    if structure is not None:
        staff.insert(list(staff).index(structure), frame)
        _set_page_break(frame, True)
    else:
        staff.append(frame)
    text = ET.SubElement(frame, "Text")
    ET.SubElement(text, "style").text = NOTES_STYLE
    node = ET.SubElement(text, "text")
    # Line breaks are <br/> elements, as MuseScore writes them
    previous = None
    if heading:
        previous = ET.SubElement(node, "b")
        previous.text = heading
    for i, line in enumerate(lines):
        if previous is not None or i > 0:
            previous = ET.SubElement(node, "br")
            previous.tail = line
        else:
            node.text = line
    _place_structure_break(staff)
    return {"replaced": len(old), "lines": len(lines), "previous": printed}


STRUCTURE_COLUMNS = [
    ("section", "Section"),
    ("bars", "Bars"),
    ("groove", "Groove"),
    ("fill", "Fills"),
]
MIN_COLUMN = 10  # a column is never wrapped narrower than this
ROW_GAP = "5"  # font size of the spacer line between rows: half a line of space, so rows are easy to tell apart


def _bars_cell(row: Dict[str, Any]) -> str:
    """Return the Bars cell of a structure row: the count label the chart shows.

    Args:
        row (Dict[str, Any]): The structure row; its `count` is used, or else
            its `bars` (a number of bars is written in fours, e.g. "2x4+2").

    Returns:
        cell (str): The text of the Bars cell.
    """
    if row.get("count"):
        return str(row["count"])
    bars = row.get("bars")
    n = count_bars(bars) if bars is not None else None
    return (
        count_label(n)
        if n is not None
        and (isinstance(bars, int) or str(bars).strip().isdigit())
        else str(bars or "")
    )


def _row_bars(row: Dict[str, Any]) -> Optional[int]:
    """Return how many bars a structure row lasts, as played.

    Args:
        row (Dict[str, Any]): The structure row.

    Returns:
        bars (Optional[int]): Its `bars` if that is a number, else what its
            count label adds up to, or None if neither gives a number.
    """
    bars = row.get("bars")
    if isinstance(bars, int) or (
        isinstance(bars, str) and bars.strip().isdigit()
    ):
        return int(bars)
    return (
        count_bars(row.get("count") or bars)
        if (row.get("count") or bars)
        else None
    )


def structure_table(
    rows: Sequence[Dict[str, Any]], width: int = TABLE_WIDTH
) -> List[List[str]]:
    """Lay out the song structure as a table, in lines of cells.

    A header line, then each row (wrapped cells give extra lines; the last line of a row has an extra empty
    cell). Columns that no row fills are left out; the widest columns are narrowed
    (their text wrapped) until a line fits in `width` characters.

    Args:
        rows (Sequence[Dict[str, Any]]): The structure rows: section, bars,
            count, groove, fill.
        width (int): The number of characters a line may take.

    Returns:
        lines (List[List[str]]): The table's lines, each a list of padded
            cells.
    """
    rows = [{**r, "bars": _bars_cell(r)} for r in rows]
    columns = [
        c
        for c in STRUCTURE_COLUMNS
        if c[0] in ("section", "bars")
        or any(str(r.get(c[0]) or "") for r in rows)
    ]
    widths = {
        key: max([len(title)] + [len(str(r.get(key) or "")) for r in rows])
        for key, title in columns
    }
    available = width - 2 * (len(columns) - 1)
    while sum(widths.values()) > available:
        key = max(
            (k for k, _ in columns if k != "bars"), key=lambda k: widths[k]
        )
        if widths[key] <= MIN_COLUMN:
            break
        widths[key] -= 1
    lines = [[title.ljust(widths[key]) for key, title in columns]]
    for row in rows:
        cells = [
            textwrap.wrap(
                str(row.get(key) or ""), widths[key], break_on_hyphens=False
            )
            or [""]
            for key, _ in columns
        ]
        for parts in zip_longest(*cells, fillvalue=""):
            lines.append(
                [
                    part.ljust(widths[key])
                    for part, (key, _) in zip(parts, columns)
                ]
            )
        lines[-1].append("")
    return lines


def set_structure_page(
    score: ScoreFile,
    heading: str,
    rows: Sequence[Dict[str, Any]],
    song: Optional[str] = None,
    artist: Optional[str] = None,
    font: str = TABLE_FONT,
) -> Dict[str, Any]:
    """Write the song structure as a table on a new page at the end.

    The page replaces an earlier one, and the table comes under the heading and a "song - artist" line (by default the title of the title frame, and its composer or,
    if there is none, its subtitle). The Bars column shows `count`
    (or `bars` in fours) and the total adds up the bars. No rows removes the page.

    Args:
        score (ScoreFile): The score.
        heading (str): The page heading.
        rows (Sequence[Dict[str, Any]]): The structure rows: section, bars,
            count, groove, fill.
        song (Optional[str]): The song name. Defaults to the title frame's
            title.
        artist (Optional[str]): The artist. Defaults to the title frame's
            composer, or else its subtitle.
        font (str): The monospaced font of the table, so its columns line up.

    Returns:
        report (Dict[str, Any]): "replaced" (1 if an earlier page was
            replaced, else 0) and "rows"; with rows, also "song" and
            "artist".
    """
    staff = _first_staff(score)
    children, last_measure, structure = _end(staff)
    if structure is not None:
        staff.remove(structure)
        _set_page_break(children[-2], False)
    if not rows:
        return {"replaced": int(structure is not None), "rows": 0}

    _set_page_break(list(staff)[-1], True)
    frame = ET.SubElement(staff, "TBox")
    text = ET.SubElement(frame, "Text")
    ET.SubElement(text, "style").text = NOTES_STYLE
    rich = _Rich(ET.SubElement(text, "text"))
    header = header_texts(score)
    song = header.get("title", "") if song is None else song
    artist = (
        (header.get("composer") or header.get("subtitle") or "")
        if artist is None
        else artist
    )
    rich.tag("font", size="16")
    rich.tag("b", heading)
    if song or artist:
        rich.tag("br")
        rich.tag("font", size="12")
        if song:
            rich.tag("b", song)
        rich.text(" \u2013 " + artist if song and artist else artist)
    rich.tag("br")
    rich.tag("br")
    rich.tag("font", size="10")
    rich.tag("font", face=font)

    table = structure_table(rows)
    header, body = table[0], table[1:]
    rich.tag("b", (NBSP * 2).join(header).rstrip().replace(" ", NBSP))
    rich.tag("br")
    rich.text("\u2500" * len("  ".join(header)))
    starts_row = True
    for cells in body:
        if starts_row:
            rich.tag("br")
            rich.tag("font", size=ROW_GAP)
            rich.text(NBSP)
            rich.tag("font", size="10")
        rich.tag("br")
        ends_row = len(cells) > len(header)
        cells = cells[: len(header)]
        first = cells[0].replace(" ", NBSP)
        if starts_row and first.strip(NBSP):
            rich.tag("b", first)
        else:
            rich.text(first)
        rich.text(
            (NBSP * 2 + (NBSP * 2).join(cells[1:])).rstrip().replace(" ", NBSP)
        )
        starts_row = ends_row
    bars = [_row_bars(r) for r in rows]
    counted_bars = [b for b in bars if b is not None]
    if bars and len(counted_bars) == len(bars):
        rich.tag("br")
        rich.tag("br")
        rich.text(f"Total: {sum(counted_bars)} bars")
    return {
        "replaced": int(structure is not None),
        "rows": len(rows),
        "song": song,
        "artist": artist,
    }
