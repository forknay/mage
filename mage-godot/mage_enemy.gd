extends CharacterBody3D

@onready var vision_agent: VisionAgent3D = $VisionAgent3D

var player: Node3D
var path_follow: PathFollow3D


@export var speed: int = 1
## How far the enemy can see, in meters.

func _ready() -> void:
	player = get_tree().get_first_node_in_group("player")
	path_follow = get_parent() as PathFollow3D
	# The navigation map is only synced after the first physics frame, so any
	# path query before that returns garbage.
	set_physics_process(false)
	await get_tree().physics_frame
	set_physics_process(true)

func _physics_process(delta: float) -> void:
	# Add the gravity.
	if not is_on_floor():
		velocity += get_gravity() * delta
		
	var sees_player: bool = vision_agent.can_see_player()
	if !sees_player:
		path_follow.progress += speed * delta
		
