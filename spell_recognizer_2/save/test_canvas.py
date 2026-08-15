"""
Interactive Drawing Canvas for testing the $Q Point-Cloud Recognizer.

Controls:
  - Left click + drag: Draw stroke
  - Mouse release: Automatically preprocesses and matches against Level 1/2 templates
  - ENTER / Space: Shows detailed prediction popup window, including which
                   (if any) spell the current drawing matches -- see
                   spell_matcher.py/spell_store.py
  - 'c': Clears the canvas
  - 'g': Toggles the spatial-index grid overlay (cell size set by
         config.SPATIAL_GRID_VISUAL_SIZE)
  - ESC: Exits application

FIXES INTEGRATED:
  - Fix 3: Added competing basic templates ('open_angle', 'wedge', 'caret', 'v_shape')

Layout of this file:
  1. Synthetic point generators      -- generate_line_points / generate_dot_points
  2. Demo recognizer construction    -- build_demo_recognizer and its helpers
  3. DollarCanvasTester               -- the interactive OpenCV canvas/UI

Canvas size, brush thickness, SceneFeature colors, and the synthetic demo-shape
parameters all live in config.py so they're easy to retune without digging
through this file.
"""

import math
import numpy as np
import cv2

from recognizer import Point, QRecognizer, SceneFeature
from template_store import load_templates_into, DEFAULT_TEMPLATES_DIR
from spell_store import load_spells, DEFAULT_SPELLS_DIR
from spell_matcher import match_spell, SpellDefinition, SpellMatchResult
from config import (
    CANVAS_WIDTH,
    CANVAS_HEIGHT,
    BRUSH_THICKNESS,
    SceneFeature_COLORS,
    DEMO_LINE_LENGTH,
    DEMO_LINE_RESAMPLE_N,
    DEMO_DOT_RADIUS,
    DEMO_DOT_RESAMPLE_N,
    SPATIAL_GRID_VISUAL_SIZE,
)


# =============================================================================
# 1. Synthetic point generators
# =============================================================================

def generate_line_points(angle_deg: float, length: float = DEMO_LINE_LENGTH,
                          n: int = DEMO_LINE_RESAMPLE_N, stroke_id: int = 0) -> list[Point]:
    """Generates synthetic line points at a specific angle."""
    angle = math.radians(angle_deg)
    dx, dy = math.cos(angle) * length, math.sin(angle) * length
    return [Point(t / (n - 1) * dx, t / (n - 1) * dy, stroke_id) for t in range(n)]


def generate_dot_points(cx: float, cy: float, radius: float = DEMO_DOT_RADIUS,
                         n: int = DEMO_DOT_RESAMPLE_N, stroke_id: int = 0) -> list[Point]:
    """Generates points in a small circle to represent a dot SceneFeature."""
    return [
        Point(cx + radius * math.cos(a), cy + radius * math.sin(a), stroke_id)
        for a in np.linspace(0, 2 * math.pi, n)
    ]


# =============================================================================
# 2. Demo recognizer construction
# =============================================================================

def _add_level1_line_templates(rec: QRecognizer) -> None:
    """Four straight-line templates at the cardinal/diagonal angles."""
    rec.add_template("line_horizontal", generate_line_points(0), level=1)
    rec.add_template("line_vertical", generate_line_points(90), level=1)
    rec.add_template("line_diag_down", generate_line_points(45), level=1)
    rec.add_template("line_diag_up", generate_line_points(135), level=1)


def _add_level1_shape_templates(rec: QRecognizer) -> None:
    """A circle plus FIX 3's simple unclosed-angle templates, so partial
    drawings win over complete complex runes."""
    circle_pts = [
        Point(200 + 100 * math.cos(a), 200 + 100 * math.sin(a))
        for a in np.linspace(0, 2 * math.pi, 50)
    ]
    rec.add_template("circle", circle_pts, level=1)

    open_angle_pts = [Point(0, 0), Point(100, 100), Point(200, 100)]
    rec.add_template("open_angle", open_angle_pts, level=1)

    wedge_pts = [Point(200, 0), Point(0, 150), Point(200, 150)]
    rec.add_template("wedge", wedge_pts, level=1)

    # Caret / Chevron '^'
    caret_pts = [Point(0, 100), Point(50, 0), Point(100, 100)]
    rec.add_template("caret", caret_pts, level=1)

    # V-Shape 'v'
    v_pts = [Point(0, 0), Point(50, 100), Point(100, 0)]
    rec.add_template("v_shape", v_pts, level=1)


def _add_level2_composite_templates(rec: QRecognizer) -> None:
    """Multi-stroke Level 2 templates (stem + dot, colon, plus)."""
    exclaim_stem = [Point(0.0, y, stroke_id=0) for y in np.linspace(0, 150, 20)]
    exclaim_dot = generate_dot_points(0.0, 185.0, radius=10.0, stroke_id=1)
    rec.add_template("exclaim", exclaim_stem + exclaim_dot, level=2)

    colon_top = generate_dot_points(0.0, 0.0, radius=10.0, stroke_id=0)
    colon_bottom = generate_dot_points(0.0, 60.0, radius=10.0, stroke_id=1)
    rec.add_template("colon", colon_top + colon_bottom, level=2)


def build_demo_recognizer() -> QRecognizer:
    """Configures default $Q recognizer with standard templates."""
    # FIX 2: Explicitly requests 64 resampling points for finer resolution
    rec = QRecognizer(num_resample_points=64)

    _add_level1_line_templates(rec)
    _add_level1_shape_templates(rec)
    _add_level2_composite_templates(rec)

    num_loaded = load_templates_into(rec, DEFAULT_TEMPLATES_DIR)
    if num_loaded:
        print(f"Loaded {num_loaded} saved template(s) from '{DEFAULT_TEMPLATES_DIR}/'")

    return rec


# =============================================================================
# 3. Interactive canvas / UI
# =============================================================================


class DollarCanvasTester:
    def __init__(self, recognizer: QRecognizer, spells: "list[SpellDefinition] | None" = None):
        self.recognizer = recognizer
        self.window_name = "$Q Recognizer Tester"
        self.canvas = np.zeros((CANVAS_HEIGHT, CANVAS_WIDTH, 3), dtype=np.uint8)
        self.drawing = False
        self.last_point = None
        self.current_stroke: list[Point] = []
        self.next_stroke_id = 0
        self.last_SceneFeatures: list[SceneFeature] = []
        self.show_grid = False  # toggled with 'g' -- draws the spatial-index grid overlay

        # Spell library (spell_matcher.py/spell_store.py) -- Layer 2 on top of
        # the Layer-1 SceneFeatures above. Loaded once at startup, same lifecycle
        # as the recognizer's own template library.
        self.spells: "list[SpellDefinition]" = spells if spells is not None else []

        # ... cv2 setup ...
        cv2.namedWindow(self.window_name)
        cv2.setMouseCallback(self.window_name, self.draw_event)

    def reset_canvas(self):
        """Clears drawing canvas and resets stroke tracking state."""
        self.canvas = np.zeros((CANVAS_HEIGHT, CANVAS_WIDTH, 3), dtype=np.uint8)
        self.drawing = False
        self.last_point = None
        self.current_stroke.clear()
        self.next_stroke_id = 0
        self.last_SceneFeatures = []
        self.recognizer.clear() # Clear persistent state

    def draw_event(self, event, x, y, flags, param):
        """OpenCV mouse interaction handler."""
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.last_point = (x, y)
            
            # Start fresh array for ONLY the active stroke
            self.current_stroke.clear() 
            self.current_stroke.append(Point(float(x), float(y), stroke_id=self.next_stroke_id))
            
            cv2.circle(self.canvas, (x, y), BRUSH_THICKNESS // 2, (255, 255, 255), -1, cv2.LINE_AA)

        elif event == cv2.EVENT_MOUSEMOVE:
            if self.drawing and self.last_point is not None:
                cv2.line(self.canvas, self.last_point, (x, y), (255, 255, 255), BRUSH_THICKNESS, cv2.LINE_AA)
                self.last_point = (x, y)
                self.current_stroke.append(Point(float(x), float(y), stroke_id=self.next_stroke_id))

        elif event == cv2.EVENT_LBUTTONUP:
            self.drawing = False
            self.last_point = None
            self.next_stroke_id += 1
            
            # Feed ONLY the newly finished stroke to the incremental orchestrator
            self.last_SceneFeatures = self.recognizer.add_stroke(self.current_stroke)

    def draw_grid_overlay(self, display_canvas):
        """
        Draws the spatial-index grid on top of `display_canvas`, purely as
        a debug visual so you can see the buckets the "only compare nearby
        strokes" logic (spatial_index.SpatialGrid) groups points into. Cell
        size is controlled by the single SPATIAL_GRID_VISUAL_SIZE constant
        in config.py -- e.g. 50.0 draws a 10-wide grid on a 500px canvas
        and a 20-wide grid on a 1000px canvas.
        """
        cell = SPATIAL_GRID_VISUAL_SIZE
        h, w = display_canvas.shape[:2]
        color = (60, 60, 60)

        x = 0.0
        while x <= w:
            xi = int(round(x))
            cv2.line(display_canvas, (xi, 0), (xi, h), color, 1, cv2.LINE_AA)
            x += cell

        y = 0.0
        while y <= h:
            yi = int(round(y))
            cv2.line(display_canvas, (0, yi), (w, yi), color, 1, cv2.LINE_AA)
            y += cell

    def predict(self) -> list[SceneFeature]:
        """Returns the dynamically maintained SceneFeatures."""
        # recognize_scene is no longer executed from scratch here.
        return self.last_SceneFeatures

    def best_spell_attempt(self, SceneFeatures: list[SceneFeature]) -> "SpellMatchResult | None":
        """
        Tries every loaded spell against the current `SceneFeatures` and returns
        whichever one scored highest -- REGARDLESS of whether it actually
        cleared its own min_score/all-slots-filled bar (unlike
        spell_matcher.match_best_spell, which only ever returns an ACCEPTED
        result). Surfacing the best near-miss too, not just a flat "no
        spell", is what turns the popup into "you're at 62% towards
        pentagram_seal" style feedback instead of a binary yes/no -- useful
        while you're still calibrating a spell's tolerances.

        Returns None only if there's nothing to compare against (no spells
        loaded, or no recognized SceneFeatures to match with).
        """
        if not self.spells or not SceneFeatures:
            return None

        best: "SpellMatchResult | None" = None
        for spell in self.spells:
            result = match_spell(spell, SceneFeatures)
            if best is None or result.score > best.score:
                best = result
        return best

    # -- Result popup -----------------------------------------------------------

    def show_prediction(self, SceneFeatures: list[SceneFeature]):
        """Displays popup window with score breakdown, plus (if any spells
        are loaded) which spell -- accepted or closest near-miss -- the
        current drawing matches."""
        spell_result = self.best_spell_attempt(SceneFeatures)

        # Popup height grows with the SceneFeature count so a busy scene (a full
        # spell can easily have 5+ recognized SceneFeatures) doesn't get its
        # rows clipped or run into the footer -- 100px header + 70px/SceneFeature
        # + a fixed block for the spell section + footer.
        SceneFeature_block_height = 100 + max(len(SceneFeatures), 1) * 70
        spell_block_height = 90
        footer_height = 60
        total_height = SceneFeature_block_height + spell_block_height + footer_height
        display = np.zeros((total_height, 620, 3), dtype=np.uint8)

        cv2.putText(display, "Recognition Results", (20, 45),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        cv2.line(display, (20, 60), (600, 60), (100, 100, 100), 1)

        if not SceneFeatures:
            cv2.putText(display, "No accepted SceneFeature matches!", (20, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            y = SceneFeature_block_height
        else:
            y = 100
            for i, feat in enumerate(SceneFeatures):
                color = SceneFeature_COLORS[i % len(SceneFeature_COLORS)]
                cv2.putText(display, f"SceneFeature {i + 1}: {feat.result.name}  [{feat.level}]",
                            (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)
                y += 32
                cv2.putText(display, f"   score {feat.result.score:.4f}  (threshold {feat.result.min_score:.2f})   distance {feat.result.distance:.2f} px",
                            (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                y += 38

        # -- Spell section -----------------------------------------------------
        spell_y = SceneFeature_block_height
        cv2.line(display, (20, spell_y - 20), (600, spell_y - 20), (100, 100, 100), 1)

        if not self.spells:
            cv2.putText(display, "No spells loaded (spells/ is empty)", (20, spell_y + 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (140, 140, 140), 1)
        elif spell_result is None or spell_result.name is None:
            # Either nothing scored above 0 for every spell, or the best
            # attempt didn't clear its own acceptance bar. Show the closest
            # attempt's score as progress feedback either way.
            near = f" (closest: {spell_result.score * 100:.0f}%)" if spell_result else ""
            cv2.putText(display, f"No spell detected{near}", (20, spell_y + 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 2)
        else:
            cv2.putText(display, f"Spell cast: {spell_result.name}", (20, spell_y + 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 220, 0), 2)
            cv2.putText(display, f"   match score {spell_result.score * 100:.0f}%  ({len(spell_result.assignment)} SceneFeature(s) matched)",
                        (20, spell_y + 45), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        cv2.putText(
            display,
            "Press Enter/Space to try again | Esc to exit",
            (20, total_height - 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (180, 180, 180),
            1,
        )

        cv2.imshow("Result", display)
        while True:
            key = cv2.waitKey(0) & 0xFF
            if key in (13, 32):
                cv2.destroyWindow("Result")
                return True
            if key == 27:
                cv2.destroyAllWindows()
                raise SystemExit(0)

    # -- Main loop --------------------------------------------------------------

    def run(self):
        """Main canvas GUI loop."""
        print("\n--- $Q Recognizer Drawing Canvas ---")
        print("  - Draw gesture(s)")
        print("  - Press ENTER for detailed results")
        print("  - Press 'c' to clear canvas")
        print("  - Press 'g' to toggle the spatial-index grid overlay")
        print("  - Press ESC to exit\n")

        while True:
            display_canvas = self.canvas.copy()

            if self.show_grid:
                self.draw_grid_overlay(display_canvas)

            cv2.putText(display_canvas, "Draw gesture(s) | ENTER: Recognize | C: Clear | G: Grid | ESC: Exit",
                        (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (120, 120, 120), 1)

            for i, feat in enumerate(self.last_SceneFeatures):
                color = SceneFeature_COLORS[i % len(SceneFeature_COLORS)]
                xs = [p.x for p in feat.points]
                ys = [p.y for p in feat.points]
                x0, y0 = int(min(xs)) - 10, int(min(ys)) - 10
                x1, y1 = int(max(xs)) + 10, int(max(ys)) + 10
                cv2.rectangle(display_canvas, (x0, y0), (x1, y1), color, 1)
                label = f"{feat.result.name} [{feat.level}]  {feat.result.score:.2f}"
                cv2.putText(display_canvas, label, (x0, max(15, y0 - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

            cv2.imshow(self.window_name, display_canvas)
            key = cv2.waitKey(10) & 0xFF

            if key == 13:
                if self.show_prediction(self.last_SceneFeatures):
                    self.reset_canvas()
            elif key == ord('c') or key == ord('C'):
                self.reset_canvas()
            elif key == ord('g') or key == ord('G'):
                self.show_grid = not self.show_grid
            elif key == 27:
                break

        cv2.destroyAllWindows()


if __name__ == "__main__":
    recognizer = build_demo_recognizer()

    spells = load_spells(DEFAULT_SPELLS_DIR)
    if spells:
        print(f"Loaded {len(spells)} spell(s) from '{DEFAULT_SPELLS_DIR}/'")
    else:
        print(f"No spells found in '{DEFAULT_SPELLS_DIR}/' -- ENTER will only show SceneFeature recognition.")

    tester = DollarCanvasTester(recognizer, spells=spells)
    tester.run()