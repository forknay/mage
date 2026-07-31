import os
from pathlib import Path

import cv2
import numpy as np

# ==========================================
# Configuration / Setup
# ==========================================
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAVE_DIR = PROJECT_ROOT / "spell_recognizer" / "dataset" / "val" / "unknown"  # Path where images will be saved
FILE_PREFIX = "unknown"  # Base name for saved images
START_INDEX = 8  # Starting index for auto-incrementing filename

# Canvas dimensions (Set to your preferred resolution)
CANVAS_WIDTH = 1000
CANVAS_HEIGHT = 1000
BRUSH_THICKNESS = 5  # Line thickness in pixels


# ==========================================
# Canvas Application Class
# ==========================================
class DrawingCanvas:

    def __init__(self, save_dir, file_prefix, start_index, width, height):
        self.save_dir = save_dir
        self.file_prefix = file_prefix
        self.current_index = start_index
        self.width = width
        self.height = height

        # Drawing state variables
        self.drawing = False
        self.last_point = None

        # Create output directory if it doesn't exist
        self.save_dir = os.fspath(Path(self.save_dir).expanduser().resolve())
        os.makedirs(self.save_dir, exist_ok=True)

        # Initialize black canvas
        self.reset_canvas()

        # Set up OpenCV window and mouse callbacks
        self.window_name = "Drawing Canvas (Enter: Save | Esc: Exit)"
        cv2.namedWindow(self.window_name, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(self.window_name, self.draw_event)

    def reset_canvas(self):
        """Creates a fresh black canvas (single-channel grayscale or 3-channel BGR)."""
        # 1-channel grayscale black image (0 = Black, 255 = White)
        self.canvas = np.zeros((self.height, self.width), dtype=np.uint8)
        self.drawing = False
        self.last_point = None

    def draw_event(self, event, x, y, flags, param):
        """Mouse callback handling drawing with left click held down."""
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.last_point = (x, y)
            # Draw a dot on initial click
            cv2.circle(
                self.canvas, (x, y), BRUSH_THICKNESS // 2, 255, -1, cv2.LINE_AA
            )

        elif event == cv2.EVENT_MOUSEMOVE:
            if self.drawing:
                current_point = (x, y)
                if self.last_point is not None:
                    # Draw anti-aliased line connecting previous point to current point
                    cv2.line(
                        self.canvas,
                        self.last_point,
                        current_point,
                        255,
                        BRUSH_THICKNESS,
                        cv2.LINE_AA,
                    )
                self.last_point = current_point

        elif event == cv2.EVENT_LBUTTONUP:
            self.drawing = False
            self.last_point = None

    def save_image(self):
        """Saves current drawing and increments index."""
        file_name = f"{self.file_prefix}_{self.current_index}.png"
        save_path = os.path.join(self.save_dir, file_name)

        # Save grayscale PNG
        success = cv2.imwrite(save_path, self.canvas)
        if success:
            print(f"Saved: {save_path}")
        else:
            print(f"Failed to save image: {save_path}")

        # Increment index for next image
        self.current_index += 1

    def run(self):
        """Main application loop."""
        print("\n=== Drawing Canvas Instructions ===")
        print("- Hold Left Click to draw white lines.")
        print("- Press ENTER to save drawing and clear canvas.")
        print("- Press ESC to exit.")
        print(
            f"Saving to: {os.path.abspath(self.save_dir)}/{self.file_prefix}_<INDEX>.png\n"
        )
        while True:
            # Display the drawing canvas
            cv2.imshow(self.window_name, self.canvas)

            # Wait 10ms for key inputs
            key = cv2.waitKey(10) & 0xFF

            # Key 13 = Enter Key
            if key == 13:
                self.save_image()
                self.reset_canvas()

            # Key 27 = Escape Key
            elif key == 27:
                print("Exiting canvas...")
                break

        cv2.destroyAllWindows()


# ==========================================
# Main Entry Point
# ==========================================
if __name__ == "__main__":
    app = DrawingCanvas(
        save_dir=SAVE_DIR,
        file_prefix=FILE_PREFIX,
        start_index=START_INDEX,
        width=CANVAS_WIDTH,
        height=CANVAS_HEIGHT,
    )
    app.run()