class_name PlayerLookAt3D
extends RayCast3D

## Casts a forward ray from wherever it's attached (typically under the
## player's Camera3D) and reports what it's currently looking at.
## RayCast3D stops at the first collider, so occlusion (a wall in front
## of an interactable) is handled for free -- no manual exclude-lists.

func _ready() -> void:
	target_position = Vector3(0, 0, -3.0)


## The collider directly under the crosshair right now, or null if nothing
## is in range or in the way.
func get_looking_at() -> Object:
	return get_collider() if is_colliding() else null
