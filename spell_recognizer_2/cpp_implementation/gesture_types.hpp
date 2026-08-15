// gesture_types.h
// =============================================================================
// Shared Data Types for the $Q Recognizer Pipeline (C++ port of gesture_types.py)
// =============================================================================
// Every type shared across the pipeline (merge_intersecting_strokes.*,
// recognizer.*, spell_matcher.*) lives here, so there's exactly one
// definition of each.
//
// Stroke owns stroke identity outright, exactly as in the Python original:
// a Point is just (x, y) with no idea which stroke it belongs to; a Stroke
// is "the points that make up one physically continuous pen-stroke",
// expressed via literal containment (a Point being an element of a
// Stroke::points vector).
#pragma once

#include <array>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "config.h"

namespace qrec {

// -----------------------------------------------------------------------
// Point
// -----------------------------------------------------------------------
struct Point {
    double x = 0.0;
    double y = 0.0;
};

// -----------------------------------------------------------------------
// Stroke
// -----------------------------------------------------------------------
// `seq` is a monotonically increasing creation-order counter, assigned
// automatically -- mirrors gesture_types.py's module-level
// itertools.count() backing Stroke.seq. It lets QRecognizer's incremental
// add_stroke API re-establish chronological order across strokes pulled
// from different sources when recomputing a touched region.
struct Stroke {
    std::vector<Point> points;
    int64_t seq;

    explicit Stroke(std::vector<Point> pts = {});
};

// Returns the next value of the process-wide monotonic stroke sequence
// counter (mirrors the Python module's `_stroke_seq_counter`).
int64_t next_stroke_seq();

// Constructs a Stroke from a list of Points, COPYING them into a new
// vector rather than aliasing the caller's buffer -- mirrors
// gesture_types.stroke_from_points's rationale (a caller reusing one
// mutable accumulation buffer across strokes must not silently mutate a
// previously created Stroke).
Stroke stroke_from_points(const std::vector<Point>& points);

// -----------------------------------------------------------------------
// Template
// -----------------------------------------------------------------------
// Represents a registered gesture template. `lut` is a 2D discrete
// Voronoi diagram (see QRecognizer::create_lut) stored as a flat
// row-major buffer of size lut_size*lut_size, holding the index of the
// nearest template point for each grid cell.
struct Template {
    std::string name;
    std::vector<Point> points;
    std::vector<double> xs;    // point x-coordinates, parallel to `points`
    std::vector<double> ys;    // point y-coordinates, parallel to `points`
    std::vector<int64_t> lut;  // flat lut_size*lut_size buffer, row-major (x-major)
    int lut_size = 0;
    int level = 0;                  // Number of physically-separate stroke units
    double aspect_ratio = 1.0;      // Raw bounding box aspect ratio before uniform scaling
    double min_score = config::DEFAULT_MIN_SCORE;
};

// -----------------------------------------------------------------------
// RecognitionResult
// -----------------------------------------------------------------------
// The output of matching candidate points against templates.
struct RecognitionResult {
    std::optional<std::string> name;
    double score = 0.0;
    double distance = 0.0;
    double min_score = 0.0;
    bool accepted = false;
};

// -----------------------------------------------------------------------
// Feature
// -----------------------------------------------------------------------
// A distinct, recognized feature (either atomic or composite) on the
// canvas. `components` holds shared_ptr<Feature> (rather than by-value
// Feature, as the Python dataclass does) so that C++ identity (pointer
// equality) can stand in for Python's `id(feat)` object identity, which
// recognizer.py's touch-cache and bundling logic rely on.
struct Feature {
    int cluster_id = 0;
    int level = 0;
    RecognitionResult result;
    std::vector<Point> points;
    // The physically-separate Stroke(s) this feature was built from.
    std::vector<Stroke> strokes;
    std::vector<std::shared_ptr<Feature>> components;

    // Lazily computed, cached (min_x, max_x, min_y, max_y) bounding box.
    // Safe to cache because `points` is treated as immutable after
    // construction, exactly like the Python original.
    mutable std::optional<std::array<double, 4>> bbox_cache;

    const std::array<double, 4>& bounding_box() const;
};

}  // namespace qrec