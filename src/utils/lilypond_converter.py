"""Convert the plugin's score analysis to compact LilyPond text."""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("LilyPondConverter")

def midi_to_lilypond_pitch(midi_pitch: int, tpc: Optional[int] = None) -> str:
    """Convert a MIDI pitch to LilyPond pitch syntax.

    If TPC (Tonal Pitch Class) is provided, uses it to determine enharmonic spelling (flats vs sharps).
    Example: 60 -> c', 67 -> g', 74 -> d''
    """
    try:
        # Fallback names if no TPC provided
        pitch_names = ['c', 'cis', 'd', 'dis', 'e', 'f', 'fis', 'g', 'gis', 'a', 'ais', 'b']
        
        if tpc is not None:
            # MuseScore TPC map (circle of fifths where 14 = C, 15 = G)
            tpc_map = {
                6: 'fes', 7: 'ces', 8: 'ges', 9: 'des', 10: 'as', 11: 'es', 12: 'bes', 13: 'f',
                14: 'c', 15: 'g', 16: 'd', 17: 'a', 18: 'e', 19: 'b', 20: 'fis',
                21: 'cis', 22: 'gis', 23: 'dis', 24: 'ais', 25: 'eis', 26: 'bis',
                27: 'fisis', 28: 'cisis', 29: 'gisis', 30: 'disis', 31: 'aisis', 32: 'eisis', 33: 'bisis',
                -1: 'feses', 0: 'ceses', 1: 'geses', 2: 'deses', 3: 'ases', 4: 'eses', 5: 'beses'
            }
            base_note = tpc_map.get(tpc, pitch_names[midi_pitch % 12])
        else:
            base_note = pitch_names[midi_pitch % 12]
            
        octave = (midi_pitch // 12) - 1
        
        # Mapping MIDI octaves to LilyPond octaves (C4 = MIDI 60 = c')
        if octave == 4:
            octave_mark = "'"
        elif octave == 5:
            octave_mark = "''"
        elif octave == 6:
            octave_mark = "'''"
        elif octave == 7:
            octave_mark = "''''"
        elif octave == 3:
            octave_mark = ""
        elif octave == 2:
            octave_mark = ","
        elif octave == 1:
            octave_mark = ",,"
        elif octave == 0:
            octave_mark = ",,,"
        else:
            octave_mark = ""  # Fallback for out-of-bounds
            
        return f"{base_note}{octave_mark}"
    except Exception as e:
        logger.error(f"Error converting MIDI pitch {midi_pitch}: {e}")
        return "c'"  # Safe fallback

def ticks_to_lilypond_duration(ticks: int) -> str:
    """Convert MuseScore ticks to LilyPond rhythmic duration.

    MuseScore defines a quarter note as 480 ticks.
    """
    try:
        mapping = {
            1920: "1",    # Whole note
            1440: "2.",   # Dotted half note
            960: "2",     # Half note
            720: "4.",    # Dotted quarter note
            480: "4",     # Quarter note
            360: "8.",    # Dotted eighth note
            320: "2*2/3", # Half triplet
            240: "8",     # Eighth note
            180: "16.",   # Dotted 16th note
            160: "4*2/3", # Quarter triplet
            120: "16",    # 16th note
            80: "8*2/3",  # Eighth triplet
            60: "32",     # 32nd note
            30: "64"      # 64th note
        }
        return mapping.get(ticks, "4")  # Default to quarter note if not mapped
    except Exception as e:
        logger.error(f"Error converting ticks {ticks}: {e}")
        return "4"

def ticks_to_spacers(ticks: int) -> List[str]:
    """Greedily consume temporal gap into valid Lilypond spacer rests."""
    if ticks <= 0:
        return []
    
    spacers = []
    # Using standard valid LilyPond rhythm sizes sorted by size descending
    mapping = [
        (1920, "1"), (1440, "2."), (960, "2"), (720, "4."), 
        (480, "4"), (360, "8."), (240, "8"), (180, "16."), 
        (120, "16"), (60, "32"), (30, "64")
    ]
    
    remaining = ticks
    for tick_val, duration_str in mapping:
        while remaining >= tick_val:
            spacers.append(f"s{duration_str}")
            remaining -= tick_val
            
    if remaining > 0:
        logger.warning(f"Could not cleanly pad ticks, remainder {remaining} ignored.")
        
    return spacers

def process_element(element: Dict[str, Any]) -> str:
    """Process a single JSON element dictionary into LilyPond syntax.

    Handles 'Chord' (with notes) and 'Rest'.
    """
    try:
        elem_name = element.get("name", "")
        duration_ticks = element.get("durationTicks", 480)
        lily_duration = ticks_to_lilypond_duration(duration_ticks)

        if elem_name == "Rest":
            return f"r{lily_duration}"
        
        elif elem_name == "Chord":
            notes = element.get("notes", [])
            lyrics_data = element.get("lyrics", [])
            lyric_str = ""
            if lyrics_data:
                texts = [lyr.get("text", "") for lyr in lyrics_data if lyr.get("text")]
                if texts:
                    # Sanitize quotes
                    safe_texts = "-".join(texts).replace('"', "'")
                    lyric_str = f'^"{safe_texts}"'

            if not notes:
                return f"r{lily_duration}{lyric_str}"
            
            lily_notes = []
            tied = []  # per note: tied to the next note (written as "~" in LilyPond)
            for note in notes:
                pitch = note.get("pitchMidi")
                tpc = note.get("tpc")
                if pitch is not None:
                    lily_notes.append(midi_to_lilypond_pitch(pitch, tpc))
                    tied.append(bool(note.get("tieForward")))

            if not lily_notes:
                return f"r{lily_duration}{lyric_str}"
            elif len(lily_notes) == 1:
                tie = "~" if tied[0] else ""
                return f"{lily_notes[0]}{lily_duration}{tie}{lyric_str}"
            elif all(tied):
                # Every note tied: one "~" after the whole chord
                joined_notes = " ".join(lily_notes)
                return f"<{joined_notes}>{lily_duration}~{lyric_str}"
            else:
                # Some or no notes tied: "~" after each tied pitch inside the chord
                joined_notes = " ".join(p + ("~" if t else "") for p, t in zip(lily_notes, tied))
                return f"<{joined_notes}>{lily_duration}{lyric_str}"
        else:
            return ""  # Ignore other elements without crashing
    except Exception as e:
        logger.error(f"Error parsing element: {e}")
        return ""

def json_to_lilypond(score_data: Dict[str, Any]) -> str:
    """Convert a JSON response representing a MuseScore measure/score into an absolute LilyPond tree.

    Assembles code into structured staffs and voices using concurrent compilation.
    """
    try:
        # Handle 'currentSelection' raw input format
        if "startStaff" in score_data and "elements" in score_data and isinstance(score_data["elements"], list):
            elements_by_staff = {}
            for elem in score_data["elements"]:
                s_idx = elem.get("staff", score_data.get("startStaff", 0))
                s_name = f"staff{s_idx}"
                if s_name not in elements_by_staff:
                    elements_by_staff[s_name] = []
                elements_by_staff[s_name].append(elem)
                
            staff_names = sorted(list(elements_by_staff.keys()), key=lambda x: int(x.replace("staff", "")))
        elif "startStaff" in score_data and isinstance(score_data.get("elements"), dict):
            # The plugin's currentSelection maps "staffN" to that staff's elements
            elements_by_staff = score_data["elements"]
            staff_names = sorted(elements_by_staff.keys(), key=lambda x: int(x.replace("staff", "")))
        else:
            # Handle 'getScore' or standard wrapped output
            staves_info = score_data.get("staves", [])
            staff_names = [st.get("name") for st in staves_info if st.get("visible", True)]
            
            measure = score_data.get("measure", {})
            if not measure:
                measures = score_data.get("measures", [])
                if measures:
                    measure = measures[0]  # Take only the first measure for demonstration
                    
            elements_by_staff = measure.get("elements", {})
            
            if not staff_names:
                staff_names = list(elements_by_staff.keys())

        lily_parts = ["<<"]
        
        for staff in staff_names:
            staff_elements = elements_by_staff.get(staff, [])
            if not staff_elements:
                continue
                
            lily_parts.append("  \\new Staff {")
            lily_parts.append("    <<")
            
            # Group elements by voice (default to voice 1 if unspecified)
            voices: Dict[int, List[Dict[str, Any]]] = {}
            for elem in staff_elements:
                # MuseScore voices are 0-indexed (0 to 3) from our QML plugin
                v = elem.get("voice", 0)
                mapped_v = v + 1
                if mapped_v not in voices:
                    voices[mapped_v] = []
                voices[mapped_v].append(elem)
            # Find base tick for this staff sequence
            base_tick = float('inf')
            for v_idx in voices:
                for elem in voices[v_idx]:
                    t = elem.get("startTick")
                    if t is not None and t < base_tick:
                        base_tick = t
            if base_tick == float('inf'):
                base_tick = 0
                
            voice_strings = []
            voice_commands = {1: "\\voiceOne", 2: "\\voiceTwo", 3: "\\voiceThree", 4: "\\voiceFour"}
            
            for v_idx in sorted(voices.keys()):
                v_elems = voices[v_idx]
                
                # Sort elements temporally to safely compute gaps
                v_elems.sort(key=lambda x: x.get("startTick", 0))
                
                formatted_elems = []
                current_tick = base_tick
                
                for e in v_elems:
                    e_tick = e.get("startTick")
                    
                    # Fill temporal gaps with spacers
                    if e_tick is not None and e_tick > current_tick:
                        gap = e_tick - current_tick
                        spacers = ticks_to_spacers(gap)
                        formatted_elems.extend(spacers)
                        current_tick = e_tick
                    
                    processed = process_element(e)
                    if processed:
                        formatted_elems.append(processed)
                    
                    # Advance internal clock by the element's explicit duration length
                    duration = e.get("durationTicks", 480)
                    if e_tick is not None:
                        current_tick = e_tick + duration
                    else:
                        current_tick += duration
                
                cmd = voice_commands.get(v_idx, "\\voiceOne")
                voice_str = f"{cmd} " + " ".join(formatted_elems)
                voice_strings.append(f"      \\new Voice {{ {voice_str} }}")
            
            # Use LilyPond's double backslash separator for multiple concurrent voices
            voices_combined = " \\\\\n".join(voice_strings)
            lily_parts.append(voices_combined)
            
            lily_parts.append("    >>")
            lily_parts.append("  }")
            
        lily_parts.append(">>")
        
        return "\n".join(lily_parts)
        
    except Exception as e:
        logger.error(f"Failed to convert JSON to LilyPond: {e}")
        return "<< >>"


def _staff_sort_key(name: str) -> int:
    try:
        return int(name.replace("staff", ""))
    except ValueError:
        return 0


def _bar_comment(measure: Dict[str, Any]) -> str:
    """"% m.N" plus the displayed number when it differs, and repeat barlines, e.g. "% m.4 (bar 6) |: :|x7"."""
    comment = f"% m.{measure.get('measure')}"
    if measure.get("number") is not None and measure.get("number") != measure.get("measure"):
        comment += f" (bar {measure['number']})"
    if measure.get("repeatStart"):
        comment += " |:"
    if measure.get("repeatEnd"):
        comment += f" :|x{measure['repeatEnd']}"
    return comment


def score_to_lilypond(score_data: Dict[str, Any]) -> str:
    """Convert a getScore analysis (one or more measures) into LilyPond, one staff per block.

    Every voice is padded with spacers so that each measure ends on a bar check
    followed by a "% m.N" comment, which keeps measures easy to compare by eye.
    """
    try:
        measures = score_data.get("measures", [])
        staves_info = score_data.get("staves", [])
        staff_names = [st.get("name") for st in staves_info if st.get("visible", True)]
        if not staff_names:
            names = {name for m in measures for name in (m.get("elements") or {})}
            staff_names = sorted(names, key=_staff_sort_key)
        short_names = {st.get("name"): st.get("shortName") for st in staves_info}

        # Measure end ticks: explicit duration, else the next measure's start, else open-ended
        ends: List[Optional[int]] = []
        for i, m in enumerate(measures):
            if m.get("durationTicks"):
                ends.append(m.get("startTick", 0) + m["durationTicks"])
            elif i + 1 < len(measures):
                ends.append(measures[i + 1].get("startTick", 0))
            else:
                ends.append(None)

        voice_commands = {1: "\\voiceOne", 2: "\\voiceTwo", 3: "\\voiceThree", 4: "\\voiceFour"}
        lily_parts = ["<<"]
        for staff in staff_names:
            voices = sorted({
                e.get("voice", 0)
                for m in measures
                for e in (m.get("elements") or {}).get(staff, [])
            })
            if not voices:
                continue

            label = short_names.get(staff)
            lily_parts.append(f"  \\new Staff {{ % {staff}" + (f" ({label})" if label else ""))
            lily_parts.append("    <<")
            voice_strings = []
            for v in voices:
                bars = []
                for m, end_tick in zip(measures, ends):
                    start_tick = m.get("startTick", 0)
                    elems = sorted(
                        (e for e in (m.get("elements") or {}).get(staff, []) if e.get("voice", 0) == v),
                        key=lambda e: e.get("startTick", 0),
                    )
                    tokens: List[str] = []
                    current = start_tick
                    for e in elems:
                        e_tick = e.get("startTick", current)
                        if e_tick > current:
                            tokens.extend(ticks_to_spacers(e_tick - current))
                        duration = e.get("durationTicks", 0)
                        if e.get("name") == "MeasureRepeat":
                            tokens.extend(ticks_to_spacers(duration))
                            tokens.append("%{ measure repeat %}")
                        else:
                            processed = process_element(e)
                            if processed:
                                tokens.append(processed)
                        current = max(current, e_tick + duration)
                    if end_tick is not None and end_tick > current:
                        tokens.extend(ticks_to_spacers(end_tick - current))
                    bars.append(" ".join(tokens) + " | " + _bar_comment(m))

                body = "\n        ".join(bars)
                cmd = voice_commands.get(v + 1, "\\voiceOne")
                voice_strings.append(f"      \\new Voice {{ {cmd}\n        {body}\n      }}")
            lily_parts.append(" \\\\\n".join(voice_strings))
            lily_parts.append("    >>")
            lily_parts.append("  }")
        lily_parts.append(">>")
        return "\n".join(lily_parts)

    except Exception as e:
        logger.error(f"Failed to convert score to LilyPond: {e}")
        return "<< >>"
