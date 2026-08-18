// spell_engine.h
// =============================================================================
// SpellEngine -- top-level API over QRecognizer + spell_matcher
// =============================================================================
// This is the thin façade a caller (e.g. whatever collects mouse/touch
// strokes) actually talks to. It owns:
//
//   - a QRecognizer, with every gesture template registered up front, and
//   - a SpellBook, with every spell definition registered up front,
//
// and exposes exactly three operations:
//
//   1. add_stroke(points)  -- feed in one physically-continuous pen-stroke
//   2. match_spell()       -- "what spell does the canvas look like right
//                              now?", checked automatically against every
//                              registered spell
//   3. clear()             -- reset for the next attempt
//
// All template/spell registration happens ONCE, inside SpellEngine's
// constructor (see register_templates()/register_spells() below) --
// callers never pass templates or spells in on a per-call basis, and
// match_spell() never takes a spell list; it always checks the full set
// SpellBook is holding.
#pragma once

#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "scripts/spell_engine/gesture_types.hpp"
#include "scripts/spell_engine/recognizer.hpp"
#include "scripts/spell_engine/spell_matcher.hpp"

namespace qrec {

// -----------------------------------------------------------------------
// SpellBook
// -----------------------------------------------------------------------
// Holds a library of SpellDefinitions and knows how to find the best
// accepted match for a given scene. This is the "spell matcher class that
// can hold spell definitions" -- the in-process analogue of what
// spell_store.load_spells() (file loading) + spell_matcher.match_best_spell()
// (matching) did together in the Python pipeline, minus the JSON
// persistence: spells are registered directly via add_spell() instead of
// being read from spells/*.json.
class SpellBook {
public:
	// Validates `spell` (same checks as SpellDefinition::validate() --
	// every RelativeDistanceConstraint must use a known relation and
	// refer to slot ids that actually exist on the spell) and adds it to
	// the library. Throws std::invalid_argument on an invalid spell,
	// exactly like a malformed spell file would fail to load.
	void add_spell(SpellDefinition spell);

	const std::vector<SpellDefinition>& spells() const { return spells_; }

	// Tries every registered spell against `features` and returns
	// whichever ACCEPTED result scored highest, or std::nullopt if
	// nothing accepted. Thin wrapper over spell_matcher::match_best_spell
	// -- this is the "automatically go through all the spells" step.
	std::optional<SpellMatchResult> match_best(const std::vector<std::shared_ptr<Feature>>& features) const;

private:
	std::vector<SpellDefinition> spells_;
};

// -----------------------------------------------------------------------
// SpellEngine
// -----------------------------------------------------------------------
class SpellEngine {
public:
	// Constructs the recognizer and spell book and registers every
	// template/spell up front (see register_templates()/register_spells()
	// in spell_engine.cpp) -- nothing further needs to be registered by
	// the caller.
	SpellEngine();

	// Incorporates one new pen-stroke (as raw points -- everything
	// recorded between one mouse-down and the matching mouse-up) into the
	// canvas, updating the incrementally-tracked recognized features.
	// Call this once per COMPLETED stroke, not once per mouse-move
	// sample -- mirrors QRecognizer::add_stroke's own contract.
	void add_stroke(const std::vector<Point>& stroke_points);

	// Same as above, for a caller that already has a fully-formed Stroke
	// (e.g. one produced by gesture_types::stroke_from_points).
	void add_stroke(const Stroke& stroke);

	// Checks the canvas drawn so far (i.e. every add_stroke call since
	// construction or the last clear()) against every registered spell,
	// automatically -- no spell list to pass in. Returns the name of the
	// best-scoring ACCEPTED spell, or "" ( empty string ) if nothing
	// matched.
	std::string match_spell() const;

	// Resets the canvas (the recognizer's incremental state) for a fresh
	// attempt -- equivalent to clearing the drawing surface.
	void clear();

	// Read-only access to the underlying recognizer/spell book, in case a
	// caller needs the raw recognized features (e.g. for on-canvas
	// overlays) or wants to inspect what's registered. Not required for
	// the add_stroke/match_spell/clear workflow.
	const QRecognizer& recognizer() const { return recognizer_; }
	const SpellBook& spellbook() const { return spellbook_; }

private:
	// Registers every gesture template the recognizer should know about.
	// Called once, from the constructor. EDIT THIS to register your own
	// shapes -- see QRecognizer::add_template (recognizer.h) for the
	// (name, strokes, level, min_score, component_shapes) contract:
	//
	//   - A Level-1 template is recognized directly from its own raw
	//     strokes -- nothing else needs to be true first.
	//   - A Level-2+ template ALSO declares which already-recognized,
	//     lower-level feature NAMES it's built from (e.g. "exclaim" =
	//     one "line_vertical" feature + one "circle" feature, so its
	//     component_shapes is {"line_vertical", "circle"}). At
	//     composition time (QRecognizer::compose_level in recognizer.cpp)
	//     the recognizer looks, within each spatially-close group of
	//     already-accepted features, for every combination whose shape
	//     names match some level-target template's declared components,
	//     confirms each candidate combination via a real $Q pass against
	//     that specific template, and -- when a group has more than one
	//     viable composite -- keeps the single best one (more components
	//     consumed wins; ties go to the higher $Q score) rather than
	//     just whichever was found first. A composite that clears its
	//     template's min_score always replaces the components it
	//     consumed, regardless of how those components' own scores
	//     compared to it.
	//
	// Loaded from assets/spell_engine/templates/*.json when built via
	// SpellEngine's normal constructor path -- see template_from_json in
	// spell_engine.cpp for the on-disk schema, including the "components"
	// array that maps to component_shapes above. A Level-2+ template
	// registered without "components" loads fine but can never actually
	// be produced on a real canvas; register_templates() logs a loud
	// warning for exactly that case.
	void register_templates();

	// Registers every spell the engine should be able to detect. Called
	// once, from the constructor. EDIT THIS to register your own spells --
	// see spell_matcher.h's SpellDefinition/SpellFeatureSlot/
	// RelativeDistanceConstraint for the full vocabulary (absolute
	// distance+angle slots, relative "farther"/"closer" constraints, and
	// "inside"/"outside" containment constraints). Spells are matched
	// against whatever features QRecognizer::features() currently holds,
	// so a spell can reference a level-2+ composite feature by name (e.g.
	// "exclaim") exactly the same way it would reference a level-1 one.
	void register_spells();

	QRecognizer recognizer_;
	SpellBook spellbook_;
};

}  // namespace qrec