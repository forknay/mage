class_name DrawOverlay
extends MeshInstance3D

## Renders the glyph being drawn as a ribbon of geometry sitting on the
## GlyphPlane in world space.
##
## The vertices are built from the recorded canvas points, never from the raw
## pen position, so what the player sees is exactly what the recogniser will
## get. The node is `top_level` and its transform is pinned to identity: the
## player's body yaws while drawing, and the glyph must not yaw with it.

## Half-thickness of the stroke, in metres.
@export var stroke_radius := 0.02
@export var stroke_color := Color(0.55, 0.85, 1.0)
## Colour of the stroke currently under the pen, so it reads as "live".
@export var active_color := Color(1.0, 0.95, 0.7)

var _plane: GlyphPlane
var _mesh := ImmediateMesh.new()
var _material: StandardMaterial3D
var _active_material: StandardMaterial3D


func _ready() -> void:
	mesh = _mesh
	_material = _make_material(stroke_color)
	_active_material = _make_material(active_color)


func _make_material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	# Unshaded so the glyph reads the same in every corner of a dark level,
	# double-sided because the ribbon is seen from both faces as the head turns.
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.albedo_color = color
	return material


## Attaches the overlay to a freshly anchored canvas.
func begin(plane: GlyphPlane) -> void:
	_plane = plane
	global_transform = Transform3D.IDENTITY
	_mesh.clear_surfaces()


func clear() -> void:
	_plane = null
	_mesh.clear_surfaces()


func render(canvas: GlyphCanvas) -> void:
	_mesh.clear_surfaces()
	if _plane == null:
		return
	for stroke in canvas.strokes:
		_add_stroke(stroke, _material)
	_add_stroke(canvas.current_stroke(), _active_material)


func _add_stroke(stroke: PackedVector2Array, material: StandardMaterial3D) -> void:
	if stroke.size() < 2:
		return

	_mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES, material)
	for i in stroke.size() - 1:
		var a := _plane.to_world(stroke[i])
		var b := _plane.to_world(stroke[i + 1])
		var along := b - a
		if along.is_zero_approx():
			continue
		along = along.normalized()

		# Two quads in a cross section rather than one flat strip. A flat
		# ribbon collapses to a sliver as the head turns away from the canvas;
		# the perpendicular quad keeps the stroke solid from any angle, which
		# is what sells it as drawn in the air rather than pasted on a plane.
		var side := along.cross(_plane.normal).normalized() * stroke_radius
		var deep := _plane.normal * stroke_radius
		_add_quad(a - side, b - side, b + side, a + side)
		_add_quad(a - deep, b - deep, b + deep, a + deep)
	_mesh.surface_end()


## Winding is irrelevant here -- the material is double-sided.
func _add_quad(a: Vector3, b: Vector3, c: Vector3, d: Vector3) -> void:
	_mesh.surface_add_vertex(a)
	_mesh.surface_add_vertex(b)
	_mesh.surface_add_vertex(c)
	_mesh.surface_add_vertex(a)
	_mesh.surface_add_vertex(c)
	_mesh.surface_add_vertex(d)
