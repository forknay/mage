// recognizer.h
// =============================================================================
// Orientation-Sensitive $Q Super-Quick Recognizer (C++ port of recognizer.py)
// =============================================================================
// An orientation-sensitive implementation of Vatavu, Anthony & Wobbrock's
// $Q Recognizer (2018) extended to support composable gesture hierarchies
// and incremental canvas updating within a single unified class.
#pragma once

#include <array>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <tuple>
#include <unordered_map>
#include <utility>
#include <vector>

#include "config.hpp"
#include "gesture_types.hpp"
#include "merge_intersecting_strokes.hpp"

namespace qrec {

// -----------------------------------------------------------------------
// _IncrementalGroup
// -----------------------------------------------------------------------
// One spatially-isolated region tracked by QRecognizer's incremental
// canvas API (add_stroke/clear/features et al.) -- NOT a recognition
// concept itself, just bookkeeping so a new stroke only ever forces
// recomputation in the region(s) it could actually affect. See
// recognizer.py's `_IncrementalGroup` docstring for the full rationale.
struct IncrementalGroup {
    std::vector<std::shared_ptr<Feature>> atomic_features;
    std::vector<std::shared_ptr<Feature>> features;
};

// Hash for a pair of raw Feature pointers, used as the touch-cache key --
// stands in for Python's `(id(feat_a), id(feat_b))` tuple key.
struct FeaturePtrPairHash {
    size_t operator()(const std::pair<const Feature*, const Feature*>& p) const noexcept {
        size_t h1 = std::hash<const void*>()(p.first);
        size_t h2 = std::hash<const void*>()(p.second);
        // Standard hash-combine.
        return h1 ^ (h2 + 0x9e3779b97f4a7c15ULL + (h1 << 6) + (h1 >> 2));
    }
};

class QRecognizer {
public:
    explicit QRecognizer(int num_resample_points = config::NUM_RESAMPLE_POINTS,
                          double frame_size = config::FRAME_SIZE, int lut_size = config::LUT_SIZE,
                          double touch_threshold = config::DEFAULT_TOUCH_THRESHOLD,
                          double endpoint_touch_threshold = config::DEFAULT_ENDPOINT_TOUCH_THRESHOLD,
                          const std::unordered_map<int, double>* level_merge_thresholds = nullptr,
                          double aspect_ratio_weight = config::ASPECT_RATIO_WEIGHT,
                          double cloud_distance_penalty_threshold = config::CLOUD_DISTANCE_PENALTY_THRESHOLD,
                          double cloud_distance_exponent = config::CLOUD_DISTANCE_EXPONENT,
                          double cloud_distance_max_weight = config::CLOUD_DISTANCE_MAX_WEIGHT);

    // -------------------------------------------------------------------
    // Public APIs: Template Registration
    // -------------------------------------------------------------------

    // Registers a new template, inferring stroke units (level) if not
    // provided (pass level < 0 for "infer", mirroring Python's
    // level=None).
    void add_template(const std::string& name, const std::vector<Stroke>& strokes, int level = -1,
                       double min_score = config::DEFAULT_MIN_SCORE);

    // Fast-path registration from cache, skipping preprocessing and LUT
    // construction. `lut` must be a flat lut_size*lut_size buffer,
    // row-major (x-major), matching create_lut's output layout.
    void add_precomputed_template(const std::string& name, const std::vector<Point>& processed_points,
                                   const std::vector<int64_t>& lut, int level, double aspect_ratio,
                                   double min_score = config::DEFAULT_MIN_SCORE);

    const std::vector<Template>& templates() const { return templates_; }

    // -------------------------------------------------------------------
    // Public APIs: Batch & Single-Gesture Recognition
    // -------------------------------------------------------------------

    // Classifies a point cloud (given as its constituent Strokes) against
    // registered templates at a specific level. Throws std::invalid_argument
    // on the same error conditions the Python `ValueError`s covered (no
    // templates registered, wrong unit count, no matching candidates).
    RecognitionResult recognize(const std::vector<Stroke>& strokes, int level = 1,
                                 const std::vector<std::string>* candidate_names = nullptr) const;

    // Parses the entire canvas bottom-up in a single batch pass: splits
    // into atomic (Level-1) features, then progressively bundles nearby
    // features into composite (Level 2+) features.
    std::vector<std::shared_ptr<Feature>> recognize_scene(
        const std::vector<Stroke>& strokes, const std::unordered_map<int, double>* level_merge_thresholds = nullptr,
        double min_score = 0.0) const;

    // -------------------------------------------------------------------
    // Public APIs: Incremental Canvas Recognition
    // -------------------------------------------------------------------

    // Flattened, fully-composed features across every tracked incremental
    // canvas region.
    std::vector<std::shared_ptr<Feature>> features() const;

    // Flattened Level-1 features across every tracked incremental canvas
    // region, BEFORE composition.
    std::vector<std::shared_ptr<Feature>> atomic_features() const;

    // Incorporates a new stroke dynamically, isolating atomic
    // recomputations to affected spatial groups while reusing untouched
    // regional caches. Returns the same thing `features()` would.
    std::vector<std::shared_ptr<Feature>> add_stroke(const Stroke& stroke);

    // Resets the incremental regional tracking state and touch cache.
    void clear();

private:
    // -------------------------------------------------------------------
    // Core Pipeline: Recognition & Composition Helpers
    // -------------------------------------------------------------------

    std::vector<std::shared_ptr<Feature>> recognize_atomic_clusters(const std::vector<Stroke>& strokes) const;

    std::vector<std::shared_ptr<Feature>> compose_from_atomic(
        const std::vector<std::shared_ptr<Feature>>& atomic_features,
        const std::unordered_map<int, double>* level_merge_thresholds, double min_score,
        std::unordered_map<std::pair<const Feature*, const Feature*>, bool, FeaturePtrPairHash>* touch_cache) const;

    std::vector<std::shared_ptr<Feature>> compose_level(
        const std::vector<std::shared_ptr<Feature>>& current_features, int target_level, double gap,
        std::unordered_map<std::pair<const Feature*, const Feature*>, bool, FeaturePtrPairHash>* touch_cache) const;

    std::vector<std::vector<std::shared_ptr<Feature>>> bundle_features_by_proximity(
        const std::vector<std::shared_ptr<Feature>>& features, double threshold,
        std::unordered_map<std::pair<const Feature*, const Feature*>, bool, FeaturePtrPairHash>* touch_cache) const;

    std::vector<const Template*> candidates_at_level(int level, const std::vector<std::string>* candidate_names) const;

    std::optional<RecognitionResult> try_recognize(const std::vector<Stroke>& strokes, int level) const;

    // Returns (best_template, best_distance, best_score). best_template
    // is nullptr if `candidates` is empty (mirrors recognize()'s
    // guarantee that candidates_at_level never returns empty -- callers
    // must ensure that).
    std::tuple<const Template*, double, double> best_matching_template(const std::vector<Point>& processed,
                                                                         double cand_aspect_ratio,
                                                                         const std::vector<const Template*>& candidates) const;

    // -------------------------------------------------------------------
    // Distance Calculations
    // -------------------------------------------------------------------

    // NOTE: exactly like recognizer.py's `_grid_lookup`, every LUT query
    // below always scales using THIS recognizer's own `lut_size_`
    // (self.lut_size in the Python original), regardless of which LUT
    // (a template's precomputed one, or the freshly-built candidate one)
    // is being queried. A per-template `lut_size` is intentionally not
    // consulted here -- that matches the Python original's behavior
    // exactly (see template_store.py's cache-fingerprinting of
    // `lut_size`, which is what keeps this assumption valid in practice).
    double bidirectional_cloud_distance_hausdorff(const std::vector<double>& cand_xs,
                                                    const std::vector<double>& cand_ys,
                                                    const std::vector<double>& temp_xs,
                                                    const std::vector<double>& temp_ys,
                                                    const std::vector<int64_t>& lut,
                                                    const std::vector<int64_t>& candidate_lut) const;

    double cloud_distance(const std::vector<double>& cand_xs, const std::vector<double>& cand_ys,
                           const std::vector<double>& temp_xs, const std::vector<double>& temp_ys,
                           const std::vector<int64_t>& lut, std::optional<double> penalty_threshold = std::nullopt,
                           std::optional<double> exponent = std::nullopt,
                           std::optional<double> max_dist_weight = std::nullopt) const;

    double reverse_cloud_distance(const std::vector<double>& temp_xs, const std::vector<double>& temp_ys,
                                   const std::vector<double>& cand_xs, const std::vector<double>& cand_ys,
                                   const std::vector<int64_t>& candidate_lut,
                                   std::optional<double> penalty_threshold = std::nullopt,
                                   std::optional<double> exponent = std::nullopt,
                                   std::optional<double> max_dist_weight = std::nullopt) const;

    static double blend_avg_max(const std::vector<double>& dists, double penalty_threshold, double exponent,
                                 double max_dist_weight);

    // -------------------------------------------------------------------
    // Look-Up Table (LUT) Engine
    // -------------------------------------------------------------------

    static void xy(const std::vector<Point>& points, std::vector<double>* xs, std::vector<double>* ys);

    // Generates a 2D discrete Voronoi diagram (LUT) storing the index of
    // the nearest point, as a flat lut_size*lut_size buffer (row-major,
    // x-major: index = gx * lut_size + gy).
    std::vector<int64_t> create_lut(const std::vector<double>& xs, const std::vector<double>& ys) const;

    std::vector<int64_t> grid_lookup(const std::vector<double>& xs, const std::vector<double>& ys,
                                      const std::vector<int64_t>& lut) const;

    // -------------------------------------------------------------------
    // Preprocessing Pipeline (Math & Resampling)
    // -------------------------------------------------------------------

    // Geometric normalization pipeline: dedupe, resample, scale, translate.
    std::vector<Point> preprocess(const std::vector<Stroke>& strokes, int level, bool already_merged) const;

    static std::pair<std::vector<Point>, std::vector<int>> flatten_with_run_ids(const std::vector<Stroke>& strokes);

    static double compute_aspect_ratio(const std::vector<Point>& points);

    static std::pair<std::vector<Point>, std::vector<int>> dedupe(const std::vector<Point>& points,
                                                                    const std::vector<int>& run_ids);

    static double path_length(const std::vector<Point>& points, const std::vector<int>& run_ids);

    std::vector<Point> resample(const std::vector<Point>& points, const std::vector<int>& run_ids, int n) const;

    static std::array<double, 4> bounding_box_wh(const std::vector<Point>& points);  // (min_x, min_y, w, h)

    static std::vector<Point> scale_uniform(const std::vector<Point>& points, double size);

    static Point centroid(const std::vector<Point>& points);

    static std::vector<Point> translate_to_origin(const std::vector<Point>& points);

    // -------------------------------------------------------------------
    // State
    // -------------------------------------------------------------------

    int n_;
    double frame_size_;
    int lut_size_;
    std::vector<Template> templates_;
    double max_distance_;
    double touch_threshold_;
    double endpoint_touch_threshold_;
    double aspect_ratio_weight_;
    double cloud_distance_penalty_threshold_;
    double cloud_distance_exponent_;
    double cloud_distance_max_weight_;
    std::unordered_map<int, double> level_merge_thresholds_;

    double max_gap_;
    double atomic_gap_;

    std::vector<IncrementalGroup> groups_;
    mutable std::unordered_map<std::pair<const Feature*, const Feature*>, bool, FeaturePtrPairHash> touch_cache_;
};

}  // namespace qrec