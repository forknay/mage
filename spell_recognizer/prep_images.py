import shutil
from pathlib import Path

import cv2

from image_utils import augment_drawing, crop_and_pad_drawing


BASE_DIR = Path(__file__).resolve().parents[1]
DATASET_DIR = BASE_DIR / "spell_recognizer" / "dataset"
OUTPUT_DIR = BASE_DIR / "spell_recognizer" / "dataset_prep"
TARGET_SIZE = (128, 128)
NUM_VARIATIONS = 10
PADDING = 20
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff"}
SPELLS = ["fireball", "tornado", "water_wall", "unknown"]  # Add more spell names as needed


def clear_dataset_prep():
    if OUTPUT_DIR.exists():
        for item in OUTPUT_DIR.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def preprocess_dataset():
    for split_name in ("train", "val"):
        for spell_name in SPELLS:
            input_dir = DATASET_DIR / split_name / spell_name
            output_dir = OUTPUT_DIR / split_name / spell_name
            output_dir.mkdir(parents=True, exist_ok=True)

            if not input_dir.exists():
                print(f"Skipping missing directory: {input_dir}")
                continue

            for image_path in sorted(input_dir.iterdir()):
                if not image_path.is_file() or image_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue

                img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
                if img is None:
                    print(f"Skipping unreadable image: {image_path}")
                    continue

                cropped_img = crop_and_pad_drawing(img, padding=PADDING)
                resized_img = cv2.resize(
                    cropped_img,
                    TARGET_SIZE,
                    interpolation=cv2.INTER_AREA,
                )

                augment_drawing(
                    resized_img,
                    output_dir=str(output_dir),
                    num_variations=NUM_VARIATIONS,
                    prefix=image_path.stem,
                )

                print(f"Processed: {image_path} -> {output_dir}")

    print("Dataset preprocessing complete.")


if __name__ == "__main__":
    clear_dataset_prep()
    preprocess_dataset()
