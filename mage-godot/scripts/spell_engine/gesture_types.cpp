// gesture_types.cpp
#include "scripts/spell_engine/gesture_types.hpp"

#include <algorithm>
#include <atomic>
#include <limits>

namespace qrec {

namespace {
// Mirrors gesture_types.py's module-level `_stroke_seq_counter =
// itertools.count()` -- a single process-wide monotonic counter shared by
// every Stroke ever constructed.
std::atomic<int64_t> g_stroke_seq_counter{0};
}  // namespace

int64_t next_stroke_seq() {
	return g_stroke_seq_counter.fetch_add(1, std::memory_order_relaxed);
}

Stroke::Stroke(std::vector<Point> pts) : points(std::move(pts)), seq(next_stroke_seq()) {}

Stroke stroke_from_points(const std::vector<Point>& points) {
	// Explicit copy of `points` into the new Stroke, matching
	// gesture_types.stroke_from_points's documented safety rationale.
	return Stroke(std::vector<Point>(points));
}

const std::array<double, 4>& Feature::bounding_box() const {
	if (!bbox_cache.has_value()) {
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
		bbox_cache = std::array<double, 4>{min_x, max_x, min_y, max_y};
	}
	return *bbox_cache;
}

}  // namespace qrec
