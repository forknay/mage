// spell_engine.cpp
#include "scripts/spell_engine/spell_engine.hpp"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <JenovaSDK.h>
#include "scripts/spell_engine/config.hpp"
#include "scripts/spell_engine/mini_json.hpp"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

namespace fs = std::filesystem;
using json = minijson::Value;

namespace qrec {

// =============================================================================
// SpellBook
// =============================================================================

void SpellBook::add_spell(SpellDefinition spell) {
	spell.validate();  // throws std::invalid_argument on a malformed spell
	spells_.push_back(std::move(spell));
}

std::optional<SpellMatchResult> SpellBook::match_best(const std::vector<std::shared_ptr<Feature>>& features) const {
	return match_best_spell(spells_, features);
}

// =============================================================================
// SpellEngine
// =============================================================================

namespace {

// =============================================================================
// JSON-backed template/spell loading
// =============================================================================
// Templates live at   <kTemplatesDir>/*.json  (one gesture template per file)
// Spells live at      <kSpellsDir>/*.json     (one SpellDefinition per file)
//
// Adjust these two paths to wherever your project keeps data assets (e.g.
// swap for a "res://..." path + ProjectSettings::globalize_path() if this
// is embedded in a Godot module). Everything below only depends on
// std::filesystem, so relocating the data is a one-line change.

const fs::path kTemplatesDir = "assets/spell_engine/templates";
const fs::path kSpellsDir = "assets/spell_engine/spells";

// Reads and parses a single JSON file, throwing std::runtime_error (with
// the offending path folded into the message) on any failure -- missing
// file, unreadable file, or malformed JSON.
json load_json_file(const fs::path& path) {
	std::ifstream in(path, std::ios::binary);
	if (!in) {
		jenova::sdk::Output("spell_engine: could not open '%s'", path.string().c_str());
		throw std::runtime_error("spell_engine: could not open '" + path.string() + "'");
	}
	std::ostringstream buffer;
	buffer << in.rdbuf();
	try {
		jenova::sdk::Output("loading a template");
		return minijson::parse(buffer.str());
	} catch (const std::exception& e) {
		jenova::sdk::Output("error loading template");
		throw std::runtime_error("spell_engine: malformed JSON in '" + path.string() + "': " + e.what());
	}
}

// Returns every *.json file directly inside `dir`, sorted by filename so
// registration order is stable/deterministic across runs. Throws
// std::runtime_error if `dir` doesn't exist.
std::vector<fs::path> list_json_files(const fs::path& dir) {
	if (!fs::is_directory(dir)) {
		jenova::sdk::Output("spell_engine: expected a directory at '%s'", dir.string().c_str());
		throw std::runtime_error("spell_engine: expected a directory at '" + dir.string() + "'");
	}
	std::vector<fs::path> files;
	for (const auto& entry : fs::directory_iterator(dir)) {
		if (entry.is_regular_file() && entry.path().extension() == ".json") {
			files.push_back(entry.path());
		}
	}
	std::sort(files.begin(), files.end());
	return files;
}

Point point_from_json(const json& j) {
	return Point{j.at("x").get<double>(), j.at("y").get<double>()};
}

Stroke stroke_from_json(const json& j) {
	std::vector<Point> pts;
	pts.reserve(j.size());
	for (const auto& pj : j) {
		pts.push_back(point_from_json(pj));
	}
	return Stroke(std::move(pts));
}

// Two template file shapes are accepted, because both exist on disk:
//
//   (a) nested, one array per pen-stroke --
//       {"name":"line_horizontal", "level":1,
//        "strokes": [ [ {"x":0,"y":0}, ... ], [ ... ] ]}
//
//   (b) flat, as written by the interactive template capture tool, with
//       stroke membership carried per-point --
//       {"name":"plus", "level":1, "min_score":0.2,
//        "points": [ {"x":254,"y":389,"stroke_id":0}, ...,
//                    {"x":300,"y":350,"stroke_id":1}, ... ]}
//
// Shape (b) MUST be split back out on "stroke_id": collapsing a
// multi-stroke gesture into one Stroke makes the pen-up gap between two
// strokes look like a real drawn segment, which corrupts the arc-length
// resampling the whole recognizer is built on (plus and triangleRune are
// both multi-stroke).
//
// A THIRD, orthogonal field applies to either shape once level >= 2:
//
//   "components": ["line_vertical", "circle"]
//
// -- the list of already-recognized, lower-level feature NAMES this
// gesture is built from (see Template::component_shapes in
// gesture_types.hpp for the full contract, and QRecognizer::compose_level
// in recognizer.cpp for how it's used at composition time). "strokes"/
// "points" is still the gesture's own raw drawn geometry either way --
// that's what the final $Q confirmation pass scores against -- but for a
// level>=2 template ONLY "components" tells the recognizer which
// sub-features to look for nearby in the first place.
struct TemplateData {
	std::string name;
	std::vector<Stroke> strokes;
	int level = -1;  // <0 means "infer from the geometry" (see add_template)
	double min_score = config::DEFAULT_MIN_SCORE;
	std::vector<std::string> component_shapes;  // level >= 2 only; see above
};

// Splits a flat "points" array into one Stroke per contiguous run of equal
// "stroke_id" (points missing the key are treated as stroke 0), preserving
// the file's point order within and across strokes.
std::vector<Stroke> strokes_from_flat_points(const json& points_json) {
	std::vector<Stroke> strokes;
	std::vector<Point> current;
	int current_id = 0;
	bool started = false;

	for (const auto& pj : points_json) {
		int id = pj.value("stroke_id", 0);
		if (started && id != current_id) {
			strokes.push_back(Stroke(std::move(current)));
			current.clear();
		}
		current.push_back(point_from_json(pj));
		current_id = id;
		started = true;
	}
	if (!current.empty()) {
		strokes.push_back(Stroke(std::move(current)));
	}
	return strokes;
}

TemplateData template_from_json(const json& j) {
	TemplateData t;
	t.name = j.at("name").get<std::string>();
	t.level = j.value("level", -1);
	t.min_score = j.value("min_score", config::DEFAULT_MIN_SCORE);

	if (j.contains("components")) {
		for (const auto& cj : j.at("components")) {
			t.component_shapes.push_back(cj.get<std::string>());
		}
	}

	if (j.contains("strokes")) {
		for (const auto& sj : j.at("strokes")) {
			t.strokes.push_back(stroke_from_json(sj));
		}
	} else if (j.contains("points")) {
		t.strokes = strokes_from_flat_points(j.at("points"));
	} else {
		throw std::runtime_error("spell_engine: template '" + t.name +
								  "' has neither a 'strokes' nor a 'points' array");
	}

	if (t.strokes.empty()) {
		throw std::runtime_error("spell_engine: template '" + t.name + "' has no points");
	}
	return t;
}
// Expected slot shape (all fields but "id"/"shape" optional):
// {"id":0, "shape":"circle", "distance":0.0, "tolerance_dist":0.35,
//  "min_angle":315.0, "max_angle":45.0, "tolerance_angle":30.0}
SpellFeatureSlot slot_from_json(const json& j) {
	SpellFeatureSlot slot;
	slot.id = j.at("id").get<int>();
	slot.shape = j.at("shape").get<std::string>();
	if (j.contains("distance") && !j.at("distance").is_null()) {
		slot.distance = j.at("distance").get<double>();
	}
	slot.tolerance_dist = j.value("tolerance_dist", config::DEFAULT_SPELL_DIST_TOLERANCE);
	if (j.contains("min_angle") && !j.at("min_angle").is_null()) {
		slot.min_angle = j.at("min_angle").get<double>();
	}
	if (j.contains("max_angle") && !j.at("max_angle").is_null()) {
		slot.max_angle = j.at("max_angle").get<double>();
	}
	slot.tolerance_angle = j.value("tolerance_angle", config::DEFAULT_SPELL_ANGLE_TOLERANCE);
	return slot;
}

// Expected relative-constraint shape:
// {"subject_id":1, "reference_id":0, "relation":"farther", "margin":0.1,
//  "tolerance":0.2}
RelativeDistanceConstraint relative_constraint_from_json(const json& j) {
	RelativeDistanceConstraint c;
	c.subject_id = j.at("subject_id").get<int>();
	c.reference_id = j.at("reference_id").get<int>();
	c.relation = j.at("relation").get<std::string>();
	c.margin = j.value("margin", 0.0);
	c.tolerance = j.value("tolerance", config::DEFAULT_SPELL_DIST_TOLERANCE);
	c.validate();  // throws std::invalid_argument on an unknown relation string
	return c;
}

// Expected spell file shape:
// {
//   "name": "circle_and_north_caret",
//   "min_score": 0.6,
//   "features": [ {...slot...}, {...slot...} ],
//   "relative_constraints": [ {...constraint...}, ... ]   // optional
// }
SpellDefinition spell_from_json(const json& j) {
	SpellDefinition spell;
	spell.name = j.at("name").get<std::string>();
	spell.min_score = j.value("min_score", config::DEFAULT_SPELL_MIN_SCORE);

	const auto& features_json = j.at("features");
	spell.features.reserve(features_json.size());
	for (const auto& slot_json : features_json) {
		spell.features.push_back(slot_from_json(slot_json));
	}

	if (j.contains("relative_constraints")) {
		const auto& constraints_json = j.at("relative_constraints");
		spell.relative_constraints.reserve(constraints_json.size());
		for (const auto& constraint_json : constraints_json) {
			spell.relative_constraints.push_back(relative_constraint_from_json(constraint_json));
		}
	}

	return spell;
}

}  // namespace

SpellEngine::SpellEngine() : recognizer_(config::NUM_RESAMPLE_POINTS) {
	// Loading templates/spells from disk can fail for reasons entirely
	// outside this code's control (asset folder not deployed yet, wrong
	// working directory, a hand-edited JSON file with a typo). None of
	// that should be able to take the whole host process down with it --
	// especially under Godot, whose engine build commonly compiles with
	// C++ exceptions disabled, in which case an uncaught throw crossing
	// this constructor doesn't unwind, it calls std::terminate()/abort()
	// and silently kills the editor. So: catch here, log loudly, and
	// leave the engine running with whatever did load (possibly nothing)
	// rather than ever letting an exception escape SpellEngine's ctor.
	try {
		register_templates();
	} catch (const std::exception& e) {
		std::cerr << "[spell_engine] failed to load templates -- gesture recognition will not work: " << e.what()
				  << std::endl;
	}
	try {
		register_spells();
	} catch (const std::exception& e) {
		std::cerr << "[spell_engine] failed to load spells -- spell matching will not work: " << e.what()
				  << std::endl;
	}
}

void SpellEngine::register_templates() {
	// Loads every *.json file under kTemplatesDir (see the loader helpers
	// above for the accepted schemas, including the level>=2-only
	// "components" field) and registers each as a gesture template.
	//
	// A failure on ONE file only skips that file -- it must never abort the
	// whole loop. Letting it abort meant a single malformed template left
	// the recognizer holding only the alphabetically-earlier templates,
	// and since best_matching_template always returns *some* best match
	// from whatever is registered, that failure surfaced not as an error
	// but as every gesture in the game recognizing as the same shape.
	// Each skip is logged loudly, and so is the final registered count.
	const auto paths = list_json_files(kTemplatesDir);
	int failed = 0;
	for (const auto& path : paths) {
		try {
			TemplateData t = template_from_json(load_json_file(path));
			recognizer_.add_template(t.name, t.strokes, t.level, t.min_score, t.component_shapes);

			// A level>=2 template with no declared components can be
			// registered (add_template doesn't reject it -- it's not
			// technically invalid data), but QRecognizer::compose_level
			// only ever searches templates that DO declare components, so
			// a template like this can never actually be produced on a
			// real canvas. That's a silent dead template unless flagged
			// here.
			const Template& registered = recognizer_.templates().back();
			if (registered.level >= 2 && registered.component_shapes.empty()) {
				jenova::sdk::Output(
					"spell_engine: WARNING template '%s' registered at level=%d with no 'components' -- "
					"it can never be recognized (see QRecognizer::compose_level in recognizer.cpp)",
					registered.name.c_str(), registered.level);
			}

			jenova::sdk::Output("spell_engine: registered template '%s' (level=%d, strokes=%d, min_score=%.2f)",
								 t.name.c_str(), registered.level, static_cast<int>(t.strokes.size()), t.min_score);
		} catch (const std::exception& e) {
			++failed;
			jenova::sdk::Output("spell_engine: SKIPPED template '%s': %s", path.string().c_str(), e.what());
		}
	}
	jenova::sdk::Output("spell_engine: %d template(s) registered, %d skipped, %d file(s) found",
						 static_cast<int>(recognizer_.templates().size()), failed, static_cast<int>(paths.size()));
}

void SpellEngine::register_spells() {
	jenova::sdk::Output("loading spell...");
	// Loads every *.json file under kSpellsDir (see spell_from_json above
	// for the expected schema -- "features" holds SpellFeatureSlots,
	// "relative_constraints" is optional) and registers each as a
	// SpellDefinition. See spell_matcher.h for the full slot/constraint
	// vocabulary (SpellFeatureSlot::distance for a fixed expected
	// distance, min_angle/max_angle for a compass sector, and
	// RelativeDistanceConstraint for "farther"/"closer"/"inside"/
	// "outside" relations between two slots).
	for (const auto& path : list_json_files(kSpellsDir)) {
		try {
			SpellDefinition spell = spell_from_json(load_json_file(path));
			spellbook_.add_spell(std::move(spell));  // validate()d inside add_spell()
		} catch (const std::exception& e) {
			jenova::sdk::Output("error loading spell");
			throw std::runtime_error("spell_engine: failed to load spell '" + path.string() + "': " + e.what());
		}
	}
}

void SpellEngine::add_stroke(const std::vector<Point>& stroke_points) {
	recognizer_.add_stroke(stroke_from_points(stroke_points));
}

void SpellEngine::add_stroke(const Stroke& stroke) { recognizer_.add_stroke(stroke); }

std::string SpellEngine::match_spell() const {
	auto features = recognizer_.features();
	auto best = spellbook_.match_best(features);
	if (best.has_value() && best->name.has_value()) {
		return *best->name;
	}
	return "";
}

void SpellEngine::clear() { recognizer_.clear(); }

}  // namespace qrec