import math
from enum import IntEnum
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class Point:
    x: float
    y: float
    stroke_id: int = 0


class Level(IntEnum):
    """
    Complexity tiers used to bundle raw pen-strokes into progressively richer
    objects.

    SHAPE  - a single recognizable primitive (a line, a circle, a triangle...).
             Strokes are only bundled at this level when they actually touch
             or cross one another (a tight proximity threshold), since that's
             what turns two separate pen-strokes into one continuous outline.

    OBJECT - a composite, multi-part figure built out of several SHAPE-level
             pieces that belong together but don't necessarily touch (e.g.
             the stem + dot of an "!", or the four sides of a square drawn as
             disconnected strokes). Strokes are bundled at this level using a
             much looser proximity threshold.

    New tiers can be added the same way: extend this enum and add a matching
    entry to DEFAULT_LEVEL_THRESHOLDS (a bigger number = a looser bundle).
    """
    SHAPE = 1
    OBJECT = 2


# Default proximity threshold (in px) used to decide whether two strokes
# belong to the same bundle at a given complexity level. Higher levels use
# looser thresholds because their parts are allowed to be spatially separated.
DEFAULT_LEVEL_THRESHOLDS: Dict[Level, float] = {
    Level.SHAPE: 8.0,
    Level.OBJECT: 60.0,
}


def _cluster_stroke_ids(points: List[Point], proximity_threshold: float) -> Dict[int, int]:
    """
    Core union-find proximity clustering, shared by every level of bundling.
    Returns {original_stroke_id: cluster_root_stroke_id}.
    """
    if not points:
        return {}

    # 1. Group raw points by their original stroke_id
    strokes_map: Dict[int, List[Point]] = {}
    for p in points:
        strokes_map.setdefault(p.stroke_id, []).append(p)

    stroke_ids = list(strokes_map.keys())
    num_strokes = len(stroke_ids)

    # 2. Union-Find structure to group intersecting/nearby strokes
    parent = {s_id: s_id for s_id in stroke_ids}

    def find(i):
        if parent[i] == i:
            return i
        parent[i] = find(parent[i])
        return parent[i]

    def union(i, j):
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    # 3. Check for intersections / close proximity between all pairs of strokes
    if num_strokes > 1:
        for i in range(num_strokes):
            id_a = stroke_ids[i]
            pts_a = strokes_map[id_a]

            min_x_a, max_x_a = min(p.x for p in pts_a), max(p.x for p in pts_a)
            min_y_a, max_y_a = min(p.y for p in pts_a), max(p.y for p in pts_a)

            for j in range(i + 1, num_strokes):
                id_b = stroke_ids[j]
                pts_b = strokes_map[id_b]

                min_x_b, max_x_b = min(p.x for p in pts_b), max(p.x for p in pts_b)
                min_y_b, max_y_b = min(p.y for p in pts_b), max(p.y for p in pts_b)

                # Fast bounding box check first (optimization)
                if (max_x_a < min_x_b - proximity_threshold or min_x_a > max_x_b + proximity_threshold or
                        max_y_a < min_y_b - proximity_threshold or min_y_a > max_y_b + proximity_threshold):
                    continue

                # Detailed point-to-point distance check for intersection
                intersects = False
                for pa in pts_a:
                    for pb in pts_b:
                        if math.hypot(pa.x - pb.x, pa.y - pb.y) <= proximity_threshold:
                            intersects = True
                            break
                    if intersects:
                        break

                if intersects:
                    union(id_a, id_b)

    return {s_id: find(s_id) for s_id in stroke_ids}


def group_strokes_by_proximity(points: List[Point], proximity_threshold: float = 8.0) -> List[List[Point]]:
    """
    Groups strokes into spatial clusters WITHOUT renumbering/flattening them.

    Returns a list of clusters; each cluster is the list of original Points
    (original stroke_id preserved) belonging to strokes that are within
    `proximity_threshold` of one another, directly or transitively. Cluster
    order follows the first-appearance order of each cluster in `points`.

    This is the building block used to split a whole canvas into separate
    "features" -- e.g. two unrelated doodles drawn far apart come back as two
    separate clusters instead of being forced into a single point cloud.
    """
    if not points:
        return []

    root_of = _cluster_stroke_ids(points, proximity_threshold)

    clusters: Dict[int, List[Point]] = {}
    order: List[int] = []
    for p in points:
        root = root_of[p.stroke_id]
        if root not in clusters:
            clusters[root] = []
            order.append(root)
        clusters[root].append(p)

    return [clusters[root] for root in order]


def bundle_by_level(points: List[Point], level: Level, threshold: Optional[float] = None) -> List[List[Point]]:
    """
    Buckets raw canvas points into clusters appropriate for the given
    complexity `level`. This is the "level type" bundling logic: the same
    proximity-clustering machinery is reused for every tier, but each level
    applies a different (configurable) threshold so strokes combine into
    progressively higher-level objects -- SHAPE: touching strokes become one
    glyph; OBJECT: nearby glyphs become one composite figure.
    """
    thr = threshold if threshold is not None else DEFAULT_LEVEL_THRESHOLDS.get(level, 8.0)
    return group_strokes_by_proximity(points, thr)


def merge_intersecting_strokes(points: List[Point], proximity_threshold: float = 8.0) -> List[Point]:
    """
    Groups strokes together if any point in stroke A is within `proximity_threshold`
    pixels of any point in stroke B (handles intersections and near-intersections).

    Returns a flat list of points (original order preserved) with stroke_id
    reassigned to a clean, sequential id per merged cluster, so downstream
    per-stroke logic (path length / resampling) treats each merged cluster as
    one continuous stroke.
    """
    if not points:
        return []

    distinct_ids = {p.stroke_id for p in points}
    if len(distinct_ids) <= 1:
        return points  # Nothing to merge

    root_of = _cluster_stroke_ids(points, proximity_threshold)

    # Map root cluster IDs to clean sequential IDs (0, 1, 2...)
    root_to_new_id: Dict[int, int] = {}
    merged_points: List[Point] = []

    for p in points:
        root_id = root_of[p.stroke_id]
        if root_id not in root_to_new_id:
            root_to_new_id[root_id] = len(root_to_new_id)

        new_stroke_id = root_to_new_id[root_id]
        merged_points.append(Point(p.x, p.y, stroke_id=new_stroke_id))

    return merged_points