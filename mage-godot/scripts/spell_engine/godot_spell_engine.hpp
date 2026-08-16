#pragma once

#include <Godot/classes/ref_counted.hpp>
#include <Godot/core/class_db.hpp>
#include <Godot/variant/array.hpp>
#include <Godot/variant/dictionary.hpp>
#include <Godot/variant/packed_vector2_array.hpp>
#include <Godot/variant/string.hpp>
#include <Godot/variant/vector2.hpp>

// Include your provided C++ header
#include "scripts/spell_engine/spell_engine.hpp"

namespace godot {

class GodotSpellEngine : public RefCounted {
	GDCLASS(GodotSpellEngine, RefCounted)

private:
	qrec::SpellEngine engine_;

protected:
	static void _bind_methods();

public:
	GodotSpellEngine();
	~GodotSpellEngine();

	// Exposed API for GDScript
	void add_stroke(const PackedVector2Array &p_points);
	String match_spell() const;
	void clear();

	// Every feature the recognizer currently holds on the canvas, one
	// Dictionary each: {name: String, score: float, min_score: float,
	// level: int, center: Vector2 (canvas coords)}. The recognizer only
	// keeps features that cleared their template's min_score, so anything
	// in here was recognized with enough certainty to act on. Read-only
	// snapshot -- meant for on-screen debug readouts, not for matching.
	Array get_features() const;
};

} // namespace godot
