class_name GlyphCanvas
extends RefCounted

## Storage for one glyph: an ordered list of strokes, each an ordered list of
## 2D canvas points.
##
## Deliberately knows nothing about 3D, input, or rendering -- it is the raw
## material the recogniser will consume, and the shape it stores is the shape
## `spell_recognizer_2` expects (points batched by stroke, `stroke_id` implied
## by position in the list).

## Strokes shorter than this are dropped on end_stroke(). A stroke of one point
## has no direction and no length, and would divide by zero in $Q's
## resampling. Tapping to place a dot therefore needs a small wiggle for now.
const MIN_STROKE_POINTS := 2

## Finished strokes, oldest first. The stroke in progress is kept separate
## until it ends -- see current_stroke().
var strokes: Array[PackedVector2Array] = []

## Minimum canvas-pixel gap between consecutive recorded points. Sampling runs
## every frame, so without this a slow hand deposits hundreds of duplicates.
var min_point_spacing := 4.0

var _current := PackedVector2Array()
var _stroke_open := false

## Instance of your C++ Spell Engine
var spell_engine: GodotSpellEngine = GodotSpellEngine.new()

func begin_stroke() -> void:
	_current = PackedVector2Array()
	_stroke_open = true


## Records `point` unless it is too close to the previous one. `force` bypasses
## that check, for the first point of a stroke. Returns whether it was kept.
func add_point(point: Vector2, force := false) -> bool:
	if not _stroke_open:
		return false
	if not force and not _current.is_empty():
		if _current[-1].distance_to(point) < min_point_spacing:
			return false
	_current.append(point)
	return true


func end_stroke() -> void:
	if _stroke_open and _current.size() >= MIN_STROKE_POINTS:
		strokes.append(_current)
		print("allo")
		spell_engine.add_stroke(_current)
		
	_current = PackedVector2Array()
	_stroke_open = false


## The stroke being drawn right now, empty when the pen is up. Rendering needs
## it; the recogniser never sees it, because an unfinished stroke is not part
## of the glyph yet.
func current_stroke() -> PackedVector2Array:
	return _current


## Hands the finished strokes to the caller and resets the canvas, so the
## caller owns the only copy and cannot be surprised by a later clear().
func take_strokes() -> Array[PackedVector2Array]:
	var finished := strokes
	strokes = []
	_current = PackedVector2Array()
	_stroke_open = false
	return finished


func clear() -> void:
	strokes = []
	_current = PackedVector2Array()
	_stroke_open = false
	spell_engine.clear()
