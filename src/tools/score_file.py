"""Tools that edit the open score's file, for what the plugin API can't do.

The flow is: the plugin saves the score, the file is backed up and edited here, and the plugin
closes and reopens it. The tab shows the change, but MuseScore's undo history starts over, so
every edit keeps a backup that restore_backup can bring back.
"""

import asyncio
import re
import shutil
import time
from pathlib import Path
from typing import (
    Annotated,
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
)

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

from ..client import MuseScoreClient
from ..mscz import ScoreFile, ScoreFileError
from ..mscz import apply_measure_repeats as write_measure_repeats
from ..mscz.frames import header_texts, set_header, set_structure_page
from ..mscz.frames import set_end_notes as write_end_notes
from ..mscz.locate import (
    OpenPartError,
    backup_score,
    list_backups,
    locate_open_score,
    new_score_id,
    read_score_id,
    score_shape,
    write_score_id,
)
from ..mscz.measure_repeats import measure_lengths
from ..mscz.parts import detach_part, part_name
from ..mscz.rolls import simplify_roll as write_roll
from .formatting import drum_pitches

# Files found or created for each score ID during this server session
KNOWN_PATHS: Dict[str, Path] = {}

# Part files made by open_score_path(reopen_part=False) that are not open in MuseScore yet: the score to fall back
# to if MuseScore refuses them (the full score the part was open in)
PART_SOURCES: Dict[Path, Path] = {}

# MuseScore crashed when a score was closed again ~0.3 s after opening it (while Muse Sounds was still loading):
# reopens are spaced by at least this many seconds
REOPEN_GAP = 4.0
_last_reopen = 0.0


async def open_score_path(
    client: MuseScoreClient,
    score_path: Optional[str] = None,
    reopen_part: bool = True,
) -> Path:
    """Save the open score and return its file.

    The file is identified by the score ID the plugin keeps in its metadata. A file is only returned if it
    carries the open score's ID and has its number of staves and measures. If the open score is a part tab,
    the part becomes a file of its own; with reopen_part=False it is not opened yet (the caller edits it and
    reopens it once, see PART_SOURCES).

    Args:
        client (MuseScoreClient): The client to the plugin.
        score_path (Optional[str]): A score file given by the user, checked
            instead of searching.
        reopen_part (bool): Whether to open a part's new file right away.

    Returns:
        path (Path): The score file.

    Raises:
        ToolError: If the file cannot be found or does not match the open
            score.
    """
    score_id = (await client.request("ensureScoreId"))["scoreId"]
    await client.request("saveScore")
    info = await client.request("scoreFileInfo")
    known = [KNOWN_PATHS[score_id]] if score_id in KNOWN_PATHS else []
    try:
        path = locate_open_score(
            score_id,
            info.get("numStaves", 0),
            info.get("numMeasures", 0),
            explicit=score_path,
            known=known,
        )
    except OpenPartError as part:
        return await open_part_as_score(
            client,
            part.path,
            part.entry,
            (info.get("numStaves", 0), info.get("numMeasures", 0)),
            reopen_part,
        )
    except ScoreFileError as e:
        raise ToolError(str(e))
    KNOWN_PATHS[score_id] = path
    return path


def part_file_name(source: Path, name: str) -> Path:
    """Name the part's score file: <score> - <part>.mscz next to `source`.

    Numbered if taken. Long part names ("Player | Kit | Drums")
    are cut to their last segment; a score already named after the part (a Save As "... - Drums" of the
    full score) gives "... - Drums only".

    Args:
        source (Path): The score file that holds the part.
        name (str): The part's name.

    Returns:
        target (Path): A file name that is not taken yet.
    """
    label = (
        re.sub(r'[\\/:*?"<>|]+', "-", name.split("|")[-1]).strip(" -.")
        or "part"
    )
    stem = source.stem
    if stem.lower().endswith(f" - {label.lower()}"):
        stem, label = stem[: -len(label) - 3], f"{label} only"
    target = source.with_name(f"{stem} - {label}.mscz")
    n = 2
    while target.exists():
        target = source.with_name(f"{stem} - {label} ({n}).mscz")
        n += 1
    return target


async def open_part_as_score(
    client: MuseScoreClient,
    source: Path,
    entry: str,
    shape: Tuple[int, int],
    reopen: bool = True,
) -> Path:
    """Open a part tab of `source` as a score file of its own.

    The open score is a part tab of `source`: file edits can't touch a part alone (it is linked to the full
    score), so the part becomes a score file of its own, opened in place of the full score (now, or by the
    caller's own reopen after its edit when `reopen` is False). The full score is backed up first.

    Args:
        client (MuseScoreClient): The client to the plugin.
        source (Path): The score file that holds the part.
        entry (str): The part's archive entry (Excerpts/...mscx).
        shape (Tuple[int, int]): The open score's staves and measures, to
            check the new file against.
        reopen (bool): Whether to open the new file right away.

    Returns:
        target (Path): The new score file.

    Raises:
        ToolError: If the part's file does not match the open score, or
            MuseScore does not reopen it.
    """
    target = part_file_name(source, part_name(source, entry))
    detach_part(source, entry, target)
    if score_shape(target) != tuple(shape):
        found = score_shape(target)
        target.unlink()
        raise ToolError(
            f"The open score is a part of {source.name}, but the saved part has {found[0]} staves and "
            f"{found[1]} bars instead of {shape[0]} and {shape[1]}; nothing was changed."
        )
    backup_score(source)
    score_id = new_score_id()
    write_score_id(target, score_id)
    KNOWN_PATHS[score_id] = target
    if not reopen:
        PART_SOURCES[target] = source
        return target
    reopened = await reopen_in_place(client, target, fallback=source)
    if not reopened["reopened"]:
        raise ToolError(
            f"The open score was a part of {source.name}; it was saved as {target}, but "
            f"{reopened['next_step']}"
        )
    return target


async def reopen_in_place(
    client: MuseScoreClient, path: Path, fallback: Optional[Path] = None
) -> Dict:
    """Close the open score and open a file in the same window.

    MuseScore 4 opens a second score in a new window, out of the plugin's reach, so the current score is
    closed first. Afterwards the score ID now open is compared with the one stored in the file, to check
    that the plugin is attached to it. If `path` cannot be opened, the plugin reopens `fallback` (default:
    `path` itself, i.e. the score just closed). Reopens are spaced by REOPEN_GAP seconds.

    Args:
        client (MuseScoreClient): The client to the plugin.
        path (Path): The score file to open.
        fallback (Optional[Path]): The file to reopen if `path` cannot be
            opened.

    Returns:
        result (Dict): "reopened" (bool), and if False a "next_step" telling
            the user what to do.
    """
    global _last_reopen
    expected = read_score_id(path)
    fallback = fallback or PART_SOURCES.pop(path, None)
    params = {"path": str(path), "fallbackPath": str(fallback or path)}
    wait = _last_reopen + REOPEN_GAP - time.monotonic()
    if wait > 0:
        await asyncio.sleep(wait)
    res = await client.send_command("reopenScore", params)
    _last_reopen = time.monotonic()
    result = res.get("result")
    if isinstance(result, dict) and result.get("success"):
        info = (await client.send_command("scoreFileInfo")).get("result") or {}
        if not expected or info.get("scoreId") == expected:
            return {"reopened": True}
    return {
        "reopened": False,
        "next_step": (
            f"MuseScore did not reopen {path} where the plugin can reach it. In MuseScore, close any score "
            f"without saving, open {path} (File > Open Recent) and run Plugins > MuseScore API Server again."
        ),
    }


class RepeatGroup(BaseModel):
    start: int = Field(
        description="First measure to turn into repeat signs (1-based)"
    )
    end: Optional[int] = Field(
        None,
        description="Last measure (1-based, inclusive). Defaults to start + bars - 1.",
    )
    bars: Literal[1, 2, 4] = Field(
        1,
        description="Size of each sign: 1, 2 or 4 bars; start..end is split into signs of this size",
    )


def split_groups(groups: List[RepeatGroup]) -> List[tuple]:
    """Split the requested runs of bars into single measure-repeat signs.

    Args:
        groups (List[RepeatGroup]): The requested runs.

    Returns:
        pairs (List[tuple]): The (first measure, size) of every sign.

    Raises:
        ToolError: If a run cannot be split into signs of its size.
    """
    pairs = []
    for g in groups:
        end = g.end if g.end is not None else g.start + g.bars - 1
        length = end - g.start + 1
        if length < 1 or length % g.bars:
            raise ToolError(
                f"Measures {g.start}-{end} cannot be split into {g.bars}-bar repeat signs"
            )
        pairs += [(start, g.bars) for start in range(g.start, end + 1, g.bars)]
    return pairs


def setup_score_file_tools(mcp: FastMCP, client: MuseScoreClient) -> None:
    """Register the tools that edit the score file on disk.

    Args:
        mcp (FastMCP): The server to register the tools on.
        client (MuseScoreClient): The client the tools send their commands
            through.
    """

    async def reopen(path: Path) -> Dict:
        """Reopen a file in place of the open score, through this client.

        Args:
            path (Path): The score file to open.

        Returns:
            result (Dict): The result of reopen_in_place.
        """
        return await reopen_in_place(client, path)

    async def edit_file(
        score_path: Optional[str],
        edit: Callable[[ScoreFile], Tuple[bool, Dict]],
    ) -> Dict:
        """Apply an edit to the open score's file, then back up and reload.

        The open score is saved first. If the edit changed the score, the old
        file is backed up and the new one written and reopened in MuseScore.

        Args:
            score_path (Optional[str]): A score file given by the user.
                Defaults to the open score's own file.
            edit (Callable[[ScoreFile], Tuple[bool, Dict]]): The edit; it
                returns whether it changed the score, and its report.

        Returns:
            result (Dict): The edit's report, with "file", and if changed
                "backup", "reopened" and "undo"; else a "message".

        Raises:
            ToolError: If the file cannot be found or the edit fails.
        """
        # A part tab becomes a file of its own: edit that file first, then open it once (two quick reopens
        # crashed MuseScore)
        path = await open_score_path(client, score_path, reopen_part=False)
        try:
            score = ScoreFile(path)
            changed, report = edit(score)
        except ScoreFileError as e:
            if path in PART_SOURCES:
                await reopen(path)
            raise ToolError(str(e))
        result = {"file": str(path), **report}
        if not changed:
            if path in PART_SOURCES:
                result.update(await reopen(path))
            result["message"] = "Nothing to change; the score was not reloaded."
            return result

        result["backup"] = str(backup_score(path))
        score.save()
        result.update(await reopen(path))
        result["undo"] = (
            "restore_backup() brings back the version before this change."
        )
        return result

    @mcp.tool(
        description=(
            "Turn bars of one staff into measure-repeat signs (1-, 2- or 4-bar) automatically. MuseScore's plugin "
            "API cannot place these signs, so this saves the score, backs the file up, writes the signs into the "
            "file and reloads it in MuseScore. The reload resets MuseScore's undo history: use restore_backup to undo. "
            "Each sign repeats the bars just before it, and the replaced bars' notes are deleted. Bars with ties or "
            "slurs crossing their barlines are skipped and reported. Pass all groups for a staff in one call."
        ),
        tags={"structure"},
    )
    async def apply_measure_repeats(
        staff: Annotated[int, "Staff index (0-based)"],
        groups: Annotated[
            List[RepeatGroup],
            'Runs of bars to replace, e.g. [{"start": 7, "end": 12, "bars": 1}]',
        ],
        score_path: Annotated[
            Optional[str],
            "Path of the score file. Defaults to the file of the score open in MuseScore.",
        ] = None,
    ):
        pairs = split_groups(groups)

        def edit(score: ScoreFile):
            """Write the measure-repeat signs into the score.

            Args:
                score (ScoreFile): The score.

            Returns:
                outcome (Tuple[bool, Dict]): Whether a group was applied, and
                    the report.
            """
            report = write_measure_repeats(score, staff, pairs)
            return bool(report["applied"]), report

        return await edit_file(score_path, edit)

    @mcp.tool(
        description=(
            "Rewrite a cymbal roll (a run of repeated or tied cymbal notes, e.g. a crash swell) as one long note "
            "per bar, tied across barlines, with a tremolo: the same sound with far fewer symbols. The roll starts "
            "on start_beat of start_measure (default beat 1; earlier notes in that bar stay as written) and ends "
            "at the end of end_measure, or after end_beat in it. Lengths that no single note value can hold are "
            "written as tied notes. Notes of the first chord that are not part of the roll (e.g. a kick) move to "
            "voice 2 with their own length. Refuses (changing nothing) if other notes or rests sit inside the roll "
            "or it doesn't start and end where notes do. Edits the score file and reloads it (undo with restore_backup)."
        ),
        tags={"formatting"},
    )
    async def simplify_roll(
        staff: Annotated[int, "Staff index (0-based)"],
        start_measure: Annotated[int, "Bar the roll starts in"],
        end_measure: Annotated[int, "Bar the roll ends in"],
        end_beat: Annotated[
            Optional[float],
            "Last beat of the roll in end_measure, inclusive (a beat is the time signature's denominator, e.g. an "
            "eighth in 12/8, so the first two dotted quarters are end_beat=6). Defaults to the end of the bar.",
        ] = None,
        drums: Annotated[
            List[str], 'Drums that roll, e.g. ["crash"] or ["ride"]'
        ] = ["crash"],
        pitches: Annotated[
            Optional[List[int]], "MIDI pitches that roll, instead of drums"
        ] = None,
        slashes: Annotated[int, "Tremolo slashes (3 = a roll)"] = 3,
        start_beat: Annotated[
            float,
            "Beat of start_measure where the roll starts (1-based, same beat unit as end_beat, so 7 is the 7th "
            "eighth in 12/8; fractions allowed). Defaults to 1.",
        ] = 1,
        score_path: Annotated[
            Optional[str],
            "Path of the score file. Defaults to the file of the score open in MuseScore.",
        ] = None,
    ):
        roll_pitches = pitches or drum_pitches(drums)

        def edit(score: ScoreFile):
            """Rewrite the roll in the score.

            Args:
                score (ScoreFile): The score.

            Returns:
                outcome (Tuple[bool, Dict]): True, and the report.

            Raises:
                ToolError: If the staff or measure range does not exist.
            """
            if not 0 <= staff < len(score.staves()):
                raise ToolError(f"Staff {staff} does not exist")
            signatures = measure_lengths(
                score.staves()[staff], score.staves()[0]
            )
            if not 1 <= start_measure <= end_measure <= len(signatures):
                raise ToolError(
                    f"Invalid measure range {start_measure}-{end_measure}"
                )

            def beat_ticks(measure: int):
                """Return the length of a beat in a measure, in ticks.

                Args:
                    measure (int): The measure, 1-based.

                Returns:
                    ticks (float): The ticks of one beat (the time
                        signature's denominator).
                """
                return 1920 / int(signatures[measure - 1].split("/")[1])

            end_ticks = (
                round(end_beat * beat_ticks(end_measure))
                if end_beat is not None
                else None
            )
            start_ticks = round((start_beat - 1) * beat_ticks(start_measure))
            return True, write_roll(
                score,
                staff,
                start_measure,
                end_measure,
                end_ticks,
                roll_pitches,
                slashes,
                start_ticks,
            )

        return await edit_file(score_path, edit)

    @mcp.tool(
        description=(
            "Tidy the title frame at the top of the score: title, subtitle, composer, lyricist and the part name "
            "shown top-left in part scores (a long part name such as 'Player | Kit | Drums' runs into the title). "
            "Leave a field out to keep it, pass an empty string to remove it. Edits the score file and reloads it "
            "(undo with restore_backup)."
        ),
        tags={"formatting"},
    )
    async def set_score_header(
        title: Annotated[Optional[str], "Title (e.g. the song name)"] = None,
        subtitle: Annotated[
            Optional[str], 'Subtitle (e.g. "Drum chart")'
        ] = None,
        composer: Annotated[
            Optional[str], "Composer / artist, shown top-right"
        ] = None,
        lyricist: Annotated[
            Optional[str], "Lyricist, shown top-left under the part name"
        ] = None,
        part_name: Annotated[
            Optional[str],
            'Part name shown top-left (e.g. "Drums"); "" removes it',
        ] = None,
        score_path: Annotated[
            Optional[str],
            "Path of the score file. Defaults to the file of the score open in MuseScore.",
        ] = None,
    ):
        fields = {
            "title": title,
            "subtitle": subtitle,
            "composer": composer,
            "lyricist": lyricist,
            "part_name": part_name,
        }
        if all(v is None for v in fields.values()):
            raise ToolError(
                "Pass at least one of title, subtitle, composer, lyricist, part_name"
            )

        def edit(score: ScoreFile):
            """Set the title frame texts in the score.

            Args:
                score (ScoreFile): The score.

            Returns:
                outcome (Tuple[bool, Dict]): Whether a text changed, and the
                    changes and resulting header.
            """
            before = header_texts(score)
            changes = set_header(score, **fields)
            changed = any(
                header_texts(score).get(k) != before.get(k) for k in fields
            )
            return changed, {"changes": changes, "header": header_texts(score)}

        return await edit_file(score_path, edit)

    @mcp.tool(
        description=(
            "Print notes at the end of the score, in a text frame after the last bar: a bold heading and one line "
            "per item, e.g. a summary of how a chart differs from the original (what was collapsed, which "
            "differences were dropped, what stays written out). Replaces notes added before (the report's `previous` "
            "lists them), so it can be re-run; append=True keeps their lines and adds the new ones; no heading and "
            "no lines removes them. Edits the score file and reloads it (undo with restore_backup)."
        ),
        tags={"formatting"},
    )
    async def set_end_notes(
        lines: Annotated[
            List[str],
            'Lines of text, e.g. ["Verses 1-3: groove x9 each", "Dropped: open-hat endings"]',
        ],
        heading: Annotated[
            str, "Bold heading above the lines"
        ] = "Changes from the original",
        append: Annotated[
            bool,
            "Keep the lines already printed and add these after them (skipping repeats), e.g. when finishing a chart made in an earlier session",
        ] = False,
        score_path: Annotated[
            Optional[str],
            "Path of the score file. Defaults to the file of the score open in MuseScore.",
        ] = None,
    ):
        def edit(score: ScoreFile):
            """Write the end notes into the score.

            Args:
                score (ScoreFile): The score.

            Returns:
                outcome (Tuple[bool, Dict]): True, and the report.
            """
            report = write_end_notes(score, heading, lines, append)
            return True, report

        return await edit_file(score_path, edit)

    @mcp.tool(
        description=(
            "Print the song structure as a table on a new page at the end of the score, after the end notes: the "
            "song and artist under the heading (taken from the title frame unless given), then one row per section "
            "with its bars (as played), groove and fills, and the total. Get the rows from song_structure and give "
            "grooves and fills musical names. Replaces a structure page added "
            "before; no rows removes it. Edits the score file and reloads it (undo with restore_backup)."
        ),
        tags={"formatting"},
    )
    async def set_song_structure(
        rows: Annotated[
            List[Dict[str, Any]],
            'One per section: {"section": "Verse 1", "bars": 16, "groove": "Verse '
            'shuffle", "fill": "Tom fill into chorus"}',
        ],
        heading: Annotated[str, "Page heading"] = "Song structure",
        song: Annotated[
            Optional[str],
            "Song name under the heading. Defaults to the title in the title frame.",
        ] = None,
        artist: Annotated[
            Optional[str],
            "Artist next to the song name. Defaults to the composer in the title frame.",
        ] = None,
        score_path: Annotated[
            Optional[str],
            "Path of the score file. Defaults to the file of the score open in MuseScore.",
        ] = None,
    ):
        for row in rows:
            if (
                not isinstance(row, dict)
                or not str(row.get("section") or "").strip()
            ):
                raise ToolError(f"Every row needs a section name: {row!r}")

        def edit(score: ScoreFile):
            """Write the song structure page into the score.

            Args:
                score (ScoreFile): The score.

            Returns:
                outcome (Tuple[bool, Dict]): True, and the report.
            """
            return True, set_structure_page(score, heading, rows, song, artist)

        return await edit_file(score_path, edit)

    @mcp.tool(
        description=(
            "Bring back the version of the open score saved before an apply_measure_repeats edit (the newest backup "
            "by default) and reload it in MuseScore. The current version is backed up first."
        ),
        tags={"structure"},
    )
    async def restore_backup(
        backup: Annotated[
            Optional[str],
            "Backup file to restore. Defaults to the newest backup of this score.",
        ] = None,
        score_path: Annotated[
            Optional[str],
            "Path of the score file. Defaults to the file of the score open in MuseScore.",
        ] = None,
    ):
        path = await open_score_path(client, score_path)
        if backup:
            source = Path(backup).expanduser()
            if not source.is_file():
                raise ToolError(f"Backup not found: {source}")
            if source.suffix.lower() != path.suffix.lower():
                raise ToolError(
                    f"{source.name} is not a {path.suffix} file: open it in MuseScore with File > Open"
                )
        else:
            backups = list_backups(path)
            if not backups:
                raise ToolError(f"No backups of {path.name} found")
            source = backups[0]

        current = backup_score(path)
        shutil.copy2(source, path)
        return {
            "file": str(path),
            "restored": str(source),
            "previous_version_backup": str(current),
            **(await reopen(path)),
        }
