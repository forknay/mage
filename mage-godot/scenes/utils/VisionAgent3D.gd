class_name VisionAgent3D
extends RayCast3D

## How far the enemy can see, in meters.
@export var sight_range: float = 20.0
## Full width of the vision cone, in degrees.
@export var sight_angle: float = 110.0
## Height of the eyes above the enemy's origin.
@export var eye_height: float = 1.5
## Layers the sight ray tests against. Deliberately excludes the enemy layer so
## that enemies never block each other's view of the player.
@export_flags_3d_physics var sight_mask: int = 1 | 2

var player: Node3D

# Called when the node enters the scene tree for the first time.
func _ready() -> void:
	player = get_tree().get_first_node_in_group("player")
	collision_mask = sight_mask
	position.y = eye_height   # raise the actual raycast origin to eye level

func can_see_player() -> bool:
	if player == null:
		return false

	var eye: Vector3 = global_position
	var to_player: Vector3 = player.global_position - eye
	if to_player.length() > sight_range:
		return false

	# -Z is forward in Godot. Compared on the horizontal plane so that looking
	# up or down a slope does not narrow the cone.
	var forward: Vector3 = -global_basis.z
	var flat_forward: Vector3 = Vector3(forward.x, 0.0, forward.z).normalized()
	var flat_to_player: Vector3 = Vector3(to_player.x, 0.0, to_player.z).normalized()
	if flat_forward.angle_to(flat_to_player) > deg_to_rad(sight_angle) / 2.0:
		return false

	# Aim Godot's native RayCast at the player
	target_position = to_local(player.global_position)
	force_raycast_update() # Update ray position immediately

	# Native collision check. No RIDs or manual physics queries needed.
	return is_colliding() and get_collider() == player
