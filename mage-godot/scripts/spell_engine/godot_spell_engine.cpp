#include "scripts/spell_engine/godot_spell_engine.hpp"

namespace godot {

void GodotSpellEngine::_bind_methods() {
	// Bind methods to Godot's reflection system
	ClassDB::bind_method(D_METHOD("add_stroke", "points"), &GodotSpellEngine::add_stroke);
	ClassDB::bind_method(D_METHOD("match_spell"), &GodotSpellEngine::match_spell);
	ClassDB::bind_method(D_METHOD("clear"), &GodotSpellEngine::clear);
}

GodotSpellEngine::GodotSpellEngine() {
	// Engine automatically runs its constructor, calling register_templates() & register_spells()
}

GodotSpellEngine::~GodotSpellEngine() {
}

void GodotSpellEngine::add_stroke(const PackedVector2Array &p_points) {
	// Convert Godot's PackedVector2Array into std::vector<qrec::Point>
	std::vector<qrec::Point> stroke_points;
	stroke_points.reserve(p_points.size());

	for (int i = 0; i < p_points.size(); ++i) {
		Vector2 pt = p_points[i];
		// Convert Vector2 (x, y) -> qrec::Point
		stroke_points.push_back(qrec::Point{ static_cast<float>(pt.x), static_cast<float>(pt.y) });
	}

	// Pass converted points directly into your backend logic
	engine_.add_stroke(stroke_points);
}

String GodotSpellEngine::match_spell() const {
	// Call spell matcher and convert std::string -> Godot String
	std::string result = engine_.match_spell();
	return String(result.c_str());
}

void GodotSpellEngine::clear() {
	engine_.clear();
}

} // namespace godot
