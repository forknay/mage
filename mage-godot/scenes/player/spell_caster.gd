extends Node3D

## Freeform glyph drawing.
##
## Holding `draw` (left mouse) opens a canvas anchored in the air in front of
## the player and starts a stroke; the crosshair is the pen, so the player
## draws by looking. Releasing ends the stroke but keeps the canvas open, so a
## glyph can be several strokes. Pressing `cast` (right mouse) commits
## everything drawn, Escape throws it away.
##
## Movement is announced, not reached into: the player listens for
## draw_started / draw_ended and locks itself (conventions.md, ADR 0002 rule 1).

## The player is now drawing and should stop moving.
signal draw_started
## Emitted on both commit and cancel -- movement resumes either way.
signal draw_ended
## A finished glyph, batched by stroke, in $Q canvas coordinates.
signal glyph_drawn(strokes: Array[PackedVector2Array])

@export var camera: Camera3D
@export var projectile_scene: PackedScene

## Distance from the eye to the canvas, in metres.
@export var canvas_distance := 2.0
## How wide the full 800px canvas is at that distance, in metres. Smaller means
## a smaller head movement covers the canvas.
@export var canvas_width := 2.4
## Minimum canvas-pixel gap between recorded points.
@export var min_point_spacing := 4.0
## How far in front of the eye the placeholder bolt spawns, in metres. Must
## clear the player capsule or it dies on the frame it is born.
@export var muzzle_offset := 0.8

@onready var _overlay: DrawOverlay = $DrawOverlay

var _canvas := GlyphCanvas.new()
var _plane: GlyphPlane
## True from the first stroke until commit or cancel, not just while held.
var _drawing := false
## True only while the left button is down.
var _pen_down := false


func _ready() -> void:
	_canvas.min_point_spacing = min_point_spacing


func _unhandled_input(event: InputEvent) -> void:
	# The Escape rule (conventions.md): while the canvas is open, Escape
	# cancels the draw and nothing else. This node sits below the player in the
	# tree, so it sees the event first and can consume it.
	if _drawing and event.is_action_pressed("ui_cancel"):
		_cancel()
		get_viewport().set_input_as_handled()
		return

	# With the cursor free, a click exists only to recapture the mouse. Letting
	# it through to the player keeps that from also starting a stroke.
	if Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
		return

	if event.is_action_pressed("draw"):
		_press_pen()
		get_viewport().set_input_as_handled()
	elif event.is_action_released("draw") and _pen_down:
		_release_pen()
		get_viewport().set_input_as_handled()
	elif event.is_action_pressed("cast") and _drawing:
		_commit()
		get_viewport().set_input_as_handled()


func _process(_delta: float) -> void:
	if not _drawing:
		return
	# The canvas rides along with the eye, so a shove or a fall moves the whole
	# glyph instead of dragging a line across it.
	_plane.follow(camera.global_position)
	if _pen_down:
		_sample_pen()
	# Cheap enough to rebuild every frame, and it means the ribbon can never be
	# left behind by a canvas that moved.
	_overlay.render(_canvas)


func _press_pen() -> void:
	if not _drawing:
		_begin()
	_pen_down = true
	_canvas.begin_stroke()
	_sample_pen(true)


func _release_pen() -> void:
	_pen_down = false
	_canvas.end_stroke()


## Reads the crosshair against the canvas and records where it lands. Rays that
## point away from the canvas are simply not recorded, so turning right around
## mid-stroke leaves a gap rather than a spike across the whole glyph.
func _sample_pen(force := false) -> void:
	var eye := camera.global_transform
	var point = _plane.raycast(eye.origin, -eye.basis.z)
	if point != null:
		_canvas.add_point(point, force)


func _begin() -> void:
	_drawing = true
	_canvas.clear()
	_plane = GlyphPlane.anchored_at(camera.global_transform, canvas_distance, canvas_width)
	_overlay.begin(_plane)
	draw_started.emit()


func _commit() -> void:
	if _pen_down:
		_release_pen()
	var strokes := _canvas.take_strokes()
	_close()
	glyph_drawn.emit(strokes)

	# Recognition goes here: feed `strokes` to the GDScript port of
	# spell_recognizer_2 and resolve the SpellData it returns (ADR 0002). Until
	# that exists, every glyph fires the same placeholder bolt.
	_fire_placeholder()


func _cancel() -> void:
	_canvas.clear()
	_close()


func _close() -> void:
	_drawing = false
	_pen_down = false
	_overlay.clear()
	draw_ended.emit()


func _fire_placeholder() -> void:
	var eye := camera.global_transform
	var forward := -eye.basis.z
	var bolt: SpellProjectile = projectile_scene.instantiate()
	# Parented to the scene root, not the player, so it flies straight instead
	# of being carried around by whoever cast it.
	get_tree().current_scene.add_child(bolt)
	bolt.global_position = eye.origin + forward * muzzle_offset
	bolt.direction = forward
