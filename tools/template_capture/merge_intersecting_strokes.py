"""
Stroke Proximity/Touch Clustering
==================================
Everything in this module answers ONE question: "which of these Strokes
physically touch or cross one another?" It knows nothing about gesture
recognition, templates, or "Level" -- it's a pure geometry primitive that
the rest of the pipeline (recognizer.py, template_capture.py) builds
meaning on top of.

Works in terms of gesture_types.Stroke throughout: a Stroke is just "the
points that make up one physically continuous pen-stroke" (points carry no
identity of their own -- see gesture_types.py). Touch-clustering groups
whole Stroke objects; the low-level segment/distance geometry underneath
still just deals in raw (x, y) Points, since a crossing test doesn't care
which stroke a point came from.

Layout of this file:
  1. Segment / distance geometry -- low-level helpers (point-to-segment,
                                     segment-to-segment, "do these two
                                     segments cross?"), operating on plain
                                     Points regardless of which Stroke(s)
                                     they came from.
  2. Stroke clustering            -- groups whole Strokes together based
                                     on the geometry helpers above.
  3. Public API                   -- group_strokes_by_proximity,
                                     count_touch_units,
                                     merge_intersecting_strokes,
                                     merge_and_count_touch_units
"""

import math
from typing import Dict, List, Optional, Tuple
from gesture_types import Point, Stroke
from config import (
    DEFAULT_TOUCH_THRESHOLD,
    DEFAULT_ENDPOINT_TOUCH_THRESHOLD,
    DEFAULT_TOUCH_DECIMATION_MIN_POINTS,
    DEFAULT_TOUCH_DECIMATION_SPACING_DIVISOR,
    DEFAULT_TOUCH_GRID_MIN_SEGMENT_PRODUCT,
)
import spatial_index

# =============================================================================
# 1. Low-level segment/distance geometry
# =============================================================================

def _point_to_segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    """Shortest distance from point (px, py) to the segment [A, B]."""
    dx, dy = bx - ax, by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq <= 1e-12:
        return math.hypot(px - ax, py - ay)

    t = ((px - ax) * dx + (py - ay) * dy) / seg_len_sq
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def _orientation(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
    """Cross product sign to determine the turn from AB to AC (>0 CCW, <0 CW, 0 collinear)."""
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def _segments_intersect(a1: Point, a2: Point, b1: Point, b2: Point) -> bool:
    """
    True proper/boundary intersection test between segments A1-A2 and B1-B2.
    This is what actually detects a visual "crossing" between two strokes.
    """
    d1 = _orientation(b1.x, b1.y, b2.x, b2.y, a1.x, a1.y)
    d2 = _orientation(b1.x, b1.y, b2.x, b2.y, a2.x, a2.y)
    d3 = _orientation(a1.x, a1.y, a2.x, a2.y, b1.x, b1.y)
    d4 = _orientation(a1.x, a1.y, a2.x, a2.y, b2.x, b2.y)

    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True

    # Collinear / touching-endpoint edge cases: fall back to bounding-box
    # containment checks for each "on the line" case.
    def on_segment(px, py, qx, qy, rx, ry) -> bool:
        return (min(px, rx) - 1e-9 <= qx <= max(px, rx) + 1e-9 and
                min(py, ry) - 1e-9 <= qy <= max(py, ry) + 1e-9)

    if d1 == 0 and on_segment(b1.x, b1.y, a1.x, a1.y, b2.x, b2.y):
        return True
    if d2 == 0 and on_segment(b1.x, b1.y, a2.x, a2.y, b2.x, b2.y):
        return True
    if d3 == 0 and on_segment(a1.x, a1.y, b1.x, b1.y, a2.x, a2.y):
        return True
    if d4 == 0 and on_segment(a1.x, a1.y, b2.x, b2.y, a2.x, a2.y):
        return True

    return False


def _segment_segment_distance(a1: Point, a2: Point, b1: Point, b2: Point) -> float:
    """
    Shortest distance between two segments. Returns 0.0 for any true
    crossing/overlap (checked first via `_segments_intersect`), otherwise the
    minimum of the four endpoint-to-opposite-segment distances -- which is
    exact for two straight segments.
    """
    if _segments_intersect(a1, a2, b1, b2):
        return 0.0

    return min(
        _point_to_segment_distance(a1.x, a1.y, b1.x, b1.y, b2.x, b2.y),
        _point_to_segment_distance(a2.x, a2.y, b1.x, b1.y, b2.x, b2.y),
        _point_to_segment_distance(b1.x, b1.y, a1.x, a1.y, a2.x, a2.y),
        _point_to_segment_distance(b2.x, b2.y, a1.x, a1.y, a2.x, a2.y),
    )


# =============================================================================
# 2. Stroke clustering
# =============================================================================

def _segment_bbox(a: Point, b: Point) -> tuple:
    """
    Returns (min_x, max_x, min_y, max_y) for a single two-point segment.
    Deliberately not routed through `bounding_box` (which takes a list and
    calls `min`/`max` with generator expressions) -- this is called once
    per segment inside `_strokes_touch`'s O(n*m) pair loop, so a direct
    2-value comparison avoids the extra function-call/iterator overhead
    that doesn't matter for whole-stroke boxes but does add up here.
    """
    return (
        a.x if a.x <= b.x else b.x, a.x if a.x >= b.x else b.x,
        a.y if a.y <= b.y else b.y, a.y if a.y >= b.y else b.y,
    )


def _bounding_boxes_within_threshold(box_a: tuple, box_b: tuple, threshold: float) -> bool:
    """
    Cheap pre-filter: true unless the two bounding boxes are farther apart
    than `threshold` on some axis, in which case the strokes definitely
    can't be touching and the (expensive) segment-pair check can be skipped.
    """
    min_x_a, max_x_a, min_y_a, max_y_a = box_a
    min_x_b, max_x_b, min_y_b, max_y_b = box_b
    if max_x_a < min_x_b - threshold or min_x_a > max_x_b + threshold:
        return False
    if max_y_a < min_y_b - threshold or min_y_a > max_y_b + threshold:
        return False
    return True


def _endpoints_touch(pts_a: List[Point], pts_b: List[Point], endpoint_threshold: float) -> bool:
    """
    Cheap, generous check: does EITHER endpoint (first or last recorded
    point -- i.e. pen-down or pen-up) of point-run A land within
    `endpoint_threshold` of EITHER endpoint of point-run B? This is
    intentionally looser than the general crossing test in `_strokes_touch`
    (see DEFAULT_ENDPOINT_TOUCH_THRESHOLD in config.py for why) and is
    checked first since it's exactly the case real hand-drawn "meant to
    meet at a corner/tip" strokes fail on with a tight threshold alone.

    Deliberately tip-to-tip only, NOT tip-to-anywhere-on-the-other-stroke:
    testing a tip against the other stroke's full body would also catch
    genuine T-junctions (a stroke ending partway along another), but it
    just as readily mis-merges two independent, roughly-parallel strokes
    whose start (or end) points simply happen to land near the other
    stroke's body -- e.g. the two separate bars of a hand-drawn "II"
    starting at the same height. Restricting the loose tolerance to
    endpoint-vs-endpoint keeps that ambiguous "runs near" case governed by
    the tighter general `threshold` in `_strokes_touch`, while still fixing
    the tip-meets-tip gap this was written for.
    """
    endpoints_a = (pts_a[0], pts_a[-1])
    endpoints_b = (pts_b[0], pts_b[-1])
    for pa in endpoints_a:
        for pb in endpoints_b:
            if math.hypot(pa.x - pb.x, pa.y - pb.y) <= endpoint_threshold:
                return True
    return False


def _decimate_points_for_touch(points: List[Point], min_spacing: float,
                                min_points: int = DEFAULT_TOUCH_DECIMATION_MIN_POINTS) -> List[Point]:
    """
    Thins `points` for TOUCH-TESTING ONLY -- never used for recognition or
    scoring, which always resamples to a fixed count regardless (see
    QRecognizer._preprocess) and so never even sees this function's output.
    A dense hand-drawn stroke can carry hundreds of raw mouse-move points
    just a pixel or two apart; none of that density adds real information
    to a proximity test running at `min_spacing`-scale thresholds, but it
    directly multiplies the O(len(A) * len(B)) cost of `_strokes_touch`'s
    segment-pair loop -- this is the fix for that.

    Keeps the stroke's first and last point UNCONDITIONALLY, so
    `_endpoints_touch` (which only ever looks at those two) behaves
    identically whether it's handed the decimated or the original points.
    Otherwise, keeps a point only once it's at least `min_spacing` away
    from the last KEPT point (not merely the last point seen) -- that's
    what collapses an arbitrarily long run of near-duplicate points down to
    a single kept point, regardless of how many of them there were.

    Deliberately a no-op below `min_points` (or a non-positive spacing):
    short strokes get negligible speedup from thinning and there's no
    reason to risk changing their behavior at all, so this only ever
    touches strokes dense enough for it to matter. This also means every
    template captured via template_capture.py -- which are typically well
    under `min_points` -- is completely unaffected.

    Tradeoff: replacing a run of points with a single straight segment
    between the kept endpoints can shift the tested geometry by up to
    roughly `min_spacing` for a pathologically jagged run (e.g. a fast
    zigzag). `min_spacing` is derived from the same `proximity_threshold`
    the touch test itself uses (see DEFAULT_TOUCH_DECIMATION_SPACING_DIVISOR
    in config.py), so in the ordinary case of a smoothly hand-drawn curve
    -- where consecutive points are far straighter than that -- the
    deviation is negligible and touch/no-touch outcomes are unchanged.
    """
    if len(points) <= min_points or min_spacing <= 0:
        return points

    kept = [points[0]]
    for p in points[1:-1]:
        if math.hypot(p.x - kept[-1].x, p.y - kept[-1].y) >= min_spacing:
            kept.append(p)
    if points[-1] is not kept[-1]:
        kept.append(points[-1])
    return kept


def _strokes_touch_grid(segs_a: List[Tuple[Point, Point]], boxes_a: List[tuple],
                         segs_b: List[Tuple[Point, Point]], boxes_b: List[tuple],
                         threshold: float) -> bool:
    """
    Grid-indexed version of the segment-pair touch test -- the structural
    fix for what the per-segment AABB prefilter in `_strokes_touch` can't
    solve on its own: that prefilter makes each of the O(len(A) * len(B))
    pair checks cheap, but doesn't reduce how many pairs get visited. For
    two long strokes whose overall extents overlap broadly along their
    whole length (e.g. two hand-drawn lines running close and roughly
    parallel for hundreds of px without ever quite touching), that pair
    count still grows quadratically with stroke length even after
    touch-test decimation caps point *density* -- decimation doesn't cap
    *length*.

    Reuses `spatial_index.SpatialGrid`, the exact structure already used
    one level up (in `_cluster_strokes`) to cluster whole strokes, just
    applied to individual segments here instead of whole strokes: segment
    B's segments are bucketed into a grid at `threshold` resolution, each
    inserted under its OWN bounding box expanded by `threshold` (so a
    segment of A within `threshold` of it is guaranteed to land in an
    overlapping cell). Every segment of A then only needs to exact-test
    against the handful of B segments sharing its cell, instead of every B
    segment there is -- turning the search from O(len(A) * len(B)) into
    close to O(len(A) + len(B)).

    The grid gives candidates, never a final answer -- `_segment_segment_distance`
    is still the exact, decisive check for every candidate pair, so this
    can only ever change how fast a pair gets checked, never which pairs
    would have counted as touching (see `_strokes_touch`'s own docstring
    for the same guarantee about its AABB prefilter).
    """
    grid: spatial_index.SpatialGrid = spatial_index.SpatialGrid(cell_size=threshold)
    for idx, box in enumerate(boxes_b):
        expanded = (box[0] - threshold, box[1] + threshold, box[2] - threshold, box[3] + threshold)
        grid.add(idx, expanded)

    for (sa1, sa2), box_a in zip(segs_a, boxes_a):
        expanded_a = (box_a[0] - threshold, box_a[1] + threshold, box_a[2] - threshold, box_a[3] + threshold)
        for idx in grid.get_potential_neighbors(expanded_a):
            sb1, sb2 = segs_b[idx]
            if _segment_segment_distance(sa1, sa2, sb1, sb2) <= threshold:
                return True
    return False


def _strokes_touch(pts_a: List[Point], pts_b: List[Point], threshold: float,
                    endpoint_threshold: float = DEFAULT_ENDPOINT_TOUCH_THRESHOLD) -> bool:
    """
    Detailed check for whether two point-runs should be merged as touching.
    Each of `pts_a`/`pts_b` is one continuous run -- typically one Stroke's
    `.points` (the internal clustering path below always calls it this
    way), but it's equally valid to pass any single flat point cloud, which
    is exactly what the public `strokes_touch` wrapper is for.

    Two passes:
      1. `_endpoints_touch`, at the looser `endpoint_threshold` -- catches
         strokes meant to meet tip-to-tip (or tip-to-middle), where the raw
         pixel gap at the join is bigger than ordinary crossing noise.
      2. The original exhaustive segment-pair test, at the tighter
         `threshold` -- build the polyline segments for each run
         (consecutive points) and test every segment pair for a
         true geometric crossing or near-miss. This is deliberately NOT a
         point-to-point distance check -- two fast-drawn strokes can
         visually cross between two sparsely-sampled mouse points, in which
         case no individual *point* from either stroke ever gets close to a
         point on the other stroke, even though the lines themselves
         clearly intersect. Testing segment-to-segment distance (with true
         intersection short-circuiting to 0.0) catches that crossing
         regardless of how coarse the sampling was.

    Pass 1 only ever makes two strokes MORE likely to merge (never less) and
    only looks at the four tip points, so it can't cause strokes that pass
    close together along their interior to merge -- that's still gated by
    the tight `threshold` in pass 2.

    Pass 2 itself is prefiltered per-segment (not just once per whole
    stroke) via `_bounding_boxes_within_threshold` -- see that segment loop
    below for why: the whole-stroke bounding-box prefilter one level up (in
    `_cluster_strokes`) can't reject a pair whose overall extents
    overlap even when the actual curves never get close anywhere (e.g. a
    circle drawn around a star -- the circle's box contains the star's, so
    every point of every segment pair would otherwise be run through the
    full `_segment_segment_distance` geometry, an O(len(A) * len(B)) cost
    that's the dominant cost of touch-detection on long, point-dense
    strokes). A per-segment AABB check is a handful of comparisons and
    reliably prunes the vast majority of pairs before they ever reach the
    expensive distance calc, without changing which pairs are ultimately
    reported as touching -- it's a widened box (`threshold`-expanded, same
    tolerance the expensive check itself uses), so it never rejects a pair
    the expensive check would have accepted.

    That per-segment prefilter still leaves an O(len(A) * len(B)) loop,
    though -- just a cheap one. For two SHORT strokes that's the fastest
    option (a tight double loop beats the setup/query overhead of building
    an index). But once both strokes are long enough that the pair count
    crosses `DEFAULT_TOUCH_GRID_MIN_SEGMENT_PRODUCT`, the loop itself
    becomes the bottleneck (the classic case: two long strokes running
    close-but-non-touching for their whole shared length, where the AABB
    prefilter can't reject much because the segments really are spatially
    near each other almost everywhere) -- at that point `_strokes_touch_grid`
    takes over, trading loop-visit count for a spatial index lookup. Both
    paths are exact for the final touch decision; only the search strategy
    to get there differs.
    """
    if _endpoints_touch(pts_a, pts_b, endpoint_threshold):
        return True

    segs_a = list(zip(pts_a, pts_a[1:])) or [(pts_a[0], pts_a[0])]
    segs_b = list(zip(pts_b, pts_b[1:])) or [(pts_b[0], pts_b[0])]

    # Precompute each segment's own bounding box ONCE, outside either
    # search strategy below, so it's never redone per-strategy.
    boxes_a = [_segment_bbox(sa1, sa2) for sa1, sa2 in segs_a]
    boxes_b = [_segment_bbox(sb1, sb2) for sb1, sb2 in segs_b]

    if len(segs_a) * len(segs_b) > DEFAULT_TOUCH_GRID_MIN_SEGMENT_PRODUCT:
        return _strokes_touch_grid(segs_a, boxes_a, segs_b, boxes_b, threshold)

    for (sa1, sa2), box_a in zip(segs_a, boxes_a):
        for (sb1, sb2), box_b in zip(segs_b, boxes_b):
            # Cheap reject: if these two segments' (threshold-expanded)
            # bounding boxes don't even overlap, they can't possibly be
            # within `threshold` of one another, so skip the expensive
            # exact geometry test entirely.
            if not _bounding_boxes_within_threshold(box_a, box_b, threshold):
                continue
            if _segment_segment_distance(sa1, sa2, sb1, sb2) <= threshold:
                return True
    return False


def _cluster_strokes(strokes: List[Stroke], proximity_threshold: float,
                      precomputed_boxes: Optional[Dict[int, Tuple[float, float, float, float]]] = None,
                      endpoint_threshold: float = DEFAULT_ENDPOINT_TOUCH_THRESHOLD
                      ) -> Dict[int, int]:
    """
    Core proximity clustering over Stroke objects (Upgraded with Fix D:
    Spatial Indexing). Returns {index_into_strokes: cluster_root_index} --
    indices into `strokes`, since Stroke itself carries no separate id to
    key by (see gesture_types.Stroke: identity is "which list you're in",
    not a tag).

    `precomputed_boxes` (OPTIMIZATION FIX #6): an optional
    {index: (min_x, max_x, min_y, max_y)} map a caller can pass in when it
    already knows some strokes' bounding boxes ahead of time.

    `endpoint_threshold`: looser tip-to-stroke tolerance used by
    `_strokes_touch` (see DEFAULT_ENDPOINT_TOUCH_THRESHOLD in config.py).
    The spatial grid's search radius below is expanded to cover whichever
    of `proximity_threshold`/`endpoint_threshold` is larger, so the cheap
    bounding-box prefilter never excludes a pair that the looser endpoint
    check would have accepted.
    """
    if not strokes:
        return {}

    n = len(strokes)
    if n <= 1:
        return {i: i for i in range(n)}

    # 1. Prepare bounding boxes -- ALWAYS from each stroke's full,
    # undecimated points (never from the touch-test-only thinned points
    # below), since a bounding box computed off a thinned stroke could
    # shrink if an interior extreme point got dropped, and this box also
    # feeds the spatial grid's coarse prefilter, which must stay exact.
    boxes: Dict[int, tuple] = {}
    for i, stroke in enumerate(strokes):
        if precomputed_boxes is not None and i in precomputed_boxes:
            boxes[i] = precomputed_boxes[i]  # FIX #6: reuse caller's cached box
        else:
            boxes[i] = bounding_box(stroke.points)

    # 2. Thin each stroke's points ONCE, up front, for touch-testing only
    # -- see `_decimate_points_for_touch`. Computed once per stroke here
    # rather than once per pairwise comparison inside `_strokes_touch`,
    # since the same stroke can be tested against several potential
    # neighbors during the BFS below; decimating it once and reusing that
    # result for every one of those comparisons avoids redoing the same
    # thinning work over and over for a busy/dense region of the canvas.
    decimation_spacing = proximity_threshold / DEFAULT_TOUCH_DECIMATION_SPACING_DIVISOR
    touch_test_points = {
        i: _decimate_points_for_touch(strokes[i].points, decimation_spacing)
        for i in range(n)
    }

    # 3. Use generic Spatial Indexing (BFS) instead of O(N^2) Union-Find (FIX D)
    # Safely accesses the function whether it is module-level or nested in the class
    try:
        cluster_func = spatial_index.cluster_spatially
    except AttributeError:
        cluster_func = spatial_index.SpatialGrid.cluster_spatially

    search_radius = max(proximity_threshold, endpoint_threshold)
    clusters = cluster_func(
        items=list(range(n)),
        get_bbox_fn=lambda i: boxes[i],
        is_touching_fn=lambda a, b: _strokes_touch(
            touch_test_points[a], touch_test_points[b], proximity_threshold, endpoint_threshold
        ),
        threshold=search_radius
    )

    # 4. Convert clustered lists back into {index: root_index} format so
    # the rest of the public API doesn't need to change.
    root_of: Dict[int, int] = {}
    for cluster in clusters:
        # Assign the first item in the connected component as the root
        root = cluster[0]
        for i in cluster:
            root_of[i] = root

    return root_of


# =============================================================================
# 3. Public API
# =============================================================================

def group_strokes_by_proximity(strokes: List[Stroke], proximity_threshold: float = DEFAULT_TOUCH_THRESHOLD,
                                precomputed_boxes: Optional[Dict[int, Tuple[float, float, float, float]]] = None,
                                endpoint_threshold: float = DEFAULT_ENDPOINT_TOUCH_THRESHOLD
                                ) -> List[List[Stroke]]:
    """
    Groups Strokes into spatial clusters.

    Returns a list of clusters; each cluster is the list of original Stroke
    objects that are within `proximity_threshold` of one another, directly
    or transitively. Cluster order follows the first-appearance order of
    each cluster in `strokes`, and each cluster's own strokes keep their
    relative order from `strokes` too.

    NOTE: this is a general-purpose proximity-clustering primitive -- it
    doesn't know or care about Level. Called with the default (tight) touch
    threshold on raw pen-strokes, it's the "do these strokes physically
    touch?" test used to build SHAPE-level units out of a canvas. The same
    primitive is reused for other kinds of clustering elsewhere (e.g.
    recognizer.py bundling already-recognized Features by proximity, via
    the lower-level `strokes_touch`/`bounding_boxes_within_threshold`
    building blocks directly) -- but that higher-level composition decision
    does not live in this file.

    `precomputed_boxes` (OPTIMIZATION FIX #6): see `_cluster_strokes` --
    purely a speed optimization for callers who already know some strokes'
    bounding boxes; leaving it as None reproduces the original behavior
    exactly.
    """
    if not strokes:
        return []

    root_of = _cluster_strokes(strokes, proximity_threshold, precomputed_boxes, endpoint_threshold)

    clusters: Dict[int, List[Stroke]] = {}
    order: List[int] = []
    for i, stroke in enumerate(strokes):
        root = root_of[i]
        if root not in clusters:
            clusters[root] = []
            order.append(root)
        clusters[root].append(stroke)

    return [clusters[root] for root in order]


def count_touch_units(strokes: List[Stroke], proximity_threshold: float = DEFAULT_TOUCH_THRESHOLD,
                       endpoint_threshold: float = DEFAULT_ENDPOINT_TOUCH_THRESHOLD) -> int:
    """
    Returns the number of physically-separate stroke units in `strokes` --
    i.e. how many touch-merged clusters `group_strokes_by_proximity` would
    produce. This is the single source of truth for "level" elsewhere in the
    pipeline: a feature/template's level is defined as exactly this count,
    not an arbitrary label. Two strokes that touch/cross (like the two
    strokes of a hand-drawn "+") collapse into ONE unit; two strokes that
    never get within `proximity_threshold` of one another (like the stem and
    dot of a hand-drawn "!") count as TWO separate units, and so on -- with
    no ceiling on how many.
    """
    return len(group_strokes_by_proximity(strokes, proximity_threshold, endpoint_threshold=endpoint_threshold))


def merge_intersecting_strokes(strokes: List[Stroke], proximity_threshold: float = DEFAULT_TOUCH_THRESHOLD,
                                endpoint_threshold: float = DEFAULT_ENDPOINT_TOUCH_THRESHOLD) -> List[Stroke]:
    """
    Merges Strokes together ONLY if any point in stroke A is within
    `proximity_threshold` pixels of any point in stroke B (handles
    intersections and near-touching strokes) -- i.e. physical contact, and
    nothing else. This is intentionally level-agnostic: it has no idea what
    a SHAPE or OBJECT is, and it will never fuse two strokes just because
    they're "supposed to" belong to the same higher-level figure. Composing
    recognized SHAPE-level features into a composite OBJECT (strokes that
    don't touch but belong together) is handled one layer up, in
    recognizer.py, after each piece has been recognized on its own.

    Returns one Stroke per touch-cluster, each holding the concatenated
    points of every original Stroke in that cluster (original per-stroke
    point order preserved, clusters in first-appearance order) -- i.e. each
    touch-merged cluster IS one Stroke object afterwards. That's what makes
    downstream per-stroke logic (path length / resampling, in
    recognizer.py) treat a merged cluster as one continuous run: it
    literally is a single Stroke now, the same way giving merged points a
    shared stroke_id used to signal that under the old tagging scheme.
    """
    if not strokes:
        return []
    if len(strokes) <= 1:
        return strokes  # Nothing to merge

    root_of = _cluster_strokes(strokes, proximity_threshold, endpoint_threshold=endpoint_threshold)

    root_to_points: Dict[int, List[Point]] = {}
    root_order: List[int] = []
    for i, stroke in enumerate(strokes):
        root = root_of[i]
        if root not in root_to_points:
            root_to_points[root] = []
            root_order.append(root)
        root_to_points[root].extend(stroke.points)

    return [Stroke(points=root_to_points[root]) for root in root_order]


def merge_and_count_touch_units(strokes: List[Stroke], proximity_threshold: float = DEFAULT_TOUCH_THRESHOLD,
                                 endpoint_threshold: float = DEFAULT_ENDPOINT_TOUCH_THRESHOLD
                                 ) -> Tuple[List[Stroke], int]:
    """
    OPTIMIZATION FIX C: `count_touch_units(strokes, t)` and
    `merge_intersecting_strokes(strokes, t)` each run their own full pass of
    the union-find + bounding-box-prefiltered segment-touch clustering in
    `_cluster_strokes` -- on the exact same `strokes` and the exact same
    `proximity_threshold`. Calling both back-to-back (as recognizer.py's
    `recognize()`/`add_template` used to: once to validate the requested
    "level" against the touch-unit count, then again moments later inside
    `_preprocess`'s call to `merge_intersecting_strokes`) pays for that
    clustering work twice for no reason -- the answer can't have changed
    between the two calls.

    This does the clustering ONCE and returns both pieces of information
    that were being derived from it separately:
      - `merged_strokes`: identical to what `merge_intersecting_strokes`
        would return (one Stroke per touch-merged cluster).
      - `unit_count`: identical to what `count_touch_units` would return
        (how many distinct touch-merged clusters there are -- always
        `len(merged_strokes)`).

    Behavior is otherwise identical to calling both functions separately --
    same threshold, same underlying `_cluster_strokes` call, same
    results -- just computed once instead of twice.
    """
    if not strokes:
        return [], 0
    if len(strokes) <= 1:
        return strokes, len(strokes)  # Nothing to merge; a non-empty input is always exactly 1 unit here.

    root_of = _cluster_strokes(strokes, proximity_threshold, endpoint_threshold=endpoint_threshold)

    root_to_points: Dict[int, List[Point]] = {}
    root_order: List[int] = []
    for i, stroke in enumerate(strokes):
        root = root_of[i]
        if root not in root_to_points:
            root_to_points[root] = []
            root_order.append(root)
        root_to_points[root].extend(stroke.points)

    merged = [Stroke(points=root_to_points[root]) for root in root_order]
    return merged, len(merged)


def bounding_box(points: List[Point]) -> tuple:
    """Returns (min_x, max_x, min_y, max_y) for a list of points."""
    return (
        min(p.x for p in points), max(p.x for p in points),
        min(p.y for p in points), max(p.y for p in points),
    )

def bounding_boxes_within_threshold(box_a: tuple, box_b: tuple, threshold: float) -> bool:
    """Public wrapper for the cheap bounding box pre-filter."""
    return _bounding_boxes_within_threshold(box_a, box_b, threshold)

def strokes_touch(pts_a: List[Point], pts_b: List[Point], threshold: float,
                   endpoint_threshold: float = DEFAULT_ENDPOINT_TOUCH_THRESHOLD) -> bool:
    """
    Public wrapper for the full touch test between two point lists, each
    treated as a single run (internal stroke boundaries within a list
    aren't respected here -- this answers "are these two POINT CLOUDS
    within `threshold` of one another", not "which strokes touch which").

    Exposed so a caller that already has two specific point clouds it
    wants to compare -- e.g. recognizer.py bundling already-recognized
    Features by proximity, via their flattened `Feature.points` -- can
    reuse the fully-optimized touch test (endpoint short-circuit,
    per-segment AABB prefilter, touch-test decimation, and grid-indexed
    search for long strokes -- see `_strokes_touch`'s own docstring)
    directly, without needing to route through
    `group_strokes_by_proximity`'s whole-canvas-of-many-strokes machinery,
    which solves a different problem (clustering many raw strokes at once)
    than "are these two point clouds I already have close to each other".
    """
    return _strokes_touch(pts_a, pts_b, threshold, endpoint_threshold)