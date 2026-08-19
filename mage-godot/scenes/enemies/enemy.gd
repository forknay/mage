extends CharacterBody3D

## Emitted once when the enemy first touches the player, not every frame.
signal player_reached
## Emitted once when the player gets away again.
signal player_lost

## How fast the enemy sweeps its view while it has nowhere to go, in radians
## per second of sweep phase.
@export var scan_speed: float = 1.2
## How far to either side the enemy sweeps while scanning, in degrees.
@export var scan_arc: float = 140.0
@export var speed: float = 3.0
## How "res://scenes/level/"long the enemy keeps chasing after losing sight of the player.
@export var memory_time: float = 3.0
## How fast the enemy turns to face where it is going, in radians per second.
@export var turn_speed: float = 6.0
## Horizontal distance that counts as touching the player.
@export var contact_distance: float = 1.2


@onready var nav_agent: NavigationAgent3D = $NavigationAgent3D
@onready var vision_agent: VisionAgent3D = $VisionAgent3D

var player: Node3D
var time_since_seen: float = INF
var touching_player: bool = false
var scanning: bool = false
var scan_center_yaw: float = 0.0
var scan_phase: float = 0.0


func _ready() -> void:
	player = get_tree().get_first_node_in_group("player")
	# The navigation map is only synced after the first physics frame, so any
	# path query before that returns garbage.
	set_physics_process(false)
	await get_tree().physics_frame
	set_physics_process(true)


func _physics_process(delta: float) -> void:
	var sees_player: bool = vision_agent.can_see_player()
	if sees_player:
		time_since_seen = 0.0
		# Only refreshed while visible, so losing sight sends the enemy to the
		# spot where it last saw the player rather than to the player.
		nav_agent.target_position = player.global_position
	else:
		time_since_seen += delta

	# Vertical velocity is passed through untouched; avoidance steers x and z.
	var desired: Vector3 = Vector3(0.0, velocity.y, 0.0)
	var move_direction: Vector3 = Vector3.ZERO

	if time_since_seen < memory_time and not nav_agent.is_navigation_finished():
		var next_location: Vector3 = nav_agent.get_next_path_position()
		move_direction = next_location - global_position
		move_direction.y = 0.0
		move_direction = move_direction.normalized()
		desired.x = move_direction.x * speed
		desired.z = move_direction.z * speed

	# The vision cone is attached to the body's facing, so the enemy must keep
	# turning even when it has stopped walking. Otherwise its cone freezes in
	# whatever direction the last step happened to aim and the player can only
	# ever be re-acquired inside that one wedge.
	if sees_player:
		# Keep watching the player even after arriving, so that circling a
		# stationary enemy does not quietly drop out of its cone.
		var to_player: Vector3 = player.global_position - global_position
		face_direction(Vector3(to_player.x, 0.0, to_player.z).normalized(), delta)
		scanning = false
	elif not move_direction.is_zero_approx():
		face_direction(move_direction, delta)
		scanning = false
	else:
		scan(delta)

	if nav_agent.avoidance_enabled:
		# Hand the intended velocity to the avoidance solver. It answers on
		# velocity_computed, and the actual movement happens there. Submitted
		# even when standing still, so other agents still steer around this one.
		nav_agent.velocity = desired
	else:
		velocity = desired
		move_and_slide()
		update_contact()


func _on_navigation_agent_3d_velocity_computed(safe_velocity: Vector3) -> void:
	# Only the horizontal result is taken; gravity stays under our control so
	# the solver cannot lift the enemy off the floor.
	velocity.x = safe_velocity.x
	velocity.z = safe_velocity.z
	move_and_slide()
	update_contact()


func update_contact() -> void:
	if player == null:
		return

	# Horizontal only, so standing on a ledge above the player is not contact.
	var offset: Vector3 = player.global_position - global_position
	var distance: float = Vector2(offset.x, offset.z).length()

	if not touching_player and distance <= contact_distance:
		touching_player = true
		_on_player_reached()
	# The small margin stops the event firing every frame when the enemy is
	# jittering right at the edge of contact range.
	elif touching_player and distance > contact_distance + 0.3:
		touching_player = false
		_on_player_lost()


## Called once when the enemy reaches the player. Nothing happens here yet;
## `touching_player` is tracked so damage or an attack animation can hang off it.
func _on_player_reached() -> void:
	player_reached.emit()


## Called once when the player escapes contact range again.
func _on_player_lost() -> void:
	player_lost.emit()

func face_direction(direction: Vector3, delta: float) -> void:
	if direction.is_zero_approx():
		return
	var target_yaw: float = atan2(-direction.x, -direction.z)
	rotation.y = rotate_toward(rotation.y, target_yaw, turn_speed * delta)

## Sweeps the vision cone back and forth while the enemy is standing still, so
## that a lost player can be spotted again. The sweep is centred on whichever
## way the enemy was facing when it stopped.
func scan(delta: float) -> void:
	if not scanning:
		scanning = true
		scan_center_yaw = rotation.y
		scan_phase = 0.0
	scan_phase += scan_speed * delta
	rotation.y = scan_center_yaw + sin(scan_phase) * deg_to_rad(scan_arc) * 0.5
