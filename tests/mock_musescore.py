"""In-memory stand-in for the MuseScore QML plugin's WebSocket API.

Speaks the same envelope as musescore-mcp-websocket.qml
({"status": "success", "result": ...} / {"status": "error", "message": ...})
over a simple 4/4-style score, so the MCP server can be run and tested without
MuseScore. Only a subset of actions is implemented; others return "Unknown command".

Run standalone on the plugin's port:  python tests/mock_musescore.py [--demo]
"""

import asyncio
import copy
import json
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from websockets.asyncio.server import serve

WHOLE_NOTE_TICKS = 1920

SEQUENCE_ACTIONS = {
    "getScore", "addNote", "addRest", "addTuplet", "appendMeasure", "deleteSelection",
    "getCursorInfo", "goToMeasure", "nextElement", "prevElement", "nextStaff", "prevStaff",
    "selectCurrentMeasure", "processSequence", "insertMeasure", "goToFinalMeasure",
    "goToBeginningOfScore", "setTimeSignature", "addLyrics", "addInstrument",
    "setStaffMute", "setInstrumentSound", "setTempo",
}

TPC_BY_PITCH_CLASS = [14, 21, 16, 23, 18, 13, 20, 15, 22, 17, 24, 19]
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _ticks(duration: Dict[str, int]) -> int:
    return WHOLE_NOTE_TICKS * duration["numerator"] // duration["denominator"]


class MockScore:
    def __init__(self, staves: int = 1, measures: int = 4, title: str = "Mock Score"):
        self.title = title
        self.num_staves = staves
        self.num_measures = measures
        self.time_signature = (4, 4)
        self.tempo = 120
        self.elements: Dict[int, List[Dict[str, Any]]] = {i: [] for i in range(staves)}
        self.cursor_tick = 0
        self.cursor_staff = 0

    @property
    def measure_ticks(self) -> int:
        num, den = self.time_signature
        return WHOLE_NOTE_TICKS * num // den

    def summary(self) -> Dict[str, Any]:
        measures = []
        for i in range(self.num_measures):
            start = i * self.measure_ticks
            end = start + self.measure_ticks
            per_staff = {
                f"staff{s}": [e for e in els if start <= e["startTick"] < end]
                for s, els in self.elements.items()
            }
            measures.append({
                "measure": i + 1,
                "startTick": start,
                "numElements": sum(len(v) for v in per_staff.values()),
                "elements": per_staff,
            })
        return {
            "title": self.title,
            "numMeasures": self.num_measures,
            "measures": measures,
            "staves": [
                {"name": f"staff{i}", "shortName": "", "visible": True}
                for i in range(self.num_staves)
            ],
        }

    def selection(self, start_tick: int, end_tick: int, start_staff: int, end_staff: int) -> Dict[str, Any]:
        elements = {
            f"staff{s}": [
                e for e in self.elements.get(s, []) if start_tick <= e["startTick"] < end_tick
            ]
            for s in range(start_staff, end_staff)
        }
        return {
            "startStaff": start_staff,
            "endStaff": end_staff,
            "startTick": start_tick,
            "elements": elements,
            "totalDuration": end_tick - start_tick,
        }

    def cursor_selection(self) -> Dict[str, Any]:
        return self.selection(self.cursor_tick, self.cursor_tick + 1, self.cursor_staff, self.cursor_staff + 1)


class MockMuseScore:
    """Command dispatcher plus a WebSocket handler."""

    def __init__(self, score: Optional[MockScore] = None):
        self.score = score or MockScore()
        self.history: List[MockScore] = []
        self.port: Optional[int] = None
        self.commands: List[Dict[str, Any]] = []

    @property
    def uri(self) -> str:
        return f"ws://127.0.0.1:{self.port}"

    async def handler(self, websocket) -> None:
        async for message in websocket:
            await websocket.send(json.dumps(self.handle_message(message)))

    def handle_message(self, message: str) -> Dict[str, Any]:
        try:
            command = json.loads(message)
            self.commands.append(command)
            return {"status": "success", "result": self.process_command(command)}
        except Exception as e:  # mirrors the plugin's catch-all
            return {"status": "error", "message": str(e)}

    def process_command(self, command: Dict[str, Any]) -> Any:
        action = command.get("action")
        params = command.get("params") or {}
        method = getattr(self, f"_do_{action}", None) if isinstance(action, str) else None
        if method is None:
            raise ValueError(f"Unknown command: {action}")
        return method(params)

    def _mutating(self) -> None:
        self.history.append(copy.deepcopy(self.score))

    def _missing(self, params: Dict[str, Any], required: List[str]) -> Optional[Dict[str, Any]]:
        missing = [k for k in required if params.get(k) is None]
        return {"error": "Missing required parameters: " + ", ".join(missing)} if missing else None

    def _ensure_room(self, end_tick: int) -> None:
        while end_tick > self.score.num_measures * self.score.measure_ticks:
            self.score.num_measures += 1

    def _place(self, element: Dict[str, Any], advance: bool) -> None:
        score = self.score
        element["startTick"] = score.cursor_tick
        element["voice"] = 0
        self._ensure_room(score.cursor_tick + element["durationTicks"])
        staff_elements = score.elements[score.cursor_staff]
        staff_elements[:] = [e for e in staff_elements if e["startTick"] != score.cursor_tick]
        staff_elements.append(element)
        staff_elements.sort(key=lambda e: e["startTick"])
        if advance:
            score.cursor_tick += element["durationTicks"]

    def _placed_selection(self, element: Dict[str, Any]) -> Dict[str, Any]:
        start = element["startTick"]
        return self.score.selection(
            start, start + element["durationTicks"], self.score.cursor_staff, self.score.cursor_staff + 1
        )

    # --- actions -------------------------------------------------------

    def _do_ping(self, params):
        return "pong"

    def _do_getScore(self, params):
        return {"success": True, "analysis": self.score.summary()}

    def _do_getCursorInfo(self, params):
        return {
            "success": True,
            "currentSelection": self.score.cursor_selection(),
            "currentScore": self.score.summary(),
        }

    def _do_goToBeginningOfScore(self, params):
        self.score.cursor_tick = 0
        self.score.cursor_staff = 0
        return {
            "success": True,
            "message": "Initialized at 0",
            "currentSelection": self.score.cursor_selection(),
            "currentScore": self.score.summary(),
        }

    def _do_goToMeasure(self, params):
        if (err := self._missing(params, ["measure"])):
            return err
        measure = params["measure"]
        if measure < 1 or measure > self.score.num_measures:
            return {"error": "Invalid measure number"}
        start = (measure - 1) * self.score.measure_ticks
        self.score.cursor_tick = start
        return {
            "success": True,
            "currentSelection": self.score.selection(
                start, start + self.score.measure_ticks, 0, self.score.num_staves
            ),
        }

    def _do_goToFinalMeasure(self, params):
        return self._do_goToMeasure({"measure": self.score.num_measures})

    def _do_addNote(self, params):
        if (err := self._missing(params, ["pitch", "duration", "advanceCursorAfterAction"])):
            return err
        duration = params["duration"]
        if not duration.get("numerator") or not duration.get("denominator"):
            return {"error": "Duration must be specified as { numerator: int, denominator: int }"}
        self._mutating()
        pitch = params["pitch"]
        note = {
            "pitchMidi": pitch,
            "tpc": TPC_BY_PITCH_CLASS[pitch % 12],
            "pitchName": NOTE_NAMES[pitch % 12],
        }
        staff_elements = self.score.elements[self.score.cursor_staff]
        if params.get("addToChord") is True and staff_elements and staff_elements[-1]["name"] == "Chord":
            chord = staff_elements[-1]
            chord["notes"].append(note)
            return {
                "success": True,
                "message": f"Note added with pitch {pitch}",
                "currentSelection": self._placed_selection(chord),
            }
        chord = {
            "name": "Chord",
            "durationTicks": _ticks(duration),
            "isTie": False,
            "isTuplet": False,
            "notes": [note],
        }
        self._place(chord, params["advanceCursorAfterAction"])
        return {
            "success": True,
            "message": f"Note added with pitch {pitch}",
            "currentSelection": self._placed_selection(chord),
        }

    def _do_addRest(self, params):
        if (err := self._missing(params, ["duration", "advanceCursorAfterAction"])):
            return err
        duration = params["duration"]
        if not duration.get("numerator") or not duration.get("denominator"):
            return {"error": "Duration must be specified as { numerator: int, denominator: int }"}
        self._mutating()
        rest = {"name": "Rest", "durationTicks": _ticks(duration), "isTie": False, "isTuplet": False}
        self._place(rest, params["advanceCursorAfterAction"])
        return {
            "success": True,
            "message": "Rest added",
            "currentSelection": self._placed_selection(rest),
        }

    def _do_addLyrics(self, params):
        lyrics = params.get("lyrics")
        if not isinstance(lyrics, list) or not lyrics:
            return {"error": "Lyrics must be specified as an array of strings"}
        self._mutating()
        remaining = list(lyrics)
        verse = params.get("verse") or 0
        added = skipped = 0
        for element in self.score.elements[self.score.cursor_staff]:
            if element["startTick"] < self.score.cursor_tick:
                continue
            if not remaining:
                break
            if element["name"] == "Chord":
                element["lyrics"] = [{"text": remaining.pop(0), "no": verse, "syllabic": 0}]
                added += 1
            else:
                skipped += 1
        message = f"Added {added} lyrics"
        if skipped:
            message += f", skipped {skipped} rests"
        if remaining:
            message += f", {len(remaining)} lyrics remaining"
        return {
            "success": True,
            "message": message,
            "addedCount": added,
            "skippedCount": skipped,
            "remainingLyrics": remaining,
            "currentSelection": self.score.cursor_selection(),
        }

    def _do_appendMeasure(self, params):
        self._mutating()
        count = params.get("count") or 1
        self.score.num_measures += count
        return {
            "success": True,
            "message": f"{count} measure(s) appended",
            "currentSelection": self.score.cursor_selection(),
        }

    def _do_addInstrument(self, params):
        if (err := self._missing(params, ["instrumentId"])):
            return err
        self._mutating()
        self.score.elements[self.score.num_staves] = []
        self.score.num_staves += 1
        return {"success": True, "message": f"Instrument {params['instrumentId']} added"}

    def _do_setTimeSignature(self, params):
        if (err := self._missing(params, ["numerator", "denominator"])):
            return err
        self._mutating()
        self.score.time_signature = (params["numerator"], params["denominator"])
        return {
            "success": True,
            "message": f"Time signature set to {params['numerator']}/{params['denominator']}",
        }

    def _do_setTempo(self, params):
        if (err := self._missing(params, ["bpm"])):
            return err
        self._mutating()
        self.score.tempo = params["bpm"]
        return {"success": True, "message": f"Tempo set to {params['bpm']} BPM"}

    def _do_undo(self, params):
        if self.history:
            self.score = self.history.pop()
        return {"success": True, "message": "Undo successful"}

    def _do_processSequence(self, params):
        sequence = params.get("sequence")
        if not sequence:
            return {"error": "No sequence specified"}
        try:
            for command in sequence:
                if command.get("action") not in SEQUENCE_ACTIONS:
                    raise ValueError(f"Invalid command: {command.get('action')}")
                self.process_command(command)
        except Exception as e:
            return {"error": str(e)}
        return {
            "success": True,
            "message": "Sequence processed",
            "currentSelection": self.score.cursor_selection(),
        }


@asynccontextmanager
async def running_mock(score: Optional[MockScore] = None, host: str = "127.0.0.1", port: int = 0):
    """Start the mock on a free port (or the given one) and yield the MockMuseScore."""
    mock = MockMuseScore(score)
    async with serve(mock.handler, host, port) as ws_server:
        mock.port = next(iter(ws_server.sockets)).getsockname()[1]
        yield mock


def demo_score() -> MockScore:
    """Twinkle Twinkle on two staves, for previewing the viewer."""
    mock = MockMuseScore(MockScore(staves=2, measures=4, title="Twinkle Twinkle (demo)"))
    quarter = {"numerator": 1, "denominator": 4}
    half = {"numerator": 1, "denominator": 2}

    def note(pitch, duration=quarter, **extra):
        mock.process_command({"action": "addNote", "params": {
            "pitch": pitch, "duration": duration, "advanceCursorAfterAction": True, **extra}})

    for pitch, duration in [
        (60, quarter), (60, quarter), (67, quarter), (67, quarter),
        (69, quarter), (69, quarter), (67, half),
        (65, quarter), (65, quarter), (64, quarter), (64, quarter),
        (62, quarter), (62, quarter),
    ]:
        note(pitch, duration)
    note(60, half, advanceCursorAfterAction=False)
    note(64, half, addToChord=True)
    note(67, half, addToChord=True)

    mock.process_command({"action": "goToBeginningOfScore"})
    mock.process_command({"action": "addLyrics", "params": {
        "lyrics": ["Twin", "kle", "twin", "kle", "lit", "tle", "star"]}})

    mock.score.cursor_staff, mock.score.cursor_tick = 1, 0
    for bar in range(4):
        for pitch in ((48, 55) if bar % 2 == 0 else (53, 55)):
            note(pitch, half)
    mock.score.cursor_staff, mock.score.cursor_tick = 0, 0
    return mock.score


async def _main(demo: bool) -> None:
    async with running_mock(demo_score() if demo else None, port=8765) as mock:
        print(f"Mock MuseScore listening on {mock.uri}")
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(_main(demo="--demo" in sys.argv))
    except KeyboardInterrupt:
        pass
