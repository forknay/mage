extends CharacterBody3D

## Emitted once when the enemy first touches the player, not every frame.
signal player_reached
## Emitted once when the player gets away again.
signal player_lost

@export var speed := 3.0
## How far the enemy can see, in meters.
@export var sight_range := 20.0
## Full width of the vision cone, in degrees.
@export var sight_angle := 110.0
## Height of the eyes above the enemy's origin.
@export var eye_height := 1.5
## How long the enemy keeps chasing after losing sight of the player.
@export var memory_time := 3.0
## How fast the enemy turns to face where it is going, in radians per second.
@export var turn_speed := 6.0
## Horizontal distance that counts as touching the player.
@export var contact_distance := 1.2
## Colour shown while in contact with the player.
@export var contact_color := Color(0.9, 0.75, 0.2)

@onready var nav_agent: NavigationAgent3D = $NavigationAgent3D
@onready var mesh: MeshInstance3D = $MeshInstance3D

var player: Node3D
var time_since_seen := INF
var touching_player := false
var material: StandardMaterial3D
var idle_color: Color


func _ready() -> void:
	# Every instance of this scene shares one material, so it has to be
	# duplicated before tinting or all the enemies change colour together.
	material = mesh.get_active_material(0).duplicate()
	mesh.material_override = material
	idle_color = material.albedo_color

	player = get_tree().get_first_node_in_group("player")
	# The navigation map is only synced after the first physics frame, so any
	# path query before that returns garbage.
	set_physics_process(false)
	await get_tree().physics_frame
	set_physics_process(true)


func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity += get_gravity() * delta

	if can_see_player():
		time_since_seen = 0.0
		# Only refreshed while visible, so losing sight sends the enemy to the
		# spot where it last saw the player rather than to the player.
		nav_agent.target_position = player.global_position
	else:
		time_since_seen += delta

	if time_since_seen < memory_time and not nav_agent.is_navigation_finished():
		var next_location := nav_agent.get_next_path_position()
		var direction := next_location - global_position
		direction.y = 0.0
		direction = direction.normalized()
		velocity.x = direction.x * speed
		velocity.z = direction.z * speed
		face_direction(direction, delta)
	else:
		velocity.x = 0.0
		velocity.z = 0.0

	move_and_slide()
	update_contact()


func update_contact() -> void:
	if player == null:
		return

	# Horizontal only, so standing on a ledge above the player is not contact.
	var offset := player.global_position - global_position
	var distance := Vector2(offset.x, offset.z).length()

	if not touching_player and distance <= contact_distance:
		touching_player = true
		_on_player_reached()
	# The small margin stops the event firing every frame when the enemy is
	# jittering right at the edge of contact range.
	elif touching_player and distance > contact_distance + 0.3:
		touching_player = false
		_on_player_lost()


## Called once when the enemy reaches the player. Replace the colour swap with
## whatever the enemy should actually do: damage, an attack animation, etc.
func _on_player_reached() -> void:
	material.albedo_color = contact_color
	player_reached.emit()


## Called once when the player escapes contact range again.
func _on_player_lost() -> void:
	material.albedo_color = idle_color
	player_lost.emit()


func can_see_player() -> bool:
	if player == null:
		return false

	var eye := global_position + Vector3.UP * eye_height
	var to_player := player.global_position - eye
	if to_player.length() > sight_range:
		return false

	# -Z is forward in Godot. Compared on the horizontal plane so that looking
	# up or down a slope does not narrow the cone.
	var forward := -global_basis.z
	var flat_forward := Vector3(forward.x, 0.0, forward.z).normalized()
	var flat_to_player := Vector3(to_player.x, 0.0, to_player.z).normalized()
	if flat_forward.angle_to(flat_to_player) > deg_to_rad(sight_angle) / 2.0:
		return false

	# Anything solid in between blocks the view, including other enemies.
	var query := PhysicsRayQueryParameters3D.create(eye, player.global_position)
	query.exclude = [get_rid()]
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	return not hit.is_empty() and hit.collider == player


func face_direction(direction: Vector3, delta: float) -> void:
	if direction.is_zero_approx():
		return
	var target_yaw := atan2(-direction.x, -direction.z)
	rotation.y = rotate_toward(rotation.y, target_yaw, turn_speed * delta)
