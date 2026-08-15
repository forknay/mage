"""
Template Capture Tool for the $Q Recognizer
============================================
A minimal companion to test_canvas.py, dedicated to building your template
library. It shows a canvas, and while you draw it records every mouse-move
as a raw (x, y, stroke_id) point -- exactly like test_canvas.py does -- so
the *points* come straight from your mouse input, not from the saved image.
The PNG snapshot saved alongside each template is purely a human-readable
reference; it is never read back in for recognition.

Each saved template gets its own JSON file (named after the template, e.g.
templates/circle.json) inside the templates directory, with `level` stored
as a plain integer -- see template_store.py. Level isn't a free label: it
must equal the number of physically-separate stroke units the template's
own strokes resolve to (e.g. a "+" drawn as two crossing strokes is level 1;
a "!" drawn as a non-touching stem + dot is level 2). If you type in a level
that doesn't match, QRecognizer.add_template will reject it at load time.
There's no cap -- level 3, 4, 5... are all valid if the strokes call for it.

How to use:
  1. Run: python template_capture.py
  2. Draw a gesture (left-click + drag). Lifting the mouse ends a stroke;
     clicking again starts a new one -- so for a multi-unit composite (e.g.
     a stem + a separate, non-touching dot), just draw each part as its own
     stroke.
  3. Press ENTER to save what's on the canvas as a template. You'll be
     prompted (in the terminal) for a name and a level. The level must equal
     however many physically-separate (non-touching) stroke units you just
     drew -- get it wrong and the save step will tell you the correct count.
  4. Press 'c' to clear the canvas without saving.
  5. Press ESC to quit.

Saving a template under a name that already exists overwrites its file.

Tunable constants (canvas size, brush thickness, default acceptance score)
live in config.py, not here -- see that file to adjust them.
"""

import os
import numpy as np
import cv2

from merge_intersecting_strokes import Point, DEFAULT_TOUCH_THRESHOLD, count_touch_units
from template_store import append_template, slugify, DEFAULT_TEMPLATES_DIR, DEFAULT_TEMPLATE_IMAGES_DIR
from config import CANVAS_WIDTH, CANVAS_HEIGHT, BRUSH_THICKNESS, DEFAULT_CAPTURE_MIN_SCORE


class TemplateCaptureTool:
    def __init__(self, templates_dir: str = DEFAULT_TEMPLATES_DIR, images_dir: str = DEFAULT_TEMPLATE_IMAGES_DIR):
        self.templates_dir = templates_dir
        self.images_dir = images_dir
        os.makedirs(self.images_dir, exist_ok=True)

        self.window_name = "$Q Template Capture"
        self.canvas = np.zeros((CANVAS_HEIGHT, CANVAS_WIDTH, 3), dtype=np.uint8)
        self.drawing = False
        self.last_point = None
        self.current_stroke: list[Point] = []
        self.next_stroke_id = 0

        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(self.window_name, self.draw_event)

    def reset_canvas(self):
        self.canvas = np.zeros((CANVAS_HEIGHT, CANVAS_WIDTH, 3), dtype=np.uint8)
        self.drawing = False
        self.last_point = None
        self.current_stroke.clear()
        self.next_stroke_id = 0

    # -- Mouse handling -------------------------------------------------------

    def draw_event(self, event, x, y, flags, param):
        """This is where the actual template points come from -- every
        mouse-down/drag/up is recorded as a Point, the same way test_canvas.py
        collects a gesture to recognize."""
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.last_point = (x, y)
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
            self.next_stroke_id += 1  # next pen-down starts a new stroke

    # -- Save flow --------------------------------------------------------------
    # Broken into small steps so the terminal-prompt flow (name -> level ->
    # min_score -> write files) reads top-to-bottom like the interaction
    # itself: `save_current` is just the outline, each helper below does one
    # prompt/validation step.

    def save_current(self):
        if len(self.current_stroke) < 2:
            print("Nothing to save yet -- draw something first.")
            return

        num_strokes = self.next_stroke_id + (1 if self.drawing else 0)
        print(f"\nCaptured {len(self.current_stroke)} points across {num_strokes} stroke(s).")

        name = self._prompt_name()
        if name is None:
            return

        level = self._prompt_level()
        min_score = self._prompt_min_score()

        image_path = self._save_snapshot(name)
        template_path = append_template(
            name=name,
            level=level,
            points=list(self.current_stroke),
            image_path=image_path,
            min_score=min_score,
            templates_dir=self.templates_dir,
        )

        print(f"Saved template '{name}' [level={int(level)}, min_score={min_score}] -> {template_path}")
        print(f"Snapshot image -> {image_path}\n")

        self.reset_canvas()

    def _prompt_name(self) -> "str | None":
        """Prompts for the template name. Returns None (and prints a message) if left empty."""
        name = input("Template name: ").strip()
        if not name:
            print("Empty name, discarding capture.")
            return None
        return name

    def _prompt_level(self) -> int:
        """
        Prompts for the level, defaulting to (and correcting any mismatch
        against) the actual count of physically-separate stroke units in
        what was just drawn -- see count_touch_units.
        """
        actual_units = count_touch_units(self.current_stroke, DEFAULT_TOUCH_THRESHOLD)
        level_input = input(f"Level (physically-separate stroke units drawn: {actual_units}): ")
        level = int(level_input) if level_input.isdigit() else actual_units

        if level != actual_units:
            print(
                f"You entered level={level}, but what you drew resolves to "
                f"{actual_units} physically-separate stroke unit(s) (strokes "
                f"that touch/cross count as one unit; strokes that stay apart "
                f"count separately). Saving it as level={level} would be "
                f"rejected when the recognizer loads it, so using "
                f"level={actual_units} instead."
            )
            level = actual_units

        return level

    def _prompt_min_score(self) -> float:
        """Prompts for the per-template acceptance threshold, falling back to the config default."""
        min_score_input = input(
            f"Acceptance threshold 0.0-1.0 (default: {DEFAULT_CAPTURE_MIN_SCORE}; lower = more forgiving "
            "for gestures that are hard to draw cleanly): "
        ).strip()
        try:
            return float(min_score_input) if min_score_input else DEFAULT_CAPTURE_MIN_SCORE
        except ValueError:
            print(f"Couldn't parse '{min_score_input}' as a number, using default {DEFAULT_CAPTURE_MIN_SCORE}.")
            return DEFAULT_CAPTURE_MIN_SCORE

    def _save_snapshot(self, name: str) -> str:
        """
        Saves a PNG snapshot purely as a human-readable reference -- it is
        never read back in; the recognizer only ever uses `points`.
        """
        slug = slugify(name)
        image_path = os.path.join(self.images_dir, f"{slug}.png")
        cv2.imwrite(image_path, self.canvas)
        return image_path

    # -- Main loop --------------------------------------------------------------

    def run(self):
        print("\n--- $Q Template Capture Tool ---")
        print("  - Draw a gesture (Left-Click & Drag). Lift + click again for a new stroke.")
        print("  - Press ENTER to save it as a template (prompts for name/level in the terminal)")
        print("  - Press 'c' to clear canvas")
        print("  - Press ESC to exit\n")

        while True:
            display_canvas = self.canvas.copy()
            cv2.putText(display_canvas, "Draw | ENTER: Save as template | C: Clear | ESC: Exit",
                        (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (120, 120, 120), 1)
            cv2.imshow(self.window_name, display_canvas)
            key = cv2.waitKey(10) & 0xFF

            if key == 13:
                self.save_current()
            elif key == ord('c') or key == ord('C'):
                self.reset_canvas()
            elif key == 27:
                break

        cv2.destroyAllWindows()


if __name__ == "__main__":
    tool = TemplateCaptureTool()
    tool.run()