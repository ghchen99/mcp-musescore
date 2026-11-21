"""TypedDict definitions for MuseScore MCP action sequences.

These types are the one list of the steps processSequence takes: the tool's
schema and description, the bars it turns into positions, and the checks on the
plugin and the mock all come from them.
"""

from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    NotRequired,
    Tuple,
    TypedDict,
    cast,
    get_args,
    get_origin,
    get_type_hints,
    is_typeddict,
)

from ..bars import Bar


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
    measure: Bar


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


class nextStaffAction(TypedDict):
    action: Literal["nextStaff"]
    params: Dict[str, Any]


class prevStaffAction(TypedDict):
    action: Literal["prevStaff"]
    params: Dict[str, Any]


class setTempoParams(TypedDict):
    bpm: float
    measure: NotRequired[Bar]


class setTempoAction(TypedDict):
    action: Literal["setTempo"]
    params: setTempoParams


class measureRangeParams(TypedDict):
    startMeasure: Bar
    endMeasure: NotRequired[Bar]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]


class selectMeasuresAction(TypedDict):
    action: Literal["selectMeasures"]
    params: measureRangeParams


class deleteMeasuresParams(TypedDict):
    startMeasure: Bar
    endMeasure: NotRequired[Bar]


class deleteMeasuresAction(TypedDict):
    action: Literal["deleteMeasures"]
    params: deleteMeasuresParams


class setRepeatBarlinesParams(TypedDict):
    startMeasure: Bar
    endMeasure: Bar
    playCount: NotRequired[int]
    clear: NotRequired[bool]


class setRepeatBarlinesAction(TypedDict):
    action: Literal["setRepeatBarlines"]
    params: setRepeatBarlinesParams


class addVoltaParams(TypedDict):
    startMeasure: Bar
    endMeasure: NotRequired[Bar]
    endings: NotRequired[List[int]]
    text: NotRequired[str]


class addVoltaAction(TypedDict):
    action: Literal["addVolta"]
    params: addVoltaParams


class colorRangeParams(TypedDict):
    startMeasure: Bar
    endMeasure: NotRequired[Bar]
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
    measure: Bar
    text: str


class addRehearsalMarkAction(TypedDict):
    action: Literal["addRehearsalMark"]
    params: addRehearsalMarkParams


class addMarkerParams(TypedDict):
    measure: Bar
    marker: Literal[
        "segno",
        "coda",
        "to_coda",
        "to_coda_symbol",
        "fine",
        "dc",
        "dc_al_fine",
        "dc_al_coda",
        "ds",
        "ds_al_fine",
        "ds_al_coda",
    ]


class addMarkerAction(TypedDict):
    action: Literal["addMarker"]
    params: addMarkerParams


class setChordSymbolParams(TypedDict):
    measure: Bar
    chord: str
    beat: NotRequired[float]
    staff: NotRequired[int]


class setChordSymbolAction(TypedDict):
    action: Literal["setChordSymbol"]
    params: setChordSymbolParams


class moveChordSymbolParams(TypedDict):
    measure: Bar
    toMeasure: Bar
    beat: NotRequired[float]
    toBeat: NotRequired[float]
    staff: NotRequired[int]


class moveChordSymbolAction(TypedDict):
    action: Literal["moveChordSymbol"]
    params: moveChordSymbolParams


class addBreakParams(TypedDict):
    measure: Bar
    kind: NotRequired[Literal["line", "page", "section"]]


class addBreakAction(TypedDict):
    action: Literal["addBreak"]
    params: addBreakParams


class setMeasuresPerSystemParams(TypedDict):
    startMeasure: Bar
    endMeasure: NotRequired[Bar]
    perSystem: int
    method: NotRequired[Literal["locks", "breaks"]]


class setMeasuresPerSystemAction(TypedDict):
    action: Literal["setMeasuresPerSystem"]
    params: setMeasuresPerSystemParams


ElementKind = Literal[
    "chord_symbols",
    "markers",
    "jumps",
    "texts",
    "labels",
    "rehearsal_marks",
    "tempo",
]


class findElementsParams(TypedDict):
    startMeasure: Bar
    endMeasure: NotRequired[Bar]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]
    kinds: NotRequired[List[ElementKind]]
    beat: NotRequired[float]
    contains: NotRequired[str]
    exact: NotRequired[bool]


class findElementsAction(TypedDict):
    action: Literal["findElements"]
    params: findElementsParams


class setPropertiesParams(findElementsParams):
    placement: NotRequired[Literal["above", "below"]]
    align: NotRequired[Literal["left", "center", "right"]]
    fontSize: NotRequired[float]
    offset: NotRequired[List[float]]
    moveBy: NotRequired[List[float]]
    reset: NotRequired[
        List[Literal["placement", "align", "fontSize", "offset"]]
    ]


class setPropertiesAction(TypedDict):
    action: Literal["setProperties"]
    params: setPropertiesParams


class setMeasureStretchParams(TypedDict):
    startMeasure: Bar
    endMeasure: NotRequired[Bar]
    stretch: float


class setMeasureStretchAction(TypedDict):
    action: Literal["setMeasureStretch"]
    params: setMeasureStretchParams


AnnotationKind = Literal[
    "texts",
    "labels",
    "rehearsal_marks",
    "tempo",
    "voltas",
    "markers",
    "jumps",
    "chord_symbols",
    "breaks",
]


class removeAnnotationsParams(TypedDict):
    startMeasure: Bar
    endMeasure: NotRequired[Bar]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]
    kinds: NotRequired[List[AnnotationKind]]
    contains: NotRequired[str]
    exact: NotRequired[bool]
    beat: NotRequired[float]


class removeAnnotationsAction(TypedDict):
    action: Literal["removeAnnotations"]
    params: removeAnnotationsParams


class removePartsParams(TypedDict):
    keepStaves: List[int]


class removePartsAction(TypedDict):
    action: Literal["removeParts"]
    params: removePartsParams


class addHighlightParams(TypedDict):
    startMeasure: Bar
    endMeasure: NotRequired[Bar]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]
    startBeat: NotRequired[float]
    endBeat: NotRequired[float]
    color: NotRequired[str]


class addHighlightAction(TypedDict):
    action: Literal["addHighlight"]
    params: addHighlightParams


class addLabelParams(TypedDict):
    measure: Bar
    text: str
    staff: NotRequired[int]
    background: NotRequired[str]
    border: NotRequired[str]


class addLabelAction(TypedDict):
    action: Literal["addLabel"]
    params: addLabelParams


class clearHighlightsParams(TypedDict):
    startMeasure: Bar
    endMeasure: NotRequired[Bar]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]
    kinds: NotRequired[
        List[Literal["highlights", "notes", "markings", "labels"]]
    ]


class clearHighlightsAction(TypedDict):
    action: Literal["clearHighlights"]
    params: clearHighlightsParams


class highlightNotesParams(TypedDict):
    startMeasure: Bar
    endMeasure: NotRequired[Bar]
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
    startMeasure: Bar
    endMeasure: NotRequired[Bar]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]
    types: NotRequired[List[str]]
    color: NotRequired[str]
    clear: NotRequired[bool]


class highlightMarkingsAction(TypedDict):
    action: Literal["highlightMarkings"]
    params: highlightMarkingsParams


class highlightSymbolsParams(TypedDict):
    startMeasure: Bar
    endMeasure: NotRequired[Bar]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]
    kinds: NotRequired[
        List[Literal["time_signatures", "repeat_barlines", "measure_repeats"]]
    ]
    mode: NotRequired[Literal["highlight", "color"]]
    color: NotRequired[str]
    clear: NotRequired[bool]


class highlightSymbolsAction(TypedDict):
    action: Literal["highlightSymbols"]
    params: highlightSymbolsParams


class setMeasureNumberingParams(TypedDict):
    measure: Bar
    addToNumber: NotRequired[int]
    excludeFromCount: NotRequired[bool]


class setMeasureNumberingAction(TypedDict):
    action: Literal["setMeasureNumbering"]
    params: setMeasureNumberingParams


class numberAsPlayedParams(TypedDict):
    exclude: NotRequired[List[Bar]]
    reset: NotRequired[bool]


class numberAsPlayedAction(TypedDict):
    action: Literal["numberAsPlayed"]
    params: numberAsPlayedParams


class addTextParams(TypedDict):
    measure: Bar
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
    startMeasure: Bar
    endMeasure: NotRequired[Bar]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]
    startBeat: NotRequired[float]
    endBeat: NotRequired[float]
    pitches: NotRequired[List[int]]
    symbol: Literal[
        "half_open", "open", "closed", "accent", "marcato", "staccato", "tenuto"
    ]


class addArticulationAction(TypedDict):
    action: Literal["addArticulation"]
    params: addArticulationParams


class removeArticulationsParams(TypedDict):
    startMeasure: Bar
    endMeasure: NotRequired[Bar]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]
    pitches: NotRequired[List[int]]
    symbols: NotRequired[List[str]]


class removeArticulationsAction(TypedDict):
    action: Literal["removeArticulations"]
    params: removeArticulationsParams


class ghostNotesParams(TypedDict):
    startMeasure: Bar
    endMeasure: NotRequired[Bar]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]
    pitches: NotRequired[List[int]]
    mode: NotRequired[Literal["list", "remove"]]


class ghostNotesAction(TypedDict):
    action: Literal["ghostNotes"]
    params: ghostNotesParams


class SectionCount(TypedDict):
    measure: Bar
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
    startMeasure: Bar
    endMeasure: NotRequired[Bar]
    startStaff: NotRequired[int]
    endStaff: NotRequired[int]
    clear: NotRequired[bool]


class beamOverRestsAction(TypedDict):
    action: Literal["beamOverRests"]
    params: beamOverRestsParams


ActionSequence = List[
    getScoreAction
    | addNoteAction
    | addTieAction
    | addTiedNoteAction
    | addRestAction
    | addTupletAction
    | addLyricsAction
    | addInstrumentAction
    | setStaffMuteAction
    | setInstrumentSoundAction
    | appendMeasureAction
    | deleteSelectionAction
    | getCursorInfoAction
    | goToMeasureAction
    | nextElementAction
    | prevElementAction
    | selectCurrentMeasureAction
    | insertMeasureAction
    | goToFinalMeasureAction
    | goToBeginningOfScoreAction
    | setTimeSignatureAction
    | nextStaffAction
    | prevStaffAction
    | setTempoAction
    | selectMeasuresAction
    | deleteMeasuresAction
    | setRepeatBarlinesAction
    | addVoltaAction
    | colorRangeAction
    | setStyleAction
    | addRehearsalMarkAction
    | addMarkerAction
    | setChordSymbolAction
    | moveChordSymbolAction
    | addBreakAction
    | setMeasuresPerSystemAction
    | findElementsAction
    | setPropertiesAction
    | setMeasureStretchAction
    | removeAnnotationsAction
    | removePartsAction
    | addHighlightAction
    | addLabelAction
    | clearHighlightsAction
    | highlightNotesAction
    | highlightMarkingsAction
    | highlightSymbolsAction
    | setMeasureNumberingAction
    | numberAsPlayedAction
    | addTextAction
    | addArticulationAction
    | removeArticulationsAction
    | ghostNotesAction
    | beamOverRestsAction
    | addSectionCountsAction
]


def _step_params(step: type) -> Tuple[str, object]:
    hints = get_type_hints(step)
    return get_args(hints["action"])[0], hints["params"]


SEQUENCE_STEPS: Dict[str, object] = dict(
    _step_params(step) for step in get_args(get_args(ActionSequence)[0])
)
"""Each step's action name and the type of its params."""


def with_positions(
    value: object, kind: object, position: Callable[[Bar], int]
) -> object:
    """Copy a step's params, turning every value typed Bar into a position.

    Args:
        value (object): The params, or a value inside them.
        kind (object): The value's type, from SEQUENCE_STEPS.
        position (Callable[[Bar], int]): Turns a bar as printed into a position.

    Returns:
        value (object): A copy with the bars as positions; other values as they
            were.
    """
    if value is None:
        return value
    if kind == Bar:
        return position(cast(Bar, value))
    if get_origin(kind) in (list, List) and isinstance(value, list):
        (item,) = get_args(kind)
        return [with_positions(v, item, position) for v in value]
    if is_typeddict(kind) and isinstance(value, dict):
        fields = get_type_hints(kind)
        return {
            k: with_positions(v, fields[k], position) if k in fields else v
            for k, v in value.items()
        }
    return value
