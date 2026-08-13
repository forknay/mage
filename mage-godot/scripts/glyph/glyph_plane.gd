class_name GlyphPlane
extends RefCounted

## The invisible sheet the player draws on.
##
## Its **orientation** is frozen the moment a draw begins, so turning the head
## sweeps the crosshair across it instead of dragging it along -- that rotation
## is the whole input. Its **position** follows the head (see follow()), so
## being shoved, landing a fall, or settling under gravity carries the sheet
## along rather than smearing a line across the glyph.
##
## Owns both directions of the world <-> canvas mapping; nothing else may
## reimplement either one, or the recorded strokes and the rendered ribbon
## drift apart.
##
## Canvas coordinates are CANVAS_SIZE x CANVAS_SIZE pixels with the origin at
## the top-left and **y increasing downward** -- the convention
## `spell_recognizer_2` expects. Getting this backwards silently mirrors every
## glyph, and $Q is orientation-sensitive, so it would misrecognise rather than
## fail loudly. The size is a scale reference, not a clip region: a wide turn
## puts points outside the box, which is harmless because $Q normalises by the
## bounding box anyway.

const CANVAS_SIZE := 800.0

## Rays grazing the canvas produce coordinates that run to infinity, so any
## pen ray more than this far off the normal is refused outright. cos(70 deg).
const MIN_FACING := 0.342

## World position of the canvas centre, i.e. canvas (400, 400).
var origin: Vector3
## Unit vector along +x on the canvas.
var right: Vector3
## Unit vector along -y on the canvas (canvas y points down).
var up: Vector3
## Unit vector pointing back at the caster.
var normal: Vector3
var pixels_per_meter: float
## How far in front of the eye the sheet hangs, in metres.
var distance: float


## Places a canvas `distance` metres in front of the eye, sized so the full
## 800px width spans `width_meters` at that distance.
static func anchored_at(eye: Transform3D, distance: float, width_meters: float) -> GlyphPlane:
	var forward := -eye.basis.z
	var plane := GlyphPlane.new()
	plane.right = eye.basis.x.normalized()
	plane.up = eye.basis.y.normalized()
	plane.normal = -forward.normalized()
	plane.pixels_per_meter = CANVAS_SIZE / width_meters
	plane.distance = distance
	plane.follow(eye.origin)
	return plane


## Carries the sheet to wherever the eye is now, keeping its orientation. Every
## already-recorded point keeps its canvas coordinates and simply moves with
## the sheet, so the glyph translates as a rigid whole.
func follow(eye_origin: Vector3) -> void:
	origin = eye_origin - normal * distance


func to_canvas(world_point: Vector3) -> Vector2:
	var offset := world_point - origin
	return Vector2(
		offset.dot(right) * pixels_per_meter + CANVAS_SIZE / 2.0,
		-offset.dot(up) * pixels_per_meter + CANVAS_SIZE / 2.0,
	)


func to_world(canvas_point: Vector2) -> Vector3:
	var x := (canvas_point.x - CANVAS_SIZE / 2.0) / pixels_per_meter
	var y := -(canvas_point.y - CANVAS_SIZE / 2.0) / pixels_per_meter
	return origin + right * x + up * y


## Canvas coordinates where a ray crosses the sheet, or `null` when the ray
## points away from it or hits it at too shallow an angle to be meaningful.
func raycast(from: Vector3, direction: Vector3) -> Variant:
	var facing := direction.dot(normal)
	if facing > -MIN_FACING:
		return null
	var distance := (origin - from).dot(normal) / facing
	if distance <= 0.0:
		return null
	return to_canvas(from + direction * distance)
