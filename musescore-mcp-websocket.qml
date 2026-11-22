import QtQuick 2.9
import MuseScore 3.0

MuseScore {
    id: root
    menuPath: "Plugins.MuseScore API Server"
    title: "MuseScore API Server"
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
            case "selectMeasures":          return selectMeasuresAction(command.params);

            // Notes & Music
            case "addNote":                 return addNote(command.params);
            case "addTie":                  return addTie(command.params);
            case "addTiedNote":             return addTiedNote(command.params);
            case "addRest":                 return addRest(command.params);
            case "addTuplet":               return addTuplet(command.params);
            case "addLyrics":               return addLyrics(command.params);

            // Measures
            case "appendMeasure":           return appendMeasure(command.params);
            case "insertMeasure":           return insertMeasure(command.params);
            case "deleteSelection":         return deleteSelection(command.params);
            case "deleteMeasures":          return deleteMeasures(command.params);

            // Staff & Instruments
            case "addInstrument":           return addInstrument(command.params);
            case "setStaffMute":            return setStaffMute(command.params);
            case "setInstrumentSound":      return setInstrumentSound(command.params);
            case "setTimeSignature":        return setTimeSignature(command.params);
            case "setTempo":                return setTempo(command.params);

            // Repeats & Formatting
            case "setRepeatBarlines":       return setRepeatBarlines(command.params);
            case "addVolta":                return addVolta(command.params);
            case "colorRange":              return colorRange(command.params);
            case "setStyle":                return setStyle(command.params);
            case "getStyle":                return getStyle(command.params);
            case "renderScore":             return renderScore(command.params);
            case "barNumbers":              return barNumbers();
            case "addRehearsalMark":        return addRehearsalMark(command.params);
            case "addMarker":               return addMarker(command.params);
            case "setChordSymbol":          return setChordSymbol(command.params);
            case "moveChordSymbol":         return moveChordSymbol(command.params);
            case "addBreak":                return addBreak(command.params);
            case "setMeasuresPerSystem":    return setMeasuresPerSystem(command.params);
            case "findElements":            return findElements(command.params);
            case "setProperties":           return setProperties(command.params);
            case "setMeasureStretch":       return setMeasureStretch(command.params);
            case "addSectionCounts":        return addSectionCounts(command.params);
            case "addHighlight":            return addHighlight(command.params);
            case "addLabel":                return addLabel(command.params);
            case "addText":                 return addText(command.params);
            case "addArticulation":         return addArticulation(command.params);
            case "removeArticulations":     return removeArticulations(command.params);
            case "ghostNotes":              return ghostNotes(command.params);
            case "beamOverRests":           return beamOverRests(command.params);
            case "removeAnnotations":       return removeAnnotations(command.params);
            case "highlightNotes":          return highlightNotes(command.params);
            case "highlightMarkings":       return highlightMarkings(command.params);
            case "highlightSymbols":        return highlightSymbols(command.params);

            // Measure numbers
            case "setMeasureNumbering":     return setMeasureNumbering(command.params);
            case "numberAsPlayed":          return numberAsPlayed(command.params);
            case "clearHighlights":         return clearHighlights(command.params);

            // Score files & parts
            case "scoreFileInfo":           return scoreFileInfo();
            case "ensureScoreId":           return ensureScoreId(command.params);
            case "saveScore":               return saveScore();
            case "exportScore":             return exportScore(command.params);
            case "openScore":               return openScore(command.params);
            case "reopenScore":             return reopenScore(command.params);
            case "removeParts":             return removeParts(command.params);

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

    // ========================================
    // MEASURE HELPERS
    // ========================================

    // Measure object for a 1-based measure number, or null when out of range.
    function getMeasure(number) {
        if (!curScore || number < 1) return null;
        var m = curScore.firstMeasure;
        for (var i = 1; m && i < number; i++) {
            m = m.nextMeasure;
        }
        return m;
    }

    function measureStartTick(m) {
        return m.firstSegment.tick;
    }

    function measureEndTick(m) {
        return m.nextMeasure ? measureStartTick(m.nextMeasure) : curScore.lastSegment.tick;
    }

    // Resolve a 1-based measure range (and optional staff range) to ticks.
    // endStaff is exclusive and defaults to the last staff.
    function measureRange(params) {
        var validation = validateParams(params, ["startMeasure"]);
        if (!validation.valid) return validation;

        var endMeasure = params.endMeasure || params.startMeasure;
        var first = getMeasure(params.startMeasure);
        var last = getMeasure(endMeasure);
        if (!first || !last || endMeasure < params.startMeasure) {
            return { error: "Invalid measure range " + params.startMeasure + "-" + endMeasure + " (score has " + curScore.nmeasures + " measures)" };
        }

        var startStaff = params.startStaff !== undefined ? params.startStaff : 0;
        var endStaff = params.endStaff !== undefined && params.endStaff !== null ? params.endStaff : curScore.nstaves;
        if (startStaff < 0 || endStaff > curScore.nstaves || startStaff >= endStaff) {
            return { error: "Invalid staff range " + startStaff + "-" + endStaff + " (score has " + curScore.nstaves + " staves, endStaff is exclusive)" };
        }

        return {
            valid: true,
            startMeasure: params.startMeasure,
            endMeasure: endMeasure,
            firstMeasure: first,
            lastMeasure: last,
            startTick: measureStartTick(first),
            endTick: measureEndTick(last),
            startStaff: startStaff,
            endStaff: endStaff
        };
    }

    // Length of one beat in ticks: the time signature's denominator (a quarter in 4/4, an eighth in 6/8).
    // The beat (1-based, to two decimals) a segment starts on in its measure, as findElements gives it.
    function beatOfSegment(seg) {
        var m = seg.parent;
        return Math.round((1 + (seg.tick - measureStartTick(m)) / beatTicks(m)) * 100) / 100;
    }

    function beatTicks(m) {
        var sig = m.timesigActual;
        return sig && sig.denominator ? 1920 / sig.denominator : 480;
    }

    // Narrow a measure range to beats: startBeat (1-based, fractions allowed) in the first measure,
    // endBeat (inclusive, the whole beat) in the last measure. Returns an error object or the range.
    function applyBeats(range, params) {
        if (params.startBeat !== undefined && params.startBeat !== null) {
            var startOffset = (params.startBeat - 1) * beatTicks(range.firstMeasure);
            if (params.startBeat < 1 || range.startTick + startOffset >= measureEndTick(range.firstMeasure)) {
                return { error: "Beat " + params.startBeat + " is outside measure " + range.startMeasure };
            }
            range.startTick += Math.round(startOffset);
        }
        if (params.endBeat !== undefined && params.endBeat !== null) {
            var lastStart = measureStartTick(range.lastMeasure);
            var endTick = lastStart + Math.round(params.endBeat * beatTicks(range.lastMeasure));
            if (params.endBeat < 1 || endTick > range.endTick) {
                return { error: "Beat " + params.endBeat + " is outside measure " + range.endMeasure };
            }
            range.endTick = endTick;
        }
        if (range.startTick >= range.endTick) return { error: "The beat range is empty" };
        return range;
    }

    // The end tick to pass to selectRange. A range that ends at the end of the score leaves the last
    // measure out (the selection is empty when that is the only one), and MuseScore then refuses actions
    // that need a selection (insert-measure, delete) or does nothing (time-delete); ending just past the
    // score's last segment takes it in.
    function selectionEndTick(endTick) {
        var scoreEnd = curScore.lastSegment.tick;
        return endTick >= scoreEnd ? scoreEnd + 1 : endTick;
    }

    function selectMeasureRange(range) {
        curScore.selection.clear();
        curScore.selection.selectRange(range.startTick, selectionEndTick(range.endTick), range.startStaff, range.endStaff);
        selectionState = {
            startStaff: range.startStaff,
            endStaff: range.endStaff,
            startTick: range.startTick,
            elements: {},
            totalDuration: range.endTick - range.startTick
        };
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
        if (element.name === "MeasureRepeat") {
            return {
                name: element.name,
                numMeasures: element.subtype || 1,
                durationTicks: element.actualDuration ? element.actualDuration.ticks : 0
            };
        }
        if (element.name !== "Chord" && element.name !== "Rest") return null;

        var base = {
            name: element.name,
            durationTicks: element.actualDuration ? element.actualDuration.ticks : 0,
            isTie: false,  // set below: true when a note of the chord is tied to the next note
            isTuplet: element.tuplet ? true : false
        };

        if (element.lyrics && element.lyrics.length > 0) {
            base.lyrics = [];
            for (var l = 0; l < element.lyrics.length; l++) {
                var lyr = element.lyrics[l];
                if (lyr) {
                    var held = lyr.lyricTicks;
                    base.lyrics.push({
                        text: lyr.text,
                        no: lyr.no,
                        syllabic: lyr.syllabic,
                        lyricTicks: held && held.ticks ? held.ticks : 0
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
                var noteData = {
                    pitchMidi: note.pitch,
                    tpc: note.tpc,
                    pitchName: getTpcName(note.tpc)
                };
                if (note.ghost) noteData.ghost = true;
                // Ties belong to single notes, not to the chord. Like ghost, only reported when present.
                if (note.tieForward) {
                    noteData.tieForward = true;
                    base.isTie = true;
                }
                if (note.tieBack) noteData.tieBack = true;
                base.notes.push(noteData);
            }
            var arts = element.articulations || [];
            if (arts.length) {
                base.articulations = [];
                for (var a = 0; a < arts.length; a++) base.articulations.push(articulationName(arts[a].symbol));
            }
            if (element.tremoloSingleChord) base.tremolo = true;
        }
                
        return base;
    }

    // ========================================
    // CORE OPERATIONS
    // ========================================

    // MuseScore 4.7 calls the undo action "action://notation/undo"; the old name "undo" is not a registered action
    // any more (cmd() only translates a few old names), so cmd("undo") did nothing. Undo is a command of its own,
    // so it also runs outside startCmd()/endCmd().
    function undo() {
        if (!curScore) return { error: "No score open" };
        cmd("action://notation/undo");
        return { success: true, message: "Undo successful" };
    }

    function goToBeginningOfScore() {
        var response = initCursorState();
        return { 
            success: true, 
            message: response, 
            currentSelection: selectionState,
            currentScore: getScoreSummary({ includeElements: false })
        };
    }

    function processSequence(params) {
        if (!curScore) return { error: "No score open" };
        if (!params.sequence) return { error: "No sequence specified" };

        var validCommands = [
            "getScore", "addNote", "addTie", "addTiedNote", "addRest", "addTuplet", "appendMeasure", "deleteSelection",
            "getCursorInfo", "goToMeasure", "nextElement", "prevElement", "nextStaff", "prevStaff",
            "selectCurrentMeasure", "processSequence", "insertMeasure", "goToFinalMeasure",
            "goToBeginningOfScore", "setTimeSignature", "addLyrics", "addInstrument",
            "setStaffMute", "setInstrumentSound", "setTempo",
            "selectMeasures", "setRepeatBarlines", "addVolta", "colorRange", "deleteMeasures",
            "setStyle", "addRehearsalMark", "addMarker", "setChordSymbol", "moveChordSymbol", "addBreak", "setMeasuresPerSystem", "findElements", "setProperties", "setMeasureStretch", "addSectionCounts", "removeParts", "addHighlight", "addLabel", "clearHighlights",
            "highlightNotes", "highlightMarkings", "highlightSymbols",
            "setMeasureNumbering", "numberAsPlayed", "addText", "removeAnnotations",
            "addArticulation", "removeArticulations", "ghostNotes", "beamOverRests"
        ];

        try {
            for (var i = 0; i < params.sequence.length; i++) {
                var command = params.sequence[i];
                if (!validCommands.includes(command.action)) {
                    throw new Error("Invalid command: " + command.action);
                }
                // A failing step stops the sequence, so later steps don't build on it and the
                // reply doesn't claim success. Each step is its own undo command, so earlier ones stay.
                var result = processCommand(command);
                if (result && typeof result === "object" && result.error !== undefined) {
                    return {
                        error: "Step " + (i + 1) + " of " + params.sequence.length + " (" + command.action +
                               ") failed: " + result.error + ". " +
                               (i ? "Steps 1-" + i + " were applied." : "No step was applied.")
                    };
                }
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
            // A selection that runs to the end of the score (see selectionEndTick) has no end segment
            var endTick = endSegment ? endSegment.tick : curScore.lastSegment.tick;

            if (startSegment) {
                var cursor = createCursor({
                    startTick: startSegment.tick,
                    startStaff: selection.startStaff    
                });

                var elementsMap = {};
                for (var st = selection.startStaff; st < selection.endStaff; st++) {
                    elementsMap[`staff${st}`] = [];
                }

                var currentSegment = startSegment;
                while (currentSegment && currentSegment.tick < endTick) {
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
                    totalDuration: endTick - startSegment.tick
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
            currentScore: params && params.verbose !== "false" ? getScoreSummary({ includeElements: false }) : null
        };
    }

    // Select one whole measure on every staff and move the cursor state to its first beat
    // (staff 0), where the next cursor action (addNote, setTimeSignature, addLyrics...) acts.
    // Selecting is not a score edit, so this runs outside startCmd()/endCmd(): inside a
    // command the new selection has no segments yet, syncStateToSelection() fell back to
    // the previous cursor position (often bar 1), and the following actions landed there.
    // The state is also set from the measure's own ticks in case the sync still disagrees.
    function selectWholeMeasure(range) {
        selectMeasureRange(range);
        var res = syncStateToSelection();
        if (res.error || selectionState.startTick !== range.startTick) {
            selectMeasureRange(range);
        }
        return { success: true, currentSelection: selectionState };
    }

    function goToMeasure(params) {
        var validation = validateParams(params, ["measure"]);
        if (!validation.valid) return validation;
        if (!curScore) return { error: "No score open" };
        if (params.measure < 1 || params.measure > curScore.nmeasures) {
            return { error: "Invalid measure number" };
        }

        var range = measureRange({ startMeasure: params.measure });
        if (!range.valid) return range;
        return selectWholeMeasure(range);
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
                // An error, not success: false, so processSequence stops and the tool fails
                return { error: "End of score reached" };
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
                return { error: "Beginning of score reached" };
            }
        });
    }

    function nextStaff(params) {
        return executeWithUndo(function() {
            syncStateToSelection();

            // From the first selected staff: goToMeasure selects every staff, and the cursor is on the first
            var newStaff = selectionState.startStaff + 1;
            if (newStaff >= curScore.nstaves) {
                return { error: "Already at the last staff" };
            }

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
                return { error: "Already at the first staff" };
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

    // The whole last measure on every staff, as goToMeasure selects a measure (also in a one-measure score).
    function goToFinalMeasure(params) {
        if (!curScore) return { error: "No score open" };
        var range = measureRange({ startMeasure: curScore.nmeasures });
        if (!range.valid) return range;
        return selectWholeMeasure(range);
    }

    // ========================================
    // SELECTION FUNCTIONS
    // ========================================

    // Same stale-selection issue as goToMeasure, so it shares selectWholeMeasure().
    function selectCurrentMeasure() {
        if (!curScore) return { error: "No score open" };

        var tick = selectionState.startTick || 0;
        var number = 1;
        var m = curScore.firstMeasure;
        while (m && tick >= measureEndTick(m)) {
            m = m.nextMeasure;
            number++;
        }
        if (!m) return { error: "Invalid cursor position" };

        var result = selectWholeMeasure(measureRange({ startMeasure: number }));
        result.message = "Selected measure " + number;
        return result;
    }

    // endStaff is exclusive, as MuseScore's selection.selectRange() treats it and as the rest of this
    // plugin does (measureRange, syncStateToSelection, the range actions of processSequence): one staff
    // is startStaff = 2, endStaff = 3. The element map used to be built with an inclusive loop, so it
    // reported a staff MuseScore had not selected, and startStaff === endStaff selected nothing at all
    // while still reporting success, which sent the edits that followed to staff 0.
    function selectCustomRange(params) {
        var validation = validateParams(params, ["startTick", "endTick", "startStaff", "endStaff"]);
        if (!validation.valid) return validation;
        if (!curScore) return { error: "No score open" };
        if (params.startStaff < 0 || params.endStaff > curScore.nstaves || params.startStaff >= params.endStaff) {
            return { error: "Invalid staff range " + params.startStaff + "-" + params.endStaff + " (score has " +
                     curScore.nstaves + " staves, endStaff is exclusive)" };
        }

        return executeWithUndo(function() {
            var startTick = params.startTick;
            var endTick = params.endTick;
            var startStaff = params.startStaff;
            var endStaff = params.endStaff;

            // Visual GUI snap
            curScore.selection.clear();
            curScore.selection.selectRange(startTick, selectionEndTick(endTick), startStaff, endStaff);

            var elementsMap = {};
            for (var st = startStaff; st < endStaff; st++) {
                elementsMap[`staff${st}`] = [];
            }

            var c = createCursor({ startTick: 0, startStaff: startStaff });
            c.rewind(0);
            var currentSegment = c.segment;

            while (currentSegment && currentSegment.tick < startTick) {
                currentSegment = currentSegment.next;
            }

            while (currentSegment && currentSegment.tick < endTick) {
                for (var s = startStaff; s < endStaff; s++) {
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
            var addToChord = params.addToChord === true;
            cursor.addNote(params.pitch, addToChord);
            var startTick = selectionState.startTick;
            var staffIdx = cursor.staffIdx;

            // Build the state from the position itself: reading the selection back with
            // syncStateToSelection() would give the old one, since MuseScore applies a new
            // selection only when the command ends. Advancing goes past the whole note, also
            // past the tied part of a note split at the barline (not onto it), but not past a
            // tie the chord added to already had.
            var currentSelection = params.advanceCursorAfterAction
                ? advanceCursorTo(tickAfter(startTick, staffIdx, !addToChord), staffIdx)
                : moveCursorTo(startTick, staffIdx);
            return {
                success: true,
                message: "Note added with pitch " + params.pitch,
                currentSelection: currentSelection
            };
        });
    }

    function chordPitches(chord) {
        var pitches = [];
        var notes = chord.notes || [];
        for (var i = 0; i < notes.length; i++) pitches.push(notes[i].pitch);
        return pitches;
    }

    function noteWithPitch(chord, pitch) {
        var notes = chord.notes || [];
        for (var i = 0; i < notes.length; i++) {
            if (notes[i].pitch === pitch) return notes[i];
        }
        return null;
    }

    // Tie notes of `first` to the same pitches in `second` (the next chord in the same staff and voice).
    // MuseScore's tie command does not refuse a note without a matching pitch in the next chord: it inserts
    // a new tied note and overwrites the music after it. So only notes whose pitch is in both chords are
    // selected. Returns { error } when nothing can be tied, else the tied, already tied and skipped pitches.
    // Throws when MuseScore did not make a tie, which rolls the whole action back.
    function tieMatchingNotes(first, second, firstTick, staffIdx, requested) {
        var firstPitches = chordPitches(first);
        var secondPitches = chordPitches(second);
        var candidates = requested || firstPitches;
        var toTie = [];
        var alreadyTied = [];
        var skipped = [];
        var seen = [];
        for (var i = 0; i < candidates.length; i++) {
            var pitch = candidates[i];
            if (seen.indexOf(pitch) >= 0) continue;
            seen.push(pitch);
            var note = noteWithPitch(first, pitch);
            if (!note || secondPitches.indexOf(pitch) < 0) {
                skipped.push(pitch);
            } else if (note.tieForward) {
                alreadyTied.push(pitch);
            } else {
                toTie.push(note);
            }
        }
        if (toTie.length === 0 && alreadyTied.length === 0) {
            return {
                error: "No pitch to tie: the chord at the cursor has [" + firstPitches.join(", ") +
                    "], the next chord has [" + secondPitches.join(", ") + "]" +
                    (requested ? ", requested [" + requested.join(", ") + "]" : "")
            };
        }

        if (toTie.length > 0) {
            curScore.selection.clear();
            for (var t = 0; t < toTie.length; t++) curScore.selection.select(toTie[t], t > 0);
            cmd("tie");
        }

        // Check the result on a fresh cursor
        var check = createCursor({ startTick: firstTick, startStaff: staffIdx });
        var tied = [];
        for (var n = 0; n < toTie.length; n++) {
            var tiedNote = noteWithPitch(check.element, toTie[n].pitch);
            if (!tiedNote || !tiedNote.tieForward) {
                throw new Error("MuseScore did not tie pitch " + toTie[n].pitch);
            }
            tied.push(toTie[n].pitch);
        }
        return { tied: tied, alreadyTied: alreadyTied, skipped: skipped };
    }

    // Put the cursor on the element at `tick` and return the new cursor state. MuseScore applies a new
    // selection only when the command ends, so reading it back here (syncStateToSelection) would still give
    // the old one. The state is built directly instead, as nextElement does.
    // The tick right after the chord or rest at `tick`: past its actual duration (which counts tuplets) and,
    // with followTies, past the tied parts MuseScore splits a note into when it crosses a barline.
    function tickAfter(tick, staffIdx, followTies) {
        var t = tick;
        while (true) {
            var el = createCursor({ startTick: t, startStaff: staffIdx }).element;
            if (!el || !el.actualDuration || el.actualDuration.ticks <= 0) return t;
            t += el.actualDuration.ticks;
            var tied = followTies && el.notes && el.notes.length > 0 && el.notes[0].tieForward;
            if (!tied) return t;
        }
    }

    // moveCursorTo for a cursor that advances: at the end of the score a measure is appended first, so the
    // next note has a place (as nextElement does at the last note) instead of overwriting the one before.
    function advanceCursorTo(tick, staffIdx) {
        if (tick >= curScore.lastSegment.tick) cmd("append-measure");
        return moveCursorTo(tick, staffIdx);
    }

    function moveCursorTo(tick, staffIdx) {
        var element = processElement(createCursor({ startTick: tick, startStaff: staffIdx }).element);
        var ticks = element ? element.durationTicks : 0;
        curScore.selection.clear();
        if (ticks > 0) curScore.selection.selectRange(tick, tick + ticks, staffIdx, staffIdx + 1);
        if (element) element.startTick = tick;
        var staffMap = {};
        staffMap["staff" + staffIdx] = element ? [element] : [];
        selectionState = {
            startStaff: staffIdx,
            endStaff: staffIdx + 1,
            startTick: tick,
            elements: staffMap,
            totalDuration: ticks
        };
        return selectionState;
    }

    function tieMessage(result) {
        return "Tied " + (result.tied.length ? "pitch " + result.tied.join(", ") : "nothing new") +
            (result.alreadyTied.length ? " (already tied: " + result.alreadyTied.join(", ") + ")" : "");
    }

    // Tie notes of the chord at the cursor to the same pitches in the next chord (same staff and voice).
    // Afterwards the cursor is on the second chord, so another addTie continues a tie chain.
    function addTie(params) {
        params = params || {};

        return executeWithUndo(function() {
            syncStateToSelection();

            var cursor = createCursor({ startTick: selectionState.startTick, startStaff: selectionState.startStaff });
            var first = cursor.element;
            var firstTick = cursor.tick;
            if (!first || first.name !== "Chord") {
                return { error: "No note or chord at the cursor to tie from" };
            }
            if (!cursor.next() || !cursor.element) {
                return { error: "No note or chord after the cursor to tie to" };
            }
            var second = cursor.element;
            var secondTick = cursor.tick;
            var staffIdx = cursor.staffIdx;
            if (second.name !== "Chord") {
                return { error: "The element after the cursor is a rest: a tie needs a note of the same pitch" };
            }

            var requested = params.pitches && params.pitches.length ? params.pitches : null;
            var result = tieMatchingNotes(first, second, firstTick, staffIdx, requested);
            if (result.error) return result;

            return {
                success: true,
                message: tieMessage(result),
                tiedPitches: result.tied,
                alreadyTied: result.alreadyTied,
                skippedPitches: result.skipped,
                currentSelection: moveCursorTo(secondTick, staffIdx)
            };
        });
    }

    // Write the next note or chord at the cursor, tied to the chord before the cursor: like "+" in
    // MuseScore's note input. The new chord gets the given duration and the pitches of the chord before,
    // or only the given ones, plus extraPitches without a tie. The whole chord is written before tying:
    // MuseScore treats tied chords as one, so a pitch added to the second chord after the tie would also be
    // added (and tied) to the first. Writing and tying are one undo step; a failed tie removes the note again.
    function addTiedNote(params) {
        var validation = validateParams(params, ["duration", "advanceCursorAfterAction"]);
        if (!validation.valid) return validation;
        if (!params.duration.numerator || !params.duration.denominator) {
            return { error: "Duration must be specified as { numerator: int, denominator: int }" };
        }

        return executeWithUndo(function() {
            syncStateToSelection();

            var cursor = createCursor({ startTick: selectionState.startTick, startStaff: selectionState.startStaff });
            var tick = cursor.tick;
            var staffIdx = cursor.staffIdx;
            if (!cursor.prev() || !cursor.element || cursor.element.name !== "Chord") {
                return { error: "No note or chord before the cursor to tie from" };
            }
            var previousTick = cursor.tick;
            var previousPitches = chordPitches(cursor.element);

            var pitches = [];
            var missing = [];
            var requested = params.pitches && params.pitches.length ? params.pitches : previousPitches;
            for (var i = 0; i < requested.length; i++) {
                if (pitches.indexOf(requested[i]) >= 0) continue;
                if (previousPitches.indexOf(requested[i]) < 0) missing.push(requested[i]);
                else pitches.push(requested[i]);
            }
            if (missing.length > 0) {
                return {
                    error: "Pitch " + missing.join(", ") + " is not in the chord before the cursor [" +
                        previousPitches.join(", ") + "]: a tie needs the same pitch"
                };
            }

            var chordPitchList = pitches.slice();
            var extra = params.extraPitches || [];
            for (var x = 0; x < extra.length; x++) {
                if (chordPitchList.indexOf(extra[x]) < 0) chordPitchList.push(extra[x]);
            }

            // Write the whole new chord first, as addNote does
            var writer = createCursor({ startTick: tick, startStaff: staffIdx });
            writer.setDuration(params.duration.numerator, params.duration.denominator);
            writer.addNote(chordPitchList[0], false);
            for (var p = 1; p < chordPitchList.length; p++) {
                writer.rewindToTick(tick);
                writer.addNote(chordPitchList[p], true);
            }

            var previous = createCursor({ startTick: previousTick, startStaff: staffIdx }).element;
            var written = createCursor({ startTick: tick, startStaff: staffIdx }).element;
            var result = tieMatchingNotes(previous, written, previousTick, staffIdx, pitches);
            if (result.error) throw new Error(result.error);  // rolls the written chord back as well

            // Advancing skips the whole written duration: a note longer than the rest of the bar is split by
            // MuseScore into tied notes, and the cursor must not land on the second part
            var target = tick;
            if (params.advanceCursorAfterAction) {
                target = tick + 1920 * params.duration.numerator / params.duration.denominator;
            }

            return {
                success: true,
                message: "Added tied " + (chordPitchList.length > 1 ? "chord " : "note ") + chordPitchList.join(", ") +
                    (chordPitchList.length > pitches.length ? " (tied: " + pitches.join(", ") + ")" : ""),
                tiedPitches: result.tied,
                currentSelection: moveCursorTo(target, staffIdx)
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
            syncStateToSelection();

            var cursor = createCursor();
            var startTick = cursor.tick;
            var staffIdx = cursor.staffIdx;
            cursor.setDuration(params.duration.numerator, params.duration.denominator);

            var ratio = fraction(params.ratio.numerator, params.ratio.denominator);
            var duration = fraction(params.duration.numerator, params.duration.denominator);

            cursor.addTuplet(ratio, duration);

            // Without advancing, the cursor stays on the tuplet's first slot, so the following addNotes fill it
            // slot by slot. Advancing moves past the whole tuplet (duration is its total length). The state is
            // built from the position, as in addNote, and MuseScore's selection follows it.
            var currentSelection = params.advanceCursorAfterAction
                ? advanceCursorTo(startTick + 1920 * params.duration.numerator / params.duration.denominator, staffIdx)
                : moveCursorTo(startTick, staffIdx);
            return {
                success: true,
                message: "Tuplet " + params.ratio.numerator + ":" + params.ratio.denominator + " added",
                currentSelection: currentSelection
            };
        });
    }

    // One entry per chord from the cursor; rests are skipped and take no entry.
    //   "Hel-"     a syllable ending in "-" is joined to the next syllable with a hyphen
    //   "" or "_"  the chord gets no syllable: the previous one is held over it (a melisma),
    //              drawn as an extender line unless that syllable is hyphenated
    // No Lyrics element is ever created with empty text: MuseScore never keeps one itself, and
    // typing "_" (the extender key) into a score holding such placeholders crashed MuseScore.
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
            var heldCount = 0;
            var skippedCount = 0;
            var previous = null;  // last syllable placed: { lyric, tick, hyphen }

            while (cursor.element && lyricsArray.length > 0) {
                var element = cursor.element;

                if (element.type === Element.CHORD || element.name === "Chord") {
                    var text = String(lyricsArray.shift());
                    if (text === "" || text === "_") {
                        // lyricTicks runs from the syllable to the start of the last chord it is held over
                        if (previous && !previous.hyphen) {
                            previous.lyric.lyricTicks = fraction(cursor.tick - previous.tick, 1920);
                        }
                        heldCount++;
                    } else {
                        var hyphen = text.length > 1 && text.charAt(text.length - 1) === "-";
                        if (hyphen) text = text.slice(0, -1);
                        var inWord = previous !== null && previous.hyphen;

                        var lyr = newElement(Element.LYRICS);
                        lyr.text = text;
                        lyr.verse = verse;
                        lyr.syllabic = hyphen ? (inWord ? Lyrics.MIDDLE : Lyrics.BEGIN)
                                              : (inWord ? Lyrics.END : Lyrics.SINGLE);
                        cursor.add(lyr);
                        previous = { lyric: lyr, tick: cursor.tick, hyphen: hyphen };
                        addedCount++;
                    }
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
            if (heldCount > 0) message += `, held ${heldCount} notes`;
            if (skippedCount > 0) message += `, skipped ${skippedCount} rests`;
            if (lyricsArray.length > 0) message += `, ${lyricsArray.length} lyrics remaining`;

            return {
                success: true,
                message: message,
                addedCount: addedCount,
                heldCount: heldCount,
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

    // Remove whole measures (all staves). Runs MuseScore's own "Remove selected range"
    // action, which manages its own undo step, so it is not wrapped in executeWithUndo.
    // Delete whole measures. Measures inside a multi-measure rest can't be selected (time-delete then does
    // nothing and reports no error), so multi-measure rests are switched off meanwhile; the measure count is
    // checked afterwards.
    function deleteMeasures(params) {
        if (!curScore) return { error: "No score open" };
        var range = measureRange({ startMeasure: params.startMeasure, endMeasure: params.endMeasure });
        if (!range.valid) return range;
        var before = curScore.nmeasures;
        var expected = range.endMeasure - range.startMeasure + 1;
        if (expected >= before) return { error: "A score must keep at least one measure" };

        var mmRests = curScore.style ? curScore.style.value("createMultiMeasureRests") : false;
        if (mmRests) {
            setStyle({ key: "createMultiMeasureRests", value: false });
            range = measureRange({ startMeasure: params.startMeasure, endMeasure: params.endMeasure });
        }
        selectMeasureRange(range);
        cmd("time-delete");
        curScore.selection.clear();
        selectionState = { startStaff: 0, endStaff: 1, startTick: 0, elements: {} };
        if (mmRests) setStyle({ key: "createMultiMeasureRests", value: true });

        var deleted = before - curScore.nmeasures;
        if (deleted !== expected) {
            return { error: "MuseScore deleted " + deleted + " of the " + expected + " measures " + range.startMeasure +
                     "-" + range.endMeasure + " (the score now has " + curScore.nmeasures + "). Select them in " +
                     "MuseScore and press Ctrl+Del." };
        }
        return {
            success: true,
            message: "Deleted measures " + range.startMeasure + "-" + range.endMeasure +
                     "; later measures are renumbered. Cursor reset to the start of the score.",
            numMeasures: curScore.nmeasures
        };
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
        
        var cursorParams = undefined;
        if (params.measure !== undefined && params.measure !== null) {
            var range = measureRange({ startMeasure: params.measure, startStaff: 0, endStaff: 1 });
            if (!range.valid) return range;
            cursorParams = { startTick: range.startTick, startStaff: 0 };
        }

        return executeWithUndo(function() {
            var cursor = createCursor(cursorParams);

            var tempo = newElement(Element.TEMPO_TEXT);
            tempo.tempo = params.bpm / 60.0;
            tempo.text = "♩ = " + params.bpm;
            
            cursor.add(tempo);
            
            return { success: true, message: "Tempo set to " + params.bpm + " BPM" };
        });
    }

    // ========================================
    // REPEATS & FORMATTING
    // ========================================

    function selectMeasuresAction(params) {
        if (!curScore) return { error: "No score open" };
        var range = measureRange(params);
        if (!range.valid) return range;

        selectMeasureRange(range);
        return {
            success: true,
            message: "Selected measures " + range.startMeasure + "-" + range.endMeasure +
                     ", staves " + range.startStaff + "-" + (range.endStaff - 1),
            startTick: range.startTick,
            endTick: range.endTick,
            startStaff: range.startStaff,
            endStaff: range.endStaff
        };
    }

    // measure.repeatStart / repeatEnd are writable from plugins only in MuseScore 4.6+.
    // On older versions the bars are selected so the user can apply the palette items.
    function setRepeatBarlines(params) {
        if (!curScore) return { error: "No score open" };
        var range = measureRange({ startMeasure: params.startMeasure, endMeasure: params.endMeasure });
        if (!range.valid) return range;

        var playCount = params.playCount || 2;
        var clear = params.clear === true;
        var label = "measures " + range.startMeasure + "-" + range.endMeasure;

        if (typeof range.firstMeasure.repeatStart === "undefined") {
            selectMeasureRange(range);
            return {
                success: false,
                fallback: "manual",
                message: "This MuseScore version does not let plugins set repeat barlines (needs MuseScore 4.6+). " +
                         label + " are now selected: in the Repeats & jumps palette click the start repeat sign, " +
                         "then the end repeat sign." +
                         (playCount !== 2 ? " Then set the play count to " + playCount + " in the measure properties." : "")
            };
        }

        return executeWithUndo(function() {
            range.firstMeasure.repeatStart = !clear;
            range.lastMeasure.repeatEnd = !clear;
            range.lastMeasure.repeatCount = clear ? 2 : playCount;
            return {
                success: true,
                message: clear
                    ? "Repeat barlines removed from " + label
                    : "Repeat barlines set around " + label + " (played " + playCount + " times)"
            };
        });
    }

    // Experimental: plugins have no dedicated volta API, so this builds the spanner by hand
    // and adds it through Cursor.add. Falls back to selecting the bars for the palette.
    function addVolta(params) {
        if (!curScore) return { error: "No score open" };
        var range = measureRange({ startMeasure: params.startMeasure, endMeasure: params.endMeasure, startStaff: 0, endStaff: 1 });
        if (!range.valid) return range;

        var endings = params.endings && params.endings.length ? params.endings : [1];
        var text = params.text || (endings.join(", ") + ".");
        var label = "measures " + range.startMeasure + "-" + range.endMeasure;

        var result = executeWithUndo(function() {
            var volta = newElement(Element.VOLTA);
            volta.spannerTick = fraction(range.startTick, 1920);
            volta.spannerTicks = fraction(range.endTick - range.startTick, 1920);
            volta.beginText = text;
            try {
                volta.volta_ending = endings;
            } catch (e) {
                console.log("Could not set volta endings: " + e.toString());
            }

            var cursor = curScore.newCursor();
            cursor.staffIdx = 0;
            cursor.voice = 0;
            cursor.rewindToTick(range.startTick);
            cursor.add(volta);
            return { success: true };
        });

        selectMeasureRange(range);
        if (result && result.error) {
            return {
                success: false,
                fallback: "manual",
                message: "Could not add the volta from the plugin (" + result.error + "). " + label +
                         " are now selected: click the matching volta in the Repeats & jumps palette, then edit its text to '" + text + "'."
            };
        }
        return {
            success: true,
            experimental: true,
            message: "Volta '" + text + "' requested over " + label + ". This uses an experimental plugin route: " +
                     "check the score. If no volta appears, press Ctrl+Z and, with the bars still selected, " +
                     "click the volta in the Repeats & jumps palette."
        };
    }

    function setColor(element, color) {
        if (!element) return 0;
        try {
            element.color = color;
            return 1;
        } catch (e) {
            return 0;
        }
    }

    // Color a chord (notes, accidentals, dots, ties, stem, hook, beam) or a rest. Returns the number of notes/rests colored.
    function paintElement(element, color) {
        if (element.name === "Rest" || element.name === "MeasureRepeat") return setColor(element, color);
        if (element.name !== "Chord") return 0;

        var count = 0;
        var notesObj = element.notes || {};
        var keys = Object.keys(notesObj);
        for (var k = 0; k < keys.length; k++) {
            var note = notesObj[keys[k]];
            count += setColor(note, color);
            setColor(note.accidental, color);
            setColor(note.tieForward, color);
            var dots = note.dots || [];
            for (var d = 0; d < dots.length; d++) {
                setColor(dots[d], color);
            }
        }
        setColor(element.stem, color);
        setColor(element.stemSlash, color);
        setColor(element.hook, color);
        setColor(element.beam, color);
        // Grace notes, e.g. the small slashed note of a flam, belong to the main chord
        var graces = element.graceNotes || [];
        for (var g = 0; g < graces.length; g++) {
            count += paintElement(graces[g], color);
        }
        return count;
    }

    function colorRange(params) {
        if (!curScore) return { error: "No score open" };
        var range = measureRange(params);
        if (!range.valid) return range;
        range = applyBeats(range, params);
        if (range.error) return range;

        var color = params.color || "#000000";
        var voices = params.voices && params.voices.length ? params.voices : [0, 1, 2, 3];

        return executeWithUndo(function() {
            var count = 0;
            var seg = range.firstMeasure.firstSegment;
            while (seg && seg.tick < range.startTick) {
                seg = seg.next;
            }
            while (seg && seg.tick < range.endTick) {
                for (var s = range.startStaff; s < range.endStaff; s++) {
                    for (var i = 0; i < voices.length; i++) {
                        var el = seg.elementAt(s * 4 + voices[i]);
                        if (el) count += paintElement(el, color);
                    }
                }
                seg = seg.next;
            }
            return {
                success: true,
                colored: count,
                message: "Colored " + count + " note(s)/rest(s) " + color + " in measures " +
                         range.startMeasure + "-" + range.endMeasure +
                         (params.startBeat || params.endBeat ? " (beats " + (params.startBeat || 1) + " to " + (params.endBeat || "end") + ")" : "") +
                         ", staves " + range.startStaff + "-" + (range.endStaff - 1)
            };
        });
    }

    function setStyle(params) {
        if (!curScore) return { error: "No score open" };
        var validation = validateParams(params, ["key", "value"]);
        if (!validation.valid) return validation;

        // setValue ignores a key MuseScore doesn't have (e.g. a removed one), so check it first and
        // report the value read back rather than the one asked for.
        if (curScore.style.value(params.key) === undefined) return { error: "Unknown style key: " + params.key };

        return executeWithUndo(function() {
            curScore.style.setValue(params.key, params.value);
            var value = curScore.style.value(params.key);
            return { success: true, key: params.key, value: value, message: "Style " + params.key + " is " + value };
        });
    }

    // Engraved pages for the render tool: the score as <path>.pdf, and each measure's box on its page
    // in staff spaces (the unit of pagePos and bbox), which the server uses to crop bars. A PDF, not
    // PNG: the PNG export writes every page at the preferences' resolution (1200 DPI by default).
    // A measure inside a multi-measure rest is not laid out and gets null.
    function renderScore(params) {
        if (!curScore) return { error: "No score open" };
        var validation = validateParams(params, ["path"]);
        if (!validation.valid) return validation;

        if (!writeScore(curScore, params.path + ".pdf", "pdf")) return { error: "MuseScore could not write the score as PDF" };
        var measures = [];
        var pageSize = null;
        for (var m = curScore.firstMeasure; m; m = m.nextMeasure) {
            var system = m.parent;
            var page = system && system.name === "System" ? system.parent : null;
            if (!page || page.name !== "Page" || !m.bbox || m.bbox.width <= 0) {
                measures.push(null);
                continue;
            }
            if (!pageSize) pageSize = page.bbox;
            var box = {
                page: page.pagenumber,
                x: m.pagePos.x + m.bbox.x,
                y: m.pagePos.y + m.bbox.y,
                width: m.bbox.width,
                height: m.bbox.height
            };
            box.content = contentBoxOf(m, box, true);
            box.notes = contentBoxOf(m, box, false);
            measures.push(box);
        }
        return {
            success: true,
            pages: curScore.npages,
            pageWidth: pageSize ? pageSize.width : null,
            pageHeight: pageSize ? pageSize.height : null,
            measures: measures,
            numbers: displayedNumbers()
        };
    }

    // The box, in staff spaces on the page, around the measure and everything attached to it that
    // may stick out of it: markers and jumps (a To Coda sign past the barline), chord symbols, texts
    // and other annotations, notes on ledger lines, lyrics. The render tool crops to it. Without
    // attachments, only the staves, notes, rests and stems: where the neighbouring systems stop a crop.
    function contentBoxOf(measure, box, attachments) {
        var r = { x0: box.x, y0: box.y, x1: box.x + box.width, y1: box.y + box.height };
        function add(e) {
            if (!e || !e.bbox || !e.pagePos || (e.bbox.width <= 0 && e.bbox.height <= 0)) return;
            var x = e.pagePos.x + e.bbox.x, y = e.pagePos.y + e.bbox.y;
            r.x0 = Math.min(r.x0, x); r.y0 = Math.min(r.y0, y);
            r.x1 = Math.max(r.x1, x + e.bbox.width); r.y1 = Math.max(r.y1, y + e.bbox.height);
        }
        var els = attachments ? (measure.elements || []) : [];
        for (var i = 0; i < els.length; i++) {
            if (els[i].type !== Element.LAYOUT_BREAK) add(els[i]);
        }
        var end = measureEndTick(measure);
        for (var seg = measure.firstSegment; seg && seg.tick < end; seg = seg.next) {
            var annotations = attachments ? (seg.annotations || []) : [];
            for (var a = 0; a < annotations.length; a++) add(annotations[a]);
            for (var t = 0; t < curScore.ntracks; t++) {
                var el = seg.elementAt(t);
                if (!el) continue;
                add(el);
                var notes = el.notes || [];
                for (var n = 0; n < notes.length; n++) add(notes[n]);
                var lyrics = attachments ? (el.lyrics || []) : [];
                for (var l = 0; l < lyrics.length; l++) add(lyrics[l]);
            }
        }
        return { x: r.x0, y: r.y0, width: r.x1 - r.x0, height: r.y1 - r.y0 };
    }

    function getStyle(params) {
        if (!curScore) return { error: "No score open" };
        var validation = validateParams(params, ["keys"]);
        if (!validation.valid) return validation;

        var styles = {};
        var unknown = [];
        for (var i = 0; i < params.keys.length; i++) {
            var value = curScore.style.value(params.keys[i]);
            if (value === undefined) unknown.push(params.keys[i]);
            else styles[params.keys[i]] = value;
        }
        return { success: true, styles: styles, unknown: unknown };
    }

    // Highlighter band: a thick, semi-transparent text line behind one staff's notes over a range of
    // measures (or beats); it follows the bars across system breaks. A line's drawn segments only exist
    // after layout, so the score is laid out mid-command and the segments are then moved onto the staff
    // with automatic placement off (otherwise MuseScore pushes the band above the notes).
    function addHighlight(params) {
        if (!curScore) return { error: "No score open" };
        var range = measureRange(params);
        if (!range.valid) return range;
        range = applyBeats(range, params);
        if (range.error) return range;

        var color = params.color || "#59FFE600";
        var width = params.width !== undefined ? params.width : 5.0;          // spatium: the 4-space staff plus 0.5 above and below
        var offsetY = params.offsetY !== undefined ? params.offsetY : bandOffsetY(2);   // centers the band on the staff

        return executeWithUndo(function() {
            var lines = [];
            for (var s = range.startStaff; s < range.endStaff; s++) {
                var line = newElement(Element.TEXTLINE);
                line.spannerTick = fraction(range.startTick, 1920);
                line.spannerTicks = fraction(range.endTick - range.startTick, 1920);
                line.spannerTrack2 = s * 4;
                line.lineWidth = width;
                line.lineColor = color;
                line.autoplace = false;
                line.z = 1;

                var cursor = curScore.newCursor();
                cursor.staffIdx = s;
                cursor.voice = 0;
                cursor.rewindToTick(range.startTick);
                cursor.add(line);
                lines.push(line);
            }

            curScore.doLayout(fraction(range.startTick, 1920), fraction(range.endTick, 1920));
            var placed = 0;
            for (var i = 0; i < lines.length; i++) {
                var segments = lines[i].spannerSegments || [];
                for (var j = 0; j < segments.length; j++) {
                    segments[j].autoplace = false;
                    segments[j].offset = Qt.point(0, offsetY);
                    placed++;
                }
            }
            return {
                success: true,
                experimental: true,
                added: lines.length,
                placedSegments: placed,
                message: "Highlighted measures " + range.startMeasure + "-" + range.endMeasure +
                         " on staves " + range.startStaff + "-" + (range.endStaff - 1)
            };
        });
    }

    // Offset that puts the center of a highlight line (autoplace off) at centerY spaces below the staff's top
    // line. Measured by rendering with the default text line style (textLinePosAbove = (0, -1)), where the
    // offset equals the center; adjusted if the score changes that style.
    function bandOffsetY(centerY) {
        var pos = curScore.style ? curScore.style.value("textLinePosAbove") : null;
        var y = pos && typeof pos.y === "number" && Math.abs(pos.y) < 20 ? pos.y : -1;
        return centerY + (-1 - y);
    }

    // Page y of a staff's top line in a measure: the y of that staff's barline, else the measure's own y.
    function staffTopY(m, staff) {
        for (var seg = m.firstSegment; seg; seg = seg.nextInMeasure) {
            var el = seg.elementAt(staff * 4);
            if (el && el.name === "BarLine") return el.pagePos.y;
        }
        return m.pagePos.y;
    }

    // Extent of a laid-out element: x on the page, y relative to its staff's top line, in spaces.
    function elementExtent(el, staffTop) {
        var p = el.pagePos;
        var b = el.bbox;
        return { x0: p.x + b.x, x1: p.x + b.x + b.width, y0: p.y + b.y - staffTop, y1: p.y + b.y + b.height - staffTop };
    }

    function extentFor(el, m, staff, pad) {
        var top = staffTopY(m, staff);
        var e = elementExtent(el, top);
        return { measure: m, staff: staff, systemY: top, x0: e.x0 - pad, x1: e.x1 + pad, y0: e.y0 - pad, y1: e.y1 + pad };
    }

    // Merge extents that overlap (or nearly touch) horizontally on the same staff and system.
    function mergeExtents(extents, gap) {
        extents.sort(function(a, b) { return a.staff - b.staff || a.systemY - b.systemY || a.x0 - b.x0; });
        var merged = [];
        for (var i = 0; i < extents.length; i++) {
            var e = extents[i];
            var last = merged.length ? merged[merged.length - 1] : null;
            if (last && last.staff === e.staff && Math.abs(last.systemY - e.systemY) < 0.01 && e.x0 <= last.x1 + gap) {
                last.x1 = Math.max(last.x1, e.x1);
                last.y0 = Math.min(last.y0, e.y0);
                last.y1 = Math.max(last.y1, e.y1);
            } else {
                merged.push({ measure: e.measure, staff: e.staff, systemY: e.systemY, x0: e.x0, x1: e.x1, y0: e.y0, y1: e.y1 });
            }
        }
        return merged;
    }

    // Translucent boxes covering page x-ranges over the full staff height (plus margin), stretched further
    // to cover the box's elements when they stick out of the staff (y0/y1, relative to the top line).
    // A text line per box, anchored to the box's measure, then (after a mid-command layout) moved and
    // resized to the exact range. Call inside a command.
    function addColumnBoxes(boxes, color, margin) {
        for (var k = 0; k < boxes.length; k++) {
            var b = boxes[k];
            b.top = Math.min(-margin, b.y0 !== undefined ? b.y0 : 0);
            b.bottom = Math.max(4 + margin, b.y1 !== undefined ? b.y1 : 4);
        }
        var lines = [];
        var minTick = -1, maxTick = 0;
        for (var i = 0; i < boxes.length; i++) {
            var m = boxes[i].measure;
            var start = measureStartTick(m);
            var end = measureEndTick(m);
            var line = newElement(Element.TEXTLINE);
            line.spannerTick = fraction(start, 1920);
            line.spannerTicks = fraction(end - start, 1920);
            line.spannerTrack2 = boxes[i].staff * 4;
            line.lineWidth = boxes[i].bottom - boxes[i].top;
            line.lineColor = color;
            line.autoplace = false;
            line.z = 1;
            var cursor = curScore.newCursor();
            cursor.staffIdx = boxes[i].staff;
            cursor.voice = 0;
            cursor.rewindToTick(start);
            cursor.add(line);
            lines.push(line);
            if (minTick < 0 || start < minTick) minTick = start;
            if (end > maxTick) maxTick = end;
        }
        if (!lines.length) return 0;

        curScore.doLayout(fraction(minTick, 1920), fraction(maxTick, 1920));
        var placed = 0;
        for (var j = 0; j < lines.length; j++) {
            var segments = lines[j].spannerSegments || [];
            if (!segments.length) continue;
            var seg = segments[0];
            var startX = seg.pagePos.x;
            var length = seg.pos2.x;
            seg.autoplace = false;
            seg.offset = Qt.point(boxes[j].x0 - startX, bandOffsetY((boxes[j].top + boxes[j].bottom) / 2));
            seg.userOff2 = Qt.point((boxes[j].x1 - boxes[j].x0) - length, 0);
            placed++;
        }
        return placed;
    }

    // Full-height boxes around individual notes (e.g. only the crash of a kick+crash chord). Hits whose
    // boxes would touch are merged into one box.
    function highlightNotes(params) {
        if (!curScore) return { error: "No score open" };
        var range = measureRange(params);
        if (!range.valid) return range;
        range = applyBeats(range, params);
        if (range.error) return range;

        var color = params.color || "#73FFD600";
        var pitches = params.pitches && params.pitches.length ? params.pitches : null;
        var voices = params.voices && params.voices.length ? params.voices : [0, 1, 2, 3];
        var pad = params.padding !== undefined ? params.padding : 0.2;
        var margin = params.margin !== undefined ? params.margin : 0.5;

        var extents = [];
        var hits = 0;
        for (var m = range.firstMeasure; m; m = m.nextMeasure) {
            for (var seg = m.firstSegment; seg; seg = seg.nextInMeasure) {
                if (seg.tick < range.startTick || seg.tick >= range.endTick) continue;
                for (var s = range.startStaff; s < range.endStaff; s++) {
                    for (var v = 0; v < voices.length; v++) {
                        var el = seg.elementAt(s * 4 + voices[v]);
                        if (!el || el.name !== "Chord") continue;
                        var notes = el.notes || [];
                        for (var n = 0; n < notes.length; n++) {
                            if (pitches && pitches.indexOf(notes[n].pitch) === -1) continue;
                            extents.push(extentFor(notes[n], m, s, pad));
                            hits++;
                        }
                    }
                }
            }
            if (measureStartTick(m) >= measureStartTick(range.lastMeasure)) break;
        }
        if (!hits) return { success: true, highlighted: 0, boxes: 0, message: "No matching notes in the range" };

        var boxes = mergeExtents(extents, 2 * pad);
        return executeWithUndo(function() {
            var placed = addColumnBoxes(boxes, color, margin);
            return { success: true, highlighted: hits, boxes: placed,
                     message: "Highlighted " + hits + " note(s) with " + placed + " box(es)" };
        });
    }

    function isRepeatBarline(barline) {
        var type = barline.barlineType;
        return (type & (4 | 8 | 64)) !== 0;  // start repeat, end repeat, end-start repeat
    }

    // Time signatures, repeat barlines and measure-repeat signs in a range: highlighted with full-height
    // boxes (mode "highlight") or recolored (mode "color"; clear resets them to black).
    function highlightSymbols(params) {
        if (!curScore) return { error: "No score open" };
        var range = measureRange(params);
        if (!range.valid) return range;
        var kinds = params.kinds && params.kinds.length ? params.kinds : ["time_signatures", "repeat_barlines", "measure_repeats"];
        var mode = params.mode || "highlight";
        var color = params.color || (mode === "color" ? "#5DADE2" : "#99A7D8F0");
        if (params.clear) color = "#000000";
        var pad = params.padding !== undefined ? params.padding : 0.25;
        var margin = params.margin !== undefined ? params.margin : 0.5;

        var found = [];
        var counts = { time_signatures: 0, repeat_barlines: 0, measure_repeats: 0 };
        for (var m = range.firstMeasure; m; m = m.nextMeasure) {
            for (var seg = m.firstSegment; seg; seg = seg.nextInMeasure) {
                for (var s = range.startStaff; s < range.endStaff; s++) {
                    var el = seg.elementAt(s * 4);
                    if (!el) continue;
                    var kind = null;
                    if (el.name === "TimeSig") kind = "time_signatures";
                    else if (el.name === "BarLine" && isRepeatBarline(el)) kind = "repeat_barlines";
                    else if (el.name === "MeasureRepeat") kind = "measure_repeats";
                    if (!kind || kinds.indexOf(kind) === -1) continue;
                    found.push({ element: el, measure: m, staff: s });
                    counts[kind]++;
                }
            }
            if (measureStartTick(m) >= measureStartTick(range.lastMeasure)) break;
        }
        if (!found.length) return { success: true, found: counts, message: "No matching symbols in the range" };

        return executeWithUndo(function() {
            if (mode === "color") {
                for (var i = 0; i < found.length; i++) found[i].element.color = color;
                return { success: true, found: counts, message: (params.clear ? "Reset " : "Colored ") + found.length + " symbol(s)" };
            }
            var extents = [];
            for (var j = 0; j < found.length; j++) {
                extents.push(extentFor(found[j].element, found[j].measure, found[j].staff, pad));
            }
            var placed = addColumnBoxes(mergeExtents(extents, 0), color, margin);
            return { success: true, found: counts, boxes: placed, message: "Highlighted " + found.length + " symbol(s) with " + placed + " box(es)" };
        });
    }

    // A translucent box behind markings such as dynamics, set on each marking's own text frame.
    function highlightMarkings(params) {
        if (!curScore) return { error: "No score open" };
        var range = measureRange(params);
        if (!range.valid) return range;
        var types = params.types && params.types.length ? params.types : ["Dynamic"];
        var color = params.color || "#8CFFD600";
        var clear = params.clear === true;

        return executeWithUndo(function() {
            var count = 0;
            var found = forEachMarking(range, types, function(marking) {
                if (clear) {
                    if (isMarkingHighlight(marking)) {
                        marking.frameType = 0;
                        count++;
                    }
                } else {
                    marking.frameType = 1;
                    marking.frameBgColor = color;
                    marking.frameFgColor = "#00000000";
                    count++;
                }
            });
            return {
                success: true,
                found: found,
                changed: count,
                message: (clear ? "Removed the highlight from " : "Highlighted ") + count + " of " + found +
                         " marking(s) (" + types.join(", ") + ")"
            };
        });
    }

    // Call fn for each annotation of the given types (Dynamic, StaffText, Tempo, ...) in the range; returns how many.
    function forEachMarking(range, types, fn) {
        var found = 0;
        var seg = range.firstMeasure.firstSegment;
        while (seg && seg.tick < range.endTick) {
            var annotations = seg.annotations || [];
            for (var a = 0; a < annotations.length; a++) {
                var ann = annotations[a];
                var staff = Math.floor(ann.track / 4);
                if (types.indexOf(ann.name) !== -1 && staff >= range.startStaff && staff < range.endStaff) {
                    found++;
                    fn(ann, seg);
                }
            }
            seg = seg.next;
        }
        return found;
    }

    function isTranslucent(color) {
        return color && color.a !== undefined && color.a < 1;
    }

    function isMarkingHighlight(marking) {
        return marking.frameType && isTranslucent(marking.frameBgColor);
    }

    // A staff text in a colored box, e.g. a section tag.
    function addLabel(params) {
        if (!curScore) return { error: "No score open" };
        var validation = validateParams(params, ["measure", "text"]);
        if (!validation.valid) return validation;
        var staff = params.staff || 0;
        var range = measureRange({ startMeasure: params.measure, startStaff: staff, endStaff: staff + 1 });
        if (!range.valid) return range;

        return executeWithUndo(function() {
            var cursor = createCursor({ startTick: range.startTick, startStaff: staff });
            var label = newElement(Element.STAFF_TEXT);
            label.text = params.text;
            label.frameType = 1;  // square frame
            label.frameBgColor = params.background || "#FFF2A8";
            label.frameFgColor = params.border || "#000000";
            if (params.color) label.color = params.color;
            cursor.add(label);
            return { success: true, message: "Label '" + params.text + "' added at measure " + params.measure + ", staff " + staff };
        });
    }

    // Free text at a measure (and beat) with its own look: size in points, bold/italic, color, above/below.
    // kind "expression" makes an expression text (italic and below the staff by default in MuseScore).
    function addText(params) {
        if (!curScore) return { error: "No score open" };
        var validation = validateParams(params, ["measure", "text"]);
        if (!validation.valid) return validation;
        var staff = params.staff || 0;
        var range = measureRange({ startMeasure: params.measure, startStaff: staff, endStaff: staff + 1 });
        if (!range.valid) return range;
        range = applyBeats(range, { startBeat: params.beat });
        if (range.error) return range;

        return executeWithUndo(function() {
            var cursor = createCursor({ startTick: range.startTick, startStaff: staff });
            var text = newElement(params.kind === "expression" ? Element.EXPRESSION : Element.STAFF_TEXT);
            text.text = params.text;
            if (params.fontSize) text.fontSize = params.fontSize;
            if (params.bold !== undefined || params.italic !== undefined) {
                text.fontStyle = (params.bold ? 1 : 0) | (params.italic ? 2 : 0);
            }
            if (params.color) text.color = params.color;
            if (params.placement) text.placement = params.placement === "below" ? 1 : 0;
            cursor.add(text);
            return { success: true, message: "Text '" + params.text + "' added at measure " + params.measure + ", staff " + staff };
        });
    }

    // Remove texts and marks in a range. kinds: "texts" (staff/expression text without a box: add_text),
    // "labels" (boxed staff text: add_label), "rehearsal_marks", "tempo", "voltas", "markers" (Segno, Coda,
    // To Coda, Fine), "jumps" (D.C., D.S.…), "chord_symbols" and "breaks" (system, page and section breaks);
    // markers, jumps and breaks belong to the measure, not to a staff.
    // `contains` limits text-based kinds to elements whose text contains that string (e.g. "*"), or equals
    // it when `exact` is true.
    function removeAnnotations(params) {
        if (!curScore) return { error: "No score open" };
        var range = measureRange(params);
        if (!range.valid) return range;
        var kinds = params.kinds && params.kinds.length ? params.kinds : ["texts"];
        var contains = params.contains || "";
        var exact = params.exact === true;
        // beat: only what is on this beat of each measure; markers, jumps, voltas and breaks have none
        var beat = params.beat !== undefined && params.beat !== null ? params.beat : null;
        var removed = { texts: 0, labels: 0, rehearsal_marks: 0, tempo: 0, voltas: 0, markers: 0, jumps: 0,
                        chord_symbols: 0, breaks: 0 };
        var targets = [];

        forEachMarking(range, ["StaffText", "Expression", "RehearsalMark", "Tempo", "TempoText", "Harmony"], function(ann, seg) {
            var kind;
            if (ann.name === "Harmony") kind = "chord_symbols";
            else if (ann.name === "RehearsalMark") kind = "rehearsal_marks";
            else if (ann.name === "Tempo" || ann.name === "TempoText") kind = "tempo";
            else kind = ann.frameType && !isTranslucent(ann.frameBgColor) ? "labels" : "texts";
            if (kinds.indexOf(kind) === -1) return;
            if (beat !== null && beatOfSegment(seg) !== beat) return;
            var plain = String(ann.text || "").replace(/<[^>]*>/g, "");
            if (contains && (exact ? plain !== contains : plain.indexOf(contains) === -1)) return;
            targets.push(ann);
            removed[kind]++;
        });
        if (kinds.indexOf("voltas") !== -1 && beat === null) {
            var spanners = curScore.spanners || [];
            for (var i = 0; i < spanners.length; i++) {
                var sp = spanners[i];
                var tick = sp.spannerTick ? sp.spannerTick.ticks : -1;
                if (sp.name === "Volta" && tick >= range.startTick && tick < range.endTick) {
                    targets.push(sp);
                    removed.voltas++;
                }
            }
        }
        // Markers and jumps hang on the measure, not on a staff
        if (beat === null && (kinds.indexOf("markers") !== -1 || kinds.indexOf("jumps") !== -1
                || kinds.indexOf("breaks") !== -1)) {
            for (var m = range.firstMeasure; m; m = m.nextMeasure) {
                var els = m.elements || [];
                for (var e = 0; e < els.length; e++) {
                    var mk = els[e].type === Element.MARKER ? "markers" : els[e].type === Element.JUMP ? "jumps"
                        : els[e].type === Element.LAYOUT_BREAK ? "breaks" : "";
                    if (mk && kinds.indexOf(mk) !== -1) {
                        targets.push(els[e]);
                        removed[mk]++;
                    }
                }
                if (measureStartTick(m) >= measureStartTick(range.lastMeasure)) break;
            }
        }
        if (!targets.length) return { success: true, removed: removed, message: "Nothing to remove" };

        var result = executeWithUndo(function() {
            for (var t = 0; t < targets.length; t++) removeElement(targets[t]);
            return { success: true };
        });
        if (result && result.error) return result;
        return { success: true, removed: removed, message: "Removed " + targets.length + " element(s)" };
    }

    // Articulation names used by the tools, as SMuFL symbols (the hi-hat ones are MuseScore's palette symbols)
    function articulationSymbols() {
        return {
            half_open: SymId.pictHalfOpen2,
            open: SymId.brassMuteOpen,
            closed: SymId.brassMuteClosed,
            accent: SymId.articAccentAbove,
            marcato: SymId.articMarcatoAbove,
            staccato: SymId.articStaccatoAbove,
            tenuto: SymId.articTenutoAbove
        };
    }

    function articulationName(symbol) {
        var symbols = articulationSymbols();
        for (var name in symbols) {
            if (symbols[name] === symbol) return name;
        }
        return "symbol " + symbol;
    }

    // Call fn(chord, segment, staff) for each chord starting in the range (beats applied) on the given voices.
    function forEachChord(range, voices, fn) {
        for (var m = range.firstMeasure; m; m = m.nextMeasure) {
            for (var seg = m.firstSegment; seg; seg = seg.nextInMeasure) {
                if (seg.tick < range.startTick || seg.tick >= range.endTick) continue;
                for (var s = range.startStaff; s < range.endStaff; s++) {
                    for (var v = 0; v < voices.length; v++) {
                        var el = seg.elementAt(s * 4 + voices[v]);
                        if (el && el.name === "Chord") fn(el, seg, s);
                    }
                }
            }
            if (measureStartTick(m) >= measureStartTick(range.lastMeasure)) break;
        }
    }

    function chordHasPitch(chord, pitches) {
        if (!pitches) return true;
        var notes = chord.notes || [];
        for (var n = 0; n < notes.length; n++) {
            if (pitches.indexOf(notes[n].pitch) !== -1) return true;
        }
        return false;
    }

    // Beam across rests inside a beat group (a dotted quarter in 6/8, 9/8, 12/8; a beat otherwise), as drum
    // charts write them: MuseScore breaks the beam at every rest left on "auto" beaming. A rest is beamed over
    // when beamable notes (shorter than a quarter) come before and after it in the same group. `clear` puts
    // the rests in the range back on "auto".
    function beamOverRests(params) {
        if (!curScore) return { error: "No score open" };
        var range = measureRange(params);
        if (!range.valid) return range;
        // engraving BeamMode values (types.h: INVALID -1, AUTO, NONE, BEGIN, BEGIN16, BEGIN32, MID, END);
        // the plugin API has no BeamMode enum in 4.7
        var mid = 5, auto = 0;
        var clear = params.clear === true;

        return executeWithUndo(function() {
            var changed = 0;
            for (var m = range.firstMeasure; m; m = m.nextMeasure) {
                var start = measureStartTick(m);
                var sig = m.timesigActual;
                var compound = sig && sig.denominator === 8 && sig.numerator > 3 && sig.numerator % 3 === 0;
                var group = compound ? 720 : beatTicks(m);
                for (var s = range.startStaff; s < range.endStaff; s++) {
                    for (var v = 0; v < 4; v++) {
                        var items = [];
                        for (var seg = m.firstSegment; seg; seg = seg.nextInMeasure) {
                            var el = seg.elementAt(s * 4 + v);
                            if (el && (el.name === "Chord" || el.name === "Rest")) items.push({ tick: seg.tick - start, cr: el });
                        }
                        for (var i = 0; i < items.length; i++) {
                            var item = items[i];
                            if (item.cr.name !== "Rest") continue;
                            if (clear) {
                                if (item.cr.beamMode !== auto) { item.cr.beamMode = auto; changed++; }
                                continue;
                            }
                            var g = Math.floor(item.tick / group);
                            var before = false, after = false;
                            for (var b = i - 1; b >= 0 && Math.floor(items[b].tick / group) === g; b--) {
                                if (items[b].cr.name === "Chord") { before = beamable(items[b].cr); break; }
                            }
                            for (var a = i + 1; a < items.length && Math.floor(items[a].tick / group) === g; a++) {
                                if (items[a].cr.name === "Chord") { after = beamable(items[a].cr); break; }
                            }
                            if (before && after && beamable(item.cr) && item.cr.beamMode !== mid) {
                                item.cr.beamMode = mid;
                                changed++;
                            }
                        }
                    }
                }
                if (measureStartTick(m) >= measureStartTick(range.lastMeasure)) break;
            }
            return { success: true, changed: changed,
                     message: (clear ? "Reset beaming of " : "Beamed over ") + changed + " rest(s)" };
        });
    }

    function beamable(chordRest) {
        return chordRest.actualDuration && chordRest.actualDuration.ticks < 480;
    }

    // Add an articulation (e.g. the half-open hi-hat symbol) to every chord in the range that contains one of
    // `pitches` (all chords if none). Chords that already have it are left alone.
    function addArticulation(params) {
        if (!curScore) return { error: "No score open" };
        var range = measureRange(params);
        if (!range.valid) return range;
        range = applyBeats(range, params);
        if (range.error) return range;
        var symbol = articulationSymbols()[params.symbol || "half_open"];
        if (symbol === undefined) return { error: "Unknown articulation " + params.symbol };
        var pitches = params.pitches && params.pitches.length ? params.pitches : null;
        var voices = params.voices && params.voices.length ? params.voices : [0, 1, 2, 3];

        return executeWithUndo(function() {
            var added = 0;
            forEachChord(range, voices, function(chord) {
                if (!chordHasPitch(chord, pitches)) return;
                var arts = chord.articulations || [];
                for (var a = 0; a < arts.length; a++) {
                    if (arts[a].symbol === symbol) return;
                }
                var art = newElement(Element.ARTICULATION);
                art.symbol = symbol;
                chord.add(art);
                added++;
            });
            return { success: true, added: added, message: "Added '" + (params.symbol || "half_open") + "' to " + added + " chord(s)" };
        });
    }

    // Remove articulations by name (default: the hi-hat symbols) from chords in the range containing `pitches`.
    function removeArticulations(params) {
        if (!curScore) return { error: "No score open" };
        var range = measureRange(params);
        if (!range.valid) return range;
        range = applyBeats(range, params);
        if (range.error) return range;
        var names = params.symbols && params.symbols.length ? params.symbols : ["half_open", "open", "closed"];
        var symbols = articulationSymbols();
        var wanted = [];
        for (var i = 0; i < names.length; i++) {
            if (symbols[names[i]] === undefined) return { error: "Unknown articulation " + names[i] };
            wanted.push(symbols[names[i]]);
        }
        var pitches = params.pitches && params.pitches.length ? params.pitches : null;

        return executeWithUndo(function() {
            var targets = [];
            forEachChord(range, [0, 1, 2, 3], function(chord) {
                if (!chordHasPitch(chord, pitches)) return;
                var arts = chord.articulations || [];
                for (var a = 0; a < arts.length; a++) {
                    if (wanted.indexOf(arts[a].symbol) !== -1) targets.push(arts[a]);
                }
            });
            for (var t = 0; t < targets.length; t++) removeElement(targets[t]);
            return { success: true, removed: targets.length };
        });
    }

    // List (mode "list") or remove (mode "remove") ghost notes in the range. A chord made only of ghost notes
    // becomes a rest.
    function ghostNotes(params) {
        if (!curScore) return { error: "No score open" };
        var range = measureRange(params);
        if (!range.valid) return range;
        var pitches = params.pitches && params.pitches.length ? params.pitches : null;
        var found = [];
        forEachChord(range, [0, 1, 2, 3], function(chord, seg, staff) {
            var notes = chord.notes || [];
            var ghosts = [];
            for (var n = 0; n < notes.length; n++) {
                if (notes[n].ghost && (!pitches || pitches.indexOf(notes[n].pitch) !== -1)) ghosts.push(notes[n]);
            }
            if (ghosts.length) found.push({ chord: chord, ghosts: ghosts, all: ghosts.length === notes.length, tick: seg.tick, staff: staff });
        });

        var bars = {};
        var numbers = [];
        for (var f = 0; f < found.length; f++) {
            var m = 1;
            for (var mm = curScore.firstMeasure; mm && measureEndTick(mm) <= found[f].tick; mm = mm.nextMeasure) m++;
            if (!bars[m]) { bars[m] = 0; numbers.push(m); }
            bars[m] += found[f].ghosts.length;
        }
        var count = 0;
        for (var b = 0; b < numbers.length; b++) count += bars[numbers[b]];
        var perBar = [];
        for (var c = 0; c < numbers.length; c++) perBar.push({ measure: numbers[c], ghostNotes: bars[numbers[c]] });
        if (params.mode !== "remove" || !found.length) {
            return { success: true, ghostNotes: count, bars: perBar };
        }

        return executeWithUndo(function() {
            for (var i = 0; i < found.length; i++) {
                if (found[i].all) {
                    removeElement(found[i].chord);
                } else {
                    for (var g = 0; g < found[i].ghosts.length; g++) removeElement(found[i].ghosts[g]);
                }
            }
            return { success: true, removed: count, bars: perBar };
        });
    }

    function isHighlightLine(spanner) {
        return spanner.name === "TextLine" && spanner.autoplace === false && isTranslucent(spanner.lineColor);
    }

    function isNoteHighlight(element) {
        return element.name === "Symbol" && isTranslucent(element.color);
    }

    // Remove what the highlight tools added in a range: bands (addHighlight), note boxes (highlightNotes),
    // marking boxes (highlightMarkings) and boxed labels (addLabel).
    function clearHighlights(params) {
        if (!curScore) return { error: "No score open" };
        var range = measureRange(params);
        if (!range.valid) return range;
        var kinds = params.kinds && params.kinds.length ? params.kinds : ["highlights", "notes", "markings", "labels"];
        var targets = [];
        var removedNotes = 0;
        var clearedMarkings = 0;

        if (kinds.indexOf("highlights") !== -1) {
            var spanners = curScore.spanners || [];
            for (var i = 0; i < spanners.length; i++) {
                var sp = spanners[i];
                var tick = sp.spannerTick ? sp.spannerTick.ticks : -1;
                var staffIdx = Math.floor(sp.track / 4);
                if (tick >= range.startTick && tick < range.endTick &&
                        staffIdx >= range.startStaff && staffIdx < range.endStaff && isHighlightLine(sp)) {
                    targets.push(sp);
                }
            }
        }
        if (kinds.indexOf("labels") !== -1) {
            forEachMarking(range, ["StaffText"], function(ann) {
                if (ann.frameType && !isTranslucent(ann.frameBgColor)) targets.push(ann);
            });
        }

        var result = executeWithUndo(function() {
            for (var t = 0; t < targets.length; t++) {
                removeElement(targets[t]);
            }
            if (kinds.indexOf("notes") !== -1) {
                var seg = range.firstMeasure.firstSegment;
                while (seg && seg.tick < range.endTick) {
                    for (var s = range.startStaff; s < range.endStaff; s++) {
                        for (var v = 0; v < 4; v++) {
                            var el = seg.elementAt(s * 4 + v);
                            if (!el || el.name !== "Chord") continue;
                            var notes = el.notes || [];
                            for (var n = 0; n < notes.length; n++) {
                                var children = notes[n].elements || [];
                                var boxes = [];
                                for (var c = 0; c < children.length; c++) {
                                    if (isNoteHighlight(children[c])) boxes.push(children[c]);
                                }
                                for (var b = 0; b < boxes.length; b++) {
                                    notes[n].remove(boxes[b]);
                                    removedNotes++;
                                }
                            }
                        }
                    }
                    seg = seg.next;
                }
            }
            if (kinds.indexOf("markings") !== -1) {
                forEachMarking(range, ["Dynamic", "StaffText", "SystemText", "Tempo", "Expression"], function(ann) {
                    if (isMarkingHighlight(ann)) {
                        ann.frameType = 0;
                        clearedMarkings++;
                    }
                });
            }
            return { success: true };
        });
        if (result && result.error) return result;

        var removed = targets.length + removedNotes + clearedMarkings;
        return {
            success: true,
            removed: removed,
            message: removed ? "Removed " + targets.length + " band(s)/label(s), " + removedNotes + " note box(es), " +
                               clearedMarkings + " marking highlight(s)" : "Nothing to remove"
        };
    }

    // Experimental, like addVolta: rehearsal marks have no dedicated API, so they go through Cursor.add.
    function addRehearsalMark(params) {
        if (!curScore) return { error: "No score open" };
        var validation = validateParams(params, ["measure", "text"]);
        if (!validation.valid) return validation;
        var range = measureRange({ startMeasure: params.measure, startStaff: 0, endStaff: 1 });
        if (!range.valid) return range;

        return executeWithUndo(function() {
            var cursor = createCursor({ startTick: range.startTick, startStaff: 0 });
            var mark = newElement(Element.REHEARSAL_MARK);
            mark.text = params.text;
            cursor.add(mark);
            return { success: true, experimental: true, message: "Rehearsal mark '" + params.text + "' added at measure " + params.measure };
        });
    }

    // Repeat markers and jumps, by the names add_marker takes. A jump's type can't be set from a plugin:
    // MuseScore derives it from jumpTo, playUntil and continueAt, which name the markers' labels (Segno
    // "segno", To Coda "coda", Coda "codab", Fine "fine"), so they are set as MuseScore's palette does.
    function markerKinds() {
        return {
            segno: { marker: MarkerType.SEGNO, name: "Segno" },
            coda: { marker: MarkerType.CODA, name: "Coda" },
            to_coda: { marker: MarkerType.TOCODA, name: "To Coda" },
            to_coda_symbol: { marker: MarkerType.TOCODASYM, name: "To Coda (symbol)" },
            fine: { marker: MarkerType.FINE, name: "Fine" },
            dc: { text: "D.C.", jumpTo: "start", playUntil: "end", continueAt: "" },
            dc_al_fine: { text: "D.C. al Fine", jumpTo: "start", playUntil: "fine", continueAt: "" },
            dc_al_coda: { text: "D.C. al Coda", jumpTo: "start", playUntil: "coda", continueAt: "codab" },
            ds: { text: "D.S.", jumpTo: "segno", playUntil: "end", continueAt: "" },
            ds_al_fine: { text: "D.S. al Fine", jumpTo: "segno", playUntil: "fine", continueAt: "" },
            ds_al_coda: { text: "D.S. al Coda", jumpTo: "segno", playUntil: "coda", continueAt: "codab" }
        };
    }

    // The markers a jump needs that the score doesn't have yet, by name.
    function missingMarkers(kind) {
        var needs = [];
        if (kind.jumpTo === "segno") needs.push({ name: "Segno", types: [MarkerType.SEGNO, MarkerType.VARSEGNO] });
        if (kind.playUntil === "coda") needs.push({ name: "To Coda", types: [MarkerType.TOCODA, MarkerType.TOCODASYM] });
        if (kind.continueAt === "codab") needs.push({ name: "Coda", types: [MarkerType.CODA, MarkerType.VARCODA] });
        if (kind.playUntil === "fine") needs.push({ name: "Fine", types: [MarkerType.FINE] });
        var present = [];
        for (var m = curScore.firstMeasure; m; m = m.nextMeasure) {
            var els = m.elements || [];
            for (var i = 0; i < els.length; i++) {
                if (els[i].type === Element.MARKER) present.push(els[i].markerType);
            }
        }
        var missing = [];
        for (var n = 0; n < needs.length; n++) {
            var found = false;
            for (var t = 0; t < needs[n].types.length; t++) {
                if (present.indexOf(needs[n].types[t]) !== -1) found = true;
            }
            if (!found) missing.push(needs[n].name);
        }
        return missing;
    }

    // params: measure (1-based), marker (a markerKinds name). Segno and Coda belong at the start of the bar,
    // To Coda, Fine and the jumps at its end; MuseScore places each by its type. A marker the bar already has
    // is refused. A jump's reply lists the markers it needs that the score doesn't have yet.
    function addMarker(params) {
        if (!curScore) return { error: "No score open" };
        var validation = validateParams(params, ["measure", "marker"]);
        if (!validation.valid) return validation;
        var kind = markerKinds()[params.marker];
        if (!kind) return { error: "Unknown marker '" + params.marker + "'" };
        var range = measureRange({ startMeasure: params.measure, startStaff: 0, endStaff: 1 });
        if (!range.valid) return range;

        var isJump = kind.marker === undefined;
        var els = range.firstMeasure.elements || [];
        for (var i = 0; i < els.length; i++) {
            var same = isJump
                ? els[i].type === Element.JUMP && els[i].jumpTo === kind.jumpTo && els[i].playUntil === kind.playUntil
                  && els[i].continueAt === kind.continueAt
                : els[i].type === Element.MARKER && els[i].markerType === kind.marker;
            if (same) return { error: "Measure " + params.measure + " already has a " + (isJump ? kind.text : kind.name) };
        }

        var result = executeWithUndo(function() {
            var cursor = createCursor({ startTick: range.startTick, startStaff: 0 });
            cursor.track = 0;
            var e;
            if (isJump) {
                e = newElement(Element.JUMP);
                e.text = kind.text;
                e.jumpTo = kind.jumpTo;
                e.playUntil = kind.playUntil;
                e.continueAt = kind.continueAt;
            } else {
                e = newElement(Element.MARKER);
                e.markerType = kind.marker;
            }
            cursor.add(e);
            return { success: true, added: e.subtypeName() };
        });
        if (!result || result.error) return result;
        result.message = "Added " + result.added + " at measure " + params.measure;
        if (isJump) {
            result.missing = missingMarkers(kind);
            if (result.missing.length) {
                result.warning = kind.text + " needs " + result.missing.join(", ")
                    + ", which the score doesn't have yet: add them with add_marker, or ask the user where they go.";
            }
        }
        return result;
    }

    // Where a chord symbol at a measure and beat (1-based, fractions allowed) on a staff goes: the chord
    // symbol already there, if any, and whether a new one can be added. MuseScore holds chord symbols on beats
    // where no note starts (inside a half note) on segments of their own, but a plugin's cursor only stops
    // where a note or rest starts, so a new one can only go there. noPlace says so, with the beats that have one.
    function chordSymbolPlace(measure, beat, staff) {
        var range = measureRange({ startMeasure: measure, startStaff: staff, endStaff: staff + 1 });
        if (!range.valid) return range;
        range = applyBeats(range, { startBeat: beat });
        if (range.error) return range;

        var m = range.firstMeasure;
        var start = measureStartTick(m);
        var end = measureEndTick(m);
        var beatLength = beatTicks(m);
        var beats = [], canAdd = false, harmony = null;
        for (var seg = m.firstSegment; seg && seg.tick < end; seg = seg.next) {
            if (seg.tick === range.startTick) {
                var anns = seg.annotations || [];
                for (var a = 0; a < anns.length; a++) {
                    if (anns[a].name === "Harmony" && Math.floor(anns[a].track / 4) === staff) harmony = anns[a];
                }
            }
            var hasChordRest = false;
            for (var v = 0; v < 4; v++) {
                var el = seg.elementAt(staff * 4 + v);
                if (el && (el.name === "Chord" || el.name === "Rest")) hasChordRest = true;
            }
            if (!hasChordRest) continue;
            var label = Math.round((1 + (seg.tick - start) / beatLength) * 100) / 100;
            if (beats.indexOf(label) === -1) beats.push(label);
            if (seg.tick === range.startTick) canAdd = true;
        }
        return {
            valid: true, tick: range.startTick, harmony: harmony, canAdd: canAdd,
            noPlace: "No note or rest starts on beat " + beat + " of measure " + measure + " (staff " + staff + "), and a "
                + "plugin can only add a chord symbol where one does: notes or rests start on "
                + (beats.length === 1 ? "beat " : "beats ") + beats.join(", ")
                + ". The user can add it there in MuseScore by hand."
        };
    }

    // The text is set after the chord symbol is added: setting it on a new, unattached Harmony crashes
    // MuseScore 4.7 (it parses the name against the score's style).
    function addChordSymbolAt(tick, staff, text) {
        var cursor = createCursor({ startTick: tick, startStaff: staff });
        var harmony = newElement(Element.HARMONY);
        cursor.add(harmony);
        harmony.text = text;
        return harmony;
    }

    // params: measure, beat (default 1), chord, staff (default 0). Changes the chord symbol on that beat, or
    // adds one. MuseScore parses the name as it does when typed (e.g. "Bb7", "F#m7b5", "C/E").
    function setChordSymbol(params) {
        if (!curScore) return { error: "No score open" };
        var validation = validateParams(params, ["measure", "chord"]);
        if (!validation.valid) return validation;
        var beat = params.beat || 1, staff = params.staff || 0;
        var place = chordSymbolPlace(params.measure, beat, staff);
        if (!place.valid) return place;
        if (!place.harmony && !place.canAdd) return { error: place.noPlace };

        return executeWithUndo(function() {
            var where = " on beat " + beat + " of measure " + params.measure;
            if (place.harmony) {
                var old = String(place.harmony.text || "");
                place.harmony.text = params.chord;
                return { success: true, chord: place.harmony.text, replaced: old || "(name not readable)",
                         message: "Changed " + (old || "the chord symbol") + " to " + place.harmony.text + where };
            }
            var harmony = addChordSymbolAt(place.tick, staff, params.chord);
            return { success: true, chord: harmony.text, message: "Added " + harmony.text + where };
        });
    }

    // params: measure, beat (default 1), toMeasure, toBeat (default 1), staff (default 0). There is no way
    // to move a chord symbol to another tick, so it is deleted and added again with the same name. A chord
    // symbol imported from MusicXML has no readable name until the score is saved, closed and opened again
    // (MuseScore fills in the name only when it loads the file), so it is
    // refused; so is a target beat that already has one.
    function moveChordSymbol(params) {
        if (!curScore) return { error: "No score open" };
        var validation = validateParams(params, ["measure", "toMeasure"]);
        if (!validation.valid) return validation;
        var beat = params.beat || 1, toBeat = params.toBeat || 1, staff = params.staff || 0;
        var from = chordSymbolPlace(params.measure, beat, staff);
        if (!from.valid) return from;
        var where = "beat " + beat + " of measure " + params.measure;
        if (!from.harmony) return { error: "There is no chord symbol on " + where + " (staff " + staff + ")" };
        var text = String(from.harmony.text || "");
        if (!text) {
            return { error: "The chord symbol on " + where + " has no readable name: it was imported from MusicXML "
                + "and becomes readable only after the score is saved, closed and opened again (saving alone is not "
                + "enough). Ask the user for its name, then set it "
                + "at the new place with set_chord_symbol and remove this one with remove_annotations "
                + "(kinds chord_symbols, this measure and beat " + beat + ")." };
        }
        var to = chordSymbolPlace(params.toMeasure, toBeat, staff);
        if (!to.valid) return to;
        var toWhere = "beat " + toBeat + " of measure " + params.toMeasure;
        if (to.harmony) {
            return { error: "There is already a chord symbol (" + (to.harmony.text || "name not readable") + ") on "
                + toWhere + ": change it with set_chord_symbol" };
        }
        if (!to.canAdd) return { error: to.noPlace };

        return executeWithUndo(function() {
            removeElement(from.harmony);
            var harmony = addChordSymbolAt(to.tick, staff, text);
            return { success: true, chord: harmony.text, message: "Moved " + harmony.text + " from " + where + " to " + toWhere };
        });
    }

    function breakTypes() {
        return { line: LayoutBreak.LINE, page: LayoutBreak.PAGE, section: LayoutBreak.SECTION };
    }

    // The layout breaks on a measure, optionally only those of one type
    function breaksOn(measure, type) {
        var found = [];
        var els = measure.elements || [];
        for (var i = 0; i < els.length; i++) {
            if (els[i].type === Element.LAYOUT_BREAK && (type === undefined || els[i].layoutBreakType === type)) {
                found.push(els[i]);
            }
        }
        return found;
    }

    // params: measure (1-based), kind ("line", "page" or "section"; default "line"). The break goes at the end
    // of the measure, as from the palette. A break of that kind the measure already has is refused.
    function addBreak(params) {
        if (!curScore) return { error: "No score open" };
        var validation = validateParams(params, ["measure"]);
        if (!validation.valid) return validation;
        var kind = params.kind || "line";
        var type = breakTypes()[kind];
        if (type === undefined) return { error: "Unknown break '" + kind + "'" };
        var range = measureRange({ startMeasure: params.measure, startStaff: 0, endStaff: 1 });
        if (!range.valid) return range;
        var existing = breaksOn(range.firstMeasure, type);
        if (existing.length) {
            return { error: "Measure " + params.measure + " already has a " + existing[0].subtypeName() };
        }

        var result = executeWithUndo(function() {
            var lb = newElement(Element.LAYOUT_BREAK);
            lb.layoutBreakType = type;  // before adding: the measure takes its break flags from the type
            range.firstMeasure.add(lb);
            return { success: true };
        });
        if (!result || result.error) return result;
        var added = breaksOn(range.firstMeasure, type);
        if (!added.length) return { error: "MuseScore did not add the break to measure " + params.measure };
        result.added = added[0].subtypeName();
        result.message = "Added a " + result.added + " at the end of measure " + params.measure;
        return result;
    }

    // The systems the measures in a range stand on, as laid out now: [{firstMeasure, lastMeasure}], measures
    // by position. Measures inside a multi-measure rest have no system of their own and are left out.
    function systemsOf(range) {
        var systems = [], current = null, key = null, position = 0;
        for (var m = curScore.firstMeasure; m; m = m.nextMeasure) {
            position++;
            if (position < range.startMeasure) continue;
            if (position > range.endMeasure) break;
            var system = m.parent;
            if (!system || system.name !== "System" || !m.pagePos) continue;
            var page = system.parent && system.parent.name === "Page" ? system.parent.pagenumber : 0;
            var here = page + ":" + Math.round(m.pagePos.y * 10);
            if (here !== key) {
                current = { firstMeasure: position, lastMeasure: position };
                systems.push(current);
                key = here;
            } else {
                current.lastMeasure = position;
            }
        }
        return systems;
    }

    // params: startMeasure, endMeasure (1-based, inclusive), perSystem, method ("locks", the default, or
    // "breaks"). Lays out the range perSystem measures to a system:
    // - "locks": system locks, as Format > Measures per system makes them; the systems keep their measures
    //   when measures before them change.
    // - "breaks": a system break after every perSystem measures (none after the score's last measure).
    // Either way the range's system breaks and the system locks there are removed first, so the result is exactly
    // perSystem measures to a system; perSystem 0 only removes them, back to MuseScore's own layout. Page and
    // section breaks stay. The reply gives the systems as laid out afterwards.
    function setMeasuresPerSystem(params) {
        if (!curScore) return { error: "No score open" };
        var validation = validateParams(params, ["startMeasure", "perSystem"]);
        if (!validation.valid) return validation;
        var range = measureRange(params);
        if (!range.valid) return range;
        var n = params.perSystem;
        var method = params.method || "locks";
        if (method !== "locks" && method !== "breaks") return { error: "Unknown method '" + method + "'" };
        if (n < 0) return { error: "perSystem must be 0 or more" };

        // addRemoveSystemLocks acts on the selected measures, and only sees a selection made before the undo
        // step starts. A range ending at the score's end tick leaves the last measure out, so it ends past it.
        var selectEnd = range.lastMeasure.nextMeasure ? range.endTick : range.lastMeasure.lastSegment.tick + 1;
        curScore.selection.selectRange(range.startTick, selectEnd, 0, curScore.nstaves);
        var result = executeWithUndo(function() {
            var removed = 0;
            var measures = [];
            for (var m = range.firstMeasure; m; m = m.nextMeasure) {
                measures.push(m);
                if (measureStartTick(m) >= measureStartTick(range.lastMeasure)) break;
            }
            for (var i = 0; i < measures.length; i++) {
                var lines = breaksOn(measures[i], LayoutBreak.LINE);
                for (var b = 0; b < lines.length; b++) {
                    measures[i].remove(lines[b]);
                    removed++;
                }
            }
            // With lock false, the locks in the selection are removed, then one is added every n measures
            curScore.addRemoveSystemLocks(method === "locks" ? n : 0, false);
            curScore.selection.clear();
            if (method === "breaks" && n > 0) {
                for (var j = n - 1; j < measures.length; j += n) {
                    if (!measures[j].nextMeasure) break;
                    var lb = newElement(Element.LAYOUT_BREAK);
                    lb.layoutBreakType = LayoutBreak.LINE;
                    measures[j].add(lb);
                }
            }
            return { success: true, removed_breaks: removed };
        });
        if (!result || result.error) return result;
        result.systems = systemsOf(range);
        return result;
    }

    // The kind of an element, by the names find_elements and remove_annotations use; "" for other elements.
    // Texts and labels are staff or expression texts, labels being the boxed ones (add_label).
    function elementKind(e) {
        if (e.type === Element.MARKER) return "markers";
        if (e.type === Element.JUMP) return "jumps";
        switch (e.name) {
            case "Harmony": return "chord_symbols";
            case "RehearsalMark": return "rehearsal_marks";
            case "Tempo": case "TempoText": return "tempo";
            case "StaffText": case "Expression":
                return e.frameType && !isTranslucent(e.frameBgColor) ? "labels" : "texts";
        }
        return "";
    }

    function elementText(e) {
        if (e.type === Element.MARKER) return e.subtypeName();
        return String(e.text || "").replace(/<[^>]*>/g, "");
    }

    // The elements of the given kinds in a range of measures and staves, optionally only on one beat or with a
    // text containing (or, with exact, equal to) `contains`: [{element, measure (position), beat, staff, kind,
    // text}]. Markers and jumps belong to the measure; they are found on every staff range that holds staff 0
    // and have no beat.
    function matchingElements(params) {
        var range = measureRange(params);
        if (!range.valid) return range;
        var kinds = params.kinds && params.kinds.length ? params.kinds
            : ["chord_symbols", "markers", "jumps", "texts", "labels", "rehearsal_marks", "tempo"];
        var contains = params.contains || "";
        var exact = params.exact === true;
        var found = [];
        function keep(e, kind, text) {
            if (kinds.indexOf(kind) === -1) return false;
            if (contains && (exact ? text !== contains : text.indexOf(contains) === -1)) return false;
            return true;
        }
        var position = params.startMeasure;
        for (var m = range.firstMeasure; m; m = m.nextMeasure, position++) {
            var start = measureStartTick(m), end = measureEndTick(m), beatLength = beatTicks(m);
            var els = m.elements || [];
            if (range.startStaff === 0) {
                for (var i = 0; i < els.length; i++) {
                    var kind = elementKind(els[i]);
                    if (kind && keep(els[i], kind, elementText(els[i]))) {
                        found.push({ element: els[i], measure: position, staff: 0, kind: kind, text: elementText(els[i]) });
                    }
                }
            }
            for (var seg = m.firstSegment; seg && seg.tick < end; seg = seg.next) {
                var beat = Math.round((1 + (seg.tick - start) / beatLength) * 100) / 100;
                if (params.beat && beat !== params.beat) continue;
                var anns = seg.annotations || [];
                for (var a = 0; a < anns.length; a++) {
                    var staff = Math.floor(anns[a].track / 4);
                    if (staff < range.startStaff || staff >= range.endStaff) continue;
                    var k = elementKind(anns[a]);
                    var text = elementText(anns[a]);
                    if (k && keep(anns[a], k, text)) {
                        found.push({ element: anns[a], measure: position, beat: beat, staff: staff, kind: k, text: text });
                    }
                }
            }
            if (measureStartTick(m) >= measureStartTick(range.lastMeasure)) break;
        }
        return found;
    }

    // What find_elements reports about an element: where it is and the properties set_properties changes, as
    // the element has them now (its own value, or its style's).
    function describeElement(f) {
        var e = f.element;
        var d = { measure: f.measure, staff: f.staff, kind: f.kind, text: f.text };
        if (f.beat !== undefined) d.beat = f.beat;
        d.placement = e.placement === Placement.BELOW ? "below" : "above";
        var align = e.align;
        d.align = align && align.length ? (["left", "right", "center"][align[0]] || String(align[0])) : null;
        d.fontSize = e.fontSize;
        d.offset = e.offset ? [Math.round(e.offset.x * 100) / 100, Math.round(e.offset.y * 100) / 100] : null;
        d.autoplace = e.autoplace;
        return d;
    }

    // params: startMeasure, endMeasure, startStaff, endStaff, kinds, beat, contains, exact
    function findElements(params) {
        if (!curScore) return { error: "No score open" };
        var found = matchingElements(params);
        if (found.error) return found;
        var elements = [];
        for (var i = 0; i < found.length; i++) elements.push(describeElement(found[i]));
        return { success: true, count: elements.length, elements: elements };
    }

    // params: the selection findElements takes, and what to change: placement ("above"/"below"), align
    // ("left"/"center"/"right"), fontSize (points), offset ([x, y] in staff spaces, replacing the current one),
    // moveBy ([dx, dy] in staff spaces, added to the current offset; y grows downwards) and reset (names of
    // these properties to put back to the style's value). The reply lists the elements as they are afterwards.
    function setProperties(params) {
        if (!curScore) return { error: "No score open" };
        var changes = ["placement", "align", "fontSize", "offset", "moveBy", "reset"];
        var any = false;
        for (var c = 0; c < changes.length; c++) if (params[changes[c]] !== undefined && params[changes[c]] !== null) any = true;
        if (!any) return { error: "Nothing to change: give placement, align, fontSize, offset, moveBy or reset" };
        if (params.align && ["left", "center", "right"].indexOf(params.align) === -1) {
            return { error: "Unknown align '" + params.align + "' (left, center or right)" };
        }
        var found = matchingElements(params);
        if (found.error) return found;
        if (!found.length) return { error: "No elements match; check them with find_elements" };

        // The plugin reads align as [h, v] (internal values) but writes it as an Align bitmask
        var hAlign = { left: Align.LEFT, right: Align.RIGHT, center: Align.HCENTER };
        var vAlign = [Align.TOP, Align.VCENTER, Align.BOTTOM, Align.BASELINE];
        var reset = params.reset || [];
        var result = executeWithUndo(function() {
            for (var i = 0; i < found.length; i++) {
                var e = found[i].element;
                if (params.placement) e.placement = params.placement === "below" ? Placement.BELOW : Placement.ABOVE;
                if (params.align) {
                    var current = e.align;
                    var v = current && current.length > 1 ? vAlign[current[1]] : Align.BASELINE;
                    e.align = hAlign[params.align] | v;
                }
                if (params.fontSize) e.fontSize = params.fontSize;
                if (params.offset) e.offset = Qt.point(params.offset[0], params.offset[1]);
                if (params.moveBy) {
                    var o = e.offset || { x: 0, y: 0 };
                    e.offset = Qt.point(o.x + params.moveBy[0], o.y + params.moveBy[1]);
                }
                for (var r = 0; r < reset.length; r++) {
                    var name = reset[r] === "moveBy" ? "offset" : reset[r];
                    if (["placement", "align", "fontSize", "offset"].indexOf(name) !== -1) e[name] = undefined;
                }
            }
            return { success: true };
        });
        if (!result || result.error) return result;
        var elements = [];
        for (var j = 0; j < found.length; j++) elements.push(describeElement(found[j]));
        return { success: true, count: elements.length, elements: elements };
    }

    // params: startMeasure, endMeasure (inclusive), stretch (1 is MuseScore's own width, 1.5 half as wide again;
    // more than 0). Sets each measure's layout stretch, as Format > Stretch does.
    function setMeasureStretch(params) {
        if (!curScore) return { error: "No score open" };
        var validation = validateParams(params, ["startMeasure", "stretch"]);
        if (!validation.valid) return validation;
        if (!(params.stretch > 0)) return { error: "stretch must be more than 0" };
        var range = measureRange(params);
        if (!range.valid) return range;

        var result = executeWithUndo(function() {
            for (var m = range.firstMeasure; m; m = m.nextMeasure) {
                m.userStretch = params.stretch;
                if (measureStartTick(m) >= measureStartTick(range.lastMeasure)) break;
            }
            return { success: true };
        });
        if (!result || result.error) return result;
        var measures = [], position = range.startMeasure;
        for (var mm = range.firstMeasure; mm; mm = mm.nextMeasure, position++) {
            measures.push({ measure: position, stretch: mm.userStretch });
            if (measureStartTick(mm) >= measureStartTick(range.lastMeasure)) break;
        }
        return { success: true, measures: measures };
    }

    // Bar counts of the sections, e.g. "2x4+2". mode "label" (default, the user's choice) writes the count in
    // parentheses in the measure's rehearsal mark: "Chorus 1 (2x4)", placed and spaced by MuseScore with the label. mode "beside" adds a staff text right of the rehearsal mark, at
    // the mark's height: its autoplace is off and its offset is set from the mark's laid-out position, so it
    // stays level with the label wherever the system starts and other texts don't push it around.
    // counts: [{measure, text}]. Counts added before at those measures, in either form (a "(...)" count at the
    // end of the label, bold staff texts made only of digits, "x" and "+"), are replaced; clear: true only
    // removes them. clearAll: true first removes such staff texts anywhere on the first staff (counts left on
    // other bars by earlier edits).
    function addSectionCounts(params) {
        if (!curScore) return { error: "No score open" };
        var validation = validateParams(params, ["counts"]);
        if (!validation.valid) return validation;
        var color = params.color || "#d62728";
        var fontSize = params.fontSize || 12;
        var gap = params.gap !== undefined ? params.gap : 0.8;  // spaces between the label's box and the count
        var inLabel = (params.mode || "label") === "label";

        return executeWithUndo(function() {
            var placed = [], skipped = [], removed = 0, labelled = [];
            if (params.clearAll) {
                var stale = [];
                for (var sm = curScore.firstMeasure; sm; sm = sm.nextMeasure) {
                    for (var ss = sm.firstSegment; ss; ss = ss.nextInMeasure) {
                        var anns = ss.annotations || [];
                        for (var sa = 0; sa < anns.length; sa++) {
                            if (Math.floor(anns[sa].track / 4) === 0 && isSectionCount(anns[sa])) stale.push(anns[sa]);
                        }
                    }
                }
                for (var st = 0; st < stale.length; st++) removeElement(stale[st]);
                removed += stale.length;
            }
            var minTick = -1, maxTick = 0;
            for (var i = 0; i < params.counts.length; i++) {
                var c = params.counts[i];
                var m = getMeasure(c.measure);
                if (!m) { skipped.push({ measure: c.measure, reason: "no such measure" }); continue; }
                var start = measureStartTick(m), end = measureEndTick(m);
                var mark = null, old = [];
                for (var seg = m.firstSegment; seg; seg = seg.nextInMeasure) {
                    var annotations = seg.annotations || [];
                    for (var a = 0; a < annotations.length; a++) {
                        var ann = annotations[a];
                        if (Math.floor(ann.track / 4) !== 0) continue;
                        if (ann.name === "RehearsalMark" && !mark) mark = ann;
                        if (isSectionCount(ann)) old.push(ann);
                    }
                }
                for (var o = 0; o < old.length; o++) removeElement(old[o]);
                removed += old.length;
                if (mark) {
                    var base = labelWithoutCount(mark.text);
                    if (base !== String(mark.text)) { mark.text = base; removed++; }
                }
                if (params.clear) continue;
                if (inLabel) {
                    if (!mark) { skipped.push({ measure: c.measure, reason: "no section label" }); continue; }
                    mark.text = labelWithoutCount(mark.text) + " (" + countText(c.text) + ")";
                    labelled.push(c.measure);
                    continue;
                }

                var cursor = createCursor({ startTick: start, startStaff: 0 });
                var text = newElement(Element.STAFF_TEXT);
                text.text = countText(c.text);
                text.fontSize = fontSize;
                text.fontStyle = 1;  // bold
                text.color = color;
                text.placement = 0;  // above
                if (mark) text.autoplace = false;
                cursor.add(text);
                placed.push({ measure: c.measure, text: text, mark: mark });
                if (minTick < 0 || start < minTick) minTick = start;
                if (end > maxTick) maxTick = end;
            }
            if (placed.length) {
                curScore.doLayout(fraction(minTick, 1920), fraction(maxTick, 1920));
                for (var j = 0; j < placed.length; j++) {
                    var p = placed[j];
                    if (!p.mark) continue;
                    var mp = p.mark.pagePos, mb = p.mark.bbox, tp = p.text.pagePos, tb = p.text.bbox;
                    var dx = (mp.x + mb.x + mb.width + gap) - (tp.x + tb.x);
                    var dy = (mp.y + mb.y + mb.height / 2) - (tp.y + tb.y + tb.height / 2);
                    // Clear what is already there: past texts (e.g. the tempo) to the right, above notes and
                    // symbols (e.g. hi-hat signs at that height)
                    var obstacles = countObstacles(p.measure, p.text, p.mark);
                    for (var tries = 0; tries < 12; tries++) {
                        var box = { x0: tp.x + tb.x + dx, x1: tp.x + tb.x + tb.width + dx,
                                    y0: tp.y + tb.y + dy, y1: tp.y + tb.y + tb.height + dy };
                        var hit = null;
                        for (var h = 0; h < obstacles.length && !hit; h++) {
                            var ob = obstacles[h];
                            if (ob.x0 < box.x1 && ob.x1 > box.x0 && ob.y0 < box.y1 && ob.y1 > box.y0) hit = ob;
                        }
                        if (!hit) break;
                        if (hit.text) dx += hit.x1 + gap - box.x0;
                        else dy -= box.y1 - (hit.y0 - 0.3);
                    }
                    var off = p.text.offset;
                    p.text.offset = Qt.point(off.x + dx, off.y + dy);
                    // Autoplace stays off: turned back on, MuseScore pushed counts into the notes. So the count is
                    // not part of the system's outline and the system above isn't kept clear of it: mode "label"
                    // has no such problem.
                }
            }
            var noLabel = [];
            for (var k = 0; k < placed.length; k++) if (!placed[k].mark) noLabel.push(placed[k].measure);
            var added = placed.length + labelled.length;
            var result = { success: true, added: added, removed: removed,
                           message: params.clear ? "Removed " + removed + " count(s)" : "Added " + added + " count(s)" };
            if (noLabel.length) result.withoutSectionLabel = noLabel;
            if (skipped.length) result.skipped = skipped;
            return result;
        });
    }

    // Laid-out boxes (page coordinates, spaces) near a section count on staff 1: texts in its measure and the
    // next one (text: true), and the notes and articulations of their chords.
    function countObstacles(measureNumber, self, mark) {
        var out = [];
        function add(el, isText) {
            if (!el || sameElement(el, self) || sameElement(el, mark)) return;
            var pp = el.pagePos, bb = el.bbox;
            if (!bb || bb.width <= 0 || bb.height <= 0) return;
            out.push({ x0: pp.x + bb.x, x1: pp.x + bb.x + bb.width, y0: pp.y + bb.y, y1: pp.y + bb.y + bb.height, text: isText });
        }
        var m = getMeasure(measureNumber);
        for (var n = 0; m && n < 2; n++, m = m.nextMeasure) {
            for (var seg = m.firstSegment; seg; seg = seg.nextInMeasure) {
                var annotations = seg.annotations || [];
                for (var a = 0; a < annotations.length; a++) {
                    if (Math.floor(annotations[a].track / 4) === 0) add(annotations[a], true);
                }
                for (var v = 0; v < 4; v++) {
                    var el = seg.elementAt(v);
                    if (!el || el.name !== "Chord") continue;
                    var notes = el.notes || [];
                    for (var k = 0; k < notes.length; k++) add(notes[k], false);
                    var arts = el.articulations || [];
                    for (var r = 0; r < arts.length; r++) add(arts[r], false);
                }
            }
        }
        return out;
    }

    function sameElement(a, b) {
        if (!a || !b) return false;
        return typeof a.is === "function" ? a.is(b) : a === b;
    }

    // A rehearsal mark's text without a trailing bar count in parentheses ("Chorus 1 (2x4)" -> "Chorus 1")
    function labelWithoutCount(text) {
        return String(text || "").replace(/\s*\((?:<[^>]*>)*[0-9][0-9x+ ]*(?:<[^>]*>)*\)\s*$/, "");
    }

    // A count as written: "2x4+2" (brackets around it are dropped: the label mode adds its own)
    function countText(text) {
        return String(text).replace(/^\s*\(\s*/, "").replace(/\s*\)\s*$/, "");
    }

    function isSectionCount(el) {
        if (el.name !== "StaffText" || el.frameType) return false;
        var plain = String(el.text || "").replace(/<[^>]*>/g, "").trim();
        return /^\(?\s*[0-9][0-9x+ ]*\)?$/.test(plain) && (el.fontStyle & 1) === 1;
    }

    // ========================================
    // SCORE FILES & PARTS
    // ========================================

    // staff index -> Part, from each part's track range (4 tracks per staff, endTrack exclusive)
    function staffParts() {
        var map = {};
        var parts = curScore.parts || [];
        for (var p = 0; p < parts.length; p++) {
            var part = parts[p];
            for (var s = Math.floor(part.startTrack / 4); s < Math.ceil(part.endTrack / 4); s++) {
                map[s] = part;
            }
        }
        return map;
    }

    function isDrumPart(part) {
        if (part.hasDrumStaff) return true;
        return (part.instrumentId || "").indexOf("drum.") === 0;
    }

    function scoreFileInfo() {
        if (!curScore) return { error: "No score open" };
        return {
            success: true,
            scoreId: curScore.metaTag("mcpScoreId") || "",
            scoreName: curScore.scoreName || "",
            title: curScore.title || "",
            numMeasures: curScore.nmeasures,
            numStaves: curScore.nstaves
        };
    }

    // The plugin API does not expose a score's file path. The server finds the file by an ID stored in the
    // score's metadata: give the open score one (a new one with renew, e.g. for a copy of another score).
    function ensureScoreId(params) {
        if (!curScore) return { error: "No score open" };
        var id = curScore.metaTag("mcpScoreId");
        if (id && !(params && params.renew)) return { success: true, scoreId: id, created: false };
        id = "mcp-" + Date.now().toString(36) + "-" + Math.floor(Math.random() * 2176782336).toString(36);
        curScore.startCmd();
        curScore.setMetaTag("mcpScoreId", id);
        curScore.endCmd();
        return { success: true, scoreId: id, created: true };
    }

    function saveScore() {
        if (!curScore) return { error: "No score open" };
        cmd("file-save");
        return { success: true, message: "Score saved" };
    }

    // Export a copy without saving the score (no Save dialog, no corruption check). writeScore() works for
    // export formats such as MusicXML (.mxl) but not for MuseScore's own .mscz/.mscx in 4.7.
    function exportScore(params) {
        if (!curScore) return { error: "No score open" };
        var validation = validateParams(params, ["path"]);
        if (!validation.valid) return validation;
        var ext = params.path.split(".").pop().toLowerCase();
        if (ext === "mscz" || ext === "mscx") return { error: "MuseScore files cannot be exported from a plugin; use .mxl" };
        if (!writeScore(curScore, params.path, ext)) return { error: "MuseScore could not export " + params.path };
        return { success: true, path: params.path };
    }

    function openedScoreResult(opened, path) {
        if (!opened || !curScore) return { error: "MuseScore could not open " + path };
        selectionState = { startStaff: 0, endStaff: 1, startTick: 0, elements: {} };
        return {
            success: true,
            path: path,
            scoreName: curScore.scoreName || "",
            numMeasures: curScore.nmeasures,
            numStaves: curScore.nstaves
        };
    }

    function openScore(params) {
        var validation = validateParams(params, ["path"]);
        if (!validation.valid) return validation;
        return openedScoreResult(readScore(params.path), params.path);
    }

    // Close the current score and open `path` in its place (MuseScore 4 would open a second score in a new
    // window, out of the plugin's reach). Save first: closing a modified score would show a dialog.
    // If `path` cannot be opened, `fallbackPath` (usually the score just closed) is opened again.
    function reopenScore(params) {
        if (!curScore) return { error: "No score open" };
        var validation = validateParams(params, ["path"]);
        if (!validation.valid) return validation;
        closeScore(curScore);
        var opened = readScore(params.path);
        if (!opened && params.fallbackPath) {
            var restored = readScore(params.fallbackPath);
            return { error: "MuseScore could not open " + params.path + (restored ? "; reopened " + params.fallbackPath : "") };
        }
        return openedScoreResult(opened, params.path);
    }

    // Remove every part that has none of the given staves (MuseScore 4.7+).
    function removeParts(params) {
        if (!curScore) return { error: "No score open" };
        var validation = validateParams(params, ["keepStaves"]);
        if (!validation.valid) return validation;
        if (typeof curScore.removeParts !== "function") {
            return { error: "This MuseScore version cannot remove instruments from a plugin (needs 4.7+). Remove them in the Instruments panel." };
        }

        var parts = curScore.parts;
        var remove = [];
        var kept = [];
        for (var p = 0; p < parts.length; p++) {
            var part = parts[p];
            var keep = false;
            for (var s = Math.floor(part.startTrack / 4); s < Math.ceil(part.endTrack / 4); s++) {
                if (params.keepStaves.indexOf(s) !== -1) keep = true;
            }
            if (keep) kept.push(part.longName || part.partName || ""); else remove.push(part);
        }
        if (kept.length === 0) return { error: "None of the staves " + params.keepStaves.join(", ") + " exist" };

        return executeWithUndo(function() {
            curScore.removeParts(remove);
            return { success: true, removed: remove.length, kept: kept, numStaves: curScore.nstaves };
        });
    }

    // ========================================
    // MEASURE NUMBERS
    // ========================================

    // Displayed measure numbers, by position (index 0 = measure 1), following MuseScore's layout rule:
    // add each measure's "add to measure number" offset, then count it unless it is excluded.
    function displayedNumbers() {
        var numbers = [];
        var count = 0;
        for (var m = curScore.firstMeasure; m; m = m.nextMeasure) {
            count += m.noOffset || 0;
            numbers.push(count + 1);
            if (!m.irregular) count++;
        }
        return numbers;
    }

    // The printed numbers and which measures are left out of the count, by position: the server
    // turns the bar numbers users give into positions with them.
    function barNumbers() {
        if (!curScore) return { error: "No score open" };
        var excluded = [];
        for (var m = curScore.firstMeasure; m; m = m.nextMeasure) excluded.push(!!m.irregular);
        return { success: true, numbers: displayedNumbers(), excluded: excluded };
    }

    // Set "Add to measure number" and/or "Exclude from measure count" on one measure.
    function setMeasureNumbering(params) {
        if (!curScore) return { error: "No score open" };
        var validation = validateParams(params, ["measure"]);
        if (!validation.valid) return validation;
        var m = getMeasure(params.measure);
        if (!m) return { error: "Invalid measure number " + params.measure };

        return executeWithUndo(function() {
            if (params.addToNumber !== undefined && params.addToNumber !== null) m.noOffset = params.addToNumber;
            if (params.excludeFromCount !== undefined && params.excludeFromCount !== null) m.irregular = params.excludeFromCount;
            return { success: true, displayedNumber: displayedNumbers()[params.measure - 1],
                     message: "Measure " + params.measure + " now shows number " + displayedNumbers()[params.measure - 1] };
        });
    }

    // Number measures as they are played: after a passage between repeat barlines played N times, the next
    // measure's offset is (N - 1) x the passage length. Every other measure's offset is reset to 0, so the
    // result does not depend on earlier runs. Optional `exclude` lists measures to leave out of the count.
    // Voltas are not taken into account (they are reported).
    function numberAsPlayed(params) {
        if (!curScore) return { error: "No score open" };
        params = params || {};
        var first = curScore.firstMeasure;
        if (first && typeof first.repeatEnd === "undefined") {
            return { error: "Reading repeat barlines needs MuseScore 4.6 or newer" };
        }

        var measures = [];
        for (var m = first; m; m = m.nextMeasure) measures.push(m);
        var offsets = [];
        for (var i = 0; i < measures.length; i++) offsets.push(0);

        var sectionStart = 0;
        var repeats = [];
        for (var j = 0; j < measures.length; j++) {
            if (measures[j].repeatStart) sectionStart = j;
            if (measures[j].repeatEnd) {
                var count = measures[j].repeatCount || 2;
                var length = j - sectionStart + 1;
                if (count > 1 && j + 1 < measures.length) offsets[j + 1] += (count - 1) * length;
                repeats.push({ start: sectionStart + 1, end: j + 1, playCount: count });
                sectionStart = j + 1;
            }
        }

        var voltas = 0;
        var spanners = curScore.spanners || [];
        for (var v = 0; v < spanners.length; v++) {
            if (spanners[v].name === "Volta") voltas++;
        }

        var exclude = params.exclude || [];
        var reset = params.reset === true;
        return executeWithUndo(function() {
            for (var k = 0; k < measures.length; k++) {
                measures[k].noOffset = reset ? 0 : offsets[k];
                if (reset) measures[k].irregular = false;
                else if (exclude.indexOf(k + 1) !== -1) measures[k].irregular = true;
            }
            if (reset) {
                var plain = displayedNumbers();
                return { success: true, reset: true, lastMeasureNumber: plain[plain.length - 1],
                         message: "Bar numbers reset to 1-" + plain[plain.length - 1] };
            }
            var numbers = displayedNumbers();
            var changed = [];
            for (var n = 0; n < measures.length; n++) {
                if (offsets[n]) changed.push({ measure: n + 1, addToNumber: offsets[n], displayedNumber: numbers[n] });
            }
            var result = {
                success: true,
                repeats: repeats,
                offsets: changed,
                lastMeasureNumber: numbers[numbers.length - 1],
                message: "Numbered " + measures.length + " measures as played; the last one shows " + numbers[numbers.length - 1]
            };
            if (voltas) result.warning = voltas + " volta(s) in the score: 1st/2nd endings are not taken into account";
            return result;
        });
    }

    // ========================================
    // SCORE ANALYSIS
    // ========================================

    function getScore(params) {
        if (!curScore) return { error: "No score open" };

        try {
            return { success: true, analysis: getScoreSummary(params) };
        } catch (e) {
            return { error: e.toString() };
        }
    }

    // The measure's own elements: markers (Segno, Coda, To Coda, Fine), jumps (D.S. al Coda…) and
    // line, page and section breaks. They hang on the measure, not on a segment, so the annotation
    // loop never sees them. A marker's text is a symbol (<sym>coda</sym>), so the type's name is used.
    function measureElementsOf(measure) {
        var found = [];
        var els = measure.elements || [];
        for (var i = 0; i < els.length; i++) {
            var e = els[i];
            if (e.type !== Element.MARKER && e.type !== Element.JUMP && e.type !== Element.LAYOUT_BREAK) continue;
            var text = String(e.text || "").replace(/<[^>]*>/g, "");
            var name = typeof e.subtypeName === "function" ? e.subtypeName() : "";
            found.push({ name: e.name, text: e.type === Element.JUMP && text ? text : (name || text) });
        }
        return found;
    }

    // opts: startMeasure / endMeasure (1-based, inclusive), staves (list of staff indices),
    // includeElements (false returns only measure positions, which navigation uses).
    function getScoreSummary(opts) {
        if (!curScore) return { error: "No score open" };

        opts = opts || {};
        var total = curScore.nmeasures;
        var numbers = displayedNumbers();
        var first = Math.max(1, opts.startMeasure || 1);
        var last = Math.min(total, opts.endMeasure || total);
        var includeElements = opts.includeElements !== false;

        var staffIndices = [];
        if (opts.staves && opts.staves.length) {
            for (var s = 0; s < opts.staves.length; s++) {
                if (opts.staves[s] >= 0 && opts.staves[s] < curScore.nstaves) staffIndices.push(opts.staves[s]);
            }
        } else {
            for (var a = 0; a < curScore.nstaves; a++) staffIndices.push(a);
        }

        var score = {
            title: curScore.metaTag("workTitle") || curScore.title || "",
            numMeasures: total,
            startMeasure: first,
            endMeasure: last,
            measures: [],
            staves: []
        };

        var partOf = staffParts();
        for (var i = 0; i < staffIndices.length; i++) {
            var idx = staffIndices[i];
            var staff = curScore.staves && curScore.staves[idx] ||
                       (typeof curScore.staff === "function" ? curScore.staff(idx) : null);
            var part = partOf[idx];
            score.staves.push({
                name: `staff${idx}`,
                index: idx,
                partName: part ? (part.longName || part.partName || "") : "",
                shortName: part ? (part.shortName || "") : (staff ? staff.shortName : ""),
                instrumentId: part ? (part.instrumentId || "") : "",
                isDrums: part ? isDrumPart(part) : false,
                visible: staff ? !staff.invisible : true
            });
        }

        var m = getMeasure(first);
        for (var n = first; m && n <= last; n++, m = m.nextMeasure) {
            var startTick = measureStartTick(m);
            var endTick = measureEndTick(m);
            var entry = { measure: n, number: numbers[n - 1], startTick: startTick, durationTicks: endTick - startTick };
            if (m.repeatStart) entry.repeatStart = true;
            if (m.repeatEnd) entry.repeatEnd = m.repeatCount || 2;
            if (m.irregular) entry.irregular = true;  // excluded from the bar count (e.g. a count-in bar)

            if (includeElements) {
                entry.numElements = 0;
                entry.elements = {};
                for (var j = 0; j < staffIndices.length; j++) {
                    entry.elements[`staff${staffIndices[j]}`] = [];
                }

                entry.markings = [];
                var seg = m.firstSegment;
                while (seg && seg.tick < endTick) {
                    for (var k = 0; k < staffIndices.length; k++) {
                        for (var v = 0; v < 4; v++) {
                            var processed = processElement(seg.elementAt(staffIndices[k] * 4 + v));
                            if (processed) {
                                processed.startTick = seg.tick;
                                processed.voice = v;
                                entry.elements[`staff${staffIndices[k]}`].push(processed);
                                entry.numElements++;
                            }
                        }
                    }
                    var annotations = seg.annotations || [];
                    for (var a = 0; a < annotations.length; a++) {
                        var ann = annotations[a];
                        var annStaff = Math.floor(ann.track / 4);
                        if (staffIndices.indexOf(annStaff) === -1) continue;
                        entry.markings.push({
                            name: ann.name,
                            text: typeof ann.subtypeName === "function" && ann.name === "Dynamic" ? ann.subtypeName()
                                  : String(ann.text || "").replace(/<[^>]*>/g, ""),
                            staff: annStaff,
                            startTick: seg.tick,
                            highlighted: isMarkingHighlight(ann) ? true : false
                        });
                    }
                    seg = seg.next;
                }
                entry.measureElements = measureElementsOf(m);
            }
            score.measures.push(entry);
        }
        return score;
    }

    // ========================================
    // INITIALIZATION
    // ========================================

    onRun: {
        console.log("Starting MuseScore API Server (Clean Version) on port 8765");
        
        api.websocketserver.listen(8765, function(clientId) {
            console.log("Client connected with ID: " + clientId);
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