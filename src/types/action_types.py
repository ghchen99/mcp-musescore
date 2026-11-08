"""TypedDict definitions for MuseScore MCP action sequences."""

from typing import Dict, Any, List, Literal, NotRequired, TypedDict


class getScoreAction(TypedDict):
    action: Literal["getScore"]
    params: Dict[str, Any]


class addNoteParams(TypedDict):
    pitch: int
    duration: Dict[Literal["numerator", "denominator"], int]
    advanceCursorAfterAction: bool
    addToChord: NotRequired[bool]


class addNoteAction(TypedDict):
    action: Literal["addNote"]
    params: addNoteParams


class addRestParams(TypedDict):
    duration: Dict[Literal["numerator", "denominator"], int]
    advanceCursorAfterAction: bool


class addRestAction(TypedDict):
    action: Literal["addRest"]
    params: addRestParams


class addTupletParams(TypedDict):
    duration: Dict[Literal["numerator", "denominator"], int]
    ratio: Dict[Literal["numerator", "denominator"], int]
    advanceCursorAfterAction: bool


class addTupletAction(TypedDict):
    action: Literal["addTuplet"]
    params: addTupletParams


class addTieParams(TypedDict):
    pitches: NotRequired[List[int]]


class addTieAction(TypedDict):
    action: Literal["addTie"]
    params: addTieParams


class addTiedNoteParams(TypedDict):
    duration: Dict[Literal["numerator", "denominator"], int]
    advanceCursorAfterAction: bool
    pitches: NotRequired[List[int]]
    extraPitches: NotRequired[List[int]]


class addTiedNoteAction(TypedDict):
    action: Literal["addTiedNote"]
    params: addTiedNoteParams


class addLyricsParams(TypedDict):
    lyrics: List[str]
    verse: int


class addLyricsAction(TypedDict):
    action: Literal["addLyrics"]
    params: addLyricsParams


class addInstrumentParams(TypedDict):
    instrumentId: str


class addInstrumentAction(TypedDict):
    action: Literal["addInstrument"]
    params: addInstrumentParams


class setStaffMuteParams(TypedDict):
    staff: int
    mute: bool


class setStaffMuteAction(TypedDict):
    action: Literal["setStaffMute"]
    params: setStaffMuteParams


class setInstrumentSoundParams(TypedDict):
    staff: int
    instrumentId: str


class setInstrumentSoundAction(TypedDict):
    action: Literal["setInstrumentSound"]
    params: setInstrumentSoundParams


class appendMeasureAction(TypedDict):
    action: Literal["appendMeasure"]
    params: Dict[str, Any]


class deleteSelectionAction(TypedDict):
    action: Literal["deleteSelection"]
    params: Dict[str, Any]


class getCursorInfoAction(TypedDict):
    action: Literal["getCursorInfo"]
    params: Dict[str, Any]


class goToMeasureParams(TypedDict):
    measure: int


class goToMeasureAction(TypedDict):
    action: Literal["goToMeasure"]
    params: goToMeasureParams


class nextElementAction(TypedDict):
    action: Literal["nextElement"]
    params: Dict[str, Any]


class prevElementAction(TypedDict):
    action: Literal["prevElement"]
    params: Dict[str, Any]


class selectCurrentMeasureAction(TypedDict):
    action: Literal["selectCurrentMeasure"]
    params: Dict[str, Any]


class insertMeasureAction(TypedDict):
    action: Literal["insertMeasure"]
    params: Dict[str, Any]


class goToFinalMeasureAction(TypedDict):
    action: Literal["goToFinalMeasure"]
    params: Dict[str, Any]


class goToBeginningOfScoreAction(TypedDict):
    action: Literal["goToBeginningOfScore"]
    params: Dict[str, Any]


class setTimeSignatureParams(TypedDict):
    numerator: int
    denominator: int


class setTimeSignatureAction(TypedDict):
    action: Literal["setTimeSignature"]
    params: setTimeSignatureParams


class undoAction(TypedDict):
    action: Literal["undo"]
    params: Dict[str, Any]


class nextStaffAction(TypedDict):
    action: Literal["nextStaff"]
    params: Dict[str, Any]


class prevStaffAction(TypedDict):
    action: Literal["prevStaff"]
    params: Dict[str, Any]


class setTempoParams(TypedDict):
    bpm: float
    measure: NotRequired[int]


class setTempoAction(TypedDict):
    action: Literal["setTempo"]
    params: setTempoParams


class measureRangeParams(TypedDict):
    startMeasure: int
    endMeasure: NotRequired[int]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]


class selectMeasuresAction(TypedDict):
    action: Literal["selectMeasures"]
    params: measureRangeParams


class deleteMeasuresParams(TypedDict):
    startMeasure: int
    endMeasure: NotRequired[int]


class deleteMeasuresAction(TypedDict):
    action: Literal["deleteMeasures"]
    params: deleteMeasuresParams


class setRepeatBarlinesParams(TypedDict):
    startMeasure: int
    endMeasure: int
    playCount: NotRequired[int]
    clear: NotRequired[bool]


class setRepeatBarlinesAction(TypedDict):
    action: Literal["setRepeatBarlines"]
    params: setRepeatBarlinesParams


class addVoltaParams(TypedDict):
    startMeasure: int
    endMeasure: NotRequired[int]
    endings: NotRequired[List[int]]
    text: NotRequired[str]


class addVoltaAction(TypedDict):
    action: Literal["addVolta"]
    params: addVoltaParams


class colorRangeParams(TypedDict):
    startMeasure: int
    endMeasure: NotRequired[int]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]
    startBeat: NotRequired[float]
    endBeat: NotRequired[float]
    color: str
    voices: NotRequired[List[int]]


class colorRangeAction(TypedDict):
    action: Literal["colorRange"]
    params: colorRangeParams


class setStyleParams(TypedDict):
    key: str
    value: Any


class setStyleAction(TypedDict):
    action: Literal["setStyle"]
    params: setStyleParams


class addRehearsalMarkParams(TypedDict):
    measure: int
    text: str


class addRehearsalMarkAction(TypedDict):
    action: Literal["addRehearsalMark"]
    params: addRehearsalMarkParams


class removePartsParams(TypedDict):
    keepStaves: List[int]


class removePartsAction(TypedDict):
    action: Literal["removeParts"]
    params: removePartsParams


class addHighlightParams(TypedDict):
    startMeasure: int
    endMeasure: NotRequired[int]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]
    startBeat: NotRequired[float]
    endBeat: NotRequired[float]
    color: NotRequired[str]


class addHighlightAction(TypedDict):
    action: Literal["addHighlight"]
    params: addHighlightParams


class addLabelParams(TypedDict):
    measure: int
    text: str
    staff: NotRequired[int]
    background: NotRequired[str]
    border: NotRequired[str]


class addLabelAction(TypedDict):
    action: Literal["addLabel"]
    params: addLabelParams


class clearHighlightsParams(TypedDict):
    startMeasure: int
    endMeasure: NotRequired[int]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]
    kinds: NotRequired[List[Literal["highlights", "notes", "markings", "labels"]]]


class clearHighlightsAction(TypedDict):
    action: Literal["clearHighlights"]
    params: clearHighlightsParams


class highlightNotesParams(TypedDict):
    startMeasure: int
    endMeasure: NotRequired[int]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]
    startBeat: NotRequired[float]
    endBeat: NotRequired[float]
    pitches: NotRequired[List[int]]
    color: NotRequired[str]


class highlightNotesAction(TypedDict):
    action: Literal["highlightNotes"]
    params: highlightNotesParams


class highlightMarkingsParams(TypedDict):
    startMeasure: int
    endMeasure: NotRequired[int]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]
    types: NotRequired[List[str]]
    color: NotRequired[str]
    clear: NotRequired[bool]


class highlightMarkingsAction(TypedDict):
    action: Literal["highlightMarkings"]
    params: highlightMarkingsParams


class highlightSymbolsParams(TypedDict):
    startMeasure: int
    endMeasure: NotRequired[int]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]
    kinds: NotRequired[List[Literal["time_signatures", "repeat_barlines", "measure_repeats"]]]
    mode: NotRequired[Literal["highlight", "color"]]
    color: NotRequired[str]
    clear: NotRequired[bool]


class highlightSymbolsAction(TypedDict):
    action: Literal["highlightSymbols"]
    params: highlightSymbolsParams


class setMeasureNumberingParams(TypedDict):
    measure: int
    addToNumber: NotRequired[int]
    excludeFromCount: NotRequired[bool]


class setMeasureNumberingAction(TypedDict):
    action: Literal["setMeasureNumbering"]
    params: setMeasureNumberingParams


class numberAsPlayedParams(TypedDict):
    exclude: NotRequired[List[int]]


class numberAsPlayedAction(TypedDict):
    action: Literal["numberAsPlayed"]
    params: numberAsPlayedParams


class addTextParams(TypedDict):
    measure: int
    text: str
    staff: NotRequired[int]
    beat: NotRequired[float]
    fontSize: NotRequired[float]
    italic: NotRequired[bool]
    bold: NotRequired[bool]
    color: NotRequired[str]
    placement: NotRequired[Literal["above", "below"]]
    kind: NotRequired[Literal["staff", "expression"]]


class addTextAction(TypedDict):
    action: Literal["addText"]
    params: addTextParams


class addArticulationParams(TypedDict):
    startMeasure: int
    endMeasure: NotRequired[int]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]
    startBeat: NotRequired[float]
    endBeat: NotRequired[float]
    pitches: NotRequired[List[int]]
    symbol: Literal["half_open", "open", "closed", "accent", "marcato", "staccato", "tenuto"]


class addArticulationAction(TypedDict):
    action: Literal["addArticulation"]
    params: addArticulationParams


class removeArticulationsParams(TypedDict):
    startMeasure: int
    endMeasure: NotRequired[int]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]
    pitches: NotRequired[List[int]]
    symbols: NotRequired[List[str]]


class removeArticulationsAction(TypedDict):
    action: Literal["removeArticulations"]
    params: removeArticulationsParams


class ghostNotesParams(TypedDict):
    startMeasure: int
    endMeasure: NotRequired[int]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]
    pitches: NotRequired[List[int]]
    mode: NotRequired[Literal["list", "remove"]]


class ghostNotesAction(TypedDict):
    action: Literal["ghostNotes"]
    params: ghostNotesParams


class SectionCount(TypedDict):
    measure: int
    text: str


class addSectionCountsParams(TypedDict):
    counts: List[SectionCount]
    mode: NotRequired[Literal["label", "beside"]]
    color: NotRequired[str]
    fontSize: NotRequired[float]
    gap: NotRequired[float]
    clear: NotRequired[bool]
    clearAll: NotRequired[bool]


class addSectionCountsAction(TypedDict):
    action: Literal["addSectionCounts"]
    params: addSectionCountsParams


class beamOverRestsParams(TypedDict):
    startMeasure: int
    endMeasure: NotRequired[int]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]
    clear: NotRequired[bool]


class beamOverRestsAction(TypedDict):
    action: Literal["beamOverRests"]
    params: beamOverRestsParams


ActionSequence = List[
    getScoreAction | addNoteAction | addTieAction | addTiedNoteAction | addRestAction | addTupletAction |
    addLyricsAction | addInstrumentAction | setStaffMuteAction | 
    setInstrumentSoundAction | appendMeasureAction | deleteSelectionAction | 
    getCursorInfoAction | goToMeasureAction | nextElementAction | 
    prevElementAction | selectCurrentMeasureAction | insertMeasureAction | 
    goToFinalMeasureAction | goToBeginningOfScoreAction | setTimeSignatureAction | 
    undoAction | nextStaffAction | prevStaffAction | setTempoAction |
    selectMeasuresAction | deleteMeasuresAction | setRepeatBarlinesAction |
    addVoltaAction | colorRangeAction | setStyleAction | addRehearsalMarkAction |
    removePartsAction | addHighlightAction | addLabelAction | clearHighlightsAction |
    highlightNotesAction | highlightMarkingsAction | highlightSymbolsAction |
    setMeasureNumberingAction | numberAsPlayedAction | addTextAction | addArticulationAction |
    removeArticulationsAction | ghostNotesAction | beamOverRestsAction | addSectionCountsAction
]