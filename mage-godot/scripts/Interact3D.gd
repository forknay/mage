class_name InteractAgent3D
extends Node3D

## Reusable "press E to interact" prompt + input handling.
## Attach as a child of an interactable, connect to `interacted`.

signal interacted

@export var action: StringName = &"interact"
@export_multiline var prompt_text: String = "Press E to interact":
	set(value):
		prompt_text = value
		if _label != null:
			_label.text = value
@export var prompt_offset: Vector3 = Vector3(0, 0.6, 0)
@export var font_size: int = 24

## Only one agent shows its prompt at a time; claiming this kicks the previous one out.
static var _active: InteractAgent3D

var _look_agent: PlayerLookAt3D
var _label: Label3D
var _showing: bool = false
var _enabled: bool = true

## This object's own collider -- the prompt shows when the player's
## LookAtAgent3D is looking directly at it.
var _collision_object: CollisionObject3D


func _ready() -> void:
	var player: Node3D = get_tree().get_first_node_in_group("player")
	if player != null:
		_look_agent = _find_look_agent(player)
	_collision_object = _find_collision_object(get_parent())

	_label = Label3D.new()
	_label.text = prompt_text
	_label.font_size = font_size
	_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	_label.no_depth_test = true
	_label.position = prompt_offset
	_label.visible = false
	add_child(_label)


func _exit_tree() -> void:
	if _active == self:
		_active = null


func _unhandled_input(event: InputEvent) -> void:
	if _showing and event.is_action_pressed(action):
		get_viewport().set_input_as_handled()
		interacted.emit()


func _process(_delta: float) -> void:
	_set_showing(_enabled and _can_interact())


## Turns the prompt off entirely, e.g. after a chest has been opened.
func set_enabled(value: bool) -> void:
	_enabled = value
	if not value:
		_set_showing(false)


func _find_look_agent(node: Node) -> PlayerLookAt3D:
	if node is PlayerLookAt3D:
		return node
	for child: Node in node.get_children():
		var found: PlayerLookAt3D = _find_look_agent(child)
		if found != null:
			return found
	return null


func _find_collision_object(node: Node) -> CollisionObject3D:
	if node is CollisionObject3D:
		return node
	for child: Node in node.get_children():
		var found: CollisionObject3D = _find_collision_object(child)
		if found != null:
			return found
	return null


func _can_interact() -> bool:
	if _collision_object == null or _look_agent == null:
		return false
	return _look_agent.get_looking_at() == _collision_object


func _set_showing(value: bool) -> void:
	if value == _showing:
		return
	_showing = value

	if value:
		if _active != null and _active != self:
			_active._force_hide()
		_active = self
	elif _active == self:
		_active = null

	_label.visible = value


func _force_hide() -> void:
	_showing = false
	_label.visible = false
