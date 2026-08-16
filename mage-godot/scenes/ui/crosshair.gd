class_name Crosshair
extends CanvasLayer

## The dot at the centre of the screen.
##
## Not decoration: the crosshair *is* the pen (see spell_caster.gd), so this
## dot is the only thing telling the player where the next stroke will land.
## It is drawn at the exact centre of the viewport, which is where the camera
## ray leaves -- put it anywhere else and the line would not follow the dot.
##
## Drawn rather than textured so it stays crisp at the 320x240 render
## resolution, where a texture would be resampled twice on its way to the
## screen.

## Radius in viewport pixels. The viewport is 320x240 and stretched, so this
## is roughly a quarter of what it will look like on a 1280x960 window.
@export var radius: float = 1.5:
	set(value):
		radius = value
		if _dot != null:
			_dot.queue_redraw()

@export var color: Color = Color(1.0, 1.0, 1.0, 0.85):
	set(value):
		color = value
		if _dot != null:
			_dot.queue_redraw()

## Dark ring under the dot, so it survives a bright wall or a torch right
## behind it. Zero disables it.
@export var outline_width: float = 1.0:
	set(value):
		outline_width = value
		if _dot != null:
			_dot.queue_redraw()

@export var outline_color: Color = Color(0.0, 0.0, 0.0, 0.5)

@onready var _dot: Control = $Dot


func _ready() -> void:
	# The Control is anchored to the centre with no size, so its own origin is
	# the centre of the screen and the drawing below needs no arithmetic.
	_dot.draw.connect(_on_dot_draw)
	_dot.queue_redraw()


func _on_dot_draw() -> void:
	if outline_width > 0.0:
		_dot.draw_circle(Vector2.ZERO, radius + outline_width, outline_color)
	_dot.draw_circle(Vector2.ZERO, radius, color)
