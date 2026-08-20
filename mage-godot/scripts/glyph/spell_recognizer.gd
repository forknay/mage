class_name SpellRecognizer
extends RefCounted

## The glyph recogniser, with the native C++ engine made optional.
##
## `GodotSpellEngine` is a Jenova nested extension and Jenova has no macOS
## build, so a Mac cannot compile or load it. Naming that class in GDScript
## there is a parse error, and a parse error in `glyph_canvas.gd` takes
## `spell_caster.gd` and the whole player scene down with it -- the game
## would be unopenable on a machine that only wanted to work on movement.
##
## So nothing outside this file names the native class. This wraps whichever
## backend is available behind the four calls the game makes, falling back to
## a stub that recognises nothing. Drawing, the overlay, casting and every
## other system then behave normally; only the recognised-feature list is
## empty. Callers do not branch on which backend is live -- `is_native()`
## exists for diagnostics, not for control flow.
##
## Calls into the backend go through `Object.call()` rather than
## `engine.add_stroke(...)`, because the two backends share no base class
## (one is a GDExtension class, the other GDScript) and a direct call would
## be an unsafe method access, which `project.godot` makes an error.
## `conventions.md` bans silencing that with `@warning_ignore`; `call()` is
## statically typed, so this is the honest way to write it.

enum Backend {
	## The C++ engine, registered by the Jenova module. Windows and Linux.
	NATIVE,
	## Accepts strokes, recognises nothing. Anywhere Jenova cannot build.
	STUB,
}

## The class the Jenova module registers. Named here and nowhere else.
const NATIVE_CLASS: StringName = &"GodotSpellEngine"

## Overrides the automatic choice. `stub` forces the fallback even where the
## native engine is available -- for checking that the rest of the game still
## runs without it. `native` refuses the silent fallback: it logs an error
## instead of letting a failed Jenova build look like a recogniser that
## suddenly matches nothing.
const BACKEND_ENV_VAR: String = "MAGE_SPELL_ENGINE"

## Which backend this instance is talking to. Set once, at construction.
var backend: Backend = Backend.STUB

## Whichever engine was chosen. `Object` because the two share no base type.
var _impl: Object

## The chosen backend is announced once per run, not once per canvas.
static var _announced: bool = false


func _init() -> void:
	backend = _resolve_backend()
	if backend == Backend.NATIVE:
		_impl = ClassDB.instantiate(NATIVE_CLASS)
	else:
		_impl = StubEngine.new()
		if not _announced:
			push_warning(_stub_notice())
	_announced = true


## Says which of the two reasons the stub is running, because "recognises
## nothing" means very different things depending on the answer.
static func _stub_notice() -> String:
	var tail: String = " Glyphs draw and cast normally, but recognise nothing."
	if OS.get_environment(BACKEND_ENV_VAR).to_lower() == "stub":
		return "Spell recogniser: stub forced by %s=stub." % BACKEND_ENV_VAR + tail
	return (
		"Spell recogniser: %s is not registered, running the stub. " % NATIVE_CLASS
		+ "Expected on macOS, where Jenova cannot build; on Windows or Linux it "
		+ "means the Jenova module needs a rebuild in the editor."
		+ tail
	)


## Whether the native engine is registered and can be instantiated. False on
## macOS always, and on Windows until the Jenova module has been built once.
static func native_available() -> bool:
	return ClassDB.class_exists(NATIVE_CLASS) and ClassDB.can_instantiate(NATIVE_CLASS)


static func _resolve_backend() -> Backend:
	var requested: String = OS.get_environment(BACKEND_ENV_VAR).to_lower()
	if requested == "stub":
		return Backend.STUB
	if native_available():
		return Backend.NATIVE
	if requested == "native":
		push_error(
			"%s=native, but %s is not registered. " % [BACKEND_ENV_VAR, NATIVE_CLASS]
			+ "Rebuild the Jenova module in the Godot editor, then restart it."
		)
	return Backend.STUB


## True when the real recogniser is behind this. For readouts and logs -- do
## not gate gameplay on it, the stub is meant to be transparent.
func is_native() -> bool:
	return backend == Backend.NATIVE


## Hands one finished stroke to the recogniser, which re-recognises the whole
## canvas. See `GlyphCanvas.end_stroke()` for when that happens.
func add_stroke(points: PackedVector2Array) -> void:
	_impl.call(&"add_stroke", points)


## Every feature currently on the canvas, one Dictionary each: {name, score,
## min_score, level, center}. Empty under the stub.
func get_features() -> Array:
	var features: Array = _impl.call(&"get_features")
	return features


## The spell the canvas spells out, or "" for no match. Empty under the stub.
func match_spell() -> String:
	var name: String = _impl.call(&"match_spell")
	return name


func clear() -> void:
	_impl.call(&"clear")


## Stands in for the native engine where it cannot be built. Deliberately
## silent rather than faked: a recogniser that guessed would send someone
## debugging a spell that never ran, and one that pushed an error per stroke
## would bury the output panel. The one warning at startup is the whole
## notice.
class StubEngine extends RefCounted:
	func add_stroke(_points: PackedVector2Array) -> void:
		pass

	func get_features() -> Array:
		return []

	func match_spell() -> String:
		return ""

	func clear() -> void:
		pass
