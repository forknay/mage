#include "scripts/spell_engine/godot_spell_engine.hpp"
#include <iostream>
// Jenova SDK (needed for sakura:: hot-reload hooks and JENOVA_ACTIVATOR)
#include <JenovaSDK.h>

namespace godot {

void GodotSpellEngine::_bind_methods() {
	ClassDB::bind_method(D_METHOD("add_stroke", "points"), &GodotSpellEngine::add_stroke);
	ClassDB::bind_method(D_METHOD("match_spell"), &GodotSpellEngine::match_spell);
	ClassDB::bind_method(D_METHOD("clear"), &GodotSpellEngine::clear);
}

GodotSpellEngine::GodotSpellEngine() {}
GodotSpellEngine::~GodotSpellEngine() {}

void GodotSpellEngine::add_stroke(const PackedVector2Array &p_points) {
	jenova::sdk::Output("called holy sheet");
	std::vector<qrec::Point> stroke_points;
	stroke_points.reserve(p_points.size());

	for (int i = 0; i < p_points.size(); ++i) {
		Vector2 pt = p_points[i];
		stroke_points.push_back(qrec::Point{ static_cast<float>(pt.x), static_cast<float>(pt.y) });
	}

	engine_.add_stroke(stroke_points);
}

String GodotSpellEngine::match_spell() const {
	std::string result = engine_.match_spell();
	return String(result.c_str());
}

void GodotSpellEngine::clear() {
	engine_.clear();
}

} // namespace godot

// ---------------------------------------------------------------------------
// Nested Extension registration
//
// Jenova does NOT look for a "jenova_register_script_types" symbol — that
// was a raw-GDExtension convention and Jenova's runtime never calls it, so
// GodotSpellEngine was never actually added to ClassDB. That's why the build
// succeeds (the code compiles fine) but GDScript can't see or instantiate
// the class: as far as Godot is concerned, it was never registered.
//
// Jenova Nested Extensions need a Register/Unregister function pair that
// call ClassDB::register_class<>() plus the Sakura hot-reload hooks
// (sakura::FinishReload / sakura::PrepareReload / sakura::Dispose), and
// those functions need to actually run — either from a Boot Script
// (JenovaBoot/JenovaShutdown) or via the JENOVA_ACTIVATOR macro below.
// ---------------------------------------------------------------------------

using namespace godot;
using namespace jenova::sdk;

void RegisterGodotSpellEngine() {
	ClassDB::register_class<GodotSpellEngine>();
	sakura::FinishReload("GodotSpellEngine");
}

void UnregisterGodotSpellEngine() {
	sakura::PrepareReload("GodotSpellEngine");
	sakura::Dispose("GodotSpellEngine");
}

// Self-activation: registers/unregisters this class automatically without
// needing a separate Boot Script. Drop this and wire RegisterGodotSpellEngine()/
// UnregisterGodotSpellEngine() into JenovaBoot()/JenovaShutdown() instead if
// load order relative to other Nested Extensions matters for you.
JENOVA_ACTIVATOR(GodotSpellEngine, RegisterGodotSpellEngine, UnregisterGodotSpellEngine)
