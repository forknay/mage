"""
Orientation-Sensitive $Q$ Super-Quick Recognizer
===============================================
An orientation-sensitive implementation of Vatavu, Anthony & Wobbrock's 
$Q$ Recognizer (2018) extended to support composable gesture hierarchies
and incremental canvas updating within a single unified class.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import spatial_index

from merge_intersecting_strokes import (
    Point,
    DEFAULT_TOUCH_THRESHOLD,
    DEFAULT_ENDPOINT_TOUCH_THRESHOLD,
    merge_intersecting_strokes,
    group_strokes_by_proximity,
    merge_and_count_touch_units,
    strokes_touch,
    bounding_box, 
    bounding_boxes_within_threshold
)
from config import (
    DEFAULT_MIN_SCORE,
    NUM_RESAMPLE_POINTS,
    FRAME_SIZE,
    LUT_SIZE,
    ASPECT_RATIO_WEIGHT,
    DEFAULT_LEVEL_MERGE_THRESHOLDS,
    CLOUD_DISTANCE_PENALTY_THRESHOLD,
    CLOUD_DISTANCE_EXPONENT,
    CLOUD_DISTANCE_MAX_WEIGHT,
)


# =============================================================================
# 1. Data Types
# =============================================================================

@dataclass
class Template:
    """Represents a registered gesture template."""
    name: str
    points: List[Point]       
    xs: np.ndarray            
    ys: np.ndarray            
    lut: np.ndarray           # 2D int array for fast O(1) candidate queries
    level: int                # Number of physically-separate stroke units
    aspect_ratio: float = 1.0 # Raw bounding box aspect ratio before uniform scaling
    min_score: float = DEFAULT_MIN_SCORE


@dataclass
class RecognitionResult:
    """The output of matching candidate points against templates."""
    name: Optional[str]
    score: float      
    distance: float   
    min_score: float = 0.0
    accepted: bool = False


@dataclass
class SceneSceneFeature:
    """A distinct, recognized SceneFeature (either atomic or composite) on the canvas."""
    cluster_id: int
    level: int
    result: RecognitionResult
    points: List[Point]
    components: List["SceneSceneFeature"] = field(default_factory=list)
    _bbox_cache: Optional[Tuple[float, float, float, float]] = field(
        default=None, repr=False, compare=False
    )

    def bounding_box(self) -> Tuple[float, float, float, float]:
        """
        Lazily computes and caches the (min_x, max_x, min_y, max_y) bounding box.
        Safe to cache because self.points are immutable after construction.
        """
        if self._bbox_cache is None:
            xs = [p.x for p in self.points]
            ys = [p.y for p in self.points]
            self._bbox_cache = (min(xs), max(xs), min(ys), max(ys))
        return self._bbox_cache


# =============================================================================
# 2. Unified QRecognizer
# =============================================================================

class QRecognizer:
    def __init__(self,
                 num_resample_points: int = NUM_RESAMPLE_POINTS,  
                 frame_size: float = FRAME_SIZE,
                 lut_size: int = LUT_SIZE,
                 touch_threshold: float = DEFAULT_TOUCH_THRESHOLD,
                 endpoint_touch_threshold: float = DEFAULT_ENDPOINT_TOUCH_THRESHOLD,
                 level_merge_thresholds: Optional[Dict[int, float]] = None,
                 aspect_ratio_weight: float = ASPECT_RATIO_WEIGHT): 
        self.n = num_resample_points
        self.frame_size = frame_size
        self.lut_size = lut_size
        self.templates: List[Template] = []
        self._max_distance = math.hypot(frame_size, frame_size)
        self.touch_threshold = touch_threshold
        self.endpoint_touch_threshold = endpoint_touch_threshold
        self.aspect_ratio_weight = aspect_ratio_weight
        self.level_merge_thresholds: Dict[int, float] = {
            **DEFAULT_LEVEL_MERGE_THRESHOLDS, **(level_merge_thresholds or {})
        }

        # ---------------------------------------------------------------------
        # Incremental State Initialization
        # ---------------------------------------------------------------------
        # Maximum gap across all composition levels
        self.max_gap = max(
            [self.touch_threshold, self.endpoint_touch_threshold] +
            list(self.level_merge_thresholds.values())
        )
        # Maximum gap for physical Level-1 touch
        self.atomic_gap = max(self.touch_threshold, self.endpoint_touch_threshold)

        self._groups: List[dict] = []
        self._touch_cache: Dict[Tuple[int, int], bool] = {}

    # -------------------------------------------------------------------------
    # Public APIs: Template Registration
    # -------------------------------------------------------------------------

    def add_template(self, name: str, points: List[Point], level: Optional[int] = None,
                      min_score: float = DEFAULT_MIN_SCORE) -> None:
        """Registers a new template, inferring stroke units (level) if not provided."""
        merged_points, actual_units = merge_and_count_touch_units(
            points, self.touch_threshold, self.endpoint_touch_threshold
        )
        
        if level is None:
            level = actual_units
        elif level != actual_units:
            raise ValueError(
                f"Template '{name}' resolves to {actual_units} stroke unit(s) but was registered "
                f"with level={level}."
            )

        aspect_ratio = self._compute_aspect_ratio(points)
        processed = self._preprocess(merged_points, level=level, already_merged=True)
        xs, ys = self._xy(processed)
        lut = self._create_lut(xs, ys)
        
        self.templates.append(Template(
            name=name, points=processed, xs=xs, ys=ys, lut=lut, level=level,
            aspect_ratio=aspect_ratio, min_score=min_score,
        ))

    def add_precomputed_template(self, name: str, processed_points: List[Point],
                                  lut, level: int, aspect_ratio: float,
                                  min_score: float = DEFAULT_MIN_SCORE) -> None:
        """Fast-path registration from cache, skipping preprocessing and LUT construction."""
        lut_arr = lut if isinstance(lut, np.ndarray) else np.array(lut, dtype=np.int64)
        xs, ys = self._xy(processed_points)
        
        self.templates.append(Template(
            name=name, points=processed_points, xs=xs, ys=ys, lut=lut_arr, level=level,
            aspect_ratio=aspect_ratio, min_score=min_score,
        ))

    # -------------------------------------------------------------------------
    # Public APIs: Batch & Single-Gesture Recognition
    # -------------------------------------------------------------------------

    def recognize(self, points: List[Point],
                  level: int = 1,
                  candidate_names: Optional[List[str]] = None) -> RecognitionResult:
        """Classifies a point cloud against registered templates at a specific level."""
        if not self.templates:
            raise ValueError("No templates registered.")

        candidates = self._candidates_at_level(level, candidate_names)
        merged_points, actual_units = merge_and_count_touch_units(
            points, self.touch_threshold, self.endpoint_touch_threshold
        )
        
        if actual_units != level:
            raise ValueError(f"Cannot classify at level={level}: input has {actual_units} units.")

        cand_aspect_ratio = self._compute_aspect_ratio(points)
        processed = self._preprocess(merged_points, level=level, already_merged=True)
        
        best_template, best_distance, best_score = self._best_matching_template(
            processed, cand_aspect_ratio, candidates
        )

        return RecognitionResult(
            name=best_template.name,
            score=best_score,
            distance=best_distance,
            min_score=best_template.min_score,
            accepted=best_score >= best_template.min_score,
        )

    def recognize_scene(self, points: List[Point],
                         level_merge_thresholds: Optional[Dict[int, float]] = None,
                         min_score: float = 0.0) -> List[SceneSceneFeature]:
        """
        Parses the entire canvas bottom-up in a single batch pass.
        1. Split into atomic (Level-1) SceneFeatures.
        2. Progressively bundle nearby SceneFeatures into composite (Level 2+) SceneFeatures.
        """
        if not points or not self.templates:
            return []

        current_SceneFeatures = self._recognize_atomic_clusters(points)
        return self._compose_from_atomic(current_SceneFeatures, level_merge_thresholds, min_score)

    # -------------------------------------------------------------------------
    # Public APIs: Incremental Canvas Recognition
    # -------------------------------------------------------------------------

    @property
    def incremental_SceneFeatures(self) -> List[SceneSceneFeature]:
        """Flattened accepted SceneFeatures across all tracked incremental canvas regions."""
        return [f for g in self._groups for f in g["SceneFeatures"]]

    def add_stroke(self, stroke_points: List[Point]) -> List[SceneSceneFeature]:
        """
        Incorporates a new stroke dynamically, isolating atomic recomputations
        to affected spatial groups while reusing untouched regional caches.

        Granularity note: both the "which groups might be affected at all"
        test and the "which atomic SceneFeatures actually need re-clustering"
        test are done PER ATOMIC SceneFeature (via SceneSceneFeature.bounding_box(),
        which is cached -- see SceneSceneFeature), not against a group's
        aggregate bounding box. A group's aggregate box is the union of
        every atomic SceneFeature's box inside it, so a new stroke landing in
        the "empty middle" of a spatially-spread-out group (e.g. two
        SceneFeatures sitting in opposite corners of a large group, with the
        new stroke somewhere between them but not actually near either)
        would spuriously satisfy an aggregate-box overlap test even though
        no individual SceneFeature in that group is anywhere near it -- forcing
        a full atomic recompute (and re-running composition) over SceneFeatures
        that couldn't possibly be touched. Testing each atomic SceneFeature's
        own box individually only ever narrows this down, never misses a
        real touch: if a SceneFeature truly is within `max_gap`/`atomic_gap` of
        the new stroke, that SceneFeature's own box will satisfy the check
        regardless of what else is (or isn't) in its group.
        """
        if not stroke_points:
            return self.incremental_SceneFeatures

        new_box = bounding_box(stroke_points)

        touched_indices = []
        for i, group in enumerate(self._groups):
            group_touched = any(
                bounding_boxes_within_threshold(new_box, feat.bounding_box(), self.max_gap)
                for feat in group["atomic_SceneFeatures"]
            )
            if group_touched:
                touched_indices.append(i)

        remaining_groups = [g for i, g in enumerate(self._groups) if i not in touched_indices]

        # Per-atomic-SceneFeature split within every touched group: only SceneFeatures
        # individually within `atomic_gap` of the new stroke get folded into
        # the physical (Level-1) recompute; everything else in the same
        # touched group is reused as-is and simply handed back into
        # composition alongside whatever comes out of the recompute.
        atomic_recompute_points = list(stroke_points)
        reused_atomic_SceneFeatures: List[SceneSceneFeature] = []
        for i in touched_indices:
            for feat in self._groups[i]["atomic_SceneFeatures"]:
                if bounding_boxes_within_threshold(new_box, feat.bounding_box(), self.atomic_gap):
                    atomic_recompute_points.extend(feat.points)
                else:
                    reused_atomic_SceneFeatures.append(feat)

        # Preserve chronological stroke ordering
        atomic_recompute_points.sort(key=lambda p: p.stroke_id)

        new_atomic_SceneFeatures = self._recognize_atomic_clusters(atomic_recompute_points)

        combined_atomic_SceneFeatures = new_atomic_SceneFeatures + reused_atomic_SceneFeatures
        combined_atomic_SceneFeatures.sort(key=lambda f: min(p.stroke_id for p in f.points))

        new_SceneFeatures = self._compose_from_atomic(
            combined_atomic_SceneFeatures, touch_cache=self._touch_cache,
        )

        remaining_groups.append({
            "atomic_SceneFeatures": combined_atomic_SceneFeatures,
            "SceneFeatures": new_SceneFeatures,
        })

        self._groups = remaining_groups
        return self.incremental_SceneFeatures

    def clear(self) -> None:
        """Resets the incremental regional tracking state and touch cache."""
        self._groups = []
        self._touch_cache = {}

    # -------------------------------------------------------------------------
    # Core Pipeline: Recognition & Composition Helpers
    # -------------------------------------------------------------------------

    def _recognize_atomic_clusters(self, points: List[Point]) -> List[SceneSceneFeature]:
        """Clusters raw points by physical touch and attempts Level-1 recognition."""
        atomic_clusters = group_strokes_by_proximity(
            points, self.touch_threshold, endpoint_threshold=self.endpoint_touch_threshold
        )

        SceneFeatures: List[SceneSceneFeature] = []
        for cluster_id, cluster_points in enumerate(atomic_clusters):
            result = self._try_recognize(cluster_points, level=1)
            SceneFeatures.append(SceneSceneFeature(
                cluster_id=cluster_id,
                level=1,
                result=result if result is not None else RecognitionResult(None, 0.0, math.inf),
                points=cluster_points,
            ))
        return SceneFeatures

    def _compose_from_atomic(self, atomic_SceneFeatures: List[SceneSceneFeature],
                              level_merge_thresholds: Optional[Dict[int, float]] = None,
                              min_score: float = 0.0,
                              touch_cache: Optional[Dict[Tuple[int, int], bool]] = None
                              ) -> List[SceneSceneFeature]:
        """Handles Level 2+ composition ladder iteratively bundling lower levels."""
        if not atomic_SceneFeatures or not self.templates:
            return []

        thresholds = {**self.level_merge_thresholds, **(level_merge_thresholds or {})}
        levels_present = sorted({t.level for t in self.templates})

        current_SceneFeatures = atomic_SceneFeatures
        for target_level in [lvl for lvl in levels_present if lvl != 1]:
            gap = thresholds.get(target_level, self.touch_threshold)
            current_SceneFeatures = self._compose_level(current_SceneFeatures, target_level, gap, touch_cache)

        return [
            f for f in current_SceneFeatures
            if f.result.accepted and f.result.score >= min_score
        ]

    def _compose_level(self, current_SceneFeatures: List[SceneSceneFeature], target_level: int,
                        gap: float, touch_cache: Optional[Dict[Tuple[int, int], bool]] = None
                        ) -> List[SceneSceneFeature]:
        """Groups SceneFeatures within a threshold and attempts recognition at `target_level`."""
        groups = self._bundle_SceneFeatures_by_proximity(current_SceneFeatures, gap, touch_cache)
        next_SceneFeatures: List[SceneSceneFeature] = []
        
        for group in groups:
            total_units = sum(feat.level for feat in group)

            if len(group) > 1 and total_units == target_level:
                combined_points = [p for feat in group for p in feat.points]
                result = self._try_recognize(combined_points, level=target_level)

                if result is not None and result.accepted:
                    next_SceneFeatures.append(SceneSceneFeature(
                        cluster_id=group[0].cluster_id,
                        level=target_level,
                        result=result,
                        points=combined_points,
                        components=list(group),
                    ))
                    continue

            next_SceneFeatures.extend(group)

        return next_SceneFeatures

    def _bundle_SceneFeatures_by_proximity(self, SceneFeatures: List[SceneSceneFeature],
                                       threshold: float,
                                       touch_cache: Optional[Dict[Tuple[int, int], bool]] = None
                                       ) -> List[List[SceneSceneFeature]]:
        """Groups scene SceneFeatures if any of their points fall within the spatial threshold."""
        if not SceneFeatures:
            return []
        if len(SceneFeatures) == 1:
            return [SceneFeatures]

        def is_touching(i: int, j: int) -> bool:
            feat_a, feat_b = SceneFeatures[i], SceneFeatures[j]
            key = (id(feat_a), id(feat_b)) if id(feat_a) < id(feat_b) else (id(feat_b), id(feat_a))
            if touch_cache is not None:
                if key in touch_cache:
                    return touch_cache[key]
            result = strokes_touch(feat_a.points, feat_b.points, threshold, DEFAULT_ENDPOINT_TOUCH_THRESHOLD)
            if touch_cache is not None:
                touch_cache[key] = result
            return result

        try:
            cluster_func = spatial_index.cluster_spatially
        except AttributeError:
            cluster_func = spatial_index.SpatialGrid.cluster_spatially

        search_radius = max(threshold, DEFAULT_ENDPOINT_TOUCH_THRESHOLD)
        index_clusters = cluster_func(
            items=list(range(len(SceneFeatures))),
            get_bbox_fn=lambda i: SceneFeatures[i].bounding_box(),
            is_touching_fn=is_touching,
            threshold=search_radius,
        )
        return [[SceneFeatures[i] for i in sorted(idxs)] for idxs in index_clusters]
        
    def _candidates_at_level(self, level: int, candidate_names: Optional[List[str]]) -> List[Template]:
        """Filters templates down to a given level and optional allow-list."""
        candidates = [t for t in self.templates if t.level == level]
        if candidate_names is not None:
            candidates = [t for t in candidates if t.name in candidate_names]
        if not candidates:
            raise ValueError(f"No templates registered at level={level} matching candidate names.")
        return candidates
        
    def _try_recognize(self, points: List[Point], level: int) -> Optional[RecognitionResult]:
        """Gracefully catches errors and returns None on invalid configurations."""
        try:
            return self.recognize(points, level=level)
        except ValueError:
            return None

    def _best_matching_template(self, processed: List[Point], cand_aspect_ratio: float,
                                 candidates: List[Template]) -> Tuple[Template, float, float]:
        """Calculates raw scores against candidate templates with exact early-exit optimization."""
        ar_penalties: List[Tuple[float, Template]] = []
        for template in candidates:
            ar_diff = abs(cand_aspect_ratio - template.aspect_ratio)
            ar_penalty = math.exp(-self.aspect_ratio_weight * (ar_diff ** 2))
            ar_penalties.append((ar_penalty, template))

        ar_penalties.sort(key=lambda pair: pair[0], reverse=True)

        best_template: Optional[Template] = None
        best_distance = math.inf
        best_score = -1.0

        cand_xs, cand_ys = self._xy(processed)
        candidate_lut = self._create_lut(cand_xs, cand_ys)

        for ar_penalty, template in ar_penalties:
            if ar_penalty <= best_score:
                break

            distance = self._bidirectional_cloud_distance_Hausdorff(
                cand_xs, cand_ys, template.xs, template.ys, template.lut, candidate_lut
            )

            raw_score = max(0.0, 1.0 - distance / self._max_distance)
            final_score = raw_score * ar_penalty

            if final_score > best_score:
                best_score = final_score
                best_distance = distance
                best_template = template

        return best_template, best_distance, best_score

    # -------------------------------------------------------------------------
    # Distance Calculations (Numpy Vectorized)
    # -------------------------------------------------------------------------

    def _bidirectional_cloud_distance_Hausdorff(self,
                                   cand_xs: np.ndarray, cand_ys: np.ndarray,
                                   temp_xs: np.ndarray, temp_ys: np.ndarray,
                                   lut: np.ndarray,
                                   candidate_lut: np.ndarray) -> float:
        """Combines forward and reverse distances to penalize missing structures bidirectionally."""
        d_cand_to_temp = self._cloud_distance(cand_xs, cand_ys, temp_xs, temp_ys, lut)
        d_temp_to_cand = self._reverse_cloud_distance(temp_xs, temp_ys, cand_xs, cand_ys, candidate_lut)
        return max(d_cand_to_temp, d_temp_to_cand)

    def _cloud_distance(self, cand_xs: np.ndarray, cand_ys: np.ndarray,
                       temp_xs: np.ndarray, temp_ys: np.ndarray,
                       lut: np.ndarray,
                       penalty_threshold: float = CLOUD_DISTANCE_PENALTY_THRESHOLD,
                       exponent: float = CLOUD_DISTANCE_EXPONENT,
                       max_dist_weight: float = CLOUD_DISTANCE_MAX_WEIGHT) -> float:
        """Fast Candidate -> Template point cloud distance via precalculated LUT."""
        matched_idx = self._grid_lookup(cand_xs, cand_ys, lut)
        tx = temp_xs[matched_idx]
        ty = temp_ys[matched_idx]
        dists = np.hypot(cand_xs - tx, cand_ys - ty)
        return self._blend_avg_max(dists, penalty_threshold, exponent, max_dist_weight)

    def _reverse_cloud_distance(self,
                            temp_xs: np.ndarray, temp_ys: np.ndarray,
                            cand_xs: np.ndarray, cand_ys: np.ndarray,
                            candidate_lut: np.ndarray,
                            penalty_threshold: float = CLOUD_DISTANCE_PENALTY_THRESHOLD,
                            exponent: float = CLOUD_DISTANCE_EXPONENT,
                            max_dist_weight: float = CLOUD_DISTANCE_MAX_WEIGHT) -> float:
        """Computes Template -> Candidate distance using hybrid Hausdorff blending."""
        matched_idx = self._grid_lookup(temp_xs, temp_ys, candidate_lut)
        cx = cand_xs[matched_idx]
        cy = cand_ys[matched_idx]
        dists = np.hypot(temp_xs - cx, temp_ys - cy)
        return self._blend_avg_max(dists, penalty_threshold, exponent, max_dist_weight)

    @staticmethod
    def _blend_avg_max(dists: np.ndarray, penalty_threshold: float, exponent: float,
                        max_dist_weight: float) -> float:
        """Applies exponential penalties to distances above threshold and blends average with maximum error."""
        over = dists > penalty_threshold
        excess = np.where(over, dists - penalty_threshold, 0.0)
        adjusted = np.where(over, dists + excess ** exponent, dists)

        avg_dist = float(adjusted.mean())
        max_dist = float(adjusted.max())
        return ((1.0 - max_dist_weight) * avg_dist) + (max_dist_weight * max_dist)

    # -------------------------------------------------------------------------
    # Look-Up Table (LUT) Engine
    # -------------------------------------------------------------------------
    
    @staticmethod
    def _xy(points: List[Point]) -> Tuple[np.ndarray, np.ndarray]:
        """Extracts X and Y coordinates into vectorized NumPy float arrays."""
        n = len(points)
        xs = np.empty(n, dtype=np.float64)
        ys = np.empty(n, dtype=np.float64)
        for i, p in enumerate(points):
            xs[i] = p.x
            ys[i] = p.y
        return xs, ys

    def _create_lut(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        """Generates a 2D discrete Voronoi diagram (LUT) storing the index of the nearest point."""
        from collections import deque

        lut_size = self.lut_size
        lut = [[-1 for _ in range(lut_size)] for _ in range(lut_size)]
        scale = lut_size / self.frame_size

        gx_all = np.clip(((xs + self.frame_size / 2.0) * scale).astype(np.int64), 0, lut_size - 1)
        gy_all = np.clip(((ys + self.frame_size / 2.0) * scale).astype(np.int64), 0, lut_size - 1)

        frontier = deque()
        for idx in range(len(xs)):
            gx = int(gx_all[idx])
            gy = int(gy_all[idx])
            if lut[gx][gy] == -1:
                lut[gx][gy] = idx
                frontier.append((gx, gy))

        while frontier:
            x, y = frontier.popleft()
            owner = lut[x][y]
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < lut_size and 0 <= ny < lut_size and lut[nx][ny] == -1:
                    lut[nx][ny] = owner
                    frontier.append((nx, ny))

        return np.array(lut, dtype=np.int64)
        
    def _grid_lookup(self, xs: np.ndarray, ys: np.ndarray, lut: np.ndarray) -> np.ndarray:
        """Vectorized LUT lookup using NumPy fancy indexing."""
        scale = self.lut_size / self.frame_size
        gx = np.clip(((xs + self.frame_size / 2.0) * scale).astype(np.int64), 0, self.lut_size - 1)
        gy = np.clip(((ys + self.frame_size / 2.0) * scale).astype(np.int64), 0, self.lut_size - 1)
        return lut[gx, gy]

    # -------------------------------------------------------------------------
    # Preprocessing Pipeline (Math & Resampling)
    # -------------------------------------------------------------------------

    def _preprocess(self, points: List[Point], level: int = 1, already_merged: bool = False) -> List[Point]:
        """Geometric normalization pipeline: dedupe, resample, scale, and translate."""
        pts = points if already_merged else merge_intersecting_strokes(
            points, proximity_threshold=self.touch_threshold, endpoint_threshold=self.endpoint_touch_threshold
        )
        pts = self._dedupe(pts)
        pts = self._resample(pts, self.n)
        pts = self._scale_uniform(pts, self.frame_size)
        pts = self._translate_to_origin(pts)
        return pts

    @staticmethod
    def _compute_aspect_ratio(points: List[Point]) -> float:
        """Calculates bounding box diagonal angle to prevent aspect ratio volatility."""
        if not points:
            return math.pi / 4.0  
        min_x = min(p.x for p in points)
        max_x = max(p.x for p in points)
        min_y = min(p.y for p in points)
        max_y = max(p.y for p in points)
        w = max_x - min_x
        h = max_y - min_y
        
        return math.atan2(h, w)

    @staticmethod
    def _dedupe(points: List[Point]) -> List[Point]:
        """Removes consecutive duplicate points."""
        if not points:
            return []
        out = [points[0]]
        for p in points[1:]:
            if math.hypot(p.x - out[-1].x, p.y - out[-1].y) > 1e-9:
                out.append(p)
        return out

    @staticmethod
    def _path_length(points: List[Point]) -> float:
        """Computes total path length ignoring gaps between distinct strokes."""
        d = 0.0
        for i in range(1, len(points)):
            if points[i].stroke_id == points[i - 1].stroke_id:
                d += math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y)
        return d

    def _resample(self, points: List[Point], n: int) -> List[Point]:
        """Resamples points evenly across geometric stroke paths."""
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
        """Extracts simple (min_x, min_y, width, height) bounding dimensions."""
        min_x = min(p.x for p in points)
        max_x = max(p.x for p in points)
        min_y = min(p.y for p in points)
        max_y = max(p.y for p in points)
        return min_x, min_y, max_x - min_x, max_y - min_y

    def _scale_uniform(self, points: List[Point], size: float) -> List[Point]:
        """Scales points uniformly based on largest bounding dimension."""
        min_x, min_y, w, h = self._bounding_box(points)
        scale = size / max(w, h, 1e-9)
        return [Point((p.x - min_x) * scale, (p.y - min_y) * scale, p.stroke_id) for p in points]

    @staticmethod
    def _centroid(points: List[Point]) -> Point:
        """Finds geometric centroid of point cloud."""
        x = sum(p.x for p in points) / len(points)
        y = sum(p.y for p in points) / len(points)
        return Point(x, y)

    def _translate_to_origin(self, points: List[Point]) -> List[Point]:
        """Translates point cloud centroid to the origin."""
        c = self._centroid(points)
        return [Point(p.x - c.x, p.y - c.y, p.stroke_id) for p in points]