// merge_intersecting_strokes.h
// =============================================================================
// Stroke Proximity/Touch Clustering (C++ port of merge_intersecting_strokes.py)
// =============================================================================
// Everything in this module answers ONE question: "which of these Strokes
// physically touch or cross one another?" It knows nothing about gesture
// recognition, templates, or "Level" -- it's a pure geometry primitive that
// the rest of the pipeline (recognizer.*) builds meaning on top of.
#pragma once

#include <array>
#include <utility>
#include <vector>

#include "config.hpp"
#include "gesture_types.hpp"
#include "spatial_index.hpp"  // for the Box alias

namespace qrec {

// -----------------------------------------------------------------------
// Public API
// -----------------------------------------------------------------------

// Returns (min_x, max_x, min_y, max_y) for a list of points.
Box bounding_box(const std::vector<Point>& points);

// Public wrapper for the cheap bounding-box pre-filter.
bool bounding_boxes_within_threshold(const Box& box_a, const Box& box_b, double threshold);

// Public wrapper for the full touch test between two point lists, each
// treated as a single run. Exposed so a caller that already has two
// specific point clouds (e.g. QRecognizer bundling already-recognized
// Features by proximity via their flattened points) can reuse the fully
// optimized touch test directly.
bool strokes_touch(const std::vector<Point>& pts_a, const std::vector<Point>& pts_b, double threshold,
                    double endpoint_threshold = config::DEFAULT_ENDPOINT_TOUCH_THRESHOLD);

// Groups Strokes into spatial clusters. Returns a list of clusters; each
// cluster is the list of original Stroke objects that are within
// `proximity_threshold` of one another, directly or transitively. Cluster
// order follows first-appearance order in `strokes`, and each cluster's
// own strokes keep their relative order from `strokes` too.
std::vector<std::vector<Stroke>> group_strokes_by_proximity(
    const std::vector<Stroke>& strokes, double proximity_threshold = config::DEFAULT_TOUCH_THRESHOLD,
    double endpoint_threshold = config::DEFAULT_ENDPOINT_TOUCH_THRESHOLD);

// Returns the number of physically-separate stroke units in `strokes` --
// the single source of truth for "level" elsewhere in the pipeline.
int count_touch_units(const std::vector<Stroke>& strokes,
                       double proximity_threshold = config::DEFAULT_TOUCH_THRESHOLD,
                       double endpoint_threshold = config::DEFAULT_ENDPOINT_TOUCH_THRESHOLD);

// Merges Strokes together ONLY if any point in stroke A is within
// `proximity_threshold` pixels of any point in stroke B (or their
// endpoints are within `endpoint_threshold`). Returns one Stroke per
// touch-cluster, each holding the concatenated points of every original
// Stroke in that cluster (original per-stroke point order preserved,
// clusters in first-appearance order).
std::vector<Stroke> merge_intersecting_strokes(
    const std::vector<Stroke>& strokes, double proximity_threshold = config::DEFAULT_TOUCH_THRESHOLD,
    double endpoint_threshold = config::DEFAULT_ENDPOINT_TOUCH_THRESHOLD);

// OPTIMIZATION FIX C: does the clustering ONCE and returns both the merged
// strokes and the unit count, instead of paying for
// `_cluster_strokes`-equivalent work twice (once via count_touch_units,
// once via merge_intersecting_strokes) the way two separate calls would.
std::pair<std::vector<Stroke>, int> merge_and_count_touch_units(
    const std::vector<Stroke>& strokes, double proximity_threshold = config::DEFAULT_TOUCH_THRESHOLD,
    double endpoint_threshold = config::DEFAULT_ENDPOINT_TOUCH_THRESHOLD);

}  // namespace qrec