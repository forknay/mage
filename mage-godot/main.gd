extends Node3D

## Rebuilds the navigation mesh from the GridMap as it actually is when the
## level loads, so extending the dungeon does not need a manual bake.
@export var bake_on_start := true

@onready var navigation_region: NavigationRegion3D = $NavigationRegion3D


func _ready() -> void:
	if bake_on_start:
		# Baked on this thread on purpose, so the mesh is complete before any
		# enemy resumes. The server still needs a few more physics frames to
		# sync it, during which path queries come back empty; agents re-query
		# every frame, so they simply stand still until it lands.
		navigation_region.bake_navigation_mesh(false)


## Call this after changing the GridMap during play. Bakes on a worker thread so
## the frame does not hitch; enemies keep pathing on the previous mesh until the
## new one lands, which takes a few frames.
func rebake_navigation() -> void:
	if navigation_region.is_baking():
		return
	navigation_region.bake_navigation_mesh()
