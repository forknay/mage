// spatial_index.h
// =============================================================================
// C++ port of spatial_index.py
// =============================================================================
// Buckets items into a 2D grid to reduce collision detection from O(N^2) to
// (amortized) O(N), plus a generic BFS-based connected-components clusterer
// built on top of it. Kept header-only/templated since both callers in this
// project (merge_intersecting_strokes and QRecognizer's feature bundling)
// cluster over plain `int` indices, exactly like the Python version clusters
// over `list(range(n))` in both call sites.
#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <functional>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace qrec {

// Box layout, matching spatial_index.py: (min_x, max_x, min_y, max_y).
using Box = std::array<double, 4>;

template <typename T>
class SpatialGrid {
public:
	explicit SpatialGrid(double cell_size) : cell_size_(std::max(1.0, cell_size)) {}

	// Inserts an item into all cells its bounding box touches.
	void add(const T& item, const Box& box) {
		for (const auto& cell : get_cells(box)) {
			grid_[cell].push_back(item);
		}
	}

	// Retrieves all unique items sharing a grid cell with the given box.
	std::vector<T> get_potential_neighbors(const Box& box) const {
		std::unordered_set<T> seen;
		std::vector<T> result;
		for (const auto& cell : get_cells(box)) {
			auto it = grid_.find(cell);
			if (it == grid_.end()) continue;
			for (const auto& item : it->second) {
				if (seen.insert(item).second) {
					result.push_back(item);
				}
			}
		}
		return result;
	}

private:
	struct CellHash {
		size_t operator()(const std::pair<int, int>& p) const noexcept {
			// Combine row/col into a single 64-bit key before hashing.
			uint64_t packed = (static_cast<uint64_t>(static_cast<uint32_t>(p.first)) << 32) |
							   static_cast<uint32_t>(p.second);
			return std::hash<uint64_t>()(packed);
		}
	};

	double cell_size_;
	std::unordered_map<std::pair<int, int>, std::vector<T>, CellHash> grid_;

	std::vector<std::pair<int, int>> get_cells(const Box& box) const {
		double min_x = box[0], max_x = box[1], min_y = box[2], max_y = box[3];
		int min_col = static_cast<int>(std::floor(min_x / cell_size_));
		int max_col = static_cast<int>(std::floor(max_x / cell_size_));
		int min_row = static_cast<int>(std::floor(min_y / cell_size_));
		int max_row = static_cast<int>(std::floor(max_y / cell_size_));

		std::vector<std::pair<int, int>> cells;
		cells.reserve(static_cast<size_t>(max_row - min_row + 1) * (max_col - min_col + 1));
		for (int r = min_row; r <= max_row; ++r) {
			for (int c = min_col; c <= max_col; ++c) {
				cells.emplace_back(r, c);
			}
		}
		return cells;
	}
};

// Groups `items` using a spatial grid to find connected components
// efficiently -- direct port of SpatialGrid.cluster_spatially (a
// module/classmethod-style function in the Python original; free function
// here since C++ has no equivalent ambiguity between the two call styles
// recognizer.py hedges against with the `try/except AttributeError`).
//
//   get_bbox_fn:    item -> (min_x, max_x, min_y, max_y)
//   is_touching_fn: detailed boolean check to confirm if two items merge
//   threshold:      maximum gap distance allowed for items to be considered
//                    touching
template <typename T>
std::vector<std::vector<T>> cluster_spatially(
	const std::vector<T>& items, const std::function<Box(const T&)>& get_bbox_fn,
	const std::function<bool(const T&, const T&)>& is_touching_fn, double threshold) {
	std::vector<std::vector<T>> clusters;
	if (items.empty()) return clusters;

	// 1. Initialize the grid. Cell size set to the threshold (floored at
	// 10.0, same as the Python original).
	double cell_size = std::max(threshold, 10.0);
	SpatialGrid<T> grid(cell_size);

	// 2. Populate the grid with expanded bounding boxes.
	std::unordered_map<T, Box> item_boxes;
	item_boxes.reserve(items.size());
	for (const auto& item : items) {
		Box box = get_bbox_fn(item);
		Box expanded{box[0] - threshold, box[1] + threshold, box[2] - threshold, box[3] + threshold};
		item_boxes[item] = expanded;
		grid.add(item, expanded);
	}

	// 3. Find connected components using BFS.
	std::unordered_set<T> visited;
	for (const auto& item : items) {
		if (visited.count(item)) continue;

		std::vector<T> current_cluster;
		std::vector<T> queue{item};
		visited.insert(item);

		size_t qi = 0;
		while (qi < queue.size()) {
			T current = queue[qi++];
			current_cluster.push_back(current);

			// Fast path: only check items in overlapping grid cells.
			auto potential_neighbors = grid.get_potential_neighbors(item_boxes[current]);
			for (const auto& neighbor : potential_neighbors) {
				if (!visited.count(neighbor)) {
					// Slow path: perform the actual, accurate geometric check.
					if (is_touching_fn(current, neighbor)) {
						visited.insert(neighbor);
						queue.push_back(neighbor);
					}
				}
			}
		}

		clusters.push_back(std::move(current_cluster));
	}

	return clusters;
}

}  // namespace qrec
