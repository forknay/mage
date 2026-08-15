#pragma once

#include <Godot/classes/ref_counted.hpp>
#include <Godot/core/class_db.hpp>
#include <Godot/variant/packed_vector2_array.hpp>
#include <Godot/variant/string.hpp>

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
};

} // namespace godot
