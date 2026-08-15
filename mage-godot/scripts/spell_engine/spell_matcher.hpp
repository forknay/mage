// spell_matcher.h
// =============================================================================
// Spell Matching -- Relational Layer on top of QRecognizer (C++ port of
// spell_matcher.py)
// =============================================================================
// $Q (recognizer.h/.cpp) intentionally throws away position: every gesture
// is uniformly scaled into a fixed frame and re-centered on its own
// centroid before scoring, because classifying "is this stroke a triangle"
// has to work no matter where on the canvas it was drawn.
//
// A *spell* is defined by exactly the information $Q throws away: not just
// "there's a star and four triangles here", but "the triangles sit roughly
// north/east/south/west of the star, at roughly this distance from it".
// That's a relational/layout question, so it lives in its own layer here,
// operating on the `qrec::Feature` list `QRecognizer::recognize_scene`
// produces (which still carries each feature's RAW, unnormalized scene
// points).
//
// See the original spell_matcher.py module docstring for the full design
// rationale (the three complementary ways a slot can be positioned:
// absolute distance+angle, relative distance ("farther"/"closer"), and
// containment ("inside"/"outside")), which this port preserves exactly.
//
// Compass angle, not math angle: 0=N, 90=E, 180=S, 270=W.
//
// Deliberately NOT rotation-invariant -- "north" is always "up on the
// page" (see the note at the bottom of spell_matcher.py for the
// alternative anchor-relative design this trades away).
#pragma once

#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "config.hpp"
#include "scripts/spell_engine/gesture_types.hpp"

namespace qrec {

// =============================================================================
// 1. Geometry helpers
// =============================================================================

// Bearing of the vector (dx, dy) in COMPASS convention: 0=North, 90=East,
// 180=South, 270=West, increasing clockwise. Screen y grows downward, so
// "up" is -dy.
double compass_angle(double dx, double dy);

// True if `angle` (compass bearing, any real number) falls inside the
// sector [min_angle, max_angle] going CLOCKWISE from min_angle to
// max_angle, correctly handling the 360/0 wraparound case.
bool angle_in_range(double angle, double min_angle, double max_angle);

// -----------------------------------------------------------------------
// PositionedFeature
// -----------------------------------------------------------------------
// A Feature re-expressed relative to the whole drawing.
struct PositionedFeature {
	std::string shape;
	double distance = 0.0;  // normalized distance from the SPELL's center
	double angle = 0.0;      // compass bearing from the SPELL's center, degrees
	double nx = 0.0;          // normalized x-offset from the SPELL's center
	double ny = 0.0;          // normalized y-offset from the SPELL's center
	double radius = 0.0;      // this feature's own normalized extent
	std::shared_ptr<Feature> source;  // original feature, kept for overlays/debugging
};

// Turns a flat feature list (as returned by QRecognizer::recognize_scene)
// into PositionedFeatures. Only features with a real recognized name are
// usable for spell matching; unrecognized/rejected clusters are silently
// skipped.
std::vector<PositionedFeature> compute_positions(const std::vector<std::shared_ptr<Feature>>& features);

// =============================================================================
// 2. Spell definitions (pure data)
// =============================================================================

// One required feature within a spell, described relationally rather than
// by absolute position. `id` only needs to be unique within its own
// SpellDefinition. `distance` is OPTIONAL (use std::nullopt): a slot that
// omits it is scored purely on shape (and angle/relative constraints, if
// any) -- no fixed expected distance from center is enforced.
struct SpellFeatureSlot {
	int id = 0;
	std::string shape;
	std::optional<double> distance = std::nullopt;
	double tolerance_dist = config::DEFAULT_SPELL_DIST_TOLERANCE;
	std::optional<double> min_angle = std::nullopt;  // nullopt -> angle unconstrained
	std::optional<double> max_angle = std::nullopt;
	double tolerance_angle = config::DEFAULT_SPELL_ANGLE_TOLERANCE;

	bool angle_constrained() const { return min_angle.has_value() && max_angle.has_value(); }
};

// A relational positioning check BETWEEN two slots, evaluated after a
// candidate assignment fills both. `relation` is one of "farther",
// "closer", "inside", "outside" -- see spell_matcher.py's
// RelativeDistanceConstraint docstring for full semantics of each.
struct RelativeDistanceConstraint {
	int subject_id = 0;
	int reference_id = 0;
	std::string relation;  // "farther" | "closer" | "inside" | "outside"
	double margin = 0.0;
	double tolerance = config::DEFAULT_SPELL_DIST_TOLERANCE;

	// Validates `relation` is one of the four known values. Throws
	// std::invalid_argument otherwise (mirrors
	// RelativeDistanceConstraint.__post_init__).
	void validate() const;
};

// `min_score` is kept for spell-file/API backward compatibility but is NOT
// used by `match_spell` to decide acceptance -- see that function's
// docstring in spell_matcher.cpp. Tune individual slot/constraint
// tolerances instead to control forgiveness.
struct SpellDefinition {
	std::string name;
	std::vector<SpellFeatureSlot> features;
	double min_score = config::DEFAULT_SPELL_MIN_SCORE;
	std::vector<RelativeDistanceConstraint> relative_constraints;

	// Validates that every constraint refers to slot ids that actually
	// exist in this spell. Throws std::invalid_argument on a bad
	// subject_id/reference_id (mirrors SpellDefinition.__post_init__).
	// Call this once after populating `features`/`relative_constraints`.
	void validate() const;
};

// =============================================================================
// 3. Matching
// =============================================================================

struct SpellMatchResult {
	std::optional<std::string> name;
	double score = 0.0;
	bool accepted = false;
	// slot.id -> matched PositionedFeature, for whichever slots got
	// filled; a slot missing from this map means nothing in the scene
	// satisfied it well enough to be worth assigning.
	std::vector<std::pair<int, PositionedFeature>> assignment;
};

// Finds the best injective assignment of `scene_features` to `spell`'s
// slots via backtracking search, exactly mirroring match_spell's
// documented semantics in spell_matcher.py (see that docstring for the
// full rationale on why `accepted` is a pure rule check rather than a
// blended-average threshold).
SpellMatchResult match_spell(const SpellDefinition& spell, const std::vector<std::shared_ptr<Feature>>& scene_features);

// Tries every known spell against the same scene and returns whichever
// ACCEPTED result scored highest, or std::nullopt if nothing accepted.
std::optional<SpellMatchResult> match_best_spell(const std::vector<SpellDefinition>& spells,
												   const std::vector<std::shared_ptr<Feature>>& scene_features);

}  // namespace qrec
