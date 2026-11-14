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
import re
import sys
import uuid
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from websockets.asyncio.server import serve

WHOLE_NOTE_TICKS = 1920

SEQUENCE_ACTIONS = {
    "getScore", "addNote", "addTie", "addTiedNote", "addRest", "addTuplet", "appendMeasure", "deleteSelection",
    "getCursorInfo", "goToMeasure", "nextElement", "prevElement", "nextStaff", "prevStaff",
    "selectCurrentMeasure", "processSequence", "insertMeasure", "goToFinalMeasure",
    "goToBeginningOfScore", "setTimeSignature", "addLyrics", "addInstrument",
    "setStaffMute", "setInstrumentSound", "setTempo",
    "selectMeasures", "setRepeatBarlines", "addVolta", "colorRange", "deleteMeasures",
    "setStyle", "addRehearsalMark", "removeParts", "addHighlight", "addLabel", "clearHighlights",
    "highlightNotes", "highlightMarkings", "highlightSymbols", "setMeasureNumbering", "numberAsPlayed",
    "addText", "removeAnnotations", "addArticulation", "removeArticulations", "ghostNotes", "beamOverRests", "addSectionCounts",
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
        self.tempo_measure: Optional[int] = None
        self.elements: Dict[int, List[Dict[str, Any]]] = {i: [] for i in range(staves)}
        self.cursor_tick = 0
        self.cursor_staff = 0
        # Repeat structure and formatting, as the plugin would leave them in the score
        self.repeat_barlines_supported = True  # False mimics MuseScore < 4.6
        self.repeats: Dict[int, Dict[str, Any]] = {}  # measure -> {"start", "end", "count"}
        self.voltas: List[Dict[str, Any]] = []
        self.colors: Dict[tuple, str] = {}  # (staff, startTick, voice) -> color
        self.selected: Optional[Dict[str, int]] = None
        self.part_names = [f"Part {i + 1}" for i in range(staves)]
        self.short_names = ["" for _ in range(staves)]
        self.drum_staves: set = set()
        self.style: Dict[str, Any] = {}
        self.rehearsal_marks: List[Dict[str, Any]] = []
        self.highlights: List[Dict[str, Any]] = []  # {"staff", "startMeasure", "endMeasure", "color"}
        self.labels: List[Dict[str, Any]] = []  # {"staff", "measure", "text", "background"}
        self.texts: List[Dict[str, Any]] = []  # addText params, with the resolved tick
        self.note_highlights: Dict[tuple, str] = {}  # (staff, startTick, pitch) -> color
        self.markings: List[Dict[str, Any]] = []  # {"staff", "startTick", "name", "text", "highlight"}
        self.symbol_requests: List[Dict[str, Any]] = []  # highlightSymbols calls (the mock has no symbols to find)
        self.score_name = title
        self.score_id: Optional[str] = None  # the plugin's mcpScoreId meta tag
        self.file_path: Optional[str] = None  # the file this score is saved in, if any
        self.part_entry: Optional[str] = None  # set when this is a part tab: saving stores the ID in that part
        self.no_offsets: Dict[int, int] = {}  # measure -> "add to measure number"
        self.irregular: set = set()  # measures excluded from the count

    @property
    def measure_ticks(self) -> int:
        num, den = self.time_signature
        return WHOLE_NOTE_TICKS * num // den

    def displayed_numbers(self) -> List[int]:
        """MuseScore's rule: add each measure's offset, then count it unless it is excluded."""
        numbers, count = [], 0
        for number in range(1, self.num_measures + 1):
            count += self.no_offsets.get(number, 0)
            numbers.append(count + 1)
            if number not in self.irregular:
                count += 1
        return numbers

    def summary(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """GetScore analysis; params mirror the plugin (startMeasure, endMeasure, staves, includeElements)."""
        params = params or {}
        first = max(1, params.get("startMeasure") or 1)
        last = min(self.num_measures, params.get("endMeasure") or self.num_measures)
        staves = [s for s in (params.get("staves") or range(self.num_staves)) if 0 <= s < self.num_staves]
        measures = []
        for number in range(first, last + 1):
            start = (number - 1) * self.measure_ticks
            end = start + self.measure_ticks
            entry: Dict[str, Any] = {"measure": number, "number": self.displayed_numbers()[number - 1], "startTick": start,
                     "durationTicks": self.measure_ticks}
            repeat = self.repeats.get(number, {})
            if repeat.get("start"):
                entry["repeatStart"] = True
            if repeat.get("end"):
                entry["repeatEnd"] = repeat.get("count") or 2
            if number in self.irregular:
                entry["irregular"] = True
            if params.get("includeElements") is not False:
                per_staff = {
                    f"staff{s}": [e for e in self.elements[s] if start <= e["startTick"] < end]
                    for s in staves
                }
                entry["numElements"] = sum(len(v) for v in per_staff.values())
                entry["elements"] = per_staff
                entry["markings"] = [
                    {"name": mk["name"], "text": mk["text"], "staff": mk["staff"], "startTick": mk["startTick"],
                     "highlighted": mk.get("highlight") is not None}
                    for mk in self.markings if mk["staff"] in staves and start <= mk["startTick"] < end
                ]
            measures.append(entry)
        return {
            "title": self.title,
            "numMeasures": self.num_measures,
            "startMeasure": first,
            "endMeasure": last,
            "measures": measures,
            "staves": [
                {"name": f"staff{i}", "index": i, "partName": self.part_names[i], "shortName": self.short_names[i],
                 "instrumentId": "drum.group" if i in self.drum_staves else "keyboard.piano",
                 "isDrums": i in self.drum_staves, "visible": True}
                for i in staves
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
        self.opened: List[str] = []  # paths opened through openScore / reopenScore
        self.opens_in_new_window = False  # True mimics MuseScore 4 opening the file out of the plugin's reach

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

    def _range(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Mirror of the plugin's measureRange(): validated measure and staff range, or an error."""
        if (err := self._missing(params, ["startMeasure"])):
            return err
        first = params["startMeasure"]
        last = params.get("endMeasure") or first
        if first < 1 or last > self.score.num_measures or last < first:
            return {"error": f"Invalid measure range {first}-{last} (score has {self.score.num_measures} measures)"}
        start_staff = params.get("startStaff") or 0
        end_staff = params.get("endStaff")
        if end_staff is None:
            end_staff = self.score.num_staves
        if start_staff < 0 or end_staff > self.score.num_staves or start_staff >= end_staff:
            return {"error": f"Invalid staff range {start_staff}-{end_staff}"}
        ticks = self.score.measure_ticks
        return {
            "valid": True, "startMeasure": first, "endMeasure": last,
            "startTick": (first - 1) * ticks, "endTick": last * ticks,
            "startStaff": start_staff, "endStaff": end_staff,
        }

    def _apply_beats(self, rng: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Mirror of the plugin's applyBeats(): narrow the range to startBeat / endBeat (inclusive)."""
        beat = WHOLE_NOTE_TICKS // self.score.time_signature[1]
        measure = self.score.measure_ticks
        if params.get("startBeat") is not None:
            offset = round((params["startBeat"] - 1) * beat)
            if params["startBeat"] < 1 or offset >= measure:
                return {"error": f"Beat {params['startBeat']} is outside measure {rng['startMeasure']}"}
            rng["startTick"] += offset
        if params.get("endBeat") is not None:
            end = (rng["endMeasure"] - 1) * measure + round(params["endBeat"] * beat)
            if params["endBeat"] < 1 or end > rng["endTick"]:
                return {"error": f"Beat {params['endBeat']} is outside measure {rng['endMeasure']}"}
            rng["endTick"] = end
        if rng["startTick"] >= rng["endTick"]:
            return {"error": "The beat range is empty"}
        return rng

    # --- actions -------------------------------------------------------

    def _do_ping(self, params):
        return "pong"

    def _do_getScore(self, params):
        return {"success": True, "analysis": self.score.summary(params)}

    def _do_getCursorInfo(self, params):
        return {
            "success": True,
            "currentSelection": self.score.cursor_selection(),
            "currentScore": self.score.summary({"includeElements": False}),
        }

    def _do_goToBeginningOfScore(self, params):
        self.score.cursor_tick = 0
        self.score.cursor_staff = 0
        return {
            "success": True,
            "message": "Initialized at 0",
            "currentSelection": self.score.cursor_selection(),
            "currentScore": self.score.summary({"includeElements": False}),
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

    def _do_addTie(self, params):
        """Tie notes of the chord at the cursor to the same pitches in the next chord, with the plugin's rules."""
        score = self.score
        staff_elements = score.elements[score.cursor_staff]
        first = next((e for e in staff_elements if e["startTick"] == score.cursor_tick), None)
        if first is None or first["name"] != "Chord":
            return {"error": "No note or chord at the cursor to tie from"}
        later = [e for e in staff_elements if e["startTick"] > first["startTick"]]
        if not later:
            return {"error": "No note or chord after the cursor to tie to"}
        second = min(later, key=lambda e: e["startTick"])
        if second["name"] != "Chord":
            return {"error": "The element after the cursor is a rest: a tie needs a note of the same pitch"}

        first_pitches = [n["pitchMidi"] for n in first["notes"]]
        second_pitches = [n["pitchMidi"] for n in second["notes"]]
        requested = params.get("pitches") or None
        to_tie, already_tied, skipped = [], [], []
        for pitch in dict.fromkeys(requested or first_pitches):
            note = next((n for n in first["notes"] if n["pitchMidi"] == pitch), None)
            if note is None or pitch not in second_pitches:
                skipped.append(pitch)
            elif note.get("tieForward"):
                already_tied.append(pitch)
            else:
                to_tie.append(pitch)
        if not to_tie and not already_tied:
            message = (f"No pitch to tie: the chord at the cursor has [{', '.join(map(str, first_pitches))}], "
                       f"the next chord has [{', '.join(map(str, second_pitches))}]")
            if requested:
                message += f", requested [{', '.join(map(str, requested))}]"
            return {"error": message}

        self._mutating()
        for pitch in to_tie:
            next(n for n in first["notes"] if n["pitchMidi"] == pitch)["tieForward"] = True
            next(n for n in second["notes"] if n["pitchMidi"] == pitch)["tieBack"] = True
        first["isTie"] = True
        score.cursor_tick = second["startTick"]
        return {
            "success": True,
            "message": f"Tied pitch {', '.join(map(str, to_tie))}" if to_tie else "Tied nothing new",
            "tiedPitches": to_tie,
            "alreadyTied": already_tied,
            "skippedPitches": skipped,
            "currentSelection": self._placed_selection(second),
        }

    def _do_addTiedNote(self, params):
        """Write a chord at the cursor tied to the chord before it, with the plugin's rules (no barline split)."""
        if (err := self._missing(params, ["duration", "advanceCursorAfterAction"])):
            return err
        duration = params["duration"]
        if not duration.get("numerator") or not duration.get("denominator"):
            return {"error": "Duration must be specified as { numerator: int, denominator: int }"}
        score = self.score
        earlier = [e for e in score.elements[score.cursor_staff] if e["startTick"] < score.cursor_tick]
        previous = max(earlier, key=lambda e: e["startTick"]) if earlier else None
        if previous is None or previous["name"] != "Chord":
            return {"error": "No note or chord before the cursor to tie from"}

        previous_pitches = [n["pitchMidi"] for n in previous["notes"]]
        pitches = list(dict.fromkeys(params.get("pitches") or previous_pitches))
        missing = [p for p in pitches if p not in previous_pitches]
        if missing:
            return {"error": f"Pitch {', '.join(map(str, missing))} is not in the chord before the cursor "
                             f"[{', '.join(map(str, previous_pitches))}]: a tie needs the same pitch"}
        extra = [p for p in dict.fromkeys(params.get("extraPitches") or []) if p not in pitches]

        self._mutating()
        notes = []
        for pitch in pitches + extra:
            note = {"pitchMidi": pitch, "tpc": TPC_BY_PITCH_CLASS[pitch % 12], "pitchName": NOTE_NAMES[pitch % 12]}
            if pitch in pitches:
                note["tieBack"] = True
                next(n for n in previous["notes"] if n["pitchMidi"] == pitch)["tieForward"] = True
            notes.append(note)
        previous["isTie"] = True
        chord = {"name": "Chord", "durationTicks": _ticks(duration), "isTie": False, "isTuplet": False, "notes": notes}
        self._place(chord, params["advanceCursorAfterAction"])
        written = pitches + extra
        message = f"Added tied {'chord' if len(written) > 1 else 'note'} {', '.join(map(str, written))}"
        if extra:
            message += f" (tied: {', '.join(map(str, pitches))})"
        return {
            "success": True,
            "message": message,
            "tiedPitches": pitches,
            "currentSelection": self.score.cursor_selection(),
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
        if params.get("measure") is not None:
            rng = self._range({"startMeasure": params["measure"]})
            if "error" in rng:
                return rng
        self._mutating()
        self.score.tempo = params["bpm"]
        self.score.tempo_measure = params.get("measure")
        return {"success": True, "message": f"Tempo set to {params['bpm']} BPM"}

    def _do_selectMeasures(self, params):
        rng = self._range(params)
        if "error" in rng:
            return rng
        self.score.selected = {k: rng[k] for k in ("startMeasure", "endMeasure", "startStaff", "endStaff")}
        return {"success": True, "message": f"Selected measures {rng['startMeasure']}-{rng['endMeasure']}",
                **{k: rng[k] for k in ("startTick", "endTick", "startStaff", "endStaff")}}

    def _do_setMeasureNumbering(self, params):
        if (err := self._missing(params, ["measure"])):
            return err
        measure = params["measure"]
        if not 1 <= measure <= self.score.num_measures:
            return {"error": f"Invalid measure number {measure}"}
        self._mutating()
        if params.get("addToNumber") is not None:
            self.score.no_offsets[measure] = params["addToNumber"]
        if params.get("excludeFromCount") is not None:
            (self.score.irregular.add if params["excludeFromCount"] else self.score.irregular.discard)(measure)
        return {"success": True, "displayedNumber": self.score.displayed_numbers()[measure - 1]}

    def _do_numberAsPlayed(self, params):
        score = self.score
        self._mutating()
        if params.get("reset"):
            score.no_offsets, score.irregular = {}, set()
            return {"success": True, "reset": True, "lastMeasureNumber": score.num_measures}
        offsets, repeats, section_start = {}, [], 1
        for number in range(1, score.num_measures + 1):
            repeat = score.repeats.get(number, {})
            if repeat.get("start"):
                section_start = number
            if repeat.get("end"):
                count = repeat.get("count") or 2
                if count > 1 and number < score.num_measures:
                    offsets[number + 1] = offsets.get(number + 1, 0) + (count - 1) * (number - section_start + 1)
                repeats.append({"start": section_start, "end": number, "playCount": count})
                section_start = number + 1
        score.no_offsets = offsets
        score.irregular.update(params.get("exclude") or [])
        numbers = score.displayed_numbers()
        return {"success": True, "repeats": repeats,
                "offsets": [{"measure": m, "addToNumber": o, "displayedNumber": numbers[m - 1]} for m, o in sorted(offsets.items())],
                "lastMeasureNumber": numbers[-1]}

    def _do_setRepeatBarlines(self, params):
        rng = self._range({"startMeasure": params.get("startMeasure"), "endMeasure": params.get("endMeasure")})
        if "error" in rng:
            return rng
        if not self.score.repeat_barlines_supported:
            self._do_selectMeasures(rng)
            return {"success": False, "fallback": "manual",
                    "message": "This MuseScore version does not let plugins set repeat barlines (needs MuseScore 4.6+)."}
        self._mutating()
        first, last = rng["startMeasure"], rng["endMeasure"]
        clear = params.get("clear") is True
        self.score.repeats.setdefault(first, {})["start"] = not clear
        self.score.repeats.setdefault(last, {})["end"] = not clear
        self.score.repeats[last]["count"] = 2 if clear else params.get("playCount") or 2
        return {"success": True, "message": f"Repeat barlines set around measures {first}-{last}"}

    def _do_addVolta(self, params):
        rng = self._range({"startMeasure": params.get("startMeasure"), "endMeasure": params.get("endMeasure")})
        if "error" in rng:
            return rng
        self._mutating()
        endings = params.get("endings") or [1]
        self.score.voltas.append({
            "startMeasure": rng["startMeasure"], "endMeasure": rng["endMeasure"], "endings": endings,
            "text": params.get("text") or ", ".join(str(e) for e in endings) + ".",
        })
        return {"success": True, "experimental": True, "message": "Volta requested"}

    def _do_colorRange(self, params):
        rng = self._range(params)
        if "error" in rng:
            return rng
        rng = self._apply_beats(rng, params)
        if "error" in rng:
            return rng
        self._mutating()
        color = params.get("color") or "#000000"
        voices = params.get("voices") or [0, 1, 2, 3]
        count = 0
        for staff in range(rng["startStaff"], rng["endStaff"]):
            for e in self.score.elements[staff]:
                if rng["startTick"] <= e["startTick"] < rng["endTick"] and e.get("voice", 0) in voices:
                    self.score.colors[(staff, e["startTick"], e.get("voice", 0))] = color
                    count += len(e.get("notes", [])) if e["name"] == "Chord" else 1
        return {"success": True, "colored": count, "message": f"Colored {count} note(s)/rest(s) {color}"}

    def _do_deleteMeasures(self, params):
        rng = self._range({"startMeasure": params.get("startMeasure"), "endMeasure": params.get("endMeasure")})
        if "error" in rng:
            return rng
        self._mutating()
        score = self.score
        start, end = rng["startTick"], rng["endTick"]
        removed_ticks = end - start
        removed_bars = rng["endMeasure"] - rng["startMeasure"] + 1

        def shift(tick):
            return tick - removed_ticks if tick >= end else tick

        for staff, elements in score.elements.items():
            kept = [e for e in elements if not start <= e["startTick"] < end]
            for e in kept:
                e["startTick"] = shift(e["startTick"])
            score.elements[staff] = kept
        score.colors = {
            (st, shift(t), v): c for (st, t, v), c in score.colors.items() if not start <= t < end
        }

        def renumber(m):
            return m - removed_bars if m > rng["endMeasure"] else m

        score.repeats = {
            renumber(m): r for m, r in score.repeats.items()
            if not rng["startMeasure"] <= m <= rng["endMeasure"]
        }
        score.voltas = [
            {**v, "startMeasure": renumber(v["startMeasure"]), "endMeasure": renumber(v["endMeasure"])}
            for v in score.voltas
            if v["endMeasure"] < rng["startMeasure"] or v["startMeasure"] > rng["endMeasure"]
        ]
        score.num_measures -= removed_bars
        score.cursor_tick, score.cursor_staff = 0, 0
        return {"success": True, "message": f"Deleted measures {rng['startMeasure']}-{rng['endMeasure']}",
                "numMeasures": score.num_measures}

    def _do_setStyle(self, params):
        if (err := self._missing(params, ["key", "value"])):
            return err
        self._mutating()
        self.score.style[params["key"]] = params["value"]
        return {"success": True}

    def _do_addRehearsalMark(self, params):
        if (err := self._missing(params, ["measure", "text"])):
            return err
        rng = self._range({"startMeasure": params["measure"]})
        if "error" in rng:
            return rng
        self._mutating()
        self.score.rehearsal_marks.append({"measure": params["measure"], "text": params["text"]})
        return {"success": True, "experimental": True}

    def _do_addHighlight(self, params):
        rng = self._range(params)
        if "error" in rng:
            return rng
        rng = self._apply_beats(rng, params)
        if "error" in rng:
            return rng
        self._mutating()
        for staff in range(rng["startStaff"], rng["endStaff"]):
            self.score.highlights.append({"staff": staff, "startMeasure": rng["startMeasure"],
                                          "endMeasure": rng["endMeasure"], "color": params.get("color")})
        return {"success": True, "experimental": True, "added": rng["endStaff"] - rng["startStaff"]}

    def _do_addLabel(self, params):
        if (err := self._missing(params, ["measure", "text"])):
            return err
        staff = params.get("staff") or 0
        rng = self._range({"startMeasure": params["measure"], "startStaff": staff, "endStaff": staff + 1})
        if "error" in rng:
            return rng
        self._mutating()
        self.score.labels.append({"staff": staff, "measure": params["measure"], "text": params["text"],
                                  "background": params.get("background")})
        return {"success": True}

    def _do_highlightNotes(self, params):
        rng = self._range(params)
        if "error" in rng:
            return rng
        rng = self._apply_beats(rng, params)
        if "error" in rng:
            return rng
        self._mutating()
        pitches = params.get("pitches")
        count = 0
        for staff in range(rng["startStaff"], rng["endStaff"]):
            for e in self.score.elements[staff]:
                if e["name"] != "Chord" or not rng["startTick"] <= e["startTick"] < rng["endTick"]:
                    continue
                for note in e["notes"]:
                    if pitches and note["pitchMidi"] not in pitches:
                        continue
                    self.score.note_highlights[(staff, e["startTick"], note["pitchMidi"])] = params.get("color")
                    count += 1
        return {"success": True, "highlighted": count}

    def _do_highlightSymbols(self, params):
        rng = self._range(params)
        if "error" in rng:
            return rng
        self._mutating()
        self.score.symbol_requests.append(params)
        return {"success": True, "found": {"time_signatures": 1, "repeat_barlines": 0, "measure_repeats": 0},
                "message": "Highlighted 1 symbol(s)"}

    def _markings_in(self, rng, types):
        return [mk for mk in self.score.markings
                if mk["name"] in types and rng["startStaff"] <= mk["staff"] < rng["endStaff"]
                and rng["startTick"] <= mk["startTick"] < rng["endTick"]]

    def _do_highlightMarkings(self, params):
        rng = self._range(params)
        if "error" in rng:
            return rng
        self._mutating()
        found = self._markings_in(rng, params.get("types") or ["Dynamic"])
        for mk in found:
            mk["highlight"] = None if params.get("clear") else params.get("color")
        return {"success": True, "found": len(found), "changed": len(found)}

    def _do_addText(self, params):
        if (err := self._missing(params, ["measure", "text"])):
            return err
        staff = params.get("staff") or 0
        rng = self._range({"startMeasure": params["measure"], "startStaff": staff, "endStaff": staff + 1})
        if "error" in rng:
            return rng
        rng = self._apply_beats(rng, {"startBeat": params.get("beat")})
        if "error" in rng:
            return rng
        self._mutating()
        self.score.texts.append({**params, "tick": rng["startTick"]})
        return {"success": True}

    def _chords_in(self, rng, pitches):
        for staff in range(rng["startStaff"], rng["endStaff"]):
            for e in self.score.elements[staff]:
                if e["name"] == "Chord" and rng["startTick"] <= e["startTick"] < rng["endTick"] and (
                        not pitches or any(n["pitchMidi"] in pitches for n in e["notes"])):
                    yield staff, e

    def _do_addArticulation(self, params):
        rng = self._range(params)
        if "error" in rng:
            return rng
        rng = self._apply_beats(rng, params)
        if "error" in rng:
            return rng
        self._mutating()
        added = 0
        for _, chord in self._chords_in(rng, params.get("pitches")):
            arts = chord.setdefault("articulations", [])
            if params["symbol"] not in arts:
                arts.append(params["symbol"])
                added += 1
        return {"success": True, "added": added}

    def _do_removeArticulations(self, params):
        rng = self._range(params)
        if "error" in rng:
            return rng
        symbols = params.get("symbols") or ["half_open", "open", "closed"]
        self._mutating()
        removed = 0
        for _, chord in self._chords_in(rng, params.get("pitches")):
            keep = [a for a in chord.get("articulations", []) if a not in symbols]
            removed += len(chord.get("articulations", [])) - len(keep)
            if keep:
                chord["articulations"] = keep
            else:
                chord.pop("articulations", None)
        return {"success": True, "removed": removed}

    def _do_addSectionCounts(self, params):
        """Mode "label": "(count)" at the end of the rehearsal mark's text; "beside": texts {measure, text,
        sectionCount: True}. Earlier counts at those measures, in either form, are replaced.
        """
        if (err := self._missing(params, ["counts"])):
            return err
        self._mutating()
        measures = {c["measure"] for c in params["counts"]}
        before = len(self.score.texts)
        self.score.texts = [t for t in self.score.texts
                            if not (t.get("sectionCount") and (params.get("clearAll") or t["measure"] in measures))]
        removed = before - len(self.score.texts)
        marks = {mk["startTick"] // self.score.measure_ticks + 1: mk for mk in self.score.markings
                 if mk["name"] == "RehearsalMark" and mk["staff"] == 0}
        for number in measures:
            if number in marks:
                base = re.sub(r"\s*\(\d[\dx+ ]*\)\s*$", "", marks[number]["text"])
                removed += base != marks[number]["text"]
                marks[number]["text"] = base
        if params.get("clear"):
            return {"success": True, "added": 0, "removed": removed}
        if params.get("mode", "label") == "label":
            done = [c for c in params["counts"] if c["measure"] in marks]
            for c in done:
                marks[c["measure"]]["text"] += f" ({c['text']})"
            return {"success": True, "added": len(done), "removed": removed}
        for c in params["counts"]:
            self.score.texts.append({"measure": c["measure"], "text": c["text"], "sectionCount": True,
                                     "color": params.get("color"), "tick": (c["measure"] - 1) * self.score.measure_ticks})
        return {"success": True, "added": len(params["counts"]), "removed": removed}

    def _do_beamOverRests(self, params):
        """Mark rests with beamable chords before and after them in the same beat (4/4 model) as beamed over."""
        rng = self._range(params)
        if "error" in rng:
            return rng
        self._mutating()
        changed = 0
        for staff in range(rng["startStaff"], rng["endStaff"]):
            items = sorted((e for e in self.score.elements[staff]
                            if e["name"] in ("Chord", "Rest") and rng["startTick"] <= e["startTick"] < rng["endTick"]),
                           key=lambda e: e["startTick"])
            for i, item in enumerate(items):
                if item["name"] != "Rest":
                    continue
                if params.get("clear"):
                    changed += bool(item.pop("beamMode", None))
                    continue
                beat = item["startTick"] // 480
                same = [e for e in items if e["startTick"] // 480 == beat and e["durationTicks"] < 480]
                before = [e for e in same if e["startTick"] < item["startTick"] and e["name"] == "Chord"]
                after = [e for e in same if e["startTick"] > item["startTick"] and e["name"] == "Chord"]
                if before and after and item["durationTicks"] < 480 and item.get("beamMode") != "mid":
                    item["beamMode"] = "mid"
                    changed += 1
        return {"success": True, "changed": changed}

    def _do_ghostNotes(self, params):
        rng = self._range(params)
        if "error" in rng:
            return rng
        pitches = params.get("pitches")
        found = [(staff, chord) for staff, chord in self._chords_in(rng, None)
                 if any(n.get("ghost") and (not pitches or n["pitchMidi"] in pitches) for n in chord["notes"])]
        per_bar: Dict[int, int] = {}
        for _, chord in found:
            bar = chord["startTick"] // self.score.measure_ticks + 1
            per_bar[bar] = per_bar.get(bar, 0) + sum(
                1 for n in chord["notes"] if n.get("ghost") and (not pitches or n["pitchMidi"] in pitches))
        bars = [{"measure": b, "ghostNotes": c} for b, c in sorted(per_bar.items())]
        total = sum(per_bar.values())
        if params.get("mode") != "remove" or not found:
            return {"success": True, "ghostNotes": total, "bars": bars}
        self._mutating()
        for _, chord in found:
            chord["notes"] = [n for n in chord["notes"] if not (n.get("ghost") and (not pitches or n["pitchMidi"] in pitches))]
            if not chord["notes"]:
                chord["name"] = "Rest"
                chord.pop("notes")
        return {"success": True, "removed": total, "bars": bars}

    def _do_removeAnnotations(self, params):
        rng = self._range(params)
        if "error" in rng:
            return rng
        kinds = params.get("kinds") or ["texts"]
        contains = params.get("contains") or ""
        exact = params.get("exact") is True
        score = self.score
        removed = dict.fromkeys(["texts", "labels", "rehearsal_marks", "tempo", "voltas"], 0)

        def inside(staff, tick):
            return rng["startStaff"] <= staff < rng["endStaff"] and rng["startTick"] <= tick < rng["endTick"]

        def keep(kind, staff, tick, text):
            if kind in kinds and inside(staff, tick) and (text == contains if exact and contains else contains in text):
                removed[kind] += 1
                return False
            return True

        self._mutating()
        ticks = score.measure_ticks
        score.texts = [t for t in score.texts if keep("texts", t.get("staff") or 0, t["tick"], t["text"])]
        score.labels = [lb for lb in score.labels if keep("labels", lb["staff"], (lb["measure"] - 1) * ticks, lb["text"])]
        score.rehearsal_marks = [r for r in score.rehearsal_marks
                                 if keep("rehearsal_marks", 0, (r["measure"] - 1) * ticks, r["text"])]
        score.voltas = [v for v in score.voltas if keep("voltas", 0, (v["startMeasure"] - 1) * ticks, "")]
        return {"success": True, "removed": removed}

    def _do_clearHighlights(self, params):
        rng = self._range(params)
        if "error" in rng:
            return rng
        kinds = params.get("kinds") or ["highlights", "notes", "markings", "labels"]

        def inside(staff, measure):
            return (rng["startStaff"] <= staff < rng["endStaff"]
                    and rng["startMeasure"] <= measure <= rng["endMeasure"])

        score = self.score
        before = len(score.highlights) + len(score.labels) + len(score.note_highlights)
        before += sum(1 for mk in score.markings if mk.get("highlight"))
        self._mutating()
        if "highlights" in kinds:
            score.highlights = [h for h in score.highlights if not inside(h["staff"], h["startMeasure"])]
        if "labels" in kinds:
            score.labels = [lb for lb in score.labels if not inside(lb["staff"], lb["measure"])]
        if "notes" in kinds:
            score.note_highlights = {
                k: c for k, c in score.note_highlights.items()
                if not (rng["startStaff"] <= k[0] < rng["endStaff"] and rng["startTick"] <= k[1] < rng["endTick"])
            }
        if "markings" in kinds:
            for mk in self._markings_in(rng, ["Dynamic", "StaffText", "SystemText", "Tempo", "Expression"]):
                mk["highlight"] = None
        after = len(score.highlights) + len(score.labels) + len(score.note_highlights)
        after += sum(1 for mk in score.markings if mk.get("highlight"))
        return {"success": True, "removed": before - after}

    def _do_ensureScoreId(self, params):
        if self.score.score_id and not params.get("renew"):
            return {"success": True, "scoreId": self.score.score_id, "created": False}
        self.score.score_id = f"mcp-mock-{uuid.uuid4().hex[:10]}"
        return {"success": True, "scoreId": self.score.score_id, "created": True}

    def _do_scoreFileInfo(self, params):
        return {"success": True, "scoreId": self.score.score_id or "", "scoreName": self.score.score_name,
                "title": self.score.title,
                "numMeasures": self.score.num_measures, "numStaves": self.score.num_staves}

    def _do_saveScore(self, params):
        """Like MuseScore saving: the score's ID is written to its file (the notes are not)."""
        if self.score.part_entry:  # a part tab: the test file already carries the ID in that part
            return {"success": True, "message": "Score saved"}
        if self.score.file_path and self.score.score_id:
            from src.mscz import ScoreFile
            file = ScoreFile(self.score.file_path)
            for tag in file.score.findall("metaTag"):
                if tag.get("name") == "mcpScoreId":
                    file.score.remove(tag)
            ET.SubElement(file.score, "metaTag", {"name": "mcpScoreId"}).text = self.score.score_id
            file.save()
        return {"success": True, "message": "Score saved"}

    def _do_openScore(self, params):
        if (err := self._missing(params, ["path"])):
            return err
        self.opened.append(params["path"])
        if self.opens_in_new_window:
            return {"success": True, "path": params["path"], "scoreName": self.score.score_name}
        from src.mscz.locate import read_score_id
        self.score.file_path = params["path"]
        self.score.score_id = read_score_id(Path(params["path"]))
        return {"success": True, "path": params["path"], "scoreName": self.score.score_name}

    def _do_reopenScore(self, params):
        """Close and open a file in place: the score takes the file's staves and ID, like MuseScore loading it."""
        if (err := self._missing(params, ["path"])):
            return err
        if self.opens_in_new_window:
            self.opened.append(params["path"])
            if params.get("fallbackPath"):
                self.opened.append(params["fallbackPath"])
            return {"error": f"MuseScore could not open {params['path']}"}
        result = self._do_openScore(params)
        from src.mscz import ScoreFile
        staves = len(ScoreFile(params["path"]).staves())
        if staves < self.score.num_staves:
            self.score.elements = {i: self.score.elements[i] for i in range(staves)}
            self.score.part_names = self.score.part_names[:staves]
            self.score.short_names = self.score.short_names[:staves]
            self.score.num_staves = staves
        return result

    def _do_exportScore(self, params):
        if (err := self._missing(params, ["path"])):
            return err
        Path(params["path"]).write_text(f"exported {self.score.num_staves} staves")
        return {"success": True, "path": params["path"]}

    def _do_removeParts(self, params):
        if (err := self._missing(params, ["keepStaves"])):
            return err
        keep = [s for s in range(self.score.num_staves) if s in params["keepStaves"]]
        if not keep:
            return {"error": "None of the staves exist"}
        self._mutating()
        score = self.score
        removed = score.num_staves - len(keep)
        score.elements = {new: score.elements[old] for new, old in enumerate(keep)}
        score.part_names = [score.part_names[s] for s in keep]
        score.short_names = [score.short_names[s] for s in keep]
        score.drum_staves = {new for new, old in enumerate(keep) if old in score.drum_staves}
        score.num_staves = len(keep)
        return {"success": True, "removed": removed, "kept": score.part_names,
                "numStaves": score.num_staves}

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
