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
	// (name, strokes, level, min_score) contract. Ships with a small demo
	// set (lines, a circle, a few open-angle shapes, plus the "exclaim"/
	// "colon" level-2 composites) mirroring test_canvas.py's
	// build_demo_recognizer, purely so the engine is usable/testable out
	// of the box.
	void register_templates();

	// Registers every spell the engine should be able to detect. Called
	// once, from the constructor. EDIT THIS to register your own spells --
	// see spell_matcher.h's SpellDefinition/SpellFeatureSlot/
	// RelativeDistanceConstraint for the full vocabulary (absolute
	// distance+angle slots, relative "farther"/"closer" constraints, and
	// "inside"/"outside" containment constraints). Ships with one
	// illustrative demo spell built from the demo templates above.
	void register_spells();

	QRecognizer recognizer_;
	SpellBook spellbook_;
};

}  // namespace qrec
