import cv2
import os
import random
import cv2
import numpy as np


def downscale_image(input_path, output_path, target_size=None):
    """Resizes an image using cv2.INTER_AREA interpolation for optimal downscaling.

    :param input_path: Path to the original image.
    :param output_path: Path to save the resized image.
    :param scale_percent: Percentage to shrink (e.g., 50 for half size).
    :param target_size: Tuple (width, height) for exact dimensions.
    """
    # 1. Read the input image
    img = cv2.imread(input_path)

    if img is None:
        raise FileNotFoundError(f"Could not load image at {input_path}")

    # Calculate target dimensions
    if target_size is not None:
        # Use exact dimensions
        dim = target_size
    else:
        raise ValueError("Specify 'target_size'.")

    # 2. Perform downsizing using INTER_AREA
    resized_img = cv2.resize(img, dim, interpolation=cv2.INTER_AREA)

    # 3. Save the downsized image
    cv2.imwrite(output_path, resized_img)

    print(
        f"Original Size: {img.shape[1]}x{img.shape[0]} | "
        f"New Size: {resized_img.shape[1]}x{resized_img.shape[0]}"
    )

# ==========================================
# Crop & Pad Helper Function
# ==========================================
def crop_and_pad_drawing(img: np.ndarray, padding: int = 20) -> np.ndarray:
    """Finds the bounding box (min/max height and width) of white drawing pixels,

    crops the image to that box, and adds a specified uniform background padding.
    """
    # Find coordinates of all white pixels (> 0)
    white_points = cv2.findNonZero(img)

    # If canvas is completely blank, return original image
    if white_points is None:
        print("Warning: Canvas is empty. Saving full black image.")
        return img

    # Get bounding box extremities
    x, y, w, h = cv2.boundingRect(white_points)
    min_x, max_x = x, x + w
    min_y, max_y = y, y + h

    # Crop tight to the drawing boundaries
    cropped = img[min_y:max_y, min_x:max_x]

    # Add black padding around the cropped gesture
    padded_img = cv2.copyMakeBorder(
        cropped,
        top=padding,
        bottom=padding,
        left=padding,
        right=padding,
        borderType=cv2.BORDER_CONSTANT,
        value=0,  # 0 = Black background padding
    )

    return padded_img


def augment_drawing(
    img: np.ndarray,
    output_dir: str = "augmented_spells",
    num_variations: int = 10,
    prefix: str = "variation",
):
    """Generates synthetic variations of hand-drawn spell gestures using perspective

    warping and morphological operations (line thinning/thickening).
    """
    if img is None:
        raise ValueError("img must be a valid numpy array")

    h, w = img.shape
    os.makedirs(output_dir, exist_ok=True)

    # Process the image directly as white ink on a black background.
    # The foreground is bright and should be thickened/thinned in place.
    base_img = img.copy()

    for i in range(1, num_variations + 1):
        aug_img = base_img.copy()

        # ---------------------------------------------------------
        # 1. Morphological Operation (Line Thinning or Thickening)
        # ---------------------------------------------------------
        # Randomly choose line thickness effect (0: Thin, 1: Thick, 2: Keep original)
        effect = random.choice(["thin", "thick", "none"])
        kernel_size = random.choice([2, 3])  # Small kernels prevent over-distortion
        kernel = np.ones((kernel_size, kernel_size), np.uint8)

        # With white ink on black background, erosion thins the bright strokes
        # and dilation thickens them. We make thinning conservative so the result
        # stays visible and does not collapse into a very thin line.
        if effect == "thin":
            eroded = cv2.erode(aug_img, kernel, iterations=1)
            nonzero_before = cv2.countNonZero(aug_img)
            nonzero_after = cv2.countNonZero(eroded)
            if nonzero_after < max(200, int(0.55 * nonzero_before)):
                aug_img = aug_img
            else:
                aug_img = eroded
        elif effect == "thick":
            aug_img = cv2.dilate(aug_img, kernel, iterations=1)

        # ---------------------------------------------------------
        # 2. Slight Perspective Warping (Non-linear Stretch)
        # ---------------------------------------------------------
        # Define original four corner points
        pts1 = np.float32([[0, 0], [w, 0], [0, h], [w, h]])

        # Shift corners randomly by a few pixels (-5% to +5% of image dims)
        max_shift = int(min(h, w) * 0.05)
        pts2 = np.float32(
            [
                [
                    random.randint(-max_shift, max_shift),
                    random.randint(-max_shift, max_shift),
                ],
                [
                    w + random.randint(-max_shift, max_shift),
                    random.randint(-max_shift, max_shift),
                ],
                [
                    random.randint(-max_shift, max_shift),
                    h + random.randint(-max_shift, max_shift),
                ],
                [
                    w + random.randint(-max_shift, max_shift),
                    h + random.randint(-max_shift, max_shift),
                ],
            ]
        )

        # Compute transformation matrix and warp
        matrix = cv2.getPerspectiveTransform(pts1, pts2)
        aug_img = cv2.warpPerspective(
            aug_img,
            matrix,
            (w, h),
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )

        # Save variation
        out_path = os.path.join(output_dir, f"{prefix}_var_{i}.png")
        cv2.imwrite(out_path, aug_img)

    print(f"Successfully created {num_variations} variations in '{output_dir}/'")
