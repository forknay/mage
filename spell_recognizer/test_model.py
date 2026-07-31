import cv2
import numpy as np
import onnxruntime as ort
from pathlib import Path

from image_utils import crop_and_pad_drawing


BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "spell_cnn.onnx"
CLASS_DIR = BASE_DIR / "dataset_prep" / "train"
CANVAS_WIDTH = 1000
CANVAS_HEIGHT = 1000
BRUSH_THICKNESS = 5


def load_model_and_classes():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"ONNX model not found: {MODEL_PATH}")

    class_names = sorted([p.name for p in CLASS_DIR.iterdir() if p.is_dir()])
    if not class_names:
        class_names = [f"class_{i}" for i in range(3)]

    session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    return session, input_name, class_names


def preprocess_image(img: np.ndarray) -> np.ndarray:
    cropped = crop_and_pad_drawing(img, padding=20)
    resized = cv2.resize(cropped, (128, 128), interpolation=cv2.INTER_AREA)
    resized = resized.astype(np.float32) / 255.0
    resized = (resized - 0.5) / 0.5
    return resized[None, None, :, :]


def to_independent_probabilities(logits: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(logits, dtype=np.float32), -50, 50)
    return 1.0 / (1.0 + np.exp(-clipped))


class DrawingTester:
    def __init__(self, session, input_name, class_names):
        self.session = session
        self.input_name = input_name
        self.class_names = class_names
        self.window_name = "Spell Tester"
        self.canvas = np.zeros((CANVAS_HEIGHT, CANVAS_WIDTH), dtype=np.uint8)
        self.drawing = False
        self.last_point = None

        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(self.window_name, self.draw_event)

    def reset_canvas(self):
        self.canvas = np.zeros((CANVAS_HEIGHT, CANVAS_WIDTH), dtype=np.uint8)
        self.drawing = False
        self.last_point = None

    def draw_event(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.last_point = (x, y)
            cv2.circle(self.canvas, (x, y), BRUSH_THICKNESS // 2, 255, -1, cv2.LINE_AA)
        elif event == cv2.EVENT_MOUSEMOVE:
            if self.drawing and self.last_point is not None:
                cv2.line(
                    self.canvas,
                    self.last_point,
                    (x, y),
                    255,
                    BRUSH_THICKNESS,
                    cv2.LINE_AA,
                )
                self.last_point = (x, y)
        elif event == cv2.EVENT_LBUTTONUP:
            self.drawing = False
            self.last_point = None

    def predict(self):
        input_data = preprocess_image(self.canvas)
        outputs = self.session.run(None, {self.input_name: input_data})
        raw_output = np.asarray(outputs[0][0], dtype=np.float32)
        return raw_output

    def show_prediction(self, raw_scores):
        display = np.zeros((400, 700, 3), dtype=np.uint8)
        title = "Prediction"
        cv2.putText(display, title, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

        scores = to_independent_probabilities(raw_scores)
        for idx, name in enumerate(self.class_names):
            score = scores[idx]
            line = f"{name}: {score:.6f}"
            y = 90 + idx * 35
            cv2.putText(display, line, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        cv2.putText(
            display,
            "Press Enter for next sample | Esc to exit",
            (20, 360),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
        )

        cv2.imshow("Prediction", display)
        while True:
            key = cv2.waitKey(0) & 0xFF
            if key == 13:
                cv2.destroyWindow("Prediction")
                return True
            if key == 27:
                cv2.destroyAllWindows()
                raise SystemExit(0)

    def run(self):
        while True:
            cv2.imshow(self.window_name, self.canvas)
            key = cv2.waitKey(10) & 0xFF

            if key == 13:
                raw_scores = self.predict()
                if self.show_prediction(raw_scores):
                    self.reset_canvas()
                    cv2.destroyWindow(self.window_name)
                    cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
                    cv2.setMouseCallback(self.window_name, self.draw_event)
            elif key == 27:
                break

        cv2.destroyAllWindows()


if __name__ == "__main__":
    session, input_name, class_names = load_model_and_classes()
    tester = DrawingTester(session, input_name, class_names)
    tester.run()
