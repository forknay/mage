// config.h
// =============================================================================
// Central Configuration for the $Q Recognizer Pipeline (C++ port of config.py)
// =============================================================================
// Every tunable constant used across the pipeline, in one place. Pure data,
// no logic -- mirrors config.py exactly, including grouping/comments, so the
// two can be diffed against each other when retuning.
#pragma once

#include <cstdint>
#include <string>
#include <unordered_map>

namespace qrec::config {

// =============================================================================
// 1. Stroke clustering (merge_intersecting_strokes.*)
// =============================================================================

// How close (in px) two strokes' points need to get before they're considered
// "physically touching" and merged into a single stroke unit.
inline constexpr double DEFAULT_TOUCH_THRESHOLD = 8.0;

// How close (px) a stroke's ENDPOINT needs to get to ANY point on another
// stroke before the two are considered "touching" for merge purposes.
inline constexpr double DEFAULT_ENDPOINT_TOUCH_THRESHOLD = 20.0;

// A stroke with more than this many raw points gets THINNED before the
// expensive per-segment touch test runs.
inline constexpr int DEFAULT_TOUCH_DECIMATION_MIN_POINTS = 24;

// Divisor applied to a call's `proximity_threshold` to get the minimum
// spacing (px) enforced between consecutive points kept during touch-test
// decimation.
inline constexpr double DEFAULT_TOUCH_DECIMATION_SPACING_DIVISOR = 3.0;

// Once two strokes' (post-decimation) segment counts multiply out to more
// than this many candidate pairs, the touch test switches to a
// grid-indexed search.
inline constexpr int DEFAULT_TOUCH_GRID_MIN_SEGMENT_PRODUCT = 4000;

// =============================================================================
// 2. Recognizer core (recognizer.* -- QRecognizer)
// =============================================================================

// Number of equidistant points every stroke (candidate or template) is
// resampled down/up to before scoring.
inline constexpr int NUM_RESAMPLE_POINTS = 64;

// Side length (px) of the square bounding box every gesture is uniformly
// scaled into before comparison.
inline constexpr double FRAME_SIZE = 250.0;

// Resolution of the 2D Look-Up Table used for O(1) nearest-template-point
// queries during scoring.
inline constexpr int LUT_SIZE = 32;

// Default per-template acceptance threshold. THE MAIN "HOW PERMISSIVE IS
// RECOGNITION OVERALL" KNOB.
inline constexpr double DEFAULT_MIN_SCORE = 0.4;

// Weight of the Gaussian aspect-ratio-deviation penalty applied on top of
// the raw cloud-distance score.
inline constexpr double ASPECT_RATIO_WEIGHT = 0.10;

// =============================================================================
// 3. Level composition (recognizer.* -- recognize_scene)
// =============================================================================

// For each target Level > 1, how far apart (px) two lower-level features are
// allowed to be and still get bundled together as candidates for that
// higher-level composite gesture. A level with no entry here falls back to
// `touch_threshold` at call time.
inline const std::unordered_map<int, double> DEFAULT_LEVEL_MERGE_THRESHOLDS = {
    {2, 60.0},
};

// =============================================================================
// 4. Cloud-distance scoring (recognizer.* -- _cloud_distance / _reverse_cloud_distance)
// =============================================================================
// These four knobs are what actually separate "ordinary sloppy drawing" from
// "a genuinely missing or extra stroke" -- tune THESE, not just
// DEFAULT_MIN_SCORE above, when you want recognition to forgive more noise
// without also forgiving a structurally different shape. See config.py for
// full rationale on each.

// Distance (px) beyond which the exponential "unmatched feature" penalty
// kicks in, in both the forward and reverse cloud-distance passes.
inline constexpr double CLOUD_DISTANCE_PENALTY_THRESHOLD = 30.0;

// Exponent applied to the portion of a distance that exceeds
// CLOUD_DISTANCE_PENALTY_THRESHOLD.
inline constexpr double CLOUD_DISTANCE_EXPONENT = 2.5;

// Blend weight between the mean adjusted distance and the max adjusted
// distance (a Hausdorff-style component).
inline constexpr double CLOUD_DISTANCE_MAX_WEIGHT = 0.25;

// =============================================================================
// 5. Template capture defaults
// =============================================================================

// Acceptance threshold offered as the default answer when capturing a new
// template interactively. Kept separate from DEFAULT_MIN_SCORE.
inline constexpr double DEFAULT_CAPTURE_MIN_SCORE = 0.5;

// =============================================================================
// 6. Canvas / UI
// =============================================================================

inline constexpr int CANVAS_WIDTH = 800;
inline constexpr int CANVAS_HEIGHT = 800;

// Thickness (px) of the brush stroke drawn on-screen. Purely cosmetic.
inline constexpr int BRUSH_THICKNESS = 4;

// Parameters for synthetic demo templates (line/dot).
inline constexpr double DEMO_LINE_LENGTH = 300.0;
inline constexpr int DEMO_LINE_RESAMPLE_N = 40;
inline constexpr double DEMO_DOT_RADIUS = 10.0;
inline constexpr int DEMO_DOT_RESAMPLE_N = 12;

// Size (px) of one cell in the spatial-index grid overlay (debug visual only;
// does NOT change the actual clustering cell size).
inline constexpr double SPATIAL_GRID_VISUAL_SIZE = 50.0;

// =============================================================================
// 7. Template storage paths
// =============================================================================

inline const std::string DEFAULT_TEMPLATES_DIR = "templates";
inline const std::string DEFAULT_TEMPLATE_IMAGES_DIR = "template_images";

// =============================================================================
// 8. Template cache
// =============================================================================

inline const std::string DEFAULT_TEMPLATE_CACHE_DIR = "template_cache";
inline constexpr bool DEFAULT_USE_TEMPLATE_CACHE = true;

// =============================================================================
// 9. Spell matching (spell_matcher.*)
// =============================================================================

inline const std::string DEFAULT_SPELLS_DIR = "spells";

// Default per-slot allowed deviation between a spell feature's expected
// normalized distance-from-center and what was actually drawn.
inline constexpr double DEFAULT_SPELL_DIST_TOLERANCE = 0.10;

// Default soft falloff margin (degrees) used when a feature lands just
// outside its slot's required angle sector.
inline constexpr double DEFAULT_SPELL_ANGLE_TOLERANCE = 20.0;

// Default per-spell acceptance threshold (informational only -- see
// spell_matcher.h).
inline constexpr double DEFAULT_SPELL_MIN_SCORE = 0.75;

// Normalized-distance-from-center below which a feature's angle is treated
// as meaningless noise and skipped.
inline constexpr double SPELL_CENTER_EPSILON = 0.05;

}  // namespace qrec::config