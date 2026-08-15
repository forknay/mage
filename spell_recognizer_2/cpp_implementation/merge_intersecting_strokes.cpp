// merge_intersecting_strokes.cpp
#include "merge_intersecting_strokes.hpp"

#include <algorithm>
#include <cmath>
#include <functional>
#include <limits>
#include <unordered_map>
#include <unordered_set>

#include "spatial_index.hpp"

namespace qrec {

// =============================================================================
// 1. Low-level segment/distance geometry
// =============================================================================

namespace {

// Shortest distance from point (px, py) to the segment [A, B].
double point_to_segment_distance(double px, double py, double ax, double ay, double bx, double by) {
    double dx = bx - ax, dy = by - ay;
    double seg_len_sq = dx * dx + dy * dy;
    if (seg_len_sq <= 1e-12) {
        return std::hypot(px - ax, py - ay);
    }
    double t = ((px - ax) * dx + (py - ay) * dy) / seg_len_sq;
    t = std::max(0.0, std::min(1.0, t));
    double cx = ax + t * dx, cy = ay + t * dy;
    return std::hypot(px - cx, py - cy);
}

// Cross product sign to determine the turn from AB to AC (>0 CCW, <0 CW, 0 collinear).
double orientation(double ax, double ay, double bx, double by, double cx, double cy) {
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
}

// True proper/boundary intersection test between segments A1-A2 and B1-B2.
bool segments_intersect(const Point& a1, const Point& a2, const Point& b1, const Point& b2) {
    double d1 = orientation(b1.x, b1.y, b2.x, b2.y, a1.x, a1.y);
    double d2 = orientation(b1.x, b1.y, b2.x, b2.y, a2.x, a2.y);
    double d3 = orientation(a1.x, a1.y, a2.x, a2.y, b1.x, b1.y);
    double d4 = orientation(a1.x, a1.y, a2.x, a2.y, b2.x, b2.y);

    if (((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))) {
        return true;
    }

    // Collinear / touching-endpoint edge cases: fall back to bounding-box
    // containment checks for each "on the line" case.
    auto on_segment = [](double px, double py, double qx, double qy, double rx, double ry) {
        return (std::min(px, rx) - 1e-9 <= qx && qx <= std::max(px, rx) + 1e-9 &&
                std::min(py, ry) - 1e-9 <= qy && qy <= std::max(py, ry) + 1e-9);
    };

    if (d1 == 0 && on_segment(b1.x, b1.y, a1.x, a1.y, b2.x, b2.y)) return true;
    if (d2 == 0 && on_segment(b1.x, b1.y, a2.x, a2.y, b2.x, b2.y)) return true;
    if (d3 == 0 && on_segment(a1.x, a1.y, b1.x, b1.y, a2.x, a2.y)) return true;
    if (d4 == 0 && on_segment(a1.x, a1.y, b2.x, b2.y, a2.x, a2.y)) return true;

    return false;
}

// Shortest distance between two segments. Returns 0.0 for any true
// crossing/overlap, otherwise the minimum of the four endpoint-to-
// opposite-segment distances -- exact for two straight segments.
double segment_segment_distance(const Point& a1, const Point& a2, const Point& b1, const Point& b2) {
    if (segments_intersect(a1, a2, b1, b2)) {
        return 0.0;
    }
    return std::min({
        point_to_segment_distance(a1.x, a1.y, b1.x, b1.y, b2.x, b2.y),
        point_to_segment_distance(a2.x, a2.y, b1.x, b1.y, b2.x, b2.y),
        point_to_segment_distance(b1.x, b1.y, a1.x, a1.y, a2.x, a2.y),
        point_to_segment_distance(b2.x, b2.y, a1.x, a1.y, a2.x, a2.y),
    });
}

// =============================================================================
// 2. Stroke clustering
// =============================================================================

// Returns (min_x, max_x, min_y, max_y) for a single two-point segment.
// Deliberately a direct 2-value comparison, not routed through
// bounding_box(), matching the Python original's rationale (called once
// per segment inside the O(n*m) pair loop).
Box segment_bbox(const Point& a, const Point& b) {
    return Box{
        a.x <= b.x ? a.x : b.x, a.x >= b.x ? a.x : b.x,
        a.y <= b.y ? a.y : b.y, a.y >= b.y ? a.y : b.y,
    };
}

bool bboxes_within_threshold_impl(const Box& box_a, const Box& box_b, double threshold) {
    double min_x_a = box_a[0], max_x_a = box_a[1], min_y_a = box_a[2], max_y_a = box_a[3];
    double min_x_b = box_b[0], max_x_b = box_b[1], min_y_b = box_b[2], max_y_b = box_b[3];
    if (max_x_a < min_x_b - threshold || min_x_a > max_x_b + threshold) return false;
    if (max_y_a < min_y_b - threshold || min_y_a > max_y_b + threshold) return false;
    return true;
}

// Cheap, generous check: does EITHER endpoint (first or last recorded
// point) of point-run A land within `endpoint_threshold` of EITHER
// endpoint of point-run B? Deliberately tip-to-tip only.
bool endpoints_touch(const std::vector<Point>& pts_a, const std::vector<Point>& pts_b,
                      double endpoint_threshold) {
    const Point* endpoints_a[2] = {&pts_a.front(), &pts_a.back()};
    const Point* endpoints_b[2] = {&pts_b.front(), &pts_b.back()};
    for (const Point* pa : endpoints_a) {
        for (const Point* pb : endpoints_b) {
            if (std::hypot(pa->x - pb->x, pa->y - pb->y) <= endpoint_threshold) {
                return true;
            }
        }
    }
    return false;
}

// Thins `points` for TOUCH-TESTING ONLY -- never used for recognition or
// scoring. Keeps the stroke's first and last point unconditionally, and
// otherwise keeps a point only once it's at least `min_spacing` away from
// the last KEPT point. No-op below `min_points` (or non-positive spacing).
std::vector<Point> decimate_points_for_touch(
    const std::vector<Point>& points, double min_spacing,
    int min_points = config::DEFAULT_TOUCH_DECIMATION_MIN_POINTS) {
    if (static_cast<int>(points.size()) <= min_points || min_spacing <= 0) {
        return points;
    }

    std::vector<Point> kept;
    kept.push_back(points.front());
    for (size_t i = 1; i + 1 < points.size(); ++i) {
        const Point& p = points[i];
        const Point& last_kept = kept.back();
        if (std::hypot(p.x - last_kept.x, p.y - last_kept.y) >= min_spacing) {
            kept.push_back(p);
        }
    }
    // The Python original guards this append with `points[-1] is not
    // kept[-1]` (an object-identity check). Since this loop only ever
    // walks `points[1:-1]` (interior points), `kept.back()` can never
    // actually *be* `points.back()` at this point unless the whole
    // function is called on a single-point list -- a case already routed
    // around by the `len(points) <= min_points` early-out above (this
    // path only runs when there are more than
    // DEFAULT_TOUCH_DECIMATION_MIN_POINTS points). So the guard is always
    // true here in practice, and the last point is unconditionally kept,
    // matching observed behavior exactly.
    kept.push_back(points.back());
    return kept;
}

// Forward declaration for the grid-indexed touch test.
bool strokes_touch_grid(const std::vector<std::pair<Point, Point>>& segs_a, const std::vector<Box>& boxes_a,
                         const std::vector<std::pair<Point, Point>>& segs_b, const std::vector<Box>& boxes_b,
                         double threshold);

// Detailed check for whether two point-runs should be merged as touching.
// Two passes: (1) endpoints_touch at the looser endpoint_threshold, (2) an
// exhaustive (or grid-accelerated, for long strokes) segment-pair test at
// the tighter `threshold`.
bool strokes_touch_impl(const std::vector<Point>& pts_a, const std::vector<Point>& pts_b, double threshold,
                         double endpoint_threshold) {
    if (endpoints_touch(pts_a, pts_b, endpoint_threshold)) {
        return true;
    }

    std::vector<std::pair<Point, Point>> segs_a, segs_b;
    if (pts_a.size() >= 2) {
        segs_a.reserve(pts_a.size() - 1);
        for (size_t i = 0; i + 1 < pts_a.size(); ++i) segs_a.emplace_back(pts_a[i], pts_a[i + 1]);
    } else {
        segs_a.emplace_back(pts_a[0], pts_a[0]);
    }
    if (pts_b.size() >= 2) {
        segs_b.reserve(pts_b.size() - 1);
        for (size_t i = 0; i + 1 < pts_b.size(); ++i) segs_b.emplace_back(pts_b[i], pts_b[i + 1]);
    } else {
        segs_b.emplace_back(pts_b[0], pts_b[0]);
    }

    std::vector<Box> boxes_a, boxes_b;
    boxes_a.reserve(segs_a.size());
    for (const auto& s : segs_a) boxes_a.push_back(segment_bbox(s.first, s.second));
    boxes_b.reserve(segs_b.size());
    for (const auto& s : segs_b) boxes_b.push_back(segment_bbox(s.first, s.second));

    if (static_cast<long long>(segs_a.size()) * static_cast<long long>(segs_b.size()) >
        config::DEFAULT_TOUCH_GRID_MIN_SEGMENT_PRODUCT) {
        return strokes_touch_grid(segs_a, boxes_a, segs_b, boxes_b, threshold);
    }

    for (size_t i = 0; i < segs_a.size(); ++i) {
        const Box& box_a = boxes_a[i];
        for (size_t j = 0; j < segs_b.size(); ++j) {
            const Box& box_b = boxes_b[j];
            if (!bboxes_within_threshold_impl(box_a, box_b, threshold)) continue;
            if (segment_segment_distance(segs_a[i].first, segs_a[i].second, segs_b[j].first, segs_b[j].second) <=
                threshold) {
                return true;
            }
        }
    }
    return false;
}

// Grid-indexed version of the segment-pair touch test -- structural fix
// for the O(len(A) * len(B)) cost of two long, broadly-overlapping
// strokes. Reuses SpatialGrid, indexed over segment indices of B.
bool strokes_touch_grid(const std::vector<std::pair<Point, Point>>& segs_a, const std::vector<Box>& boxes_a,
                         const std::vector<std::pair<Point, Point>>& segs_b, const std::vector<Box>& boxes_b,
                         double threshold) {
    SpatialGrid<int> grid(threshold);
    for (size_t idx = 0; idx < boxes_b.size(); ++idx) {
        const Box& box = boxes_b[idx];
        Box expanded{box[0] - threshold, box[1] + threshold, box[2] - threshold, box[3] + threshold};
        grid.add(static_cast<int>(idx), expanded);
    }

    for (size_t i = 0; i < segs_a.size(); ++i) {
        const Box& box_a = boxes_a[i];
        Box expanded_a{box_a[0] - threshold, box_a[1] + threshold, box_a[2] - threshold, box_a[3] + threshold};
        for (int idx : grid.get_potential_neighbors(expanded_a)) {
            const auto& sb = segs_b[static_cast<size_t>(idx)];
            if (segment_segment_distance(segs_a[i].first, segs_a[i].second, sb.first, sb.second) <= threshold) {
                return true;
            }
        }
    }
    return false;
}

// Core proximity clustering over Stroke objects. Returns
// {index_into_strokes: cluster_root_index}.
std::unordered_map<int, int> cluster_strokes(const std::vector<Stroke>& strokes, double proximity_threshold,
                                              double endpoint_threshold) {
    std::unordered_map<int, int> root_of;
    int n = static_cast<int>(strokes.size());
    if (n == 0) return root_of;
    if (n <= 1) {
        for (int i = 0; i < n; ++i) root_of[i] = i;
        return root_of;
    }

    // 1. Bounding boxes, always from each stroke's full, undecimated points.
    std::vector<Box> boxes(n);
    for (int i = 0; i < n; ++i) {
        boxes[i] = bounding_box(strokes[i].points);
    }

    // 2. Thin each stroke's points ONCE, up front, for touch-testing only.
    double decimation_spacing = proximity_threshold / config::DEFAULT_TOUCH_DECIMATION_SPACING_DIVISOR;
    std::vector<std::vector<Point>> touch_test_points(n);
    for (int i = 0; i < n; ++i) {
        touch_test_points[i] = decimate_points_for_touch(strokes[i].points, decimation_spacing);
    }

    // 3. Spatial-index-accelerated BFS clustering.
    std::vector<int> items(n);
    for (int i = 0; i < n; ++i) items[i] = i;

    std::function<Box(const int&)> get_bbox_fn = [&boxes](const int& i) { return boxes[i]; };
    std::function<bool(const int&, const int&)> is_touching_fn = [&](const int& a, const int& b) {
        return strokes_touch_impl(touch_test_points[a], touch_test_points[b], proximity_threshold,
                                   endpoint_threshold);
    };

    double search_radius = std::max(proximity_threshold, endpoint_threshold);
    auto clusters = cluster_spatially<int>(items, get_bbox_fn, is_touching_fn, search_radius);

    // 4. Convert clustered lists back into {index: root_index} format.
    for (const auto& cluster : clusters) {
        int root = cluster.front();
        for (int i : cluster) {
            root_of[i] = root;
        }
    }
    return root_of;
}

}  // namespace

// =============================================================================
// 3. Public API
// =============================================================================

Box bounding_box(const std::vector<Point>& points) {
    double min_x = std::numeric_limits<double>::infinity();
    double max_x = -std::numeric_limits<double>::infinity();
    double min_y = std::numeric_limits<double>::infinity();
    double max_y = -std::numeric_limits<double>::infinity();
    for (const auto& p : points) {
        min_x = std::min(min_x, p.x);
        max_x = std::max(max_x, p.x);
        min_y = std::min(min_y, p.y);
        max_y = std::max(max_y, p.y);
    }
    return Box{min_x, max_x, min_y, max_y};
}

bool bounding_boxes_within_threshold(const Box& box_a, const Box& box_b, double threshold) {
    return bboxes_within_threshold_impl(box_a, box_b, threshold);
}

bool strokes_touch(const std::vector<Point>& pts_a, const std::vector<Point>& pts_b, double threshold,
                    double endpoint_threshold) {
    return strokes_touch_impl(pts_a, pts_b, threshold, endpoint_threshold);
}

std::vector<std::vector<Stroke>> group_strokes_by_proximity(const std::vector<Stroke>& strokes,
                                                              double proximity_threshold,
                                                              double endpoint_threshold) {
    if (strokes.empty()) return {};

    auto root_of = cluster_strokes(strokes, proximity_threshold, endpoint_threshold);

    std::unordered_map<int, std::vector<Stroke>> clusters;
    std::vector<int> order;
    for (size_t i = 0; i < strokes.size(); ++i) {
        int root = root_of[static_cast<int>(i)];
        if (clusters.find(root) == clusters.end()) {
            clusters[root] = {};
            order.push_back(root);
        }
        clusters[root].push_back(strokes[i]);
    }

    std::vector<std::vector<Stroke>> result;
    result.reserve(order.size());
    for (int root : order) result.push_back(clusters[root]);
    return result;
}

int count_touch_units(const std::vector<Stroke>& strokes, double proximity_threshold, double endpoint_threshold) {
    return static_cast<int>(group_strokes_by_proximity(strokes, proximity_threshold, endpoint_threshold).size());
}

std::vector<Stroke> merge_intersecting_strokes(const std::vector<Stroke>& strokes, double proximity_threshold,
                                                double endpoint_threshold) {
    if (strokes.empty()) return {};
    if (strokes.size() <= 1) return strokes;  // Nothing to merge

    auto root_of = cluster_strokes(strokes, proximity_threshold, endpoint_threshold);

    std::unordered_map<int, std::vector<Point>> root_to_points;
    std::vector<int> root_order;
    for (size_t i = 0; i < strokes.size(); ++i) {
        int root = root_of[static_cast<int>(i)];
        if (root_to_points.find(root) == root_to_points.end()) {
            root_to_points[root] = {};
            root_order.push_back(root);
        }
        auto& dst = root_to_points[root];
        dst.insert(dst.end(), strokes[i].points.begin(), strokes[i].points.end());
    }

    std::vector<Stroke> result;
    result.reserve(root_order.size());
    for (int root : root_order) result.emplace_back(std::move(root_to_points[root]));
    return result;
}

std::pair<std::vector<Stroke>, int> merge_and_count_touch_units(const std::vector<Stroke>& strokes,
                                                                  double proximity_threshold,
                                                                  double endpoint_threshold) {
    if (strokes.empty()) return {{}, 0};
    if (strokes.size() <= 1) return {strokes, static_cast<int>(strokes.size())};

    auto root_of = cluster_strokes(strokes, proximity_threshold, endpoint_threshold);

    std::unordered_map<int, std::vector<Point>> root_to_points;
    std::vector<int> root_order;
    for (size_t i = 0; i < strokes.size(); ++i) {
        int root = root_of[static_cast<int>(i)];
        if (root_to_points.find(root) == root_to_points.end()) {
            root_to_points[root] = {};
            root_order.push_back(root);
        }
        auto& dst = root_to_points[root];
        dst.insert(dst.end(), strokes[i].points.begin(), strokes[i].points.end());
    }

    std::vector<Stroke> merged;
    merged.reserve(root_order.size());
    for (int root : root_order) merged.emplace_back(std::move(root_to_points[root]));
    int count = static_cast<int>(merged.size());
    return {std::move(merged), count};
}

}  // namespace qrec