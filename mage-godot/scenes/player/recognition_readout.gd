class_name RecognitionReadout
extends CanvasLayer

## Names the features the recogniser found, on screen, as the glyph is drawn.
##
## The engine already logs every recognition to the terminal; this puts the
## same answer where the player is actually looking, so a testing session never
## has to alt-tab to read it. Purely a development aid: nothing in the game
## reads it back, and deleting the node is enough to remove it.
##
## The text is temporary by design -- it holds long enough to read, then fades,
## so a stale name is never left sitting over the next glyph.

## Seconds the text stays at full strength after the last update.
@export var hold_seconds: float = 2.0
## Seconds it takes to fade out after that.
@export var fade_seconds: float = 1.0
## Shown when a finished stroke was recognised as nothing at all, so silence
## always means "the readout is not running", never "the engine found nothing".
@export var empty_text: String = "(nothing recognised)"

@onready var _label: Label = $Label

## Seconds since the last update, counted only while text is showing.
var _age: float = 0.0


func _ready() -> void:
	_label.text = ""
	_label.modulate.a = 0.0


func _process(delta: float) -> void:
	if _label.text.is_empty():
		return

	_age += delta
	var fading: float = _age - hold_seconds
	if fading <= 0.0:
		_label.modulate.a = 1.0
	elif fading >= fade_seconds:
		_label.text = ""
		_label.modulate.a = 0.0
	else:
		_label.modulate.a = 1.0 - fading / fade_seconds


## Names every feature on the canvas, one per line, with the score it was
## recognised at. `features` is what GlyphCanvas.recognized_features() returns;
## the engine has already dropped anything that failed its template's
## min_score, so everything passed in is worth showing.
func show_features(features: Array) -> void:
	var lines: PackedStringArray = PackedStringArray()
	for feature: Dictionary in features:
		var feature_name: String = feature.get("name", "?")
		var score: float = feature.get("score", 0.0)
		lines.append("%s  %.2f" % [feature_name, score])

	if lines.is_empty():
		show_message(empty_text)
	else:
		show_message("\n".join(lines))


## Puts arbitrary text up under the same hold-and-fade rules.
func show_message(text: String) -> void:
	_label.text = text
	_label.modulate.a = 1.0
	_age = 0.0
