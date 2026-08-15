// spell_engine.cpp
#include "spell_engine.hpp"

#include <cmath>

#include "config.hpp"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

namespace qrec {

// =============================================================================
// SpellBook
// =============================================================================

void SpellBook::add_spell(SpellDefinition spell) {
    spell.validate();  // throws std::invalid_argument on a malformed spell
    spells_.push_back(std::move(spell));
}

std::optional<SpellMatchResult> SpellBook::match_best(const std::vector<std::shared_ptr<Feature>>& features) const {
    return match_best_spell(spells_, features);
}

// =============================================================================
// SpellEngine
// =============================================================================

namespace {

// Small synthetic-shape generators, mirroring test_canvas.py's
// generate_line_points/generate_dot_points -- used only to seed the demo
// template set below. Not part of the public API.

std::vector<Point> demo_line_points(double angle_deg, double length = config::DEMO_LINE_LENGTH,
                                     int n = config::DEMO_LINE_RESAMPLE_N) {
    double angle = angle_deg * M_PI / 180.0;
    double dx = std::cos(angle) * length;
    double dy = std::sin(angle) * length;
    std::vector<Point> pts;
    pts.reserve(static_cast<size_t>(n));
    for (int t = 0; t < n; ++t) {
        double f = static_cast<double>(t) / static_cast<double>(n - 1);
        pts.push_back(Point{f * dx, f * dy});
    }
    return pts;
}

std::vector<Point> demo_dot_points(double cx, double cy, double radius = config::DEMO_DOT_RADIUS,
                                    int n = config::DEMO_DOT_RESAMPLE_N) {
    std::vector<Point> pts;
    pts.reserve(static_cast<size_t>(n));
    for (int i = 0; i < n; ++i) {
        double a = 2.0 * M_PI * static_cast<double>(i) / static_cast<double>(n - 1);
        pts.push_back(Point{cx + radius * std::cos(a), cy + radius * std::sin(a)});
    }
    return pts;
}

}  // namespace

SpellEngine::SpellEngine() : recognizer_(config::NUM_RESAMPLE_POINTS) {
    register_templates();
    register_spells();
}

void SpellEngine::register_templates() {
    // -- Level-1 lines (cardinal/diagonal) -----------------------------
    recognizer_.add_template("line_horizontal", {Stroke(demo_line_points(0))}, 1);
    recognizer_.add_template("line_vertical", {Stroke(demo_line_points(90))}, 1);
    recognizer_.add_template("line_diag_down", {Stroke(demo_line_points(45))}, 1);
    recognizer_.add_template("line_diag_up", {Stroke(demo_line_points(135))}, 1);

    // -- Level-1 shapes ---------------------------------------------------
    std::vector<Point> circle_pts;
    for (int i = 0; i < 50; ++i) {
        double a = 2.0 * M_PI * i / 49.0;
        circle_pts.push_back(Point{200 + 100 * std::cos(a), 200 + 100 * std::sin(a)});
    }
    recognizer_.add_template("circle", {Stroke(circle_pts)}, 1);

    recognizer_.add_template("open_angle", {Stroke({Point{0, 0}, Point{100, 100}, Point{200, 100}})}, 1);
    recognizer_.add_template("wedge", {Stroke({Point{200, 0}, Point{0, 150}, Point{200, 150}})}, 1);
    recognizer_.add_template("caret", {Stroke({Point{0, 100}, Point{50, 0}, Point{100, 100}})}, 1);   // '^'
    recognizer_.add_template("v_shape", {Stroke({Point{0, 0}, Point{50, 100}, Point{100, 0}})}, 1);   // 'v'

    // -- Level-2 composites -----------------------------------------------
    std::vector<Point> stem_pts;
    for (int i = 0; i < 20; ++i) stem_pts.push_back(Point{0.0, 150.0 * i / 19.0});
    Stroke exclaim_stem(stem_pts);
    Stroke exclaim_dot(demo_dot_points(0.0, 185.0, 10.0));
    recognizer_.add_template("exclaim", {exclaim_stem, exclaim_dot}, 2);

    Stroke colon_top(demo_dot_points(0.0, 0.0, 10.0));
    Stroke colon_bottom(demo_dot_points(0.0, 60.0, 10.0));
    recognizer_.add_template("colon", {colon_top, colon_bottom}, 2);
}

void SpellEngine::register_spells() {
    // Demo spell built from the shapes registered in register_templates()
    // above: a "circle" sitting at the drawing's center, with a "caret"
    // drawn somewhere north of it. Replace/extend this with your own
    // SpellDefinitions -- see spell_matcher.h for the full slot/constraint
    // vocabulary (SpellFeatureSlot::distance for a fixed expected
    // distance, min_angle/max_angle for a compass sector, and
    // RelativeDistanceConstraint for "farther"/"closer"/"inside"/
    // "outside" relations between two slots).
    SpellDefinition circle_and_north_caret;
    circle_and_north_caret.name = "circle_and_north_caret";

    SpellFeatureSlot circle_slot;
    circle_slot.id = 0;
    circle_slot.shape = "circle";
    circle_slot.distance = 0.0;
    circle_slot.tolerance_dist = 0.35;

    SpellFeatureSlot caret_slot;
    caret_slot.id = 1;
    caret_slot.shape = "caret";
    caret_slot.min_angle = 315.0;
    caret_slot.max_angle = 45.0;
    caret_slot.tolerance_angle = 30.0;

    circle_and_north_caret.features = {circle_slot, caret_slot};

    spellbook_.add_spell(std::move(circle_and_north_caret));
}

void SpellEngine::add_stroke(const std::vector<Point>& stroke_points) {
    recognizer_.add_stroke(stroke_from_points(stroke_points));
}

void SpellEngine::add_stroke(const Stroke& stroke) { recognizer_.add_stroke(stroke); }

std::string SpellEngine::match_spell() const {
    auto features = recognizer_.features();
    auto best = spellbook_.match_best(features);
    if (best.has_value() && best->name.has_value()) {
        return *best->name;
    }
    return "";
}

void SpellEngine::clear() { recognizer_.clear(); }

}  // namespace qrec