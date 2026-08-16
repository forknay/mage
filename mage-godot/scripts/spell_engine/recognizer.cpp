// recognizer.cpp
#include "scripts/spell_engine/recognizer.hpp"

#include <algorithm>
#include <cmath>
#include <deque>
#include <numeric>
#include <set>
#include <stdexcept>
#include <JenovaSDK.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

namespace qrec {

namespace {
// ---------------------------------------------------------------------------
// TEMP DEBUG SWITCH
// ---------------------------------------------------------------------------
// While `true`, every recognition that found *any* best-matching template is
// treated as accepted, regardless of how low its score was against that
// template's min_score. This exists purely so features/spells surface while
// you're iterating on templates, without also having to fight min_score
// tuning at the same time. Flip back to `false` once you're done debugging
// -- shipping with this on means the recognizer accepts literally anything.
constexpr bool kDisableRecognitionThreshold = true;
}  // namespace

// =============================================================================
// Construction
// =============================================================================

QRecognizer::QRecognizer(int num_resample_points, double frame_size, int lut_size, double touch_threshold,
						  double endpoint_touch_threshold,
						  const std::unordered_map<int, double>* level_merge_thresholds,
						  double aspect_ratio_weight, double cloud_distance_penalty_threshold,
						  double cloud_distance_exponent, double cloud_distance_max_weight)
	: n_(num_resample_points),
	  frame_size_(frame_size),
	  lut_size_(lut_size),
	  max_distance_(std::hypot(frame_size, frame_size)),
	  touch_threshold_(touch_threshold),
	  endpoint_touch_threshold_(endpoint_touch_threshold),
	  aspect_ratio_weight_(aspect_ratio_weight),
	  cloud_distance_penalty_threshold_(cloud_distance_penalty_threshold),
	  cloud_distance_exponent_(cloud_distance_exponent),
	  cloud_distance_max_weight_(cloud_distance_max_weight) {
	// level_merge_thresholds = {**DEFAULT_LEVEL_MERGE_THRESHOLDS, **(level_merge_thresholds or {})}
	level_merge_thresholds_ = config::DEFAULT_LEVEL_MERGE_THRESHOLDS;
	if (level_merge_thresholds != nullptr) {
		for (const auto& kv : *level_merge_thresholds) {
			level_merge_thresholds_[kv.first] = kv.second;
		}
	}

	// Maximum gap across all composition levels.
	max_gap_ = std::max(touch_threshold_, endpoint_touch_threshold_);
	for (const auto& kv : level_merge_thresholds_) {
		max_gap_ = std::max(max_gap_, kv.second);
	}
	// Maximum gap for physical Level-1 touch.
	atomic_gap_ = std::max(touch_threshold_, endpoint_touch_threshold_);
}

// =============================================================================
// Public APIs: Template Registration
// =============================================================================

void QRecognizer::add_template(const std::string& name, const std::vector<Stroke>& strokes, int level,
								double min_score) {
	auto [merged_strokes, actual_units] = merge_and_count_touch_units(strokes, touch_threshold_, endpoint_touch_threshold_);

	int resolved_level = level;
	if (level < 0) {
		resolved_level = actual_units;
	} else if (level != actual_units) {
		throw std::invalid_argument("Template '" + name + "' resolves to " + std::to_string(actual_units) +
									 " stroke unit(s) but was registered with level=" + std::to_string(level) + ".");
	}

	std::vector<Point> all_points;
	for (const auto& s : strokes) all_points.insert(all_points.end(), s.points.begin(), s.points.end());
	double aspect_ratio = compute_aspect_ratio(all_points);

	std::vector<Point> processed = preprocess(merged_strokes, resolved_level, /*already_merged=*/true);
	std::vector<double> xs, ys;
	xy(processed, &xs, &ys);
	std::vector<int64_t> lut = create_lut(xs, ys);

	Template t;
	t.name = name;
	t.points = processed;
	t.xs = xs;
	t.ys = ys;
	t.lut = lut;
	t.lut_size = lut_size_;
	t.level = resolved_level;
	t.aspect_ratio = aspect_ratio;
	t.min_score = min_score;
	templates_.push_back(std::move(t));
}

void QRecognizer::add_precomputed_template(const std::string& name, const std::vector<Point>& processed_points,
											const std::vector<int64_t>& lut, int level, double aspect_ratio,
											double min_score) {
	std::vector<double> xs, ys;
	xy(processed_points, &xs, &ys);

	Template t;
	t.name = name;
	t.points = processed_points;
	t.xs = xs;
	t.ys = ys;
	t.lut = lut;
	t.lut_size = lut_size_;
	t.level = level;
	t.aspect_ratio = aspect_ratio;
	t.min_score = min_score;
	templates_.push_back(std::move(t));
}

// =============================================================================
// Public APIs: Batch & Single-Gesture Recognition
// =============================================================================

RecognitionResult QRecognizer::recognize(const std::vector<Stroke>& strokes, int level,
										  const std::vector<std::string>* candidate_names) const {
	if (templates_.empty()) {
		jenova::sdk::Output("recognize: no templates registered");
	}

	auto candidates = candidates_at_level(level, candidate_names);

	auto [merged_strokes, actual_units] = merge_and_count_touch_units(strokes, touch_threshold_, endpoint_touch_threshold_);

	if (actual_units != level) {
		jenova::sdk::Output("recognize: cannot classify at level=%d: input has %d units", level, actual_units);
		throw std::invalid_argument("Cannot classify at level=" + std::to_string(level) + ": input has " +
									 std::to_string(actual_units) + " units.");
	}

	std::vector<Point> all_points;
	for (const auto& s : strokes) all_points.insert(all_points.end(), s.points.begin(), s.points.end());
	double cand_aspect_ratio = compute_aspect_ratio(all_points);

	std::vector<Point> processed = preprocess(merged_strokes, level, /*already_merged=*/true);

	auto [best_template, best_distance, best_score] = best_matching_template(processed, cand_aspect_ratio, candidates);

	RecognitionResult result;
	if (best_template != nullptr) {
		result.name = best_template->name;
		result.min_score = best_template->min_score;
	}
	result.score = best_score;
	result.distance = best_distance;
	result.accepted = (best_template != nullptr) && (kDisableRecognitionThreshold || best_score >= best_template->min_score);
	jenova::sdk::Output("recognize: best_template: %s", best_template ? best_template->name.c_str() : "none");
	return result;
}

std::vector<std::shared_ptr<Feature>> QRecognizer::recognize_scene(
	const std::vector<Stroke>& strokes, const std::unordered_map<int, double>* level_merge_thresholds,
	double min_score) const {
	if (strokes.empty() || templates_.empty()) {
		return {};
	}

	auto current_features = recognize_atomic_clusters(strokes);
	return compose_from_atomic(current_features, level_merge_thresholds, min_score, /*touch_cache=*/nullptr);
}

// =============================================================================
// Public APIs: Incremental Canvas Recognition
// =============================================================================

std::vector<std::shared_ptr<Feature>> QRecognizer::features() const {
	std::vector<std::shared_ptr<Feature>> result;
	for (const auto& g : groups_) {
		result.insert(result.end(), g.features.begin(), g.features.end());
	}
	return result;
}

std::vector<std::shared_ptr<Feature>> QRecognizer::atomic_features() const {
	std::vector<std::shared_ptr<Feature>> result;
	for (const auto& g : groups_) {
		result.insert(result.end(), g.atomic_features.begin(), g.atomic_features.end());
	}
	return result;
}

std::vector<std::shared_ptr<Feature>> QRecognizer::add_stroke(const Stroke& stroke) {
	if (stroke.points.empty()) {
		return features();
	}

	Box new_box = bounding_box(stroke.points);

	std::vector<int> touched_indices;
	for (size_t i = 0; i < groups_.size(); ++i) {
		bool group_touched = false;
		for (const auto& feat : groups_[i].atomic_features) {
			if (bounding_boxes_within_threshold(new_box, feat->bounding_box(), max_gap_)) {
				group_touched = true;
				break;
			}
		}
		if (group_touched) touched_indices.push_back(static_cast<int>(i));
	}

	std::vector<IncrementalGroup> remaining_groups;
	{
		std::set<int> touched_set(touched_indices.begin(), touched_indices.end());
		for (size_t i = 0; i < groups_.size(); ++i) {
			if (touched_set.find(static_cast<int>(i)) == touched_set.end()) {
				remaining_groups.push_back(groups_[i]);
			}
		}
	}

	std::vector<Stroke> atomic_recompute_strokes;
	atomic_recompute_strokes.push_back(stroke);
	std::vector<std::shared_ptr<Feature>> reused_atomic_features;

	for (int i : touched_indices) {
		for (const auto& feat : groups_[static_cast<size_t>(i)].atomic_features) {
			if (bounding_boxes_within_threshold(new_box, feat->bounding_box(), atomic_gap_)) {
				atomic_recompute_strokes.insert(atomic_recompute_strokes.end(), feat->strokes.begin(),
												 feat->strokes.end());
			} else {
				reused_atomic_features.push_back(feat);
			}
		}
	}

	// Preserve chronological stroke ordering via each Stroke's own
	// creation-order `seq`.
	std::stable_sort(atomic_recompute_strokes.begin(), atomic_recompute_strokes.end(),
					  [](const Stroke& a, const Stroke& b) { return a.seq < b.seq; });

	auto new_atomic_features = recognize_atomic_clusters(atomic_recompute_strokes);

	std::vector<std::shared_ptr<Feature>> combined_atomic_features = new_atomic_features;
	combined_atomic_features.insert(combined_atomic_features.end(), reused_atomic_features.begin(),
									 reused_atomic_features.end());
	// Precompute each feature's sort key (min seq across its strokes) ONCE
	// up front -- mirrors Python's `sort(key=...)`, which also only calls
	// the key function once per element, rather than recomputing it on
	// every comparison a naive comparator-based sort would.
	{
		std::vector<std::pair<int64_t, std::shared_ptr<Feature>>> keyed;
		keyed.reserve(combined_atomic_features.size());
		for (const auto& f : combined_atomic_features) {
			int64_t min_seq = std::numeric_limits<int64_t>::max();
			for (const auto& s : f->strokes) min_seq = std::min(min_seq, s.seq);
			keyed.emplace_back(min_seq, f);
		}
		std::stable_sort(keyed.begin(), keyed.end(),
						  [](const auto& a, const auto& b) { return a.first < b.first; });
		combined_atomic_features.clear();
		for (auto& kv : keyed) combined_atomic_features.push_back(std::move(kv.second));
	}

	auto new_features = compose_from_atomic(combined_atomic_features, /*level_merge_thresholds=*/nullptr,
											 /*min_score=*/0.0, &touch_cache_);

	IncrementalGroup new_group;
	new_group.atomic_features = combined_atomic_features;
	new_group.features = new_features;
	remaining_groups.push_back(std::move(new_group));

	groups_ = std::move(remaining_groups);
	for (const auto& g : groups_) {
		for (const auto& f : g.features) {
			f->cluster_id = static_cast<int>(&g - &groups_[0]);
		}
	}
	jenova::sdk::Output("Feature recognized:");
	for (const auto& g : groups_) {
		for (const auto& f : g.features) {
			if (f->result.name.has_value()) {
				std::string line = f->result.name.value() + " (score=" + std::to_string(f->result.score) + ")";
				jenova::sdk::Output(line.c_str());
			}
		}
	}

	return features();
}

void QRecognizer::clear() {
	groups_.clear();
	touch_cache_.clear();
}

// =============================================================================
// Core Pipeline: Recognition & Composition Helpers
// =============================================================================

std::vector<std::shared_ptr<Feature>> QRecognizer::recognize_atomic_clusters(const std::vector<Stroke>& strokes) const {
	auto atomic_clusters = group_strokes_by_proximity(strokes, touch_threshold_, endpoint_touch_threshold_);

	std::vector<std::shared_ptr<Feature>> features_out;
	features_out.reserve(atomic_clusters.size());
	for (size_t cluster_id = 0; cluster_id < atomic_clusters.size(); ++cluster_id) {
		const auto& cluster_strokes = atomic_clusters[cluster_id];
		auto result_opt = try_recognize(cluster_strokes, /*level=*/1);

		std::vector<Point> cluster_points;
		for (const auto& s : cluster_strokes) cluster_points.insert(cluster_points.end(), s.points.begin(), s.points.end());

		auto feat = std::make_shared<Feature>();
		feat->cluster_id = static_cast<int>(cluster_id);
		feat->level = 1;
		if (result_opt.has_value()) {
			feat->result = *result_opt;
		} else {
			feat->result = RecognitionResult{std::nullopt, 0.0, std::numeric_limits<double>::infinity(), 0.0, false};
		}
		feat->points = std::move(cluster_points);
		feat->strokes = cluster_strokes;
		features_out.push_back(std::move(feat));
	}
	return features_out;
}

std::vector<std::shared_ptr<Feature>> QRecognizer::compose_from_atomic(
	const std::vector<std::shared_ptr<Feature>>& atomic_features,
	const std::unordered_map<int, double>* level_merge_thresholds, double min_score,
	std::unordered_map<std::pair<const Feature*, const Feature*>, bool, FeaturePtrPairHash>* touch_cache) const {
	if (atomic_features.empty() || templates_.empty()) {
		return {};
	}

	std::unordered_map<int, double> thresholds = level_merge_thresholds_;
	if (level_merge_thresholds != nullptr) {
		for (const auto& kv : *level_merge_thresholds) thresholds[kv.first] = kv.second;
	}

	std::set<int> levels_present;
	for (const auto& t : templates_) levels_present.insert(t.level);

	std::vector<std::shared_ptr<Feature>> current_features = atomic_features;
	for (int target_level : levels_present) {
		if (target_level == 1) continue;
		double gap = touch_threshold_;
		auto it = thresholds.find(target_level);
		if (it != thresholds.end()) gap = it->second;
		current_features = compose_level(current_features, target_level, gap, touch_cache);
	}

	std::vector<std::shared_ptr<Feature>> out;
	for (const auto& f : current_features) {
		if (f->result.accepted && f->result.score >= min_score) out.push_back(f);
	}
	return out;
}

std::vector<std::shared_ptr<Feature>> QRecognizer::compose_level(
	const std::vector<std::shared_ptr<Feature>>& current_features, int target_level, double gap,
	std::unordered_map<std::pair<const Feature*, const Feature*>, bool, FeaturePtrPairHash>* touch_cache) const {
	auto groups = bundle_features_by_proximity(current_features, gap, touch_cache);
	std::vector<std::shared_ptr<Feature>> next_features;

	for (const auto& group : groups) {
		int total_units = 0;
		for (const auto& feat : group) total_units += feat->level;

		if (group.size() > 1 && total_units == target_level) {
			std::vector<Stroke> combined_strokes;
			for (const auto& feat : group) combined_strokes.insert(combined_strokes.end(), feat->strokes.begin(), feat->strokes.end());

			auto result_opt = try_recognize(combined_strokes, target_level);
			if (result_opt.has_value() && result_opt->accepted) {
				std::vector<Point> combined_points;
				for (const auto& feat : group) combined_points.insert(combined_points.end(), feat->points.begin(), feat->points.end());

				auto feat_out = std::make_shared<Feature>();
				feat_out->cluster_id = group.front()->cluster_id;
				feat_out->level = target_level;
				feat_out->result = *result_opt;
				feat_out->points = std::move(combined_points);
				feat_out->strokes = std::move(combined_strokes);
				feat_out->components = group;
				next_features.push_back(std::move(feat_out));
				continue;
			}
		}

		next_features.insert(next_features.end(), group.begin(), group.end());
	}

	return next_features;
}

std::vector<std::vector<std::shared_ptr<Feature>>> QRecognizer::bundle_features_by_proximity(
	const std::vector<std::shared_ptr<Feature>>& features_in, double threshold,
	std::unordered_map<std::pair<const Feature*, const Feature*>, bool, FeaturePtrPairHash>* touch_cache) const {
	if (features_in.empty()) return {};
	if (features_in.size() == 1) return {{features_in[0]}};

	auto is_touching = [&](const int& i, const int& j) -> bool {
		const Feature* feat_a = features_in[static_cast<size_t>(i)].get();
		const Feature* feat_b = features_in[static_cast<size_t>(j)].get();
		std::pair<const Feature*, const Feature*> key =
			(feat_a < feat_b) ? std::make_pair(feat_a, feat_b) : std::make_pair(feat_b, feat_a);

		if (touch_cache != nullptr) {
			auto it = touch_cache->find(key);
			if (it != touch_cache->end()) return it->second;
		}
		bool result = strokes_touch(feat_a->points, feat_b->points, threshold, config::DEFAULT_ENDPOINT_TOUCH_THRESHOLD);
		if (touch_cache != nullptr) {
			(*touch_cache)[key] = result;
		}
		return result;
	};

	std::vector<int> items(features_in.size());
	std::iota(items.begin(), items.end(), 0);

	std::function<Box(const int&)> get_bbox_fn = [&features_in](const int& i) {
		return features_in[static_cast<size_t>(i)]->bounding_box();
	};
	std::function<bool(const int&, const int&)> is_touching_fn = is_touching;

	double search_radius = std::max(threshold, config::DEFAULT_ENDPOINT_TOUCH_THRESHOLD);
	auto index_clusters = cluster_spatially<int>(items, get_bbox_fn, is_touching_fn, search_radius);

	std::vector<std::vector<std::shared_ptr<Feature>>> result;
	result.reserve(index_clusters.size());
	for (auto& idxs : index_clusters) {
		std::sort(idxs.begin(), idxs.end());
		std::vector<std::shared_ptr<Feature>> group;
		group.reserve(idxs.size());
		for (int idx : idxs) group.push_back(features_in[static_cast<size_t>(idx)]);
		result.push_back(std::move(group));
	}
	return result;
}

std::vector<const Template*> QRecognizer::candidates_at_level(int level,
																const std::vector<std::string>* candidate_names) const {
	std::vector<const Template*> candidates;
	for (const auto& t : templates_) {
		if (t.level == level) candidates.push_back(&t);
	}
	if (candidate_names != nullptr) {
		std::vector<const Template*> filtered;
		for (const auto* t : candidates) {
			if (std::find(candidate_names->begin(), candidate_names->end(), t->name) != candidate_names->end()) {
				filtered.push_back(t);
			}
		}
		candidates = std::move(filtered);
	}
	if (candidates.empty()) {
		throw std::invalid_argument("No templates registered at level=" + std::to_string(level) +
									 " matching candidate names.");
	}
	return candidates;
}

std::optional<RecognitionResult> QRecognizer::try_recognize(const std::vector<Stroke>& strokes, int level) const {
	try {
		return recognize(strokes, level);
	} catch (const std::invalid_argument&) {
		return std::nullopt;
	}
}

std::tuple<const Template*, double, double> QRecognizer::best_matching_template(
	const std::vector<Point>& processed, double cand_aspect_ratio, const std::vector<const Template*>& candidates) const {
	std::vector<std::pair<double, const Template*>> ar_penalties;
	ar_penalties.reserve(candidates.size());
	for (const auto* tmpl : candidates) {
		double ar_diff = std::abs(cand_aspect_ratio - tmpl->aspect_ratio);
		double ar_penalty = std::exp(-aspect_ratio_weight_ * (ar_diff * ar_diff));
		ar_penalties.emplace_back(ar_penalty, tmpl);
	}

	std::stable_sort(ar_penalties.begin(), ar_penalties.end(),
					  [](const auto& a, const auto& b) { return a.first > b.first; });

	const Template* best_template = nullptr;
	double best_distance = std::numeric_limits<double>::infinity();
	double best_score = -1.0;

	std::vector<double> cand_xs, cand_ys;
	xy(processed, &cand_xs, &cand_ys);
	std::vector<int64_t> candidate_lut = create_lut(cand_xs, cand_ys);

	for (const auto& pair : ar_penalties) {
		double ar_penalty = pair.first;
		const Template* tmpl = pair.second;
		if (ar_penalty <= best_score) break;

		double distance = bidirectional_cloud_distance_hausdorff(cand_xs, cand_ys, tmpl->xs, tmpl->ys, tmpl->lut,
																   candidate_lut);

		double raw_score = std::max(0.0, 1.0 - distance / max_distance_);
		double final_score = raw_score * ar_penalty;

		if (final_score > best_score) {
			best_score = final_score;
			best_distance = distance;
			best_template = tmpl;
		}
	}

	return {best_template, best_distance, best_score};
}

// =============================================================================
// Distance Calculations (vectorized-equivalent, plain loops)
// =============================================================================

double QRecognizer::bidirectional_cloud_distance_hausdorff(const std::vector<double>& cand_xs,
															 const std::vector<double>& cand_ys,
															 const std::vector<double>& temp_xs,
															 const std::vector<double>& temp_ys,
															 const std::vector<int64_t>& lut,
															 const std::vector<int64_t>& candidate_lut) const {
	double d_cand_to_temp = cloud_distance(cand_xs, cand_ys, temp_xs, temp_ys, lut);
	double d_temp_to_cand = reverse_cloud_distance(temp_xs, temp_ys, cand_xs, cand_ys, candidate_lut);
	return std::max(d_cand_to_temp, d_temp_to_cand);
}

double QRecognizer::cloud_distance(const std::vector<double>& cand_xs, const std::vector<double>& cand_ys,
									const std::vector<double>& temp_xs, const std::vector<double>& temp_ys,
									const std::vector<int64_t>& lut, std::optional<double> penalty_threshold,
									std::optional<double> exponent, std::optional<double> max_dist_weight) const {
	auto matched_idx = grid_lookup(cand_xs, cand_ys, lut);
	std::vector<double> dists(cand_xs.size());
	for (size_t i = 0; i < cand_xs.size(); ++i) {
		int64_t mi = matched_idx[i];
		double tx = temp_xs[static_cast<size_t>(mi)];
		double ty = temp_ys[static_cast<size_t>(mi)];
		dists[i] = std::hypot(cand_xs[i] - tx, cand_ys[i] - ty);
	}
	return blend_avg_max(dists, penalty_threshold.value_or(cloud_distance_penalty_threshold_),
						  exponent.value_or(cloud_distance_exponent_),
						  max_dist_weight.value_or(cloud_distance_max_weight_));
}

double QRecognizer::reverse_cloud_distance(const std::vector<double>& temp_xs, const std::vector<double>& temp_ys,
											const std::vector<double>& cand_xs, const std::vector<double>& cand_ys,
											const std::vector<int64_t>& candidate_lut,
											std::optional<double> penalty_threshold, std::optional<double> exponent,
											std::optional<double> max_dist_weight) const {
	auto matched_idx = grid_lookup(temp_xs, temp_ys, candidate_lut);
	std::vector<double> dists(temp_xs.size());
	for (size_t i = 0; i < temp_xs.size(); ++i) {
		int64_t mi = matched_idx[i];
		double cx = cand_xs[static_cast<size_t>(mi)];
		double cy = cand_ys[static_cast<size_t>(mi)];
		dists[i] = std::hypot(temp_xs[i] - cx, temp_ys[i] - cy);
	}
	return blend_avg_max(dists, penalty_threshold.value_or(cloud_distance_penalty_threshold_),
						  exponent.value_or(cloud_distance_exponent_),
						  max_dist_weight.value_or(cloud_distance_max_weight_));
}

double QRecognizer::blend_avg_max(const std::vector<double>& dists, double penalty_threshold, double exponent,
								   double max_dist_weight) {
	std::vector<double> adjusted(dists.size());
	for (size_t i = 0; i < dists.size(); ++i) {
		double d = dists[i];
		if (d > penalty_threshold) {
			double excess = d - penalty_threshold;
			adjusted[i] = d + std::pow(excess, exponent);
		} else {
			adjusted[i] = d;
		}
	}

	double avg_dist = 0.0;
	double max_dist = -std::numeric_limits<double>::infinity();
	for (double v : adjusted) {
		avg_dist += v;
		max_dist = std::max(max_dist, v);
	}
	avg_dist /= static_cast<double>(adjusted.size());

	return ((1.0 - max_dist_weight) * avg_dist) + (max_dist_weight * max_dist);
}

// =============================================================================
// Look-Up Table (LUT) Engine
// =============================================================================

void QRecognizer::xy(const std::vector<Point>& points, std::vector<double>* xs, std::vector<double>* ys) {
	xs->resize(points.size());
	ys->resize(points.size());
	for (size_t i = 0; i < points.size(); ++i) {
		(*xs)[i] = points[i].x;
		(*ys)[i] = points[i].y;
	}
}

std::vector<int64_t> QRecognizer::create_lut(const std::vector<double>& xs, const std::vector<double>& ys) const {
	int lut_size = lut_size_;
	std::vector<int64_t> lut(static_cast<size_t>(lut_size) * static_cast<size_t>(lut_size), -1);
	auto at = [&](int gx, int gy) -> int64_t& { return lut[static_cast<size_t>(gx) * static_cast<size_t>(lut_size) + static_cast<size_t>(gy)]; };

	double scale = static_cast<double>(lut_size) / frame_size_;

	std::vector<int> gx_all(xs.size()), gy_all(xs.size());
	for (size_t i = 0; i < xs.size(); ++i) {
		int gx = static_cast<int>((xs[i] + frame_size_ / 2.0) * scale);
		int gy = static_cast<int>((ys[i] + frame_size_ / 2.0) * scale);
		gx = std::clamp(gx, 0, lut_size - 1);
		gy = std::clamp(gy, 0, lut_size - 1);
		gx_all[i] = gx;
		gy_all[i] = gy;
	}

	std::deque<std::pair<int, int>> frontier;
	for (size_t idx = 0; idx < xs.size(); ++idx) {
		int gx = gx_all[idx];
		int gy = gy_all[idx];
		if (at(gx, gy) == -1) {
			at(gx, gy) = static_cast<int64_t>(idx);
			frontier.emplace_back(gx, gy);
		}
	}

	static const int dxs[4] = {1, -1, 0, 0};
	static const int dys[4] = {0, 0, 1, -1};
	while (!frontier.empty()) {
		auto [x, y] = frontier.front();
		frontier.pop_front();
		int64_t owner = at(x, y);
		for (int d = 0; d < 4; ++d) {
			int nx = x + dxs[d];
			int ny = y + dys[d];
			if (nx >= 0 && nx < lut_size && ny >= 0 && ny < lut_size && at(nx, ny) == -1) {
				at(nx, ny) = owner;
				frontier.emplace_back(nx, ny);
			}
		}
	}

	return lut;
}

std::vector<int64_t> QRecognizer::grid_lookup(const std::vector<double>& xs, const std::vector<double>& ys,
											   const std::vector<int64_t>& lut) const {
	int lut_size = lut_size_;
	double scale = static_cast<double>(lut_size) / frame_size_;
	std::vector<int64_t> result(xs.size());
	for (size_t i = 0; i < xs.size(); ++i) {
		int gx = static_cast<int>((xs[i] + frame_size_ / 2.0) * scale);
		int gy = static_cast<int>((ys[i] + frame_size_ / 2.0) * scale);
		gx = std::clamp(gx, 0, lut_size - 1);
		gy = std::clamp(gy, 0, lut_size - 1);
		result[i] = lut[static_cast<size_t>(gx) * static_cast<size_t>(lut_size) + static_cast<size_t>(gy)];
	}
	return result;
}

// =============================================================================
// Preprocessing Pipeline (Math & Resampling)
// =============================================================================

std::vector<Point> QRecognizer::preprocess(const std::vector<Stroke>& strokes, int /*level*/,
											bool already_merged) const {
	std::vector<Stroke> merged = already_merged
									  ? strokes
									  : merge_intersecting_strokes(strokes, touch_threshold_, endpoint_touch_threshold_);

	auto [pts0, run_ids0] = flatten_with_run_ids(merged);
	auto [pts1, run_ids1] = dedupe(pts0, run_ids0);
	std::vector<Point> pts2 = resample(pts1, run_ids1, n_);
	std::vector<Point> pts3 = scale_uniform(pts2, frame_size_);
	std::vector<Point> pts4 = translate_to_origin(pts3);
	return pts4;
}

std::pair<std::vector<Point>, std::vector<int>> QRecognizer::flatten_with_run_ids(const std::vector<Stroke>& strokes) {
	std::vector<Point> pts;
	std::vector<int> run_ids;
	for (size_t run_id = 0; run_id < strokes.size(); ++run_id) {
		for (const auto& p : strokes[run_id].points) {
			pts.push_back(p);
			run_ids.push_back(static_cast<int>(run_id));
		}
	}
	return {pts, run_ids};
}

double QRecognizer::compute_aspect_ratio(const std::vector<Point>& points) {
	if (points.empty()) {
		return M_PI / 4.0;
	}
	double min_x = points[0].x, max_x = points[0].x;
	double min_y = points[0].y, max_y = points[0].y;
	for (const auto& p : points) {
		min_x = std::min(min_x, p.x);
		max_x = std::max(max_x, p.x);
		min_y = std::min(min_y, p.y);
		max_y = std::max(max_y, p.y);
	}
	double w = max_x - min_x;
	double h = max_y - min_y;
	return std::atan2(h, w);
}

std::pair<std::vector<Point>, std::vector<int>> QRecognizer::dedupe(const std::vector<Point>& points,
																	  const std::vector<int>& run_ids) {
	if (points.empty()) return {{}, {}};
	std::vector<Point> out_pts;
	std::vector<int> out_runs;
	out_pts.push_back(points[0]);
	out_runs.push_back(run_ids[0]);
	for (size_t i = 1; i < points.size(); ++i) {
		const Point& p = points[i];
		const Point& last = out_pts.back();
		if (std::hypot(p.x - last.x, p.y - last.y) > 1e-9) {
			out_pts.push_back(p);
			out_runs.push_back(run_ids[i]);
		}
	}
	return {out_pts, out_runs};
}

double QRecognizer::path_length(const std::vector<Point>& points, const std::vector<int>& run_ids) {
	double d = 0.0;
	for (size_t i = 1; i < points.size(); ++i) {
		if (run_ids[i] == run_ids[i - 1]) {
			d += std::hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);
		}
	}
	return d;
}

std::vector<Point> QRecognizer::resample(const std::vector<Point>& points, const std::vector<int>& run_ids,
										  int n) const {
	if (points.size() < 2) {
		Point p = points.empty() ? Point{0.0, 0.0} : points[0];
		return std::vector<Point>(static_cast<size_t>(n), p);
	}

	std::vector<Point> pts(points);
	std::vector<int> runs(run_ids);
	double interval = path_length(pts, runs) / static_cast<double>(n - 1);
	if (interval <= 1e-9) {
		return std::vector<Point>(static_cast<size_t>(n), pts[0]);
	}

	double D = 0.0;
	std::vector<Point> new_points;
	new_points.push_back(pts[0]);

	size_t i = 1;
	while (i < pts.size()) {
		if (runs[i] == runs[i - 1]) {
			double d = std::hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
			if ((D + d) >= interval) {
				double t = (interval - D) / d;
				Point q{
					pts[i - 1].x + t * (pts[i].x - pts[i - 1].x),
					pts[i - 1].y + t * (pts[i].y - pts[i - 1].y),
				};
				new_points.push_back(q);
				pts.insert(pts.begin() + static_cast<long>(i), q);
				runs.insert(runs.begin() + static_cast<long>(i), runs[i]);
				D = 0.0;
				// `i` is still incremented unconditionally below (matching
				// the Python original's `i += 1` at the bottom of the
				// while-loop, run every iteration regardless of whether an
				// insert happened) -- since `q` was just inserted AT index
				// `i` (shifting the original pts[i] to i+1), advancing to
				// i+1 next correctly resumes at that shifted-right original
				// point, continuing to consume the remainder of the same
				// source segment from where interval-accumulation left off.
			} else {
				D += d;
			}
		}
		++i;
	}

	while (new_points.size() < static_cast<size_t>(n)) {
		new_points.push_back(pts.back());
	}
	new_points.resize(static_cast<size_t>(n));
	return new_points;
}

std::array<double, 4> QRecognizer::bounding_box_wh(const std::vector<Point>& points) {
	double min_x = points[0].x, max_x = points[0].x;
	double min_y = points[0].y, max_y = points[0].y;
	for (const auto& p : points) {
		min_x = std::min(min_x, p.x);
		max_x = std::max(max_x, p.x);
		min_y = std::min(min_y, p.y);
		max_y = std::max(max_y, p.y);
	}
	return {min_x, min_y, max_x - min_x, max_y - min_y};
}

std::vector<Point> QRecognizer::scale_uniform(const std::vector<Point>& points, double size) {
	auto [min_x, min_y, w, h] = bounding_box_wh(points);
	double scale = size / std::max({w, h, 1e-9});
	std::vector<Point> out;
	out.reserve(points.size());
	for (const auto& p : points) {
		out.push_back(Point{(p.x - min_x) * scale, (p.y - min_y) * scale});
	}
	return out;
}

Point QRecognizer::centroid(const std::vector<Point>& points) {
	double x = 0.0, y = 0.0;
	for (const auto& p : points) {
		x += p.x;
		y += p.y;
	}
	x /= static_cast<double>(points.size());
	y /= static_cast<double>(points.size());
	return Point{x, y};
}

std::vector<Point> QRecognizer::translate_to_origin(const std::vector<Point>& points) {
	Point c = centroid(points);
	std::vector<Point> out;
	out.reserve(points.size());
	for (const auto& p : points) {
		out.push_back(Point{p.x - c.x, p.y - c.y});
	}
	return out;
}

}  // namespace qrec
