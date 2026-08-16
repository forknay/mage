class_name GlyphPlane
extends RefCounted

## The invisible sheet the player draws on.
##
## The sheet is carried by the eye, never re-derived from it, so it holds
## whatever offset it happens to have. What differs between the two modes is
## only which part of the eye's movement carries it:
##
## - **Pinned** (`anchor` held): translation only. Walking or falling takes the
##   sheet along, turning does not, so the crosshair sweeps across a sheet that
##   stands still in the world -- that sweep is the whole drawing input.
## - **Unpinned**: rotation as well. The sheet holds its position relative to
##   the view, so the caster can turn right around and carry a half-drawn glyph
##   with them.
##
## Because both modes carry rather than recentre, switching between them never
## moves the sheet: it stays exactly where it was on the frame the mode changed.
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

const CANVAS_SIZE: float = 800.0

## Rays grazing the sheet produce coordinates that run to infinity, so any pen
## ray more than this far off the normal is refused outright. cos(70 deg).
const MIN_FACING: float = 0.342

## Where the sheet is in the world. `basis.x` is canvas +x, `basis.y` is canvas
## -y (canvas y points down), and `basis.z` is the normal, facing the caster.
var transform: Transform3D
var pixels_per_meter: float

## Where the eye was at the last carry(), so the sheet can be moved by how far
## the eye moved rather than being placed relative to where it now is.
var _last_eye: Transform3D


## Hangs a sheet `distance` metres in front of the eye and square to it, sized
## so its full 800px width spans `width_meters` at that distance.
static func anchored_at(eye: Transform3D, distance: float, width_meters: float) -> GlyphPlane:
	var plane: GlyphPlane = GlyphPlane.new()
	plane.pixels_per_meter = CANVAS_SIZE / width_meters
	plane.transform = eye.translated_local(Vector3(0.0, 0.0, -distance))
	plane._last_eye = eye
	return plane


## Moves the sheet by however far the eye has moved since the last call --
## translation only while `pinned`, the full rigid motion otherwise.
func carry(eye: Transform3D, pinned: bool) -> void:
	if pinned:
		transform.origin += eye.origin - _last_eye.origin
	else:
		transform = eye * (_last_eye.affine_inverse() * transform)
		# Composing a transform onto itself every frame lets rounding skew the
		# basis, which would slowly shear the canvas.
		transform.basis = transform.basis.orthonormalized()
	_last_eye = eye


func to_canvas(world_point: Vector3) -> Vector2:
	var offset: Vector3 = world_point - transform.origin
	return Vector2(
		offset.dot(transform.basis.x) * pixels_per_meter + CANVAS_SIZE / 2.0,
		-offset.dot(transform.basis.y) * pixels_per_meter + CANVAS_SIZE / 2.0,
	)


func to_world(canvas_point: Vector2) -> Vector3:
	var x: float = (canvas_point.x - CANVAS_SIZE / 2.0) / pixels_per_meter
	var y: float = -(canvas_point.y - CANVAS_SIZE / 2.0) / pixels_per_meter
	return transform.origin + transform.basis.x * x + transform.basis.y * y


## Canvas coordinates where a ray crosses the sheet, or `null` when the ray
## points away from it or hits it at too shallow an angle to be meaningful.
##
## Typed `Variant` rather than `Vector2` on purpose: this is the one place in
## the codebase where "no answer" is a real result, and Vector2 has no null.
## Callers must null-check before use -- see spell_caster._sample_pen().
func raycast(from: Vector3, direction: Vector3) -> Variant:
	var normal: Vector3 = transform.basis.z
	var facing: float = direction.dot(normal)
	if facing > -MIN_FACING:
		return null
	var travel: float = (transform.origin - from).dot(normal) / facing
	if travel <= 0.0:
		return null
	return to_canvas(from + direction * travel)
