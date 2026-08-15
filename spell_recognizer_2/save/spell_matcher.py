"""
Spell Matching -- Relational Layer on top of QRecognizer
==========================================================
$Q (recognizer.py) intentionally throws away position: every gesture is
uniformly scaled into a fixed frame and re-centered on its own centroid
before scoring (see QRecognizer._preprocess), because classifying "is this
stroke a triangle" has to work no matter where on the canvas it was drawn.

A *spell*, though, is defined by exactly the information $Q throws away:
not just "there's a star and four triangles here", but "the triangles sit
roughly north/east/south/west of the star, at roughly this distance from
it". That's a relational/layout question, not a shape-classification
question, so it lives in its own layer instead of being bolted onto
QRecognizer:

  Layer 1 (recognizer.py, unchanged): classify each physically-separate
    stroke cluster into a named, leveled SceneFeature (circle, triangle, star_5,
    ...) via QRecognizer.recognize_scene. Position is deliberately ignored
    here.

  Layer 2 (this module): given the List[SceneFeature] recognize_scene just
    produced -- which still carries each SceneFeature's RAW, unnormalized scene
    points (SceneFeature.points is the pre-_preprocess data) -- work out
    where each SceneFeature sits *relative to the whole drawing* and match that
    layout against a library of spell definitions.

Every SceneFeature in a spell (including circles/lines/rings -- there's no
special "center" node type; everything is a SceneFeature, some just happen to
sit at distance ~0) is described the same way: a shape name, a distance
from the spell's own center (normalized to the drawing's own size, so
spells are scale-invariant regardless of how big they're drawn), and an
optional angle sector ("between compass bearing X and Y") for SceneFeatures
whose *position* -- not just presence -- matters, like "a triangle north of
center". Compass angle, not math angle: 0=N, 90=E, 180=S, 270=W, matching
how someone points at a compass rather than how atan2 returns radians.

What this module deliberately does NOT give you: rotation invariance. The
spell center is derived from the drawing itself, but "north" is always
"up on the page" -- a correctly-drawn spell rotated 30 degrees will not
match. That's a real tradeoff (see module-level note at the bottom for the
one-line change that would trade it back for angle-relative-to-an-anchor-
SceneFeature instead of true north), made deliberately because "triangle to the
north" is meaningless once you drop absolute orientation.

Layout of this file:
  1. Geometry helpers        -- compass_angle, angle_in_range,
                                 compute_positions (SceneFeature -> relative
                                 distance/angle)
  2. Spell definitions        -- SpellSceneFeatureSlot, SpellDefinition (pure
                                  data -- persistence lives in spell_store.py)
  3. Matching                 -- SpellMatchResult, match_spell,
                                  match_best_spell
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from merge_intersecting_strokes import Point

if TYPE_CHECKING:
    from recognizer import SceneFeature

from config import (
    DEFAULT_SPELL_DIST_TOLERANCE,
    DEFAULT_SPELL_ANGLE_TOLERANCE,
    DEFAULT_SPELL_MIN_SCORE,
    SPELL_CENTER_EPSILON,
)


# =============================================================================
# 1. Geometry helpers
# =============================================================================

def compass_angle(dx: float, dy: float) -> float:
    """
    Bearing of the vector (dx, dy) in COMPASS convention: 0=North, 90=East,
    180=South, 270=West, increasing clockwise -- not math convention (0 on
    the positive x-axis, counter-clockwise), because spell authors think in
    "north of center", not "positive x-axis". Screen y grows downward, so
    "up" is -dy; that's the only reason dy is negated here.
    """
    return math.degrees(math.atan2(dx, -dy)) % 360.0


def angle_in_range(angle: float, min_angle: float, max_angle: float) -> bool:
    """
    True if `angle` (compass bearing, any real number) falls inside the
    sector [min_angle, max_angle] going CLOCKWISE from min_angle to
    max_angle. Handles the wraparound case (e.g. min=315, max=45 spans
    through the 360/0 seam) by checking whether the sector itself wraps,
    rather than assuming min_angle <= max_angle the way a plain range check
    would.
    """
    a = angle % 360.0
    lo = min_angle % 360.0
    hi = max_angle % 360.0
    if lo <= hi:
        return lo <= a <= hi
    return a >= lo or a <= hi


def _sector_overshoot(angle: float, min_angle: float, max_angle: float) -> float:
    """
    For an `angle` OUTSIDE the [min_angle, max_angle] sector, how many
    degrees past the nearer edge it sits. Used only for soft scoring (see
    _slot_score) -- angle_in_range is the hard gate; this is what turns a
    near-miss into a partial-credit score instead of a flat zero.
    """
    lo, hi = min_angle % 360.0, max_angle % 360.0
    span = (hi - lo) % 360.0
    rel = (angle % 360.0 - lo) % 360.0  # position within the sector's own frame, 0..360
    # rel <= span would mean "inside", which the caller already ruled out;
    # the distance past the far (hi) edge going forward vs. past the near
    # (lo) edge going backward -- take whichever is smaller.
    return min(rel - span, 360.0 - rel)


def _centroid_xy(points: List[Point]) -> Tuple[float, float]:
    x = sum(p.x for p in points) / len(points)
    y = sum(p.y for p in points) / len(points)
    return x, y


def _bounding_diagonal(all_points: List[Point]) -> float:
    """Diagonal of the bounding box over every point in the whole drawing --
    what SceneFeature distances are normalized against, so a spell drawn big or
    small still matches the same normalized distances."""
    xs = [p.x for p in all_points]
    ys = [p.y for p in all_points]
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    return math.hypot(w, h)


@dataclass
class PositionedSceneFeature:
    """
    A SceneFeature re-expressed relative to the whole drawing: everything
    the matcher actually needs, decoupled from recognizer.py's SceneFeature
    type so this module only depends on it for type-checking, not at
    runtime (see the TYPE_CHECKING import above).
    """
    shape: str
    distance: float           # normalized: 0.0 = at the spell's own center
    angle: float               # compass bearing, degrees
    source: "SceneFeature"     # original SceneFeature, kept for overlays/debugging


def compute_positions(SceneFeatures: List["SceneFeature"]) -> List[PositionedSceneFeature]:
    """
    Turns a flat List[SceneFeature] (as returned by
    QRecognizer.recognize_scene) into PositionedSceneFeatures: each SceneFeature's
    shape name plus its distance/angle relative to the drawing's OWN center
    (the centroid of every SceneFeature's own centroid, each SceneFeature weighted
    equally regardless of how many points/strokes made it up -- so a
    fiddly, many-point star doesn't drag the center toward itself more
    than a simple two-point line would) and the drawing's OWN size
    (bounding-box diagonal over every point in the whole drawing).

    Only SceneFeatures with a real recognized name are usable for spell
    matching (an unrecognized/rejected cluster can't fill a spell slot), so
    those are silently skipped here rather than raising -- a spell match
    against a scene with some unrecognized clutter in it should still be
    possible.
    """
    named = [f for f in SceneFeatures if f.result.name is not None]
    if not named:
        return []

    centroids = [_centroid_xy(f.points) for f in named]
    center_x = sum(c[0] for c in centroids) / len(centroids)
    center_y = sum(c[1] for c in centroids) / len(centroids)

    all_points = [p for f in named for p in f.points]
    diag = _bounding_diagonal(all_points)
    if diag <= 1e-9:
        diag = 1.0  # degenerate single-point drawing -- avoid div-by-zero

    positioned = []
    for feat, (cx, cy) in zip(named, centroids):
        dx, dy = cx - center_x, cy - center_y
        raw_dist = math.hypot(dx, dy)
        positioned.append(PositionedSceneFeature(
            shape=feat.result.name,
            distance=raw_dist / diag,
            angle=compass_angle(dx, dy),
            source=feat,
        ))
    return positioned


# =============================================================================
# 2. Spell definitions (pure data; see spell_store.py for JSON persistence)
# =============================================================================

@dataclass
class SpellSceneFeatureSlot:
    """
    One required SceneFeature within a spell, described relationally rather
    than by absolute position -- see this module's docstring. `id` only
    needs to be unique within its own SpellDefinition (it's how a match
    result reports which scene SceneFeature filled which slot).
    """
    id: int
    shape: str
    distance: float
    tolerance_dist: float = DEFAULT_SPELL_DIST_TOLERANCE
    min_angle: Optional[float] = None   # None -> angle unconstrained (any position OK)
    max_angle: Optional[float] = None
    tolerance_angle: float = DEFAULT_SPELL_ANGLE_TOLERANCE  # soft margin for scoring just outside the sector

    def angle_constrained(self) -> bool:
        return self.min_angle is not None and self.max_angle is not None


@dataclass
class SpellDefinition:
    name: str
    SceneFeatures: List[SpellSceneFeatureSlot]
    min_score: float = DEFAULT_SPELL_MIN_SCORE


# =============================================================================
# 3. Matching
# =============================================================================

@dataclass
class SpellMatchResult:
    name: Optional[str]
    score: float
    accepted: bool
    # slot.id -> matched PositionedSceneFeature, for whichever slots got filled;
    # a slot missing from this dict means nothing in the scene satisfied it
    # well enough to be worth assigning (useful for "you're missing the
    # north triangle" style feedback even on a rejected match).
    assignment: Dict[int, PositionedSceneFeature] = field(default_factory=dict)


def _slot_score(slot: SpellSceneFeatureSlot, feat: PositionedSceneFeature) -> float:
    """
    Score in [0.0, 1.0] for matching `feat` to `slot`, given they already
    share the same shape (shape match is a hard gate, checked by the
    caller via the by-shape candidate grouping in match_spell -- a
    triangle can never fill a circle's slot no matter how well-positioned
    it is). Blends a distance-closeness score with an angle-closeness
    score (the latter only when the slot actually constrains angle),
    rather than being a hard pass/fail, so near-misses still produce a
    meaningful score for feedback instead of just "no match" -- the same
    philosophy _cloud_distance/_blend_avg_max use in recognizer.py.
    """
    dist_diff = abs(feat.distance - slot.distance)
    if dist_diff > slot.tolerance_dist:
        return 0.0
    dist_score = 1.0 - (dist_diff / slot.tolerance_dist if slot.tolerance_dist > 1e-9 else 0.0)

    if not slot.angle_constrained() or slot.distance <= SPELL_CENTER_EPSILON:
        return dist_score  # angle is meaningless this close to center, or the slot doesn't care

    if angle_in_range(feat.angle, slot.min_angle, slot.max_angle):
        return dist_score

    overshoot = _sector_overshoot(feat.angle, slot.min_angle, slot.max_angle)
    angle_score = max(0.0, 1.0 - overshoot / max(slot.tolerance_angle, 1e-9))
    if angle_score <= 0.0:
        return 0.0
    return dist_score * angle_score


def match_spell(spell: SpellDefinition, scene_SceneFeatures: List["SceneFeature"]
                 ) -> SpellMatchResult:
    """
    Finds the best injective assignment of `scene_SceneFeatures` to `spell`'s
    slots (each scene SceneFeature can fill at most one slot) via backtracking:
    for every slot, only shape-matching, positive-score candidates are
    ever tried, plus a "leave unfilled" branch. Spell templates are small
    (a handful of SceneFeatures), so this is cheap -- no need for a general
    subgraph-isomorphism solver.

    Score = mean _slot_score over every slot in the spell (an unfilled
    slot contributes 0 to that average). `accepted` requires BOTH every
    slot to be filled (score alone can't distinguish "filled badly" from
    "empty" -- both drag a small spell's average down similarly) AND the
    resulting score to clear `spell.min_score`.
    """
    positioned = compute_positions(scene_SceneFeatures)

    # Group candidates by shape up front so each slot only ever considers
    # scene SceneFeatures that could possibly fill it.
    by_shape: Dict[str, List[int]] = {}
    for idx, feat in enumerate(positioned):
        by_shape.setdefault(feat.shape, []).append(idx)

    slots = spell.SceneFeatures
    used = [False] * len(positioned)
    current: Dict[int, int] = {}

    best: Dict[int, int] = {}
    best_score = -1.0

    def backtrack(slot_pos: int, running_score: float) -> None:
        nonlocal best, best_score
        if slot_pos == len(slots):
            avg = running_score / len(slots) if slots else 0.0
            if avg > best_score:
                best_score = avg
                best = dict(current)
            return

        slot = slots[slot_pos]
        for idx in by_shape.get(slot.shape, []):
            if used[idx]:
                continue
            score = _slot_score(slot, positioned[idx])
            if score <= 0.0:
                continue
            used[idx] = True
            current[slot.id] = idx
            backtrack(slot_pos + 1, running_score + score)
            del current[slot.id]
            used[idx] = False

        # Also try leaving this slot unfilled, so a spell missing one
        # required SceneFeature still yields the best possible PARTIAL match
        # (useful for near-miss feedback) instead of no assignment at all.
        backtrack(slot_pos + 1, running_score)

    backtrack(0, 0.0)

    assignment = {slot_id: positioned[idx] for slot_id, idx in best.items()}
    all_filled = len(assignment) == len(slots)
    final_score = max(best_score, 0.0)
    accepted = all_filled and final_score >= spell.min_score

    return SpellMatchResult(
        name=spell.name if accepted else None,
        score=final_score,
        accepted=accepted,
        assignment=assignment,
    )


def match_best_spell(spells: List[SpellDefinition], scene_SceneFeatures: List["SceneFeature"]
                      ) -> Optional[SpellMatchResult]:
    """
    Tries every known spell against the same scene and returns whichever
    ACCEPTED result scored highest, or None if nothing accepted. Mirrors
    QRecognizer.recognize's "best template wins" shape, just one level up
    (best SPELL instead of best per-level template).
    """
    best_result: Optional[SpellMatchResult] = None
    for spell in spells:
        result = match_spell(spell, scene_SceneFeatures)
        if result.accepted and (best_result is None or result.score > best_result.score):
            best_result = result
    return best_result


# -----------------------------------------------------------------------------
# Note on rotation invariance (see module docstring)
# -----------------------------------------------------------------------------
# To match a spell drawn at any rotation, angles would need to be measured
# relative to one designated "anchor" SceneFeature's bearing from center instead
# of true north -- i.e. `angle = (compass_angle(dx, dy) - anchor_bearing) %
# 360` for every SceneFeature, anchor included (which then sits at angle 0 by
# definition). That's a change to compute_positions (needs to know which
# SceneFeature is the anchor) and to how SpellSceneFeatureSlot.min_angle/max_angle
# are interpreted (relative bearing from the anchor, not compass bearing) --
# deliberately NOT done here since it trades away the ability to express
# "must be drawn upright", which most spells probably want.