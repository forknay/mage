"""
Orientation-Sensitive $Q$ Super-Quick Recognizer
=================================================
An orientation-sensitive implementation of Vatavu, Anthony & Wobbrock's 
$Q$ Recognizer (2018).

Unlike $1, $Q treats gestures as Point Clouds. This makes gesture recognition 
inherently invariant to STROKE DIRECTION and STARTING POINT, while retaining 
high accuracy and sub-millisecond matching speed via a 2D Look-Up Table (LUT).

On top of the base $Q algorithm, this module adds "level" bundling: strokes
can be registered/recognized as simple SHAPE primitives (a line, a circle...)
or as composite OBJECT figures made of several strokes that belong together
without necessarily touching (see merge_intersecting_strokes.Level). A whole
canvas can then be split into multiple independent features and recognized in
one pass via `QRecognizer.recognize_scene`.

Reference:
  Vatavu, R.-D., Anthony, L. and Wobbrock, J.O. (2018).
  $Q: A Super-Quick, Accurate $1-Family Recognizer for User Interfaces.
  Proc. ACM Hum.-Comput. Interact. 2, ISS, Article 140 (November 2018).
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple
from merge_intersecting_strokes import (
    Point,
    Level,
    DEFAULT_LEVEL_THRESHOLDS,
    merge_intersecting_strokes,
    bundle_by_level,
)


# ---------------------------------------------------------------------------
# Core Data Structures
# ---------------------------------------------------------------------------
# Point is imported from merge_intersecting_strokes so the whole pipeline
# (canvas -> bundling -> preprocessing -> recognition) shares one definition.


@dataclass
class Template:
    name: str
    points: List[Point]       # Preprocessed points
    lut: List[List[int]]      # 2D Look-Up Table for fast distance queries
    level: Level = Level.SHAPE  # Complexity tier this template was registered at


@dataclass
class RecognitionResult:
    name: Optional[str]
    score: float      # 1.0 = perfect match, 0.0 = worst possible
    distance: float   # Raw lower-bound point-cloud distance (lower is better)


@dataclass
class SceneFeature:
    """
    One spatially-distinct bundle of strokes recognized on a canvas, plus the
    result of classifying it. `QRecognizer.recognize_scene` returns a list of
    these -- one per detected feature -- instead of forcing an entire canvas
    into a single top-1 guess.
    """
    cluster_id: int
    level: Level
    result: RecognitionResult
    points: List[Point]       # Raw points belonging to this feature


# ---------------------------------------------------------------------------
# $Q$ Recognizer Implementation
# ---------------------------------------------------------------------------

class QRecognizer:
    """
    $Q$ Gesture Recognizer.
    
    Inherent Properties:
      - Direction Invariant: Drawing forward or backward gives the same score.
      - Start-Point Invariant: Starting at any corner or loop point gives the same score.
      - Orientation Sensitive: Uniform scaling preserves shape aspect ratio and orientation.
      - Level Aware: templates are registered at a complexity Level (SHAPE or
        OBJECT); strokes are bundled with a threshold matching that level
        before being compared, and `recognize_scene` can pick out and
        classify multiple independent features on the same canvas.
    """

    def __init__(self,
                 num_resample_points: int = 32,
                 frame_size: float = 250.0,
                 lut_size: int = 32,
                 level_thresholds: Optional[dict] = None):
        self.n = num_resample_points          # Point cloud size (N)
        self.frame_size = frame_size          # Normalized bounding box scale
        self.lut_size = lut_size              # Grid resolution for 2D Look-Up Table (m)
        self.templates: List[Template] = []
        self._max_distance = math.hypot(frame_size, frame_size)
        # Per-instance override of the default proximity thresholds used to
        # bundle strokes at each complexity level (see merge_intersecting_strokes.Level).
        self.level_thresholds = {**DEFAULT_LEVEL_THRESHOLDS, **(level_thresholds or {})}

    # -- Public API -----------------------------------------------------

    def add_template(self, name: str, points: List[Point], level: Level = Level.SHAPE) -> None:
        """Registers a gesture (single stroke or multi-stroke) as a template at a given complexity level."""
        processed = self._preprocess(points, level=level)
        lut = self._create_lut(processed)
        self.templates.append(Template(name=name, points=processed, lut=lut, level=level))

    def recognize(self, points: List[Point],
                  level: Level = Level.SHAPE,
                  candidate_names: Optional[List[str]] = None) -> RecognitionResult:
        """Classifies a raw stroke against registered templates of a given complexity `level`."""
        if not self.templates:
            raise ValueError("No templates registered.")

        candidates = [t for t in self.templates if t.level == level]
        if candidate_names is not None:
            candidates = [t for t in candidates if t.name in candidate_names]
        if not candidates:
            raise ValueError(f"No templates registered at level={level.name} matching the given candidate_names.")

        processed = self._preprocess(points, level=level)

        best_name = None
        best_distance = math.inf

        for template in candidates:
            distance = self._cloud_distance(processed, template.points, template.lut)
            if distance < best_distance:
                best_distance = distance
                best_name = template.name

        # Calculate normalized score [0.0, 1.0]
        score = max(0.0, 1.0 - best_distance / self._max_distance)
        return RecognitionResult(name=best_name, score=score, distance=best_distance)

    def recognize_scene(self, points: List[Point],
                         object_threshold: Optional[float] = None,
                         min_score: float = 0.0) -> List[SceneFeature]:
        """
        Splits raw canvas input into spatially distinct bundles ("objects",
        using a loose OBJECT-level proximity threshold) and recognizes each
        one independently -- this is what allows a single canvas to contain,
        and correctly report, more than one drawn feature at once.

        For every bundle, this first tries to match it against composite
        OBJECT-level templates (multi-part figures); if no OBJECT template
        scores better, it falls back to matching the bundle as a single
        SHAPE-level primitive. Whichever level scores higher wins.
        """
        if not points or not self.templates:
            return []

        obj_thr = object_threshold if object_threshold is not None else self.level_thresholds.get(
            Level.OBJECT, DEFAULT_LEVEL_THRESHOLDS[Level.OBJECT]
        )
        clusters = bundle_by_level(points, Level.OBJECT, obj_thr)

        levels_present = {t.level for t in self.templates}
        # Try the richer OBJECT-level match first, then fall back to SHAPE.
        ordered_levels = [lvl for lvl in (Level.OBJECT, Level.SHAPE) if lvl in levels_present]

        features: List[SceneFeature] = []
        for cluster_id, cluster_points in enumerate(clusters):
            best_result: Optional[RecognitionResult] = None
            best_level: Optional[Level] = None

            for lvl in ordered_levels:
                try:
                    result = self.recognize(cluster_points, level=lvl)
                except ValueError:
                    continue
                if best_result is None or result.score > best_result.score:
                    best_result, best_level = result, lvl

            if best_result is not None and best_result.score >= min_score:
                features.append(SceneFeature(
                    cluster_id=cluster_id,
                    level=best_level,
                    result=best_result,
                    points=cluster_points,
                ))

        return features

    # -- Preprocessing Pipeline -----------------------------------------

    def _preprocess(self, points: List[Point], level: Level = Level.SHAPE) -> List[Point]:
        # Merge overlapping/intersecting strokes before processing! The
        # threshold depends on the complexity level being matched: SHAPE
        # templates only fuse strokes that actually touch, while OBJECT
        # templates are allowed to fuse strokes that are merely close together.
        threshold = self.level_thresholds.get(level, DEFAULT_LEVEL_THRESHOLDS.get(level, 8.0))
        pts = merge_intersecting_strokes(points, proximity_threshold=threshold)

        pts = self._dedupe(pts)
        pts = self._resample(pts, self.n)
        pts = self._scale_uniform(pts, self.frame_size)
        pts = self._translate_to_origin(pts)
        return pts

    @staticmethod
    def _dedupe(points: List[Point]) -> List[Point]:
        if not points:
            return []
        out = [points[0]]
        for p in points[1:]:
            if math.hypot(p.x - out[-1].x, p.y - out[-1].y) > 1e-9:
                out.append(p)
        return out

    @staticmethod
    def _path_length(points: List[Point]) -> float:
        d = 0.0
        for i in range(1, len(points)):
            if points[i].stroke_id == points[i - 1].stroke_id:
                d += math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y)
        return d

    def _resample(self, points: List[Point], n: int) -> List[Point]:
        if len(points) < 2:
            p = points[0] if points else Point(0.0, 0.0)
            return [p] * n

        pts = list(points)
        interval = self._path_length(pts) / (n - 1)
        if interval <= 1e-9:
            return [pts[0]] * n

        D = 0.0
        new_points = [pts[0]]
        i = 1
        while i < len(pts):
            if pts[i].stroke_id == pts[i - 1].stroke_id:
                d = math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y)
                if (D + d) >= interval:
                    t = (interval - D) / d
                    q = Point(
                        pts[i - 1].x + t * (pts[i].x - pts[i - 1].x),
                        pts[i - 1].y + t * (pts[i].y - pts[i - 1].y),
                        pts[i].stroke_id
                    )
                    new_points.append(q)
                    pts.insert(i, q)
                    D = 0.0
                else:
                    D += d
            i += 1

        while len(new_points) < n:
            new_points.append(pts[-1])
        return new_points[:n]

    @staticmethod
    def _bounding_box(points: List[Point]) -> Tuple[float, float, float, float]:
        min_x = min(p.x for p in points)
        max_x = max(p.x for p in points)
        min_y = min(p.y for p in points)
        max_y = max(p.y for p in points)
        return min_x, min_y, max_x - min_x, max_y - min_y

    def _scale_uniform(self, points: List[Point], size: float) -> List[Point]:
        min_x, min_y, w, h = self._bounding_box(points)
        scale = size / max(w, h, 1e-9)
        return [Point((p.x - min_x) * scale, (p.y - min_y) * scale, p.stroke_id) for p in points]

    @staticmethod
    def _centroid(points: List[Point]) -> Point:
        x = sum(p.x for p in points) / len(points)
        y = sum(p.y for p in points) / len(points)
        return Point(x, y)

    def _translate_to_origin(self, points: List[Point]) -> List[Point]:
        c = self._centroid(points)
        return [Point(p.x - c.x, p.y - c.y, p.stroke_id) for p in points]

    # -- $Q$ Look-Up Table (LUT) Engine -----------------------------------

    def _create_lut(self, points: List[Point]) -> List[List[int]]:
        """Pre-computes a 2D Look-Up Table storing the index of the nearest
        template point for every grid cell on the normalized frame."""
        lut = [[0 for _ in range(self.lut_size)] for _ in range(self.lut_size)]
        scale = self.lut_size / self.frame_size

        for x in range(self.lut_size):
            # Center of grid cell in normalized coordinates
            px = (x + 0.5) / scale - self.frame_size / 2.0
            for y in range(self.lut_size):
                py = (y + 0.5) / scale - self.frame_size / 2.0

                best_idx = 0
                best_dist = math.inf
                for idx, p in enumerate(points):
                    d = math.hypot(p.x - px, p.y - py)
                    if d < best_dist:
                        best_dist = d
                        best_idx = idx
                lut[x][y] = best_idx

        return lut

    def _cloud_distance(self, candidate_pts: List[Point], 
                       template_pts: List[Point], 
                       lut: List[List[int]]) -> float:
        """Fast point-cloud distance calculation using LUT indexing."""
        scale = self.lut_size / self.frame_size
        total_dist = 0.0

        for p in candidate_pts:
            # Map point coordinates to LUT grid indices
            gx = int((p.x + self.frame_size / 2.0) * scale)
            gy = int((p.y + self.frame_size / 2.0) * scale)

            # Clamp index within grid bounds
            gx = max(0, min(self.lut_size - 1, gx))
            gy = max(0, min(self.lut_size - 1, gy))

            # Retrieve nearest template point index from LUT
            matched_idx = lut[gx][gy]
            tp = template_pts[matched_idx]

            total_dist += math.hypot(p.x - tp.x, p.y - tp.y)

        return total_dist / len(candidate_pts)


# ---------------------------------------------------------------------------
# Verification & Direction-Invariance / Level Demo
# ---------------------------------------------------------------------------

def _line(angle_deg: float, length: float = 100.0, n: int = 20, reverse: bool = False) -> List[Point]:
    """Generates line points. If reverse=True, draws from end-to-start."""
    angle = math.radians(angle_deg)
    dx, dy = math.cos(angle) * length, math.sin(angle) * length
    points = [Point(t / (n - 1) * dx, t / (n - 1) * dy) for t in range(n)]
    return points[::-1] if reverse else points


if __name__ == "__main__":
    rec = QRecognizer()

    # Register SHAPE-level (single primitive) templates in normal forward direction
    rec.add_template("line_horizontal", _line(0), level=Level.SHAPE)
    rec.add_template("line_vertical", _line(90), level=Level.SHAPE)

    # Register an OBJECT-level (composite) template: a "plus" made of two
    # strokes that cross each other -- registered as its own multi-stroke
    # figure rather than just a pair of independent lines.
    plus_horizontal = [Point(p.x - 50, p.y, stroke_id=0) for p in _line(0, length=100, n=20)]
    plus_vertical = [Point(p.x, p.y - 50, stroke_id=1) for p in _line(90, length=100, n=20)]
    rec.add_template("plus", plus_horizontal + plus_vertical, level=Level.OBJECT)

    print("\n=== Testing $Q$ Recognizer Direction Invariance ===")

    # 1. Test Forward Horizontal Line
    fwd_result = rec.recognize(_line(0, reverse=False))
    print(f"Forward Stroke (Left to Right)  -> Match: {fwd_result.name:<16} Score: {fwd_result.score:.4f}")

    # 2. Test Backward Horizontal Line
    rev_result = rec.recognize(_line(0, reverse=True))
    print(f"Reverse Stroke (Right to Left)  -> Match: {rev_result.name:<16} Score: {rev_result.score:.4f}")

    print("\n-> Both match seamlessly without needing duplicate template entries!")

    print("\n=== Testing Level-Based Scene Recognition (multiple features) ===")
    # Build one "canvas" containing two unrelated things drawn far apart:
    # a lone horizontal line near the origin, and a separate "+" far away.
    scene_points: List[Point] = [Point(p.x, p.y, stroke_id=0) for p in _line(0, length=100, n=20)]

    far_plus_h = [Point(p.x + 400, p.y + 400, stroke_id=1) for p in plus_horizontal]
    far_plus_v = [Point(p.x + 400, p.y + 400, stroke_id=2) for p in plus_vertical]
    scene_points += far_plus_h + far_plus_v

    features = rec.recognize_scene(scene_points)
    print(f"Detected {len(features)} separate feature(s) on the scene:")
    for f in features:
        print(f"  - feature {f.cluster_id}: {f.result.name:<16} level={f.level.name:<6} score={f.result.score:.4f}")