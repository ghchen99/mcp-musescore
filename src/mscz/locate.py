"""Find the file behind the open score, and back it up before editing.

The plugin API does not expose a score's path. The plugin stores an ID in the
score's metadata (ensureScoreId) and saves it; the file is then looked up among
the paths the server already knows and MuseScore's open (session/session.json)
and recent (recent_files.json) files, by that ID.
"""

import json
import os
import re
import shutil
import uuid
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .score_file import ScoreFile, ScoreFileError

SCORE_SUFFIXES = (".mscz", ".mscx")


def musescore_data_dirs() -> List[Path]:
    """Return MuseScore 4's data folders on Linux, macOS and Windows.

    Returns:
        dirs (List[Path]): The folders to look in; only MUSESCORE_DATA_DIR if
            that variable is set.
    """
    if os.environ.get("MUSESCORE_DATA_DIR"):
        return [Path(os.environ["MUSESCORE_DATA_DIR"])]
    home = Path.home()
    dirs = [
        home / ".local" / "share" / "MuseScore" / "MuseScore4",
        home / "Library" / "Application Support" / "MuseScore" / "MuseScore4",
    ]
    if os.environ.get("LOCALAPPDATA"):
        dirs.append(
            Path(os.environ["LOCALAPPDATA"]) / "MuseScore" / "MuseScore4"
        )
    return dirs


def _listed_paths(path: Path) -> List[Path]:
    """Read the file paths listed in one of MuseScore's JSON files.

    Handles both a plain list of paths and a list of objects with a "path" or
    "filePath" key, as in session.json and recent_files.json.

    Args:
        path (Path): The JSON file.

    Returns:
        paths (List[Path]): The listed paths; empty if the file is missing or
            not valid JSON.
    """
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    paths = []
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict):
            entry = entry.get("path") or entry.get("filePath")
        if isinstance(entry, str):
            paths.append(Path(entry))
    return paths


SCORE_ID_TAG = "mcpScoreId"
_SCORE_ID = re.compile(rb'<metaTag name="mcpScoreId">([^<]*)</metaTag>')


def read_score_id(path: Path) -> Optional[str]:
    """Read the score ID the plugin stores in a score's metadata.

    Args:
        path (Path): The score file, .mscz or .mscx.

    Returns:
        score_id (Optional[str]): The value of the `mcpScoreId` meta tag, or
            None if the file has none or cannot be read.
    """
    try:
        if path.suffix.lower() == ".mscx":
            data = path.read_bytes()
        else:
            with zipfile.ZipFile(path) as z:
                names = [
                    n
                    for n in z.namelist()
                    if n.endswith(".mscx") and "/" not in n
                ]
                data = z.read(names[0]) if names else b""
    except (OSError, zipfile.BadZipFile):
        return None
    match = _SCORE_ID.search(data)
    return match.group(1).decode("utf-8") if match else None


def part_with_score_id(path: Path, score_id: str) -> Optional[str]:
    """Find the part score in a .mscz that carries a score ID.

    A score ID lands in a part when the plugin runs while a part's tab is open
    in MuseScore.

    Args:
        path (Path): The score file.
        score_id (str): The score ID to look for.

    Returns:
        entry (Optional[str]): The archive entry of the part score
            (Excerpts/...mscx), or None if no part carries the ID or the file is
            not a .mscz.
    """
    if path.suffix.lower() != ".mscz":
        return None
    try:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.startswith("Excerpts/") and name.endswith(".mscx"):
                    match = _SCORE_ID.search(z.read(name))
                    if match and match.group(1).decode("utf-8") == score_id:
                        return name
    except (OSError, zipfile.BadZipFile):
        return None
    return None


class OpenPartError(ScoreFileError):
    """The open score is a part (excerpt) stored inside another score's file.

    Attributes:
        path (Path): The score file that holds the part.
        entry (str): The part's archive entry in that file.
    """

    def __init__(self, path: Path, entry: str) -> None:
        """Record the score file and the part's entry in it.

        Args:
            path (Path): The score file that holds the part.
            entry (str): The part's archive entry in that file.
        """
        super().__init__(f"The open score is the part {entry} of {path}")
        self.path, self.entry = path, entry


def new_score_id() -> str:
    """Make a new ID to tag a score with.

    Returns:
        score_id (str): "mcp-" and 12 random hex digits, e.g.
            "mcp-1a2b3c4d5e6f".
    """
    return f"mcp-{uuid.uuid4().hex[:12]}"


def write_score_id(path: Path, score_id: str) -> None:
    """Store a score ID in a score file's metadata, and save the file.

    Any existing score ID is replaced.

    Args:
        path (Path): The score file.
        score_id (str): The score ID to store.
    """
    score = ScoreFile(path)
    for tag in score.score.findall("metaTag"):
        if tag.get("name") == SCORE_ID_TAG:
            score.score.remove(tag)
    tag = ET.Element("metaTag", {"name": SCORE_ID_TAG})
    tag.text = score_id
    score.score.insert(0, tag)
    score.save()


def score_shape(path: Path) -> Tuple[int, int]:
    """Count the staves and measures of a score file.

    Args:
        path (Path): The score file.

    Returns:
        shape (Tuple[int, int]): The number of staves and the number of measures
            (of the first staff).
    """
    staves = ScoreFile(path).staves()
    return len(staves), len(staves[0].findall("Measure")) if staves else 0


def candidate_files(known: Iterable[Path] = ()) -> List[Path]:
    """List the score files the open score may be saved in.

    Args:
        known (Iterable[Path]): Paths the server already knows, which come
            first.

    Returns:
        paths (List[Path]): `known`, then MuseScore's open and recent files:
            existing .mscz and .mscx files, without duplicates.
    """
    paths = list(known)
    for data_dir in musescore_data_dirs():
        paths += _listed_paths(data_dir / "session" / "session.json")
        paths += _listed_paths(data_dir / "recent_files.json")
    return [
        p
        for p in dict.fromkeys(paths)
        if p.suffix.lower() in SCORE_SUFFIXES and p.is_file()
    ]


def locate_open_score(
    score_id: str,
    staves: int,
    measures: int,
    explicit: Optional[str] = None,
    known: Iterable[Path] = (),
) -> Path:
    """Find the file of the score open in MuseScore, by its score ID.

    The score must have been saved just before, so that its file holds the ID.
    Among several files with the ID (copies made with Save As), the most
    recently saved wins. The file must also have the open score's number of
    staves and measures, otherwise nothing is edited.

    Args:
        score_id (str): The open score's score ID.
        staves (int): The open score's number of staves.
        measures (int): The open score's number of measures.
        explicit (Optional[str]): A score file given by the user, checked
            instead of searching.
        known (Iterable[Path]): Paths the server already knows, searched first.

    Returns:
        path (Path): The score file.

    Raises:
        OpenPartError: If the ID is found in a part inside a score file: the
            open score is that part.
        ScoreFileError: If no file with the ID is found, `explicit` does not
            exist or is another score, or the file's staves and measures do not
            match the open score.
    """
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ScoreFileError(f"Score file not found: {path}")
        candidates = [path]
    else:
        candidates = candidate_files(known)

    matches = [p for p in candidates if read_score_id(p) == score_id]
    if not matches:
        parts = [(p, part_with_score_id(p, score_id)) for p in candidates]
        parts = [(p, entry) for p, entry in parts if entry]
        if parts:
            raise OpenPartError(
                *max(parts, key=lambda pe: pe[0].stat().st_mtime)
            )
        if explicit:
            raise ScoreFileError(
                f"{candidates[0]} is not the file of the score open in MuseScore. Open that file in MuseScore "
                "(and run the plugin), or leave score_path out to use the open score's own file."
            )
        raise ScoreFileError(
            "Could not find the saved file of the score open in MuseScore. Save it once with File > Save "
            "(a new score has no file yet), or pass score_path."
        )
    path = max(matches, key=lambda p: p.stat().st_mtime)

    shape = score_shape(path)
    if shape != (staves, measures):
        raise ScoreFileError(
            f"{path} has {shape[0]} staves and {shape[1]} measures, but the open score has {staves} and "
            f"{measures}. Save the score in MuseScore and try again; nothing was changed."
        )
    return path


def backup_dir() -> Path:
    """Return the folder that backups go into.

    Returns:
        directory (Path): MCP_MUSESCORE_BACKUP_DIR if set, else ~/.mcp-
            musescore/backups.
    """
    return Path(
        os.environ.get("MCP_MUSESCORE_BACKUP_DIR")
        or Path.home() / ".mcp-musescore" / "backups"
    )


def backup_score(path: Path) -> Path:
    """Copy a score into the backup folder, as <name>.<timestamp><suffix>.

    Args:
        path (Path): The score file to back up.

    Returns:
        target (Path): The backup file.
    """
    directory = backup_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = directory / f"{path.stem}.{stamp}{path.suffix}"
    shutil.copy2(path, target)
    return target


def list_backups(path: Path) -> List[Path]:
    """List the backups of a score, newest first.

    Args:
        path (Path): The score file.

    Returns:
        backups (List[Path]): Its backup files, newest first; empty if there are
            none.
    """
    directory = backup_dir()
    if not directory.is_dir():
        return []
    prefix = f"{path.stem}."
    found = [
        p
        for p in directory.iterdir()
        if p.name.startswith(prefix)
        and p.suffix == path.suffix
        and p.stem[len(prefix) :][:8].isdigit()
    ]
    return sorted(found, key=lambda p: p.name, reverse=True)
