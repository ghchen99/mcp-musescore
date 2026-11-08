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
            case "addRehearsalMark":        return addRehearsalMark(command.params);
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

    function selectMeasureRange(range) {
        curScore.selection.clear();
        curScore.selection.selectRange(range.startTick, range.endTick, range.startStaff, range.endStaff);
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
            currentScore: getScoreSummary({ includeElements: false })
        };
    }

    function processSequence(params) {
        if (!curScore) return { error: "No score open" };
        if (!params.sequence) return { error: "No sequence specified" };

        var validCommands = [
            "getScore", "addNote", "addTie", "addRest", "addTuplet", "appendMeasure", "deleteSelection",
            "getCursorInfo", "goToMeasure", "nextElement", "prevElement", "nextStaff", "prevStaff",
            "selectCurrentMeasure", "processSequence", "insertMeasure", "goToFinalMeasure",
            "goToBeginningOfScore", "setTimeSignature", "addLyrics", "addInstrument",
            "setStaffMute", "setInstrumentSound", "setTempo",
            "selectMeasures", "setRepeatBarlines", "addVolta", "colorRange", "deleteMeasures",
            "setStyle", "addRehearsalMark", "addSectionCounts", "removeParts", "addHighlight", "addLabel", "clearHighlights",
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

    // Tie notes of the chord at the cursor to the same pitches in the next chord (same staff and voice).
    // MuseScore's tie command does not refuse a note without a matching pitch in the next chord: it inserts
    // a new tied note and overwrites the music after it. So only notes whose pitch is in both chords are
    // selected. Afterwards the cursor is on the second chord, so another addTie continues a tie chain.
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

            var firstPitches = chordPitches(first);
            var secondPitches = chordPitches(second);
            var requested = params.pitches && params.pitches.length ? params.pitches : null;
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

            // Check the result on a fresh cursor; throwing rolls the whole action back
            var check = createCursor({ startTick: firstTick, startStaff: staffIdx });
            var tied = [];
            for (var n = 0; n < toTie.length; n++) {
                var tiedNote = noteWithPitch(check.element, toTie[n].pitch);
                if (!tiedNote || !tiedNote.tieForward) {
                    throw new Error("MuseScore did not tie pitch " + toTie[n].pitch);
                }
                tied.push(toTie[n].pitch);
            }

            // Move the cursor to the second chord. MuseScore applies a new selection only when the command ends,
            // so reading it back here (syncStateToSelection) would still report the first chord. Build the cursor
            // state directly instead, as nextElement does.
            var secondTicks = second.actualDuration ? second.actualDuration.ticks : 0;
            curScore.selection.clear();
            curScore.selection.selectRange(secondTick, secondTick + secondTicks, staffIdx, staffIdx + 1);
            var secondElement = processElement(createCursor({ startTick: secondTick, startStaff: staffIdx }).element);
            secondElement.startTick = secondTick;
            var staffMap = {};
            staffMap["staff" + staffIdx] = [secondElement];
            selectionState = {
                startStaff: staffIdx,
                endStaff: staffIdx + 1,
                startTick: secondTick,
                elements: staffMap,
                totalDuration: secondTicks
            };

            return {
                success: true,
                message: "Tied " + (tied.length ? "pitch " + tied.join(", ") : "nothing new") +
                    (alreadyTied.length ? " (already tied: " + alreadyTied.join(", ") + ")" : ""),
                tiedPitches: tied,
                alreadyTied: alreadyTied,
                skippedPitches: skipped,
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

        return executeWithUndo(function() {
            curScore.style.setValue(params.key, params.value);
            return { success: true, message: "Style " + params.key + " set to " + params.value };
        });
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
    // "labels" (boxed staff text: add_label), "rehearsal_marks", "tempo", "voltas". `contains` limits text-based
    // kinds to elements whose text contains that string (e.g. "*"), or equals it when `exact` is true.
    function removeAnnotations(params) {
        if (!curScore) return { error: "No score open" };
        var range = measureRange(params);
        if (!range.valid) return range;
        var kinds = params.kinds && params.kinds.length ? params.kinds : ["texts"];
        var contains = params.contains || "";
        var exact = params.exact === true;
        var removed = { texts: 0, labels: 0, rehearsal_marks: 0, tempo: 0, voltas: 0 };
        var targets = [];

        forEachMarking(range, ["StaffText", "Expression", "RehearsalMark", "Tempo", "TempoText"], function(ann) {
            var kind;
            if (ann.name === "RehearsalMark") kind = "rehearsal_marks";
            else if (ann.name === "Tempo" || ann.name === "TempoText") kind = "tempo";
            else kind = ann.frameType && !isTranslucent(ann.frameBgColor) ? "labels" : "texts";
            if (kinds.indexOf(kind) === -1) return;
            var plain = String(ann.text || "").replace(/<[^>]*>/g, "");
            if (contains && (exact ? plain !== contains : plain.indexOf(contains) === -1)) return;
            targets.push(ann);
            removed[kind]++;
        });
        if (kinds.indexOf("voltas") !== -1) {
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