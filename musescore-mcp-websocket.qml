import QtQuick 2.9
import MuseScore 3.0

MuseScore {
    id: root
    menuPath: "Plugins.MuseScore API Server"
    description: "Exposes MuseScore API via WebSocket (Clean Version)"
    version: "2.0"
    
    property var clientConnections: []
    property var selectionState: ({
        startStaff: 0,
        endStaff: 1,
        startTick: 0,
        elements: []
    })

    // ========================================
    // WEBSOCKET & MESSAGE PROCESSING
    // ========================================

    function processMessage(message, clientId) {
        console.log("Received message: " + message);
        try {
            var command = JSON.parse(message);
            var result = processCommand(command);
            api.websocketserver.send(clientId, JSON.stringify({
                status: "success",
                result: result
            }));
        } catch (e) {
            console.log("Error processing command: " + e.toString());
            api.websocketserver.send(clientId, JSON.stringify({
                status: "error",
                message: e.toString()
            }));
        }
    }

    function processCommand(command) {
        console.log("Processing command: " + command.action);
        
        switch(command.action) {
            // Core operations
            case "getScore":                return getScore(command.params);
            case "syncStateToSelection":    return syncStateToSelection();
            case "ping":                    return "pong";
            case "undo":                    return undo();
            case "goToBeginningOfScore":    return goToBeginningOfScore();
            case "processSequence":         return processSequence(command.params);

            // Navigation
            case "getCursorInfo":           return getCursorInfo(command.params);
            case "goToMeasure":             return goToMeasure(command.params);
            case "goToFinalMeasure":        return goToFinalMeasure(command.params);
            case "nextElement":             return nextElement(command.params);
            case "prevElement":             return prevElement(command.params);
            case "nextStaff":               return nextStaff(command.params);
            case "prevStaff":               return prevStaff(command.params);

            // Selection
            case "selectCurrentMeasure":    return selectCurrentMeasure(command.params);
            case "selectCustomRange":       return selectCustomRange(command.params);

            // Notes & Music
            case "addNote":                 return addNote(command.params);
            case "scoreContext":            return scoreContext();
            case "readPassage":             return readPassage(command.params);
            case "writePassage":            return writePassage(command.params);
            case "addRest":                 return addRest(command.params);
            case "addTuplet":               return addTuplet(command.params);
            case "addLyrics":               return addLyrics(command.params);

            // Measures
            case "appendMeasure":           return appendMeasure(command.params);
            case "insertMeasure":           return insertMeasure(command.params);
            case "deleteSelection":         return deleteSelection(command.params);

            // Staff & Instruments
            case "addInstrument":           return addInstrument(command.params);
            case "setStaffMute":            return setStaffMute(command.params);
            case "setInstrumentSound":      return setInstrumentSound(command.params);
            case "setTimeSignature":        return setTimeSignature(command.params);
            case "setTempo":                return setTempo(command.params);

            default:
                throw new Error("Unknown command: " + command.action);
        }
    }

    // ========================================
    // UTILITY FUNCTIONS
    // ========================================

    function validateParams(params, required) {
        var missing = [];
        for (var i = 0; i < required.length; i++) {
            if (params[required[i]] === undefined) {
                missing.push(required[i]);
            }
        }
        return missing.length > 0 ? { error: "Missing required parameters: " + missing.join(", ") } : { valid: true };
    }

    function executeWithUndo(operation) {
        if (!curScore) return { error: "No score open" };
        
        curScore.startCmd();
        try {
            var result = operation();
            curScore.endCmd();
            return result;
        } catch (e) {
            curScore.endCmd(true);
            return { error: e.toString() };
        }
    }

    function getNoteName(note) {
        const noteNames = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
        return noteNames[note % 12];
    }

    function getTpcName(tpc) {
        if (tpc === -1) return "Fbb";
        var tpcNames = [
            "Cbb", "Gbb", "Dbb", "Abb", "Ebb", "Bbb", "Fb",
            "Cb",  "Gb",  "Db",  "Ab",  "Eb",  "Bb",  "F",
            "C",   "G",   "D",   "A",   "E",   "B",   "F#",
            "C#",  "G#",  "D#",  "A#",  "E#",  "B#",  "F##",
            "C##", "G##", "D##", "A##", "E##", "B##", "F###"
        ];
        if (tpc >= 0 && tpc < tpcNames.length) {
            return tpcNames[tpc];
        }
        return "Unknown";
    }

    function getDurationName(duration) {
        const durationNames = ["LONG","BREVE","WHOLE","HALF","QUARTER","EIGHTH","16TH","32ND","64TH","128TH","256TH","512TH","1024TH","ZERO","MEASURE","INVALID"];
        return durationNames[duration] || "UNKNOWN";
    }

    // ========================================
    // CURSOR MANAGEMENT
    // ========================================

    function createCursor(params) {
        if (!curScore) throw new Error("No score open");
        
        if (!params || Object.keys(params).length === 0) {
            params = selectionState;
        }
        
        var cursor = curScore.newCursor();
        cursor.inputStateMode = Cursor.INPUT_STATE_SYNC_WITH_SCORE;
        
        // Set track
        if (params.startStaff !== undefined) cursor.staffIdx = params.startStaff;
        if (params.voice !== undefined) cursor.voice = params.voice;
        
        // Position cursor
        if (params.rewindMode !== undefined) {
            cursor.rewind(params.rewindMode);
        } else if (params.startTick !== undefined) {
            try {
                cursor.rewindToTick(params.startTick);
            } catch (e) {
                console.log("rewindToTick failed, using manual navigation");
                cursor.rewind(0);
                while (cursor.tick < params.startTick && cursor.next()) {}
            }
        } else if (params.measure !== undefined) {
            cursor.rewind(0);
            for (var i = 0; i < params.measure && cursor.nextMeasure(); i++) {}
        } else {
            cursor.rewind(0);
        }
        
        // Set duration
        if (params.duration) {
            cursor.setDuration(params.duration.numerator || 1, params.duration.denominator || 4);
        }
        
        return cursor;
    }

    function initCursorState() {
        if (!curScore) return "No score open";
        
        return executeWithUndo(function() {
            var cursor = curScore.newCursor();
            cursor.rewind(0);

            var startTick = cursor.tick;
            cursor.next();
            var endTick = cursor.tick;
            var element = cursor.element;

            selectionState = {
                startStaff: cursor.staffIdx,
                endStaff: cursor.staffIdx + 1,
                startTick: startTick,
                elements: element ? [processElement(element)] : []
            };
            
            curScore.selection.clear();
            curScore.selection.selectRange(startTick, endTick, 0, 0);
            
            return "Initialized at " + [startTick, endTick, 0, 0].join(',');
        });
    }

    // ========================================
    // ELEMENT PROCESSING
    // ========================================

    function processElement(element) {
        if (!element) return null;
        if (element.name !== "Chord" && element.name !== "Rest") return null;

        var base = {
            name: element.name,
            durationTicks: element.actualDuration ? element.actualDuration.ticks : 0,
            isTie: element.tieForward ? true : false,
            isTuplet: element.tuplet ? true : false
        };

        if (element.lyrics && element.lyrics.length > 0) {
            base.lyrics = [];
            for (var l = 0; l < element.lyrics.length; l++) {
                var lyr = element.lyrics[l];
                if (lyr) {
                    base.lyrics.push({
                        text: lyr.text,
                        no: lyr.no,
                        syllabic: lyr.syllabic
                    });
                }
            }
        }

        if (element.name === "Chord") {
            base.notes = [];
            var notesObj = element.notes || {};
            var keys = Object.keys(notesObj);
            for (var k = 0; k < keys.length; k++) {
                var note = notesObj[keys[k]];
                base.notes.push({
                    pitchMidi: note.pitch,
                    tpc: note.tpc,
                    pitchName: getTpcName(note.tpc)
                });
            }
        }
                
        return base;
    }

    // ========================================
    // CORE OPERATIONS
    // ========================================

    function undo() {
        return executeWithUndo(function() {
            cmd("undo");
            return { success: true, message: "Undo successful" };
        });
    }

    function goToBeginningOfScore() {
        var response = initCursorState();
        return { 
            success: true, 
            message: response, 
            currentSelection: selectionState,
            currentScore: getScoreSummary()
        };
    }

    function processSequence(params) {
        if (!curScore) return { error: "No score open" };
        if (!params.sequence) return { error: "No sequence specified" };

        var validCommands = [
            "getScore", "addNote", "addRest", "addTuplet", "appendMeasure", "deleteSelection",
            "getCursorInfo", "goToMeasure", "nextElement", "prevElement", "nextStaff", "prevStaff",
            "selectCurrentMeasure", "processSequence", "insertMeasure", "goToFinalMeasure",
            "goToBeginningOfScore", "setTimeSignature", "addLyrics", "addInstrument",    
            "setStaffMute", "setInstrumentSound", "setTempo"
        ];

        try {
            for (var i = 0; i < params.sequence.length; i++) {
                var command = params.sequence[i];
                if (!validCommands.includes(command.action)) {
                    throw new Error("Invalid command: " + command.action);
                }
                processCommand(command);
            }
            return { success: true, message: "Sequence processed", currentSelection: selectionState };
        } catch (e) {
            return { error: e.toString() };
        }
    }

    // ========================================
    // NAVIGATION FUNCTIONS
    // ========================================

    function syncStateToSelection() {
        if (!curScore) return { error: "No score open" };

        try {
            var selection = curScore.selection;
            var startSegment = selection.startSegment;
            var endSegment = selection.endSegment;

            if (startSegment && endSegment) {
                var cursor = createCursor({
                    startTick: startSegment.tick,
                    startStaff: selection.startStaff    
                });

                var elementsMap = {};
                for (var st = selection.startStaff; st < selection.endStaff; st++) {
                    elementsMap[`staff${st}`] = [];
                }

                var currentSegment = startSegment;
                while (currentSegment && currentSegment.tick < endSegment.tick) {
                    for (var s = selection.startStaff; s < selection.endStaff; s++) {
                        for (var v = 0; v < 4; v++) {
                            var track = s * 4 + v;
                            var el = currentSegment.elementAt(track);
                            if (el) {
                                var processed = processElement(el);
                                if (processed) {
                                    processed.voice = v;
                                    processed.startTick = currentSegment.tick;
                                    elementsMap[`staff${s}`].push(processed);
                                }
                            }
                        }
                    }
                    currentSegment = currentSegment.next;
                }

                selectionState = {
                    startStaff: selection.startStaff,
                    endStaff: selection.endStaff,
                    startTick: startSegment.tick,
                    elements: elementsMap,
                    totalDuration: endSegment.tick - startSegment.tick
                };
            } else {
                var c = createCursor();
                if (c && c.element) {
                    var elElement = processElement(c.element);
                    elElement.startTick = c.tick;
                    var sStart = selection.startStaff || 0;
                    var singleMap = {};
                    singleMap[`staff${sStart}`] = [elElement];
                    
                    selectionState = {
                        startStaff: sStart,
                        endStaff: sStart + 1,
                        startTick: c.tick,
                        elements: singleMap,
                        totalDuration: elElement.durationTicks
                    };
                } else {
                    return { error: "No valid selection or cursor elements found" };
                }
            }

            return { success: true, currentSelection: selectionState };
        } catch (e) {
            return { success: false, error: e.toString() };
        }
    }

    function getCursorInfo(params) {
        if (!curScore) return { error: "No score open" };
        
        syncStateToSelection();
        return { 
            success: true, 
            currentSelection: selectionState, 
            currentScore: params && params.verbose !== "false" ? getScoreSummary() : null
        };
    }

    function goToMeasure(params) {
        var validation = validateParams(params, ["measure"]);
        if (!validation.valid) return validation;

        return executeWithUndo(function() {
            var score = getScoreSummary();
            if (params.measure < 1 || params.measure > score.measures.length) {
                return { error: "Invalid measure number" };
            }
            var measureIdx = params.measure - 1;
            var measure = score.measures[measureIdx];
            var startTick = measure.startTick;
            
            var endTick = (measureIdx + 1 < score.measures.length) ? score.measures[measureIdx + 1].startTick : curScore.lastSegment.tick;
            
            curScore.selection.clear();
            curScore.selection.selectRange(startTick, endTick, 0, curScore.nstaves);
            
            var res = syncStateToSelection();
            if (res.error) return res;
            
            return { success: true, currentSelection: selectionState };
        });
    }

    function nextElement(params) {
        return executeWithUndo(function() {
            syncStateToSelection();
            
            var cursor = createCursor({ 
                startTick: selectionState.startTick, 
                startStaff: selectionState.startStaff 
            });

            var numElements = params && params.numElements || 1;
            var success = true;
            for (var i = 0; i < numElements && success; i++) {
                success = cursor.next();
            }
            
            if (success) {
                var element = processElement(cursor.element);
                var startTick = cursor.tick;
                var staffIdx = cursor.staffIdx;
                
                // Check if we need to append a measure
                if (startTick + element.durationTicks >= curScore.lastSegment.tick) {
                    cmd("append-measure");
                }

                curScore.selection.clear();
                curScore.selection.selectRange(startTick, startTick + element.durationTicks, staffIdx, staffIdx + 1);

                selectionState = {
                    startStaff: staffIdx,
                    endStaff: staffIdx + 1,
                    startTick: startTick,
                    elements: [element],
                    totalDuration: element.durationTicks
                };
                
                return { success: true, currentSelection: selectionState };
            } else {
                return { success: false, message: "End of score reached" };
            }
        });
    }

    function prevElement(params) {
        return executeWithUndo(function() {
            syncStateToSelection();
            
            var cursor = createCursor({ 
                startTick: selectionState.startTick, 
                startStaff: selectionState.startStaff 
            });

            var endTick = cursor.tick;
            var numElements = params && params.numElements || 1;
            var success = true;
            
            for (var i = 0; i < numElements && success; i++) {
                success = cursor.prev();
            }

            if (success) {
                var element = processElement(cursor.element);
                var startTick = cursor.tick;
                var staffIdx = cursor.staffIdx;
                
                curScore.selection.clear();
                curScore.selection.selectRange(startTick, endTick, staffIdx, staffIdx + 1);

                selectionState = {
                    startStaff: staffIdx,
                    endStaff: staffIdx + 1,
                    startTick: startTick,
                    elements: [element],
                    totalDuration: endTick - startTick
                };
                
                return { success: true, currentSelection: selectionState };
            } else {
                return { success: false, message: "Beginning of score reached" };
            }
        });
    }

    function nextStaff(params) {
        return executeWithUndo(function() {
            syncStateToSelection();

            if (selectionState.endStaff >= curScore.nstaves) {
                return { success: false, message: "Already at last staff" };
            }

            var newStaff = selectionState.endStaff;
            var cursor = createCursor({ 
                startTick: selectionState.startTick, 
                startStaff: newStaff 
            });

            var element = processElement(cursor.element);
            
            curScore.selection.clear();
            curScore.selection.selectRange(
                selectionState.startTick, 
                selectionState.startTick + element.durationTicks, 
                newStaff, 
                newStaff + 1
            );

            selectionState = {
                startStaff: newStaff,
                endStaff: newStaff + 1,
                startTick: selectionState.startTick,
                elements: [element],
                totalDuration: element.durationTicks
            };

            return { success: true, currentSelection: selectionState };
        });
    }

    function prevStaff(params) {
        return executeWithUndo(function() {
            syncStateToSelection();

            if (selectionState.startStaff <= 0) {
                return { success: false, message: "Already at first staff" };
            }

            var newStaff = selectionState.startStaff - 1;
            var cursor = createCursor({ 
                startTick: selectionState.startTick, 
                startStaff: newStaff 
            });

            var element = processElement(cursor.element);
            
            curScore.selection.clear();
            curScore.selection.selectRange(
                selectionState.startTick, 
                selectionState.startTick + element.durationTicks, 
                newStaff, 
                newStaff + 1
            );

            selectionState = {
                startStaff: newStaff,
                endStaff: newStaff + 1,
                startTick: selectionState.startTick,
                elements: [element],
                totalDuration: element.durationTicks
            };

            return { success: true, currentSelection: selectionState };
        });
    }

    function goToFinalMeasure(params) {
        return executeWithUndo(function() {
            var cursor = createCursor({ startTick: 0 });
            var count = 0;
            var startTick = 0;

            while (cursor.nextMeasure()) {
                startTick = cursor.tick;
                count++;
            }

            if (count === 0) {
                return { success: false, message: "Already at the last measure" };
            }

            cursor.rewindToTick(startTick);
            cursor.next();
            var endTick = cursor.tick;
            var staffIdx = cursor.staffIdx;
            
            curScore.selection.clear();
            curScore.selection.selectRange(startTick, endTick, staffIdx, staffIdx + 1);
            
            selectionState = {
                startStaff: staffIdx,
                endStaff: staffIdx + 1,
                startTick: startTick,
                elements: [processElement(cursor.element)],
                totalDuration: endTick - startTick
            };

            return { success: true, currentSelection: selectionState };
        });
    }

    // ========================================
    // SELECTION FUNCTIONS
    // ========================================

    function selectCurrentMeasure() {
        return executeWithUndo(function() {
            var cursor = createCursor({ 
                startTick: selectionState.startTick || 0, 
                startStaff: selectionState.startStaff || 0 
            });

            var currTick = cursor.tick;
            var scoreSummary = getScoreSummary();

            var measureIdx = scoreSummary.measures.filter(function(m) { 
                return m.startTick <= currTick; 
            }).length - 1;
            
            if (measureIdx < 0) return { error: "Invalid cursor position" };
            
            var measure = scoreSummary.measures[measureIdx];
            var startTick = measure.startTick;
            var endTick = (measureIdx + 1 < scoreSummary.measures.length) ? scoreSummary.measures[measureIdx + 1].startTick : curScore.lastSegment.tick;

            curScore.selection.clear();
            curScore.selection.selectRange(startTick, endTick, 0, curScore.nstaves);

            var res = syncStateToSelection();
            if (res.error) return res;
            
            return { success: true, message: `Selected measure ${measureIdx + 1}`, currentSelection: selectionState };
        });
    }

    // Lookup tables the passage serialiser needs. Properties, not `var`s: a
    // top-level `var` in a QML object is a load error, and the whole plugin
    // fails to load with "JavaScript declaration outside Script element".
    property var tpcNames: [
        "Cbb", "Gbb", "Dbb", "Abb", "Ebb", "Bbb", "Fb",
        "Cb",  "Gb",  "Db",  "Ab",  "Eb",  "Bb",  "F",
        "C",   "G",   "D",   "A",   "E",   "B",   "F#",
        "C#",  "G#",  "D#",  "A#",  "E#",  "B#",  "F##",
        "C##", "G##", "D##", "A##", "E##", "B##", "F###"
    ]

    property var durationSymbols: ({ "w": 1920, "h": 960, "q": 480, "e": 240,
                                     "s": 120, "t": 60, "x": 30 })
    property var durationOrder: ["w", "h", "q", "e", "s", "t", "x"]
    property var dotTexts: ["", ".", ".."]
    property var dotFactors: [1, 1.5, 1.75]

    // ========================================
    // PASSAGE API  (compact read/write form)
    // ========================================
    //
    // A compact textual form for reading and writing music: "Eb2/h." rather than
    // a JSON element per note, and "[c4/e d4/e e4/e]3:2" for a tuplet. A read of
    // a 117-measure score costs 9.4 KB instead of 134 KB, and a write is
    // validated in full before anything is touched.
    //
    // The grammar is specified in the fork's SPEC.md section 1 and PARSED in
    // src/passage.py. This side only serialises, because the score data is here;
    // parsing is the failure-prone half and belongs where it can be tested
    // without MuseScore in the loop.
    //
    // Two guards worth keeping when editing any of this:
    //   - Never write outside the score. Doing so left curScore unusable and
    //     killed the process, twice. scoreEndTick() exists for that reason.
    //   - A selection change must happen OUTSIDE startCmd(). selectRange() is
    //     refused while an operation is in progress, silently.

    function elementToPassage(el, scale) {
        if (!el) return null;
        var isChord = (el.type === Element.CHORD || el.name === "Chord");
        var isRest = (el.type === Element.REST || el.name === "Rest");
        if (!isChord && !isRest) return null;

        var actual = el.actualDuration ? el.actualDuration.ticks : 0;
        if (!actual) return null;
        var written = scale ? Math.round(actual * scale.n / scale.d) : actual;

        var body;
        if (isRest) {
            body = "r";
        } else {
            var items = [];
            var notesObj = el.notes || {};
            var keys = Object.keys(notesObj);
            for (var k = 0; k < keys.length; k++) {
                var n = notesObj[keys[k]];
                if (!n) continue;
                items.push({ midi: n.pitch,
                             text: pitchText(n.pitch, n.tpc) + (n.tieForward ? "~" : "") });
            }
            if (!items.length) return null;
            items.sort(function(a, b) { return a.midi - b.midi; });
            var parts = [];
            for (var i = 0; i < items.length; i++) parts.push(items[i].text);
            body = parts.join("+");
        }
        return body + "/" + durationText(written);
    }

    function passageForStaffRange(staff, startTick, endTick) {
        if (!curScore) return "";
        var cursor = curScore.newCursor();
        cursor.inputStateMode = Cursor.INPUT_STATE_INDEPENDENT;
        cursor.staffIdx = staff;
        cursor.voice = 0;
        cursor.rewind(0);

        var tokens = [];
        var seg = cursor.segment;
        while (seg && seg.tick < startTick) seg = seg.next;

        while (seg && seg.tick < endTick) {
            var el = seg.elementAt(staff * 4);
            if (!el) { seg = seg.next; continue; }

            var tup = el.tuplet;
            if (!tup) {
                var tok = elementToPassage(el, null);
                if (tok) tokens.push(tok);
                seg = seg.next;
                continue;
            }

            // Gather the elements belonging to this tuplet. Object identity is
            // the only handle the API gives for "same tuplet".
            var ratio = tupletRatioOf(tup);
            var inner = [];
            var walk = seg;
            while (walk && walk.tick < endTick) {
                var wel = walk.elementAt(staff * 4);
                if (!wel || wel.tuplet !== tup) break;
                var wtok = elementToPassage(wel, ratio);
                if (wtok) inner.push(wtok);
                walk = walk.next;
            }

            if (ratio && inner.length > 1) {
                tokens.push("[" + inner.join(" ") + "]" + ratio.n + ":" + ratio.d);
                seg = walk;
            } else {
                // Cannot group it confidently. Emit raw ticks rather than invent
                // a bracket that may be wrong — the Python parser refuses
                // ambiguous raw ticks, so this degrades into a clear error
                // instead of a silent corruption.
                var solo = elementToPassage(el, null);
                if (solo) tokens.push(solo);
                seg = seg.next;
            }
        }
        return tokens.join(" ");
    }

    function readPassage(params) {
        if (!curScore) return { error: "No score open" };
        params = params || {};

        var starts = measureStarts();
        var n = starts.length;
        var count = params.measures !== undefined ? params.measures : 1;
        var firstIdx;

        if (params.measure !== undefined) {
            firstIdx = params.measure - 1;
            if (firstIdx < 0 || firstIdx >= n)
                return { error: "measure out of range (1.." + n + ")" };
        } else if (params.startTick !== undefined) {
            firstIdx = 0;
            for (var i = 0; i < n; i++) if (starts[i] <= params.startTick) firstIdx = i;
        } else {
            return { error: "give measure or startTick" };
        }

        var lastIdx = Math.min(firstIdx + count - 1, n - 1);
        var staves = params.staves !== undefined ? params.staves : [0];

        var out = [];
        for (var m = firstIdx; m <= lastIdx; m++) {
            // The last measure has no following start; read to the end of the score.
            var mEnd = (m + 1 < n) ? starts[m + 1] : Number.MAX_VALUE;
            var entry = { m: m + 1, tick: starts[m] };
            for (var s = 0; s < staves.length; s++) {
                var staff = staves[s];
                if (staff < 0 || staff >= curScore.nstaves) continue;
                entry["s" + staff] = passageForStaffRange(staff, starts[m], mEnd);
            }
            out.push(entry);
        }

        var result = { measures: out, ticksPerQuarter: 480 };
        if (params.includeContext !== false) result.context = passageContext(starts);
        return { success: true, passage: result };
    }

    function writePassage(params) {
        if (!curScore) return { error: "No score open" };
        var validation = validateParams(params, ["staff", "startTick", "ticks", "elements"]);
        if (!validation.valid) return validation;
        if (!params.elements || !params.elements.length)
            return { error: "elements must not be empty" };

        var staff = params.staff;
        var voice = params.voice !== undefined ? params.voice : 0;
        var startTick = params.startTick;

        if (staff < 0 || staff >= curScore.nstaves)
            return { error: "staff out of range (0.." + (curScore.nstaves - 1) + ")" };
        if (voice < 0 || voice > 3)
            return { error: "voice out of range (0..3)" };

        // Tuplet writing is known-dangerous — addTuplet() can snap backwards and
        // swallow the preceding note, and every following note then lands a slot
        // late. Refuse rather than guess: the Python side already refuses
        // ambiguous raw ticks for the same reason.
        for (var t = 0; t < params.elements.length; t++) {
            if (params.elements[t].tuplet) {
                return { error: "tuplet writing is not implemented yet; "
                              + "write it by hand, or use add_tuplet_run" };
            }
        }

        var staffCount = curScore.nstaves;

        var response = executeWithUndo(function() {
            var cursor = curScore.newCursor();
            cursor.inputStateMode = Cursor.INPUT_STATE_INDEPENDENT;
            cursor.staffIdx = staff;
            cursor.voice = voice;
            cursor.rewindToTick(startTick);

            // rewindToTick() lands only on an EXISTING segment, so inside an
            // empty measure it snaps to a barline. Walk back to at-or-before the
            // target and fill the gap with a rest, which creates the segment the
            // write needs to start from. Same trick as addTupletRun.
            if (startTick > 0) {
                while (cursor.tick > startTick && cursor.prev()) { }
                var gap = startTick - cursor.tick;
                if (gap > 0) {
                    cursor.setDuration(gap, 1920);
                    cursor.addRest();
                }
            }

            var tick = startTick;
            for (var i = 0; i < params.elements.length; i++) {
                var el = params.elements[i];
                writeElementAt(cursor, el, tick);
                tick += el.ticks;
            }

            // Read back inside the same undo group and hand the string to Python
            // to compare. A tool's own success flag is not evidence, and a
            // target-only check would happily confirm a write that landed on the
            // wrong staff.
            return {
                actual: passageForStaffRange(staff, startTick, startTick + params.ticks),
                neighbour: staff > 0
                    ? passageForStaffRange(staff - 1, startTick, startTick + params.ticks)
                    : (staff + 1 < staffCount
                        ? passageForStaffRange(staff + 1, startTick, startTick + params.ticks)
                        : null)
            };
        });

        if (response && response.error) return response;
        return {
            success: true,
            staff: staff,
            startTick: startTick,
            ticks: params.ticks,
            actual: response.actual,
            neighbour_staff: staff > 0 ? staff - 1 : (staff + 1 < staffCount ? staff + 1 : null),
            neighbour: response.neighbour
        };
    }

    function writeElementAt(cursor, el, tick) {
        if (el.rest) {
            cursor.rewindToTick(tick);
            cursor.setDuration(el.ticks, 1920);
            cursor.addRest();
            return;
        }
        for (var p = 0; p < el.pitches.length; p++) {
            cursor.rewindToTick(tick);
            cursor.setDuration(el.ticks, 1920);
            cursor.addNote(el.pitches[p].midi, p > 0);
        }
    }

    function passageContext(starts) {
        var key = [];
        var timeSig = [];
        if (!curScore) return { key: key, time_sig: timeSig };
        var cursor = curScore.newCursor();
        cursor.inputStateMode = Cursor.INPUT_STATE_INDEPENDENT;
        cursor.staffIdx = 0;

        var lastKey = null;
        var lastTs = null;
        for (var m = 0; m < starts.length; m++) {
            cursor.rewindToTick(starts[m]);
            var k = cursor.keySignature;
            if (k !== lastKey) {
                key.push({ m: m + 1, value: keyNameOf(k) });
                lastKey = k;
            }

            // Cursor exposes no time-signature property. Read it off the measure
            // when the API offers one, and fall back to the measure's length.
            var ts = null;
            try {
                var meas = cursor.measure;
                if (meas && meas.timesigNominal) {
                    ts = meas.timesigNominal.numerator + "/" + meas.timesigNominal.denominator;
                }
            } catch (e) { ts = null; }
            if (ts === null) {
                var nextStart = (m + 1 < starts.length) ? starts[m + 1] : null;
                ts = "ticks:" + (nextStart === null ? "?" : (nextStart - starts[m]));
            }
            if (ts !== lastTs) {
                timeSig.push({ m: m + 1, value: ts });
                lastTs = ts;
            }
        }
        return { key: key, time_sig: timeSig };
    }

    function scoreContext() {
        if (!curScore) return { error: "No score open" };
        var staves = [];
        for (var i = 0; i < curScore.nstaves; i++) {
            var staff = curScore.staves && curScore.staves[i] ||
                        (typeof curScore.staff === "function" ? curScore.staff(i) : null);
            staves.push({
                name: "staff" + i,
                shortName: staff ? staff.shortName : "",
                visible: staff ? !staff.invisible : true
            });
        }
        return {
            success: true,
            context: {
                title: curScore.metaTag("workTitle") || curScore.title || "",
                path: (typeof curScore.path === "string" ? curScore.path : null),
                numMeasures: curScore.nmeasures,
                endTick: scoreEndTick(),
                nstaves: curScore.nstaves,
                staves: staves,
                measureStarts: measureStarts()
            }
        };
    }

    function scoreEndTick() {
        if (!curScore) return 0;
        var c = curScore.newCursor();
        c.inputStateMode = Cursor.INPUT_STATE_INDEPENDENT;
        c.rewind(0);
        var last = c.tick;
        // The element has to be remembered INSIDE the loop. Once next() has run
        // off the end, cursor.element is null, so reading it afterwards returned
        // the last bar's start tick and dropped its duration — which made the
        // final bar unwritable, and read as "past the end of the score".
        var lastEl = c.element;
        while (c.next()) {
            last = c.tick;
            lastEl = c.element;
        }
        if (lastEl && lastEl.actualDuration && lastEl.actualDuration.ticks) {
            last += lastEl.actualDuration.ticks;
        }
        return last;
    }

    function durationSymbolFor(ticks) {
        for (var i = 0; i < durationOrder.length; i++) {
            for (var d = 0; d < dotFactors.length; d++) {
                if (durationSymbols[durationOrder[i]] * dotFactors[d] === ticks)
                    return durationOrder[i] + dotTexts[d];
            }
        }
        return null;
    }

    function pitchText(pitchMidi, tpc) {
        var name = (tpc === undefined || tpc === null || tpc < 0) ? "Fbb" : tpcNames[tpc];
        if (name === undefined) name = "C";
        var letter = name.charAt(0);
        var acc = name.substring(1);
        var letters = { "C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11 };
        var offsets = { "": 0, "n": 0, "#": 1, "##": 2, "b": -1, "bb": -2 };
        var letterSemitone = letters[letter];
        if (letterSemitone === undefined) { letter = "C"; acc = ""; letterSemitone = 0; }
        var accOffset = offsets[acc];
        if (accOffset === undefined) accOffset = 0;
        var natural = pitchMidi - accOffset;
        var octave = Math.floor((natural - letterSemitone) / 12) - 1;
        return name + octave;
    }

    function tupletRatioOf(tup) {
        if (!tup) return null;
        var n = tup.actualNotes;
        var d = tup.normalNotes;
        if ((n === undefined || d === undefined) && tup.ratio) {
            n = tup.ratio.numerator;
            d = tup.ratio.denominator;
        }
        if (!n || !d) return null;
        return { n: n, d: d };
    }

    function durationText(ticks) {
        var sym = durationSymbolFor(ticks);
        return sym !== null ? sym : String(ticks);
    }

    function keyNameOf(fifths) {
        var table = { "-7": "Cb", "-6": "Gb", "-5": "Db", "-4": "Ab", "-3": "Eb",
                      "-2": "Bb", "-1": "F", "0": "C", "1": "G", "2": "D",
                      "3": "A", "4": "E", "5": "B", "6": "F#", "7": "C#" };
        var k = table[String(fifths)];
        return k === undefined ? ("fifths=" + fifths) : k;
    }

    function measureStarts() {
        var starts = [];
        if (!curScore) return starts;
        var cursor = curScore.newCursor();
        cursor.inputStateMode = Cursor.INPUT_STATE_INDEPENDENT;
        cursor.rewind(0);
        for (var i = 0; i < curScore.nmeasures; i++) {
            starts.push(cursor.tick);
            if (i + 1 < curScore.nmeasures && !cursor.nextMeasure()) break;
        }
        return starts;
    }

    function spannerKindOf(el) {
        if (!el) return null;
        if (el.type === Element.SLUR    || el.name === "Slur")    return "slur";
        if (el.type === Element.TIE     || el.name === "Tie")     return "tie";
        if (el.type === Element.HAIRPIN || el.name === "Hairpin") return "hairpin";
        return null;
    }

    function bridgeLog(msg) {
        try { api.log.info("[mcp-bridge] " + msg); } catch (e) { }
    }

    function tickFraction(ticks) {
        return fraction(ticks, 1920);
    }

    function selectCustomRange(params) {
        var validation = validateParams(params, ["startTick", "endTick", "startStaff", "endStaff"]);
        if (!validation.valid) return validation;

        return executeWithUndo(function() {
            var startTick = params.startTick;
            var endTick = params.endTick;
            var startStaff = params.startStaff;
            var endStaff = params.endStaff;

            // Visual GUI snap
            curScore.selection.clear();
            curScore.selection.selectRange(startTick, endTick, startStaff, endStaff);

            var elementsMap = {};
            for (var st = startStaff; st <= endStaff; st++) {
                elementsMap[`staff${st}`] = [];
            }

            var c = createCursor({ startTick: 0, startStaff: startStaff });
            c.rewind(0);
            var currentSegment = c.segment;

            while (currentSegment && currentSegment.tick < startTick) {
                currentSegment = currentSegment.next;
            }

            while (currentSegment && currentSegment.tick < endTick) {
                for (var s = startStaff; s <= endStaff; s++) {
                    for (var v = 0; v < 4; v++) {
                        var track = s * 4 + v;
                        var el = currentSegment.elementAt(track);
                        if (el) {
                            var processed = processElement(el);
                            if (processed) {
                                processed.voice = v;
                                processed.startTick = currentSegment.tick;
                                elementsMap[`staff${s}`].push(processed);
                            }
                        }
                    }
                }
                currentSegment = currentSegment.next;
            }

            selectionState = {
                startStaff: startStaff,
                endStaff: endStaff,
                startTick: startTick,
                elements: elementsMap,
                totalDuration: endTick - startTick
            };

            return { success: true, message: "Custom range mapped", currentSelection: selectionState };
        });
    }

    // ========================================
    // NOTE & MUSIC OPERATIONS
    // ========================================

    function addNote(params) {
        var validation = validateParams(params, ["pitch", "duration", "advanceCursorAfterAction"]);
        if (!validation.valid) return validation;

        if (!params.duration.numerator || !params.duration.denominator) {
            return { error: "Duration must be specified as { numerator: int, denominator: int }" };
        }

        return executeWithUndo(function() {
            syncStateToSelection();
            
            var cursor = createCursor();
            cursor.setDuration(params.duration.numerator, params.duration.denominator);
            
            // Melody is the default. Pass addToChord: true to stack a pitch on the current chord.
            cursor.addNote(params.pitch, params.addToChord === true);
            cursor.rewindToTick(selectionState.startTick);

            if (params.advanceCursorAfterAction) {
                cursor.next();
            }

            var element = processElement(cursor.element);
            var startTick = cursor.tick;
            var staffIdx = cursor.staffIdx;
            var durationTicks = element && element.durationTicks ? element.durationTicks : 0;

            curScore.selection.clear();
            if (durationTicks > 0) {
                curScore.selection.selectRange(startTick, startTick + durationTicks, staffIdx, staffIdx + 1);
            }

            var syncRes = syncStateToSelection();
            if (syncRes && syncRes.error) {
                var staffMap = {};
                staffMap["staff" + staffIdx] = element ? [element] : [];
                selectionState = {
                    startStaff: staffIdx,
                    endStaff: staffIdx + 1,
                    startTick: startTick,
                    elements: staffMap,
                    totalDuration: durationTicks
                };
            }

            return { 
                success: true, 
                message: "Note added with pitch " + params.pitch,
                currentSelection: selectionState
            };
        });
    }

    function addRest(params) {
        var validation = validateParams(params, ["duration", "advanceCursorAfterAction"]);
        if (!validation.valid) return validation;

        if (!params.duration.numerator || !params.duration.denominator) {
            return { error: "Duration must be specified as { numerator: int, denominator: int }" };
        }

        return executeWithUndo(function() {
            syncStateToSelection();
            
            var cursor = createCursor();
            cursor.setDuration(params.duration.numerator, params.duration.denominator);
            cursor.addRest();
            cursor.rewindToTick(selectionState.startTick);

            if (params.advanceCursorAfterAction) {
                cursor.next();
            }

            var element = processElement(cursor.element);
            var startTick = cursor.tick;
            var staffIdx = cursor.staffIdx;

            curScore.selection.clear();
            curScore.selection.selectRange(startTick, startTick + element.durationTicks, staffIdx, staffIdx + 1);

            selectionState = {
                startStaff: staffIdx,
                endStaff: staffIdx + 1,
                startTick: startTick,
                elements: [element],
                totalDuration: element.durationTicks
            };

            return { success: true, message: "Rest added", currentSelection: selectionState };
        });
    }

    function addTuplet(params) {
        var validation = validateParams(params, ["ratio", "duration", "advanceCursorAfterAction"]);
        if (!validation.valid) return validation;

        if (!params.ratio.numerator || !params.ratio.denominator || 
            !params.duration.numerator || !params.duration.denominator) {
            return { error: "Ratio and duration must be specified as { numerator: int, denominator: int }" };
        }
        
        return executeWithUndo(function() {
            var cursor = createCursor();
            cursor.setDuration(params.duration.numerator, params.duration.denominator);
            
            var ratio = fraction(params.ratio.numerator, params.ratio.denominator);
            var duration = fraction(params.duration.numerator, params.duration.denominator);
            
            cursor.addTuplet(ratio, duration);
            cursor.next();

            if (params.advanceCursorAfterAction) {
                cursor.next();
            }

            var element = processElement(cursor.element);
            var startTick = cursor.tick;
            var staffIdx = cursor.staffIdx;

            selectionState = {
                startStaff: staffIdx,
                endStaff: staffIdx + 1,
                startTick: startTick,
                elements: [element],
                totalDuration: element.durationTicks
            };

            return { 
                success: true, 
                message: "Tuplet " + params.ratio.numerator + ":" + params.ratio.denominator + " added",
                currentSelection: selectionState
            };
        });
    }

    function addLyrics(params) {
        if (!params.lyrics || !Array.isArray(params.lyrics) || params.lyrics.length === 0) {
            return { error: "Lyrics must be specified as an array of strings" };
        }
        
        return executeWithUndo(function() {
            syncStateToSelection();
            
            var cursor = createCursor({ 
                startTick: selectionState.startTick, 
                startStaff: selectionState.startStaff 
            });
            
            var lyricsArray = params.lyrics.slice();
            var verse = params.verse || 0;
            var addedCount = 0;
            var skippedCount = 0;
            
            while (cursor.element && lyricsArray.length > 0) {
                var element = cursor.element;
                
                if (element.type === Element.CHORD || element.name === "Chord") {
                    var lyr = newElement(Element.LYRICS);
                    lyr.text = lyricsArray.shift();
                    lyr.verse = verse;
                    
                    cursor.add(lyr);
                    addedCount++;
                } else if (element.type === Element.REST || element.name === "Rest") {
                    skippedCount++;
                }
                
                if (!cursor.next()) break;
            }
            
            var finalElement = processElement(cursor.element) || selectionState.elements[0];
            var finalTick = cursor.tick;
            var staffIdx = cursor.staffIdx;
            
            selectionState = {
                startStaff: staffIdx,
                endStaff: staffIdx + 1,
                startTick: finalTick,
                elements: [finalElement],
                totalDuration: finalElement.durationTicks || selectionState.totalDuration
            };
            
            curScore.selection.clear();
            curScore.selection.selectRange(finalTick, finalTick + (finalElement.durationTicks || 0), staffIdx, staffIdx + 1);
            
            var message = `Added ${addedCount} lyrics`;
            if (skippedCount > 0) message += `, skipped ${skippedCount} rests`;
            if (lyricsArray.length > 0) message += `, ${lyricsArray.length} lyrics remaining`;
            
            return { 
                success: true, 
                message: message,
                addedCount: addedCount,
                skippedCount: skippedCount,
                remainingLyrics: lyricsArray,
                currentSelection: selectionState
            };
        });
    }

    // ========================================
    // MEASURE OPERATIONS
    // ========================================

    function appendMeasure(params) {
        return executeWithUndo(function() {
            var count = params && params.count || 1;
            
            for (var i = 0; i < count; i++) {
                cmd("append-measure");
            }
            
            return { 
                success: true, 
                message: count + " measure(s) appended",
                currentSelection: selectionState
            };
        });
    }

    function insertMeasure(params) {
        return executeWithUndo(function() {
            cmd("insert-measure");
            syncStateToSelection();
            
            return { 
                success: true, 
                message: "Measure inserted",
                currentSelection: selectionState
            };
        });
    }

    function deleteSelection(params) {
        return executeWithUndo(function() {
            if (params && params.measure) {
                createCursor({ measure: params.measure });
            }
            
            cmd("delete");
            
            return { 
                success: true, 
                message: "Selection deleted",
                currentSelection: selectionState
            };
        });
    }

    // ========================================
    // STAFF & INSTRUMENT OPERATIONS
    // ========================================

    function addInstrument(params) {
        var validation = validateParams(params, ["instrumentId"]);
        if (!validation.valid) return validation;
        
        return executeWithUndo(function() {
            curScore.appendPart(params.instrumentId);
            return { success: true, message: "Instrument " + params.instrumentId + " added" };
        });
    }

    function setStaffMute(params) {
        var validation = validateParams(params, ["staff"]);
        if (!validation.valid) return validation;
        
        return executeWithUndo(function() {
            var staff = curScore.staves && curScore.staves[params.staff] || 
                       (typeof curScore.staff === "function" ? curScore.staff(params.staff) : null);
            
            if (staff) {
                staff.invisible = Boolean(params.mute);
                return { success: true, message: "Staff " + (params.mute ? "muted" : "unmuted") };
            } else {
                return { error: "Staff not found" };
            }
        });
    }

    function setInstrumentSound(params) {
        var validation = validateParams(params, ["staff", "instrumentId"]);
        if (!validation.valid) return validation;
        
        return executeWithUndo(function() {
            cmd("instruments");
            return { success: true, message: "Instrument dialog opened, manual selection required" };
        });
    }

    function setTimeSignature(params) {
        var validation = validateParams(params, ["numerator", "denominator"]);
        if (!validation.valid) return validation;
        
        return executeWithUndo(function() {
            var cursor = createCursor();
            var currTick = cursor.tick;
            var currStaff = cursor.staffIdx;

            var ts = newElement(Element.TIMESIG);
            ts.timesig = fraction(params.numerator, params.denominator);
            cursor.add(ts);

            return { 
                success: true, 
                message: "Time signature set to " + params.numerator + "/" + params.denominator
            };
        });
    }

    function setTempo(params) {
        var validation = validateParams(params, ["bpm"]);
        if (!validation.valid) return validation;
        
        return executeWithUndo(function() {
            var cursor = createCursor();
            
            var tempo = newElement(Element.TEMPO_TEXT);
            tempo.tempo = params.bpm / 60.0;
            tempo.text = "♩ = " + params.bpm;
            
            cursor.add(tempo);
            
            return { success: true, message: "Tempo set to " + params.bpm + " BPM" };
        });
    }

    // ========================================
    // SCORE ANALYSIS
    // ========================================

    function getScore(params) {
        if (!curScore) return { error: "No score open" };
        
        try {
            return { success: true, analysis: getScoreSummary() };
        } catch (e) {
            return { error: e.toString() };
        }
    }

    function getScoreSummary() {
        if (!curScore) return { error: "No score open" };

        return executeWithUndo(function() {
            var tempState = selectionState;
            var score = {
                title: curScore.metaTag("workTitle") || curScore.title || "",
                numMeasures: curScore.nmeasures,
                measures: [],
                staves: []
            };
            
            // Analyze staves
            for (var i = 0; i < curScore.nstaves; i++) {
                var staff = curScore.staves && curScore.staves[i] || 
                           (typeof curScore.staff === "function" ? curScore.staff(i) : null);
                
                score.staves.push({
                    name: `staff${i}`,
                    shortName: staff ? staff.shortName : "",
                    visible: staff ? !staff.invisible : true
                });
            }

            // Analyze measures
            var cursor = createCursor({startTick: 0});
            var measureBoundaries = [];

            // Get measure boundaries
            for (var i = 0; i < curScore.nmeasures; i++) {
                var measure = {
                    measure: i + 1, 
                    startTick: cursor.tick,
                    numElements: 0, 
                    elements: {}
                };

                for (var j = 0; j < curScore.nstaves; j++) {
                    measure.elements[`staff${j}`] = [];
                }

                measureBoundaries.push(cursor.tick);
                score.measures.push(measure);
                cursor.nextMeasure();
            }

            // Process elements for each staff
            for (var k = 0; k < curScore.nstaves; k++) {
                cursor.rewind(0);
                var currentSegment = cursor.segment;

                while (currentSegment) {
                    var measureIdx = measureBoundaries.filter(function(tick) {
                        return tick <= currentSegment.tick;
                    }).length - 1;

                    for (var v = 0; v < 4; v++) {
                        var track = k * 4 + v;
                        var el = currentSegment.elementAt(track);
                        if (el) {
                            score.measures[measureIdx].numElements++;
                            var processedElement = processElement(el);
                            if (processedElement) {
                                processedElement.startTick = currentSegment.tick;
                                processedElement.voice = v;
                                score.measures[measureIdx].elements[`staff${k}`].push(processedElement);
                            }
                        }
                    }
                    currentSegment = currentSegment.next;
                }
            }

            // Restore state
            selectionState = tempState;
            return score;
        });
    }

    // ========================================
    // INITIALIZATION
    // ========================================

    // Uses the bridgeLog() already defined above. console.log is NOT usable
    // here: a plugin's stdout goes nowhere, so this file used to start in
    // complete silence and the only way to tell "running" from "never loaded"
    // was to guess.
    onRun: {
        var v = (typeof mscoreMajorVersion !== "undefined") ? mscoreMajorVersion : "?";
        var w = (typeof mscoreMinorVersion !== "undefined") ? mscoreMinorVersion : "?";
        bridgeLog("starting on MuseScore " + v + "." + w
            + "; engraving api " + (api.engraving ? "ok" : "MISSING")
            + ", websocketserver " + (typeof api.websocketserver)
            + ", score " + (curScore
                ? ("'" + (curScore.metaTag("workTitle") || curScore.title
                          || "untitled") + "', " + curScore.nmeasures + " measures")
                : "NONE - open a score"));

        // MuseScore 4.7 exposes api.websocketserver in the GUI but NOT in the
        // console/--extension context. Calling listen() unguarded throws
        // "TypeError: Cannot call method 'listen' of undefined", which reads
        // like a broken plugin rather than a context without the API.
        if (typeof api.websocketserver === "undefined") {
            bridgeLog("CANNOT START: no api.websocketserver in this context "
                + "(typeof is 'undefined'). Run the plugin from the GUI - "
                + "Plugins > MuseScore API Server - where it does exist.");
            return;
        }

        api.websocketserver.listen(8765, function(clientId) {
            bridgeLog("listening on 8765; client connected, id " + clientId);
            clientConnections.push(clientId);

            api.websocketserver.onMessage(clientId, function(message) {
                processMessage(message, clientId);
            });
        });

        if (curScore) {
            initCursorState();
        }
    }
}