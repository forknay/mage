"""
Interactive Drawing Canvas for testing the $Q Point-Cloud Recognizer.

How to use:
  1. Make sure recognizer.py and merge_intersecting_strokes.py are in the same folder.
  2. Run this script: python test_canvas.py
  3. Draw with your mouse (left-click + drag). Lifting the mouse button ends a
     stroke; clicking again starts a brand new one -- so you can draw a
     multi-stroke figure (like a "+" or a "!") or several unrelated shapes
     anywhere on the canvas before recognizing.
  4. Press ENTER / RETURN to run recognition. Strokes are automatically
     bundled by proximity into one or more "features" (see Level in
     recognizer.py): touching/crossing strokes become a single SHAPE, nearby-
     but-separate strokes become a composite OBJECT, and strokes drawn far
     apart are recognized as independent features. Every feature found gets
     its own result -- not just a single top-1 guess for the whole canvas.
  5. Press 'c' at any time to clear the canvas and try drawing again.
  6. Press ESC to quit.
"""

import math
import numpy as np
import cv2

# Change this import:
from recognizer import Point, QRecognizer, Level, SceneFeature


# --- Constants & Configuration ---
CANVAS_WIDTH = 800
CANVAS_HEIGHT = 800
BRUSH_THICKNESS = 4

# Distinct colors (BGR) cycled through to label each recognized feature.
FEATURE_COLORS = [
    (0, 255, 0),
    (0, 128, 255),
    (255, 200, 0),
    (255, 0, 255),
    (0, 255, 255),
]


def generate_line_points(angle_deg: float, length: float = 300.0, n: int = 40, stroke_id: int = 0) -> list[Point]:
    """Helper to generate template stroke points at specific angles."""
    angle = math.radians(angle_deg)
    dx, dy = math.cos(angle) * length, math.sin(angle) * length
    return [Point(t / (n - 1) * dx, t / (n - 1) * dy, stroke_id) for t in range(n)]


def generate_dot_points(cx: float, cy: float, radius: float = 10.0, n: int = 12, stroke_id: int = 0) -> list[Point]:
    """Helper to generate a small circular 'dot' stroke (e.g. for punctuation)."""
    return [
        Point(cx + radius * math.cos(a), cy + radius * math.sin(a), stroke_id)
        for a in np.linspace(0, 2 * math.pi, n)
    ]


def build_demo_recognizer() -> QRecognizer:
    """Initialize the recognizer and register default template gestures at each level."""
    rec = QRecognizer()

    # --- Level.SHAPE templates: single-primitive gestures -------------------
    rec.add_template("line_horizontal", generate_line_points(0), level=Level.SHAPE)
    rec.add_template("line_vertical", generate_line_points(90), level=Level.SHAPE)
    rec.add_template("line_diag_down", generate_line_points(45), level=Level.SHAPE)  # '\' direction in screen coords
    rec.add_template("line_diag_up", generate_line_points(135), level=Level.SHAPE)   # '/' direction in screen coords

    # Circle (drawn clockwise starting from rightmost point)
    circle_pts = [
        Point(200 + 100 * math.cos(a), 200 + 100 * math.sin(a))
        for a in np.linspace(0, 2 * math.pi, 50)
    ]
    rec.add_template("circle", circle_pts, level=Level.SHAPE)

    # Caret / Chevron '^'
    caret_pts = [Point(0, 100), Point(50, 0), Point(100, 100)]
    rec.add_template("caret", caret_pts, level=Level.SHAPE)

    # V-Shape 'v'
    v_pts = [Point(0, 0), Point(50, 100), Point(100, 0)]
    rec.add_template("v_shape", v_pts, level=Level.SHAPE)

    # --- Level.OBJECT templates: composite, multi-part figures --------------
    # These are made of two or more strokes that don't necessarily touch, so
    # they can only be told apart from a pile of unrelated single strokes once
    # bundled together at the OBJECT level.

    # Exclamation mark "!" = a vertical stem stroke + a separate dot stroke
    # underneath it, with a gap between them.
    exclaim_stem = [Point(0.0, y, stroke_id=0) for y in np.linspace(0, 150, 20)]
    exclaim_dot = generate_dot_points(0.0, 185.0, radius=10.0, stroke_id=1)
    rec.add_template("exclaim", exclaim_stem + exclaim_dot, level=Level.OBJECT)

    # Colon ":" = two separate dot strokes stacked with a gap.
    colon_top = generate_dot_points(0.0, 0.0, radius=10.0, stroke_id=0)
    colon_bottom = generate_dot_points(0.0, 60.0, radius=10.0, stroke_id=1)
    rec.add_template("colon", colon_top + colon_bottom, level=Level.OBJECT)

    # Plus "+" made of two strokes that cross -- registered as its own
    # composite figure rather than just two independent lines.
    plus_h = [Point(x - 50, 0, stroke_id=0) for x in np.linspace(0, 100, 20)]
    plus_v = [Point(0, y - 50, stroke_id=1) for y in np.linspace(0, 100, 20)]
    rec.add_template("plus", plus_h + plus_v, level=Level.OBJECT)

    return rec


class DollarCanvasTester:
    def __init__(self, recognizer: QRecognizer):
        self.recognizer = recognizer
        self.window_name = "$Q Recognizer Tester"
        self.canvas = np.zeros((CANVAS_HEIGHT, CANVAS_WIDTH, 3), dtype=np.uint8)
        self.drawing = False
        self.last_point = None
        self.current_stroke: list[Point] = []
        self.next_stroke_id = 0
        self.last_features: list[SceneFeature] = []

        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(self.window_name, self.draw_event)

    def reset_canvas(self):
        """Clears the visual canvas and point buffer."""
        self.canvas = np.zeros((CANVAS_HEIGHT, CANVAS_WIDTH, 3), dtype=np.uint8)
        self.drawing = False
        self.last_point = None
        self.current_stroke.clear()
        self.next_stroke_id = 0
        self.last_features = []

    def draw_event(self, event, x, y, flags, param):
        """Mouse callback handling continuous line drawing and multi-stroke point collection."""
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.last_point = (x, y)
            # Every new pen-down starts a brand new stroke_id. This is what
            # lets separate strokes be told apart and later re-bundled (by
            # proximity, per Level) into one or more recognized features.
            self.current_stroke.append(Point(float(x), float(y), stroke_id=self.next_stroke_id))
            self.last_features = []  # stale the moment a new stroke starts
            cv2.circle(self.canvas, (x, y), BRUSH_THICKNESS // 2, (255, 255, 255), -1, cv2.LINE_AA)

        elif event == cv2.EVENT_MOUSEMOVE:
            if self.drawing and self.last_point is not None:
                cv2.line(
                    self.canvas,
                    self.last_point,
                    (x, y),
                    (255, 255, 255),
                    BRUSH_THICKNESS,
                    cv2.LINE_AA,
                )
                self.last_point = (x, y)
                self.current_stroke.append(Point(float(x), float(y), stroke_id=self.next_stroke_id))

        elif event == cv2.EVENT_LBUTTONUP:
            self.drawing = False
            self.last_point = None
            self.next_stroke_id += 1  # the next pen-down begins a new stroke

    def predict(self) -> list[SceneFeature]:
        """Recognizes every spatially distinct bundle of strokes currently on the canvas."""
        if len(self.current_stroke) < 2:
            return []
        return self.recognizer.recognize_scene(self.current_stroke)

    def show_prediction(self, features: list[SceneFeature]):
        """Displays recognition results (one row per detected feature) in a pop-up UI window."""
        display = np.zeros((420, 620, 3), dtype=np.uint8)

        cv2.putText(display, "Recognition Results", (20, 45),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        cv2.line(display, (20, 60), (600, 60), (100, 100, 100), 1)

        if not features:
            cv2.putText(display, "Not enough stroke points drawn!", (20, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        else:
            y = 100
            for i, feat in enumerate(features):
                color = FEATURE_COLORS[i % len(FEATURE_COLORS)]
                cv2.putText(display, f"Feature {i + 1}: {feat.result.name}  [{feat.level.name}]",
                            (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)
                y += 32
                cv2.putText(display, f"   score {feat.result.score:.4f}   distance {feat.result.distance:.2f} px",
                            (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                y += 38

        cv2.putText(
            display,
            "Press Enter/Space to try again | Esc to exit",
            (20, 390),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (180, 180, 180),
            1,
        )

        cv2.imshow("Result", display)
        while True:
            key = cv2.waitKey(0) & 0xFF
            if key in (13, 32):  # Enter or Space key
                cv2.destroyWindow("Result")
                return True
            if key == 27:        # ESC key
                cv2.destroyAllWindows()
                raise SystemExit(0)

    def run(self):
        """Main rendering/key event loop."""
        print("\n--- $Q Recognizer Drawing Canvas ---")
        print("  - Draw one or more strokes (Left-Click & Drag)")
        print("  - Press ENTER to recognize every feature on the canvas")
        print("  - Press 'c' to clear canvas")
        print("  - Press ESC to exit\n")

        while True:
            # Render HUD instructions on the drawing window
            display_canvas = self.canvas.copy()
            cv2.putText(display_canvas, "Draw gesture(s) | ENTER: Recognize | C: Clear | ESC: Exit",
                        (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (120, 120, 120), 1)

            # Overlay a bounding box + label for each feature from the last
            # recognition pass, so it's immediately visible which strokes got
            # bundled together and what each bundle was recognized as.
            for i, feat in enumerate(self.last_features):
                color = FEATURE_COLORS[i % len(FEATURE_COLORS)]
                xs = [p.x for p in feat.points]
                ys = [p.y for p in feat.points]
                x0, y0 = int(min(xs)) - 10, int(min(ys)) - 10
                x1, y1 = int(max(xs)) + 10, int(max(ys)) + 10
                cv2.rectangle(display_canvas, (x0, y0), (x1, y1), color, 2)
                label = f"{feat.result.name} [{feat.level.name}]"
                cv2.putText(display_canvas, label, (x0, max(15, y0 - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

            cv2.imshow(self.window_name, display_canvas)
            key = cv2.waitKey(10) & 0xFF

            if key == 13:  # Press ENTER to predict
                features = self.predict()
                self.last_features = features
                if self.show_prediction(features):
                    self.reset_canvas()
            elif key == ord('c') or key == ord('C'):  # Clear canvas
                self.reset_canvas()
            elif key == 27:  # Press ESC to quit
                break

        cv2.destroyAllWindows()


if __name__ == "__main__":
    recognizer = build_demo_recognizer()
    tester = DollarCanvasTester(recognizer)
    tester.run()