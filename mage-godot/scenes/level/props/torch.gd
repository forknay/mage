extends Node3D

## How far the light dims and brightens, as a fraction of its resting energy.
@export_range(0.0, 1.0) var flicker_depth: float = 0.22
## Roughly how many times a second the flame gutters.
@export var flicker_speed: float = 3.0
## How far the light drifts from the flame, in metres. This is what makes cast
## shadows crawl, and the effect is amplified by the distance from the caster to
## whatever it lands on, so a couple of centimetres goes a long way. Set to 0 to
## hold the shadows perfectly still and flicker on brightness alone.
@export var flicker_sway: float = 0.005

@onready var light: OmniLight3D = $Light

var noise: FastNoiseLite = FastNoiseLite.new()
var base_energy: float = 0.0
var base_position: Vector3 = Vector3.ZERO
var time: float = 0.0


func _ready() -> void:
	base_energy = light.light_energy
	base_position = light.position

	noise.noise_type = FastNoiseLite.TYPE_SIMPLEX
	# The default frequency of 0.01 would need a thousand seconds to cross the
	# field once. At 1.0 a step of flicker_speed per second is one flicker.
	noise.frequency = 1.0
	# Both the seed and the starting offset are randomised so that a corridor
	# lined with torches does not pulse in unison.
	noise.seed = randi()
	time = randf() * 1000.0


func _process(delta: float) -> void:
	time += delta * flicker_speed

	# Two octaves: a slow swell with a faster tremor over it. A single octave
	# reads as a sine wave rather than as fire.
	var swell: float = noise.get_noise_1d(time)
	var tremor: float = noise.get_noise_1d(time * 3.7 + 100.0)
	var amount: float = swell * 0.7 + tremor * 0.3

	light.light_energy = maxf(0.0, base_energy * (1.0 + amount * flicker_depth))
	light.position = base_position + Vector3(
		noise.get_noise_1d(time * 0.8 + 300.0),
		noise.get_noise_1d(time * 0.8 + 600.0),
		0.0
	) * flicker_sway
