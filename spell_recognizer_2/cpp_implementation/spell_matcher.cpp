// spell_matcher.cpp
#include "spell_matcher.hpp"

#include <algorithm>
#include <cmath>
#include <functional>
#include <limits>
#include <map>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

namespace qrec {

// =============================================================================
// 1. Geometry helpers
// =============================================================================

double compass_angle(double dx, double dy) {
    double deg = std::fmod(std::atan2(dx, -dy) * 180.0 / M_PI, 360.0);
    if (deg < 0) deg += 360.0;
    return deg;
}

namespace {

double norm360(double a) {
    double r = std::fmod(a, 360.0);
    if (r < 0) r += 360.0;
    return r;
}

}  // namespace

bool angle_in_range(double angle, double min_angle, double max_angle) {
    double a = norm360(angle);
    double lo = norm360(min_angle);
    double hi = norm360(max_angle);
    if (lo <= hi) {
        return lo <= a && a <= hi;
    }
    return a >= lo || a <= hi;
}

namespace {

// For an `angle` OUTSIDE the [min_angle, max_angle] sector, how many
// degrees past the nearer edge it sits. Used only for soft scoring --
// angle_in_range is the hard gate.
double sector_overshoot(double angle, double min_angle, double max_angle) {
    double lo = norm360(min_angle), hi = norm360(max_angle);
    double span = norm360(hi - lo);
    double rel = norm360(norm360(angle) - lo);
    return std::min(rel - span, 360.0 - rel);
}

std::pair<double, double> centroid_xy(const std::vector<Point>& points) {
    double x = 0.0, y = 0.0;
    for (const auto& p : points) {
        x += p.x;
        y += p.y;
    }
    x /= static_cast<double>(points.size());
    y /= static_cast<double>(points.size());
    return {x, y};
}

// Average distance of `points` from their own centroid (cx, cy).
double mean_radius(const std::vector<Point>& points, double cx, double cy) {
    double sum = 0.0;
    for (const auto& p : points) {
        sum += std::hypot(p.x - cx, p.y - cy);
    }
    return sum / static_cast<double>(points.size());
}

// Diagonal of the bounding box over every point in the whole drawing.
double bounding_diagonal(const std::vector<Point>& all_points) {
    double min_x = all_points[0].x, max_x = all_points[0].x;
    double min_y = all_points[0].y, max_y = all_points[0].y;
    for (const auto& p : all_points) {
        min_x = std::min(min_x, p.x);
        max_x = std::max(max_x, p.x);
        min_y = std::min(min_y, p.y);
        max_y = std::max(max_y, p.y);
    }
    double w = max_x - min_x;
    double h = max_y - min_y;
    return std::hypot(w, h);
}

}  // namespace

std::vector<PositionedFeature> compute_positions(const std::vector<std::shared_ptr<Feature>>& features) {
    std::vector<std::shared_ptr<Feature>> named;
    for (const auto& f : features) {
        if (f->result.name.has_value()) named.push_back(f);
    }
    if (named.empty()) return {};

    std::vector<std::pair<double, double>> centroids;
    centroids.reserve(named.size());
    for (const auto& f : named) centroids.push_back(centroid_xy(f->points));

    double center_x = 0.0, center_y = 0.0;
    for (const auto& c : centroids) {
        center_x += c.first;
        center_y += c.second;
    }
    center_x /= static_cast<double>(centroids.size());
    center_y /= static_cast<double>(centroids.size());

    std::vector<Point> all_points;
    for (const auto& f : named) all_points.insert(all_points.end(), f->points.begin(), f->points.end());
    double diag = bounding_diagonal(all_points);
    if (diag <= 1e-9) diag = 1.0;  // degenerate single-point drawing -- avoid div-by-zero

    std::vector<PositionedFeature> positioned;
    positioned.reserve(named.size());
    for (size_t i = 0; i < named.size(); ++i) {
        const auto& feat = named[i];
        double cx = centroids[i].first, cy = centroids[i].second;
        double dx = cx - center_x, dy = cy - center_y;
        double raw_dist = std::hypot(dx, dy);
        double own_radius = mean_radius(feat->points, cx, cy);

        PositionedFeature pf;
        pf.shape = *feat->result.name;
        pf.distance = raw_dist / diag;
        pf.angle = compass_angle(dx, dy);
        pf.nx = dx / diag;
        pf.ny = dy / diag;
        pf.radius = own_radius / diag;
        pf.source = feat;
        positioned.push_back(std::move(pf));
    }
    return positioned;
}

// =============================================================================
// 2. Spell definitions
// =============================================================================

void RelativeDistanceConstraint::validate() const {
    if (relation != "farther" && relation != "closer" && relation != "inside" && relation != "outside") {
        throw std::invalid_argument(
            "RelativeDistanceConstraint.relation must be 'farther', 'closer', 'inside', or 'outside', got '" +
            relation + "'.");
    }
}

void SpellDefinition::validate() const {
    std::unordered_set<int> known_ids;
    for (const auto& slot : features) known_ids.insert(slot.id);
    for (const auto& c : relative_constraints) {
        c.validate();
        if (known_ids.find(c.subject_id) == known_ids.end()) {
            throw std::invalid_argument("Spell '" + name + "': RelativeDistanceConstraint.subject_id=" +
                                         std::to_string(c.subject_id) + " does not match any feature slot id.");
        }
        if (known_ids.find(c.reference_id) == known_ids.end()) {
            throw std::invalid_argument("Spell '" + name + "': RelativeDistanceConstraint.reference_id=" +
                                         std::to_string(c.reference_id) + " does not match any feature slot id.");
        }
    }
}

// =============================================================================
// 3. Matching
// =============================================================================

namespace {

// Score in [0.0, 1.0] for matching `feat` to `slot`, given they already
// share the same shape (shape match is a hard gate, checked by the caller
// via the by-shape candidate grouping in match_spell).
double slot_score(const SpellFeatureSlot& slot, const PositionedFeature& feat) {
    double dist_score;
    if (slot.distance.has_value()) {
        double dist_diff = std::abs(feat.distance - *slot.distance);
        if (dist_diff > slot.tolerance_dist) return 0.0;
        dist_score = 1.0 - (slot.tolerance_dist > 1e-9 ? (dist_diff / slot.tolerance_dist) : 0.0);
    } else {
        dist_score = 1.0;  // no fixed distance requirement
    }

    if (!slot.angle_constrained() || feat.distance <= config::SPELL_CENTER_EPSILON) {
        return dist_score;
    }

    if (angle_in_range(feat.angle, *slot.min_angle, *slot.max_angle)) {
        return dist_score;
    }

    double overshoot = sector_overshoot(feat.angle, *slot.min_angle, *slot.max_angle);
    double angle_score = std::max(0.0, 1.0 - overshoot / std::max(slot.tolerance_angle, 1e-9));
    if (angle_score <= 0.0) return 0.0;
    return dist_score * angle_score;
}

// Score in [0.0, 1.0] for one RelativeDistanceConstraint against a
// (possibly partial) slot assignment.
double relative_constraint_score(const RelativeDistanceConstraint& constraint,
                                  const std::unordered_map<int, const PositionedFeature*>& positioned_by_slot) {
    auto subj_it = positioned_by_slot.find(constraint.subject_id);
    auto ref_it = positioned_by_slot.find(constraint.reference_id);
    if (subj_it == positioned_by_slot.end() || ref_it == positioned_by_slot.end()) {
        return 0.0;
    }
    const PositionedFeature& subj = *subj_it->second;
    const PositionedFeature& ref = *ref_it->second;

    double tolerance = std::max(constraint.tolerance, 1e-9);
    double slack;

    if (constraint.relation == "farther") {
        slack = (subj.distance - ref.distance) - constraint.margin;
    } else if (constraint.relation == "closer") {
        slack = (ref.distance - subj.distance) - constraint.margin;
    } else if (constraint.relation == "inside") {
        double gap = std::hypot(subj.nx - ref.nx, subj.ny - ref.ny);
        slack = (ref.radius + constraint.margin) - gap;
    } else {  // "outside"
        double gap = std::hypot(subj.nx - ref.nx, subj.ny - ref.ny);
        slack = gap - (ref.radius + constraint.margin);
    }

    if (slack >= 0.0) return 1.0;
    return std::max(0.0, 1.0 + slack / tolerance);
}

}  // namespace

SpellMatchResult match_spell(const SpellDefinition& spell, const std::vector<std::shared_ptr<Feature>>& scene_features) {
    std::vector<PositionedFeature> positioned = compute_positions(scene_features);

    // Group candidates by shape up front.
    std::unordered_map<std::string, std::vector<int>> by_shape;
    for (size_t idx = 0; idx < positioned.size(); ++idx) {
        by_shape[positioned[idx].shape].push_back(static_cast<int>(idx));
    }

    const auto& slots = spell.features;
    const auto& constraints = spell.relative_constraints;
    int num_terms = static_cast<int>(slots.size() + constraints.size());

    std::vector<bool> used(positioned.size(), false);
    // current: slot_id -> positioned index. Using a std::map keeps
    // iteration order deterministic (not that it matters for correctness,
    // only for reproducibility).
    std::map<int, int> current;

    std::map<int, int> best;
    double best_score = -1.0;

    // Recursive backtracking search -- direct port of match_spell's
    // nested `backtrack` closure. `running_slot_score` accumulates the
    // sum of per-slot scores decided so far.
    std::function<void(size_t, double)> backtrack = [&](size_t slot_pos, double running_slot_score) {
        if (slot_pos == slots.size()) {
            double constraint_score = 0.0;
            if (!constraints.empty()) {
                std::unordered_map<int, const PositionedFeature*> positioned_by_slot;
                for (const auto& kv : current) positioned_by_slot[kv.first] = &positioned[static_cast<size_t>(kv.second)];
                for (const auto& c : constraints) {
                    constraint_score += relative_constraint_score(c, positioned_by_slot);
                }
            }
            double total = running_slot_score + constraint_score;
            double avg = num_terms ? (total / num_terms) : 0.0;
            if (avg > best_score) {
                best_score = avg;
                best = current;
            }
            return;
        }

        const SpellFeatureSlot& slot = slots[slot_pos];
        auto it = by_shape.find(slot.shape);
        if (it != by_shape.end()) {
            for (int idx : it->second) {
                if (used[static_cast<size_t>(idx)]) continue;
                double score = slot_score(slot, positioned[static_cast<size_t>(idx)]);
                if (score <= 0.0) continue;
                used[static_cast<size_t>(idx)] = true;
                current[slot.id] = idx;
                backtrack(slot_pos + 1, running_slot_score + score);
                current.erase(slot.id);
                used[static_cast<size_t>(idx)] = false;
            }
        }

        // Also try leaving this slot unfilled.
        backtrack(slot_pos + 1, running_slot_score);
    };

    backtrack(0, 0.0);

    SpellMatchResult out;
    std::vector<std::pair<int, PositionedFeature>> assignment;
    for (const auto& kv : best) {
        assignment.emplace_back(kv.first, positioned[static_cast<size_t>(kv.second)]);
    }
    bool all_filled = assignment.size() == slots.size();
    double final_score = std::max(best_score, 0.0);

    bool constraints_satisfied = true;
    if (!constraints.empty()) {
        std::unordered_map<int, const PositionedFeature*> positioned_by_slot;
        for (const auto& kv : best) positioned_by_slot[kv.first] = &positioned[static_cast<size_t>(kv.second)];
        for (const auto& c : constraints) {
            if (relative_constraint_score(c, positioned_by_slot) <= 0.0) {
                constraints_satisfied = false;
                break;
            }
        }
    }
    bool accepted = all_filled && constraints_satisfied;

    out.name = accepted ? std::optional<std::string>(spell.name) : std::nullopt;
    out.score = final_score;
    out.accepted = accepted;
    out.assignment = std::move(assignment);
    return out;
}

std::optional<SpellMatchResult> match_best_spell(const std::vector<SpellDefinition>& spells,
                                                   const std::vector<std::shared_ptr<Feature>>& scene_features) {
    std::optional<SpellMatchResult> best_result;
    for (const auto& spell : spells) {
        SpellMatchResult result = match_spell(spell, scene_features);
        if (result.accepted && (!best_result.has_value() || result.score > best_result->score)) {
            best_result = std::move(result);
        }
    }
    return best_result;
}

}  // namespace qrec

// -----------------------------------------------------------------------------
// Note on rotation invariance (see header docstring)
// -----------------------------------------------------------------------------
// To match a spell drawn at any rotation, angles would need to be measured
// relative to one designated "anchor" feature's bearing from center instead
// of true north -- i.e. angle = (compass_angle(dx, dy) - anchor_bearing) %
// 360 for every feature, anchor included (which then sits at angle 0 by
// definition). That's a change to compute_positions (needs to know which
// feature is the anchor) and to how SpellFeatureSlot::min_angle/max_angle
// are interpreted (relative bearing from the anchor, not compass bearing) --
// deliberately NOT done here since it trades away the ability to express
// "must be drawn upright", which most spells probably want.
//
// Note: relative-distance/containment constraints (RelativeDistanceConstraint)
// are already rotation-agnostic by construction -- "farther from center",
// "closer than", and "inside"/"outside" don't care about compass direction,
// only distance/radius -- so they keep working unchanged even if the above
// were ever implemented.