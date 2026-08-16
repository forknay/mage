extends Node3D

## Emitted once, the first time the player opens this chest.
signal opened

## How close the player has to be to interact, in metres. Measured on the
## horizontal plane only, so standing on a ledge above a chest does not count.
@export var interact_range := 2.0

@onready var model: Node3D = $Model

var player: Node3D
var is_open := false


func _ready() -> void:
	player = get_tree().get_first_node_in_group("player")


func _unhandled_input(event: InputEvent) -> void:
	if is_open or player == null or not event.is_action_pressed("interact"):
		return
	if not player_in_range():
		return
	# Claiming the event stops a second chest behind this one from opening on the
	# same key press.
	get_viewport().set_input_as_handled()
	open()


func player_in_range() -> bool:
	var offset := player.global_position - global_position
	return Vector2(offset.x, offset.z).length() <= interact_range


## Placeholder: for now the chest just vanishes, which is enough to see that the
## interaction fired. Replace the body of this with the lid animation, loot, etc.
func open() -> void:
	is_open = true
	model.visible = false
	opened.emit()
