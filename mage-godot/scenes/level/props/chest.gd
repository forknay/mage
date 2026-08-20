extends Node3D

signal opened

@onready var model: Node3D = $Model
@onready var interact_agent: InteractAgent3D = $Interact3D

var is_open: bool = false


func _ready() -> void:
	interact_agent.interacted.connect(open)


func open() -> void:
	is_open = true
	interact_agent.set_enabled(false)
	model.visible = false
	opened.emit()
