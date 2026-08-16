class_name SpellProjectile
extends Area3D

## Placeholder bolt fired on every commit until the recogniser exists.
##
## Moves itself instead of using physics so its speed is exact and it cannot be
## deflected by anything. It carries no effect: enemy.gd has no damage API yet,
## and per ADR 0002 damage belongs to resolve_spell(), not to the projectile.

@export var speed: float = 22.0
## Seconds before it gives up, so misses do not fly forever.
@export var lifetime: float = 4.0

## Set by the caster immediately after instantiation. Unit length, world space.
var direction: Vector3 = Vector3.FORWARD

var _age: float = 0.0


func _ready() -> void:
	body_entered.connect(_on_body_entered)


func _physics_process(delta: float) -> void:
	_age += delta
	if _age >= lifetime:
		queue_free()
		return
	global_position += direction * speed * delta


func _on_body_entered(_body: Node3D) -> void:
	queue_free()
