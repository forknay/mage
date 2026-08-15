"""
Spell Matching -- Relational Layer on top of QRecognizer
==========================================================
$Q (recognizer.py) throws away position on purpose: every gesture gets
scaled into a fixed frame and re-centered on its own centroid before
scoring, because "is this a triangle" has to work no matter where on the
canvas it was drawn.

A *spell* cares about exactly the thing $Q throws away: not just "there's
a star and four triangles here", but "the triangles sit north/east/south/
west of the star, roughly this far out". That's a layout question, not a
shape question, so it lives here instead of inside QRecognizer.

  Layer 1 (recognizer.py): classify each stroke cluster into a named
    shape (circle, triangle, star_5, ...). No position involved.

  Layer 2 (this file): take the List[SceneFeature] Layer 1 produced and
    check whether their LAYOUT matches a known spell.

A feature's position in a spell can be described three ways, and any of
them can be mixed within the same spell:

  1. Absolute: "distance 0.75 from center, north of center."
     `SpellFeatureSlot.distance` is optional -- leave it out and only
     shape (+ angle/relative rules, if any) are checked.

  2. Relative distance: "the triangle must be farther out than the star."
     No fixed number needed for either slot.

  3. Containment: "this feature must sit inside/outside that circle,"
     checked against the OTHER feature's own center and size, not the
     spell's center -- so it works no matter where the circle sits.

Every check in this file returns a score from 0.0 to 1.0 instead of a
flat yes/no -- a near-miss still gets partial credit, which is what
produces "closest: 76%" style feedback instead of a blank "no match".
Final acceptance, though, is a hard rule check (see `match_spell`): every
slot and every relative constraint has to individually clear its own
tolerance. There's no overall "accuracy" number that things get averaged
into and possibly slip past a threshold on.

Angles use COMPASS convention: 0=North, 90=East, 180=South, 270=West,
clockwise -- not math convention -- because spell authors think "north of
center", not "positive x-axis".

Not supported: rotation invariance. "North" always means "up on the
page". See the note at the bottom of this file for what changing that
would involve, and why it wasn't done.

Layout of this file:
  1. Geometry helpers  -- angle math, centroid/radius helpers,
                           compute_positions (SceneFeature -> position)
  2. Spell definitions -- SpellFeatureSlot, RelativeDistanceConstraint,
                           SpellDefinition (pure data; JSON lives in
                           spell_store.py)
  3. Matching          -- SpellMatchResult, match_spell, match_best_spell
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
    """Bearing of vector (dx, dy) as a compass reading: 0=N, 90=E, 180=S,
    270=W, clockwise."""
    # atan2(dx, -dy) instead of the usual atan2(dy, dx): swapping the args
    # rotates math-angle (0=east, counter-clockwise) into compass-angle
    # (0=north, clockwise). dy is negated because screen y grows DOWNWARD,
    # so "up the page" is -dy, not +dy.
    return math.degrees(math.atan2(dx, -dy)) % 360.0


def angle_in_range(angle: float, min_angle: float, max_angle: float) -> bool:
    """True if `angle` falls inside [min_angle, max_angle], going
    CLOCKWISE from min to max (so min=315, max=45 correctly covers the
    sector wrapping through 0/360, e.g. "north-ish")."""
    a = angle % 360.0
    lo = min_angle % 360.0
    hi = max_angle % 360.0
    if lo <= hi:
        # Normal case, no wraparound: e.g. lo=60, hi=120.
        return lo <= a <= hi
    # Wraparound case: e.g. lo=315, hi=45. The sector is everything from
    # 315 up to 360, PLUS everything from 0 up to 45.
    return a >= lo or a <= hi


def _sector_overshoot(angle: float, min_angle: float, max_angle: float) -> float:
    """For an `angle` that's OUTSIDE [min_angle, max_angle], how many
    degrees past the closer edge it landed. Used only to turn a near-miss
    into partial credit instead of a flat 0 -- angle_in_range is the real
    gate; this only runs once that's already False."""
    lo, hi = min_angle % 360.0, max_angle % 360.0
    span = (hi - lo) % 360.0
    # Re-measure the angle relative to lo, so the sector always looks like
    # a simple [0, span] range regardless of where it sits on the compass.
    rel = (angle % 360.0 - lo) % 360.0
    # rel is now either inside [0, span] (shouldn't happen -- caller
    # already confirmed we're outside the sector) or past one of the two
    # edges. Distance past the far edge (hi), going forward, vs. distance
    # past the near edge (lo), going backward -- take whichever is closer.
    return min(rel - span, 360.0 - rel)


def _centroid_xy(points: List[Point]) -> Tuple[float, float]:
    """Plain average of a list of points -- their center of mass."""
    x = sum(p.x for p in points) / len(points)
    y = sum(p.y for p in points) / len(points)
    return x, y


def _mean_radius(points: List[Point], cx: float, cy: float) -> float:
    """Average distance of `points` from their own centroid (cx, cy).
    This is a feature's rough "size" -- for an actual hand-drawn circle,
    its points really do sit about this far from its own center, so this
    doubles as "the circle's radius" for containment checks. For other
    shapes it's just a size estimate: a tight star has a small radius, a
    sprawling triangle a bigger one."""
    return sum(math.hypot(p.x - cx, p.y - cy) for p in points) / len(points)


def _bounding_diagonal(all_points: List[Point]) -> float:
    """Diagonal of the bounding box around every point in the whole
    drawing. Every distance/radius in this file gets divided by this
    number, so a spell drawn twice as big still measures the same."""
    xs = [p.x for p in all_points]
    ys = [p.y for p in all_points]
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    return math.hypot(w, h)


@dataclass
class PositionedFeature:
    """
    One SceneFeature, re-expressed relative to the whole drawing. This is
    all the position info the matcher needs -- it doesn't touch
    recognizer.SceneFeature directly at runtime (only for type hints, via
    the TYPE_CHECKING import above), so this module has no hard runtime
    dependency on recognizer.py.
    """
    shape: str                  # recognized shape name, e.g. "circle"
    distance: float             # normalized distance from the SPELL's center
    angle: float                 # compass bearing from the SPELL's center, degrees
    nx: float                    # normalized x-offset from the SPELL's center
    ny: float                    # normalized y-offset from the SPELL's center
    # distance == hypot(nx, ny) and angle == compass_angle(nx, ny) -- nx/ny
    # are kept as their own fields just so feature-to-feature math
    # (relative distance, containment) doesn't have to reconstruct x/y
    # from distance+angle every time it's needed.
    radius: float                 # this feature's OWN normalized size (see _mean_radius)
    source: "SceneFeature"       # the original feature, kept around for overlays/debugging


def compute_positions(features: List["SceneFeature"]) -> List[PositionedFeature]:
    """Turns the flat feature list from QRecognizer.recognize_scene into
    PositionedFeatures -- each feature's shape plus where it sits relative
    to the rest of the drawing."""
    # Only features the recognizer actually named can fill a spell slot;
    # unrecognized clutter is just skipped, not an error.
    named = [f for f in features if f.result.name is not None]
    if not named:
        return []

    # The spell's "center" is the average of every feature's own centroid
    # -- NOT weighted by point count, so a fiddly many-point star doesn't
    # pull the center toward itself more than a simple two-point line.
    centroids = [_centroid_xy(f.points) for f in named]
    center_x = sum(c[0] for c in centroids) / len(centroids)
    center_y = sum(c[1] for c in centroids) / len(centroids)

    # Everything gets normalized against the whole drawing's own size, so
    # a spell drawn bigger or smaller still matches.
    all_points = [p for f in named for p in f.points]
    diag = _bounding_diagonal(all_points)
    if diag <= 1e-9:
        diag = 1.0  # a degenerate single-point drawing -- avoid divide-by-zero

    positioned = []
    for feat, (cx, cy) in zip(named, centroids):
        dx, dy = cx - center_x, cy - center_y     # offset from spell center, raw px
        raw_dist = math.hypot(dx, dy)               # distance from spell center, raw px
        own_radius = _mean_radius(feat.points, cx, cy)  # this feature's own size, raw px
        positioned.append(PositionedFeature(
            shape=feat.result.name,
            distance=raw_dist / diag,
            angle=compass_angle(dx, dy),
            nx=dx / diag,
            ny=dy / diag,
            radius=own_radius / diag,
            source=feat,
        ))
    return positioned


# =============================================================================
# 2. Spell definitions (pure data; see spell_store.py for JSON persistence)
# =============================================================================

@dataclass
class SpellFeatureSlot:
    """
    One required feature within a spell. `id` just needs to be unique
    within its own SpellDefinition -- it's how a match result reports
    which scene feature filled which slot, and how a
    RelativeDistanceConstraint points back at a slot.
    """
    id: int
    shape: str
    # `distance` is OPTIONAL. Leave it as None for a slot that's
    # positioned purely by angle and/or a RelativeDistanceConstraint
    # instead of a fixed number -- e.g. "farther out than the star",
    # with no fixed absolute distance for either one.
    distance: Optional[float] = None
    tolerance_dist: float = DEFAULT_SPELL_DIST_TOLERANCE
    min_angle: Optional[float] = None    # None -> angle unconstrained, any position OK
    max_angle: Optional[float] = None
    tolerance_angle: float = DEFAULT_SPELL_ANGLE_TOLERANCE  # soft margin just outside the sector

    def angle_constrained(self) -> bool:
        """True if this slot actually cares about angle."""
        return self.min_angle is not None and self.max_angle is not None


@dataclass
class RelativeDistanceConstraint:
    """
    A positioning check BETWEEN two slots, e.g. "the triangle must sit
    farther out than the star" or "this rune must sit inside that circle".
    Checked once a candidate assignment has filled both slots.

    `subject_id` / `reference_id` are SpellFeatureSlot.id values, both
    belonging to the same spell (checked in SpellDefinition.__post_init__).

    `relation` is one of:
      - "farther": subject's distance from spell-center must beat
        reference's distance from spell-center by at least `margin`.
      - "closer": same, but subject must be the smaller distance.
      - "inside": subject must sit within reference's OWN radius (checked
        against reference's own center, not the spell's center -- so a
        containing circle can sit anywhere in the spell and this still
        works). `margin` is extra slack added to reference's radius.
      - "outside": the opposite of "inside" -- subject must sit beyond
        reference's own radius (+ margin).

        Why "outside" exists as its own thing, instead of just using
        "farther": for two CONCENTRIC circles (same spell-center offset,
        different sizes), "farther"/"closer" can't tell them apart --
        both sit at ~0 distance from the spell center no matter how big
        either one is. "outside" sidesteps that by checking against the
        reference's own radius instead. So "a feature sitting in the ring
        between two circles" is: outside(inner) AND inside(outer).

    `tolerance` controls how fast the score falls off once the relation
    is violated -- violated by a hair still scores near 1.0, violated by
    a lot scores 0.0. Same units as PositionedFeature.distance/radius, so
    it defaults to the same tolerance constant those use.
    """
    subject_id: int
    reference_id: int
    relation: str
    margin: float = 0.0
    tolerance: float = DEFAULT_SPELL_DIST_TOLERANCE

    def __post_init__(self):
        if self.relation not in ("farther", "closer", "inside", "outside"):
            raise ValueError(
                f"RelativeDistanceConstraint.relation must be 'farther', 'closer', "
                f"'inside', or 'outside', got {self.relation!r}."
            )


@dataclass
class SpellDefinition:
    """
    A named collection of slots (+ optional relative constraints) that
    together describe a spell's layout.

    `min_score` is kept only so old spell files/API calls still work --
    `match_spell` does NOT use it to decide acceptance (see that
    function). To make a spell easier or harder to trigger, adjust the
    individual slot/constraint tolerance values instead.
    """
    name: str
    features: List[SpellFeatureSlot]
    min_score: float = DEFAULT_SPELL_MIN_SCORE
    relative_constraints: List[RelativeDistanceConstraint] = field(default_factory=list)

    def __post_init__(self):
        # Catch a typo'd subject_id/reference_id right away, at spell-load
        # time -- otherwise it just silently scores 0 forever, which looks
        # identical to "this constraint is correctly failing".
        known_ids = {slot.id for slot in self.features}
        for c in self.relative_constraints:
            if c.subject_id not in known_ids:
                raise ValueError(
                    f"Spell '{self.name}': RelativeDistanceConstraint.subject_id={c.subject_id} "
                    f"does not match any feature slot id."
                )
            if c.reference_id not in known_ids:
                raise ValueError(
                    f"Spell '{self.name}': RelativeDistanceConstraint.reference_id={c.reference_id} "
                    f"does not match any feature slot id."
                )


# =============================================================================
# 3. Matching
# =============================================================================

@dataclass
class SpellMatchResult:
    name: Optional[str]
    score: float
    accepted: bool
    # slot.id -> the PositionedFeature that filled it. A slot missing from
    # this dict means nothing in the scene filled it well enough -- useful
    # for "you're missing the north triangle" feedback even when rejected.
    assignment: Dict[int, PositionedFeature] = field(default_factory=dict)


def _slot_score(slot: SpellFeatureSlot, feat: PositionedFeature) -> float:
    """
    Score from 0.0 to 1.0 for matching `feat` to `slot`. Shape is assumed
    to already match (the caller only ever calls this for same-shape
    pairs) -- this only scores POSITION: distance-from-center (if the
    slot has one) and angle-from-center (if the slot constrains angle).
    """
    if slot.distance is not None:
        dist_diff = abs(feat.distance - slot.distance)
        if dist_diff > slot.tolerance_dist:
            return 0.0  # too far from where the slot expects it -- hard fail
        # Linear falloff: dead-on = 1.0, right at the tolerance edge = 0.0.
        dist_score = 1.0 - (dist_diff / slot.tolerance_dist if slot.tolerance_dist > 1e-9 else 0.0)
    else:
        dist_score = 1.0  # slot has no fixed distance -- don't penalize on it at all

    # A feature sitting basically ON the spell's center doesn't have a
    # meaningful "north/south/east/west" -- skip the angle check for it.
    # (Checked against the feature's OWN actual distance, not the slot's
    # expected distance, since the slot might not even have one.)
    if not slot.angle_constrained() or feat.distance <= SPELL_CENTER_EPSILON:
        return dist_score

    if angle_in_range(feat.angle, slot.min_angle, slot.max_angle):
        return dist_score  # inside the required sector -- full credit on angle

    # Outside the sector -- give partial credit if it's close, based on
    # how many degrees past the edge it landed.
    overshoot = _sector_overshoot(feat.angle, slot.min_angle, slot.max_angle)
    angle_score = max(0.0, 1.0 - overshoot / max(slot.tolerance_angle, 1e-9))
    if angle_score <= 0.0:
        return 0.0
    return dist_score * angle_score


def _relative_constraint_score(constraint: RelativeDistanceConstraint,
                                positioned_by_slot: Dict[int, PositionedFeature]) -> float:
    """Score from 0.0 to 1.0 for one RelativeDistanceConstraint, given
    the slots it references are (maybe) filled."""
    subj = positioned_by_slot.get(constraint.subject_id)
    ref = positioned_by_slot.get(constraint.reference_id)
    if subj is None or ref is None:
        return 0.0  # can't check a relation between something that isn't there

    tolerance = max(constraint.tolerance, 1e-9)

    # "slack" = how far past satisfied this is. >= 0 means the rule
    # holds; negative means it's violated by that many normalized units.
    if constraint.relation == "farther":
        slack = (subj.distance - ref.distance) - constraint.margin
    elif constraint.relation == "closer":
        slack = (ref.distance - subj.distance) - constraint.margin
    elif constraint.relation == "inside":
        # Distance from subject to REFERENCE's own center (not the spell
        # center) -- this is what lets a containing circle sit anywhere.
        gap = math.hypot(subj.nx - ref.nx, subj.ny - ref.ny)
        slack = (ref.radius + constraint.margin) - gap
    else:  # "outside" -- same gap, just the opposite sign of comparison.
        gap = math.hypot(subj.nx - ref.nx, subj.ny - ref.ny)
        slack = gap - (ref.radius + constraint.margin)

    if slack >= 0.0:
        return 1.0  # rule holds, with slack to spare -- full credit
    # Violated, but maybe only a little -- fall off linearly over
    # `tolerance` normalized units, floor at 0.0.
    return max(0.0, 1.0 + slack / tolerance)


def match_spell(spell: SpellDefinition, scene_features: List["SceneFeature"]
                 ) -> SpellMatchResult:
    """
    Tries to fit `scene_features` into `spell`'s slots and checks whether
    every rule (per-slot position, plus every relative constraint) is
    satisfied.
    """
    positioned = compute_positions(scene_features)

    # Bucket candidates by shape up front, so each slot only ever
    # considers features that could possibly fill it (a triangle can
    # never fill a circle's slot).
    by_shape: Dict[str, List[int]] = {}
    for idx, feat in enumerate(positioned):
        by_shape.setdefault(feat.shape, []).append(idx)

    slots = spell.features
    constraints = spell.relative_constraints
    num_terms = len(slots) + len(constraints)  # used only for the informational `score`, not for accept/reject

    used = [False] * len(positioned)   # which scene features are already claimed by a slot
    current: Dict[int, int] = {}       # slot.id -> scene feature index, for the assignment being built

    best: Dict[int, int] = {}
    best_score = -1.0

    def backtrack(slot_pos: int, running_slot_score: float) -> None:
        """Try every way of filling slots[slot_pos:], keeping whichever
        complete assignment scores highest on average. Spells only have a
        handful of slots, so plain backtracking (no fancy solver) is
        cheap enough."""
        nonlocal best, best_score

        if slot_pos == len(slots):
            # Every slot has been decided (filled or left empty) -- now
            # score the relative constraints against this specific
            # assignment and see if it's the best one seen so far.
            constraint_score = 0.0
            if constraints:
                positioned_by_slot = {sid: positioned[idx] for sid, idx in current.items()}
                constraint_score = sum(
                    _relative_constraint_score(c, positioned_by_slot) for c in constraints
                )
            total = running_slot_score + constraint_score
            avg = total / num_terms if num_terms else 0.0
            if avg > best_score:
                best_score = avg
                best = dict(current)
            return

        slot = slots[slot_pos]
        # Try filling this slot with every shape-matching, still-unused
        # candidate that scores above 0.
        for idx in by_shape.get(slot.shape, []):
            if used[idx]:
                continue
            score = _slot_score(slot, positioned[idx])
            if score <= 0.0:
                continue  # doesn't fit this slot well enough to even try
            used[idx] = True
            current[slot.id] = idx
            backtrack(slot_pos + 1, running_slot_score + score)
            del current[slot.id]
            used[idx] = False

        # Also try leaving this slot EMPTY, so a spell missing one piece
        # still produces the best possible partial match (for near-miss
        # feedback) instead of nothing at all.
        backtrack(slot_pos + 1, running_slot_score)

    backtrack(0, 0.0)

    assignment = {slot_id: positioned[idx] for slot_id, idx in best.items()}
    all_filled = len(assignment) == len(slots)
    final_score = max(best_score, 0.0)

    # Acceptance is a straight rule check, not an accuracy threshold.
    # Every filled slot in `best` is already guaranteed to have scored
    # above 0 (the loop above never keeps a 0-or-below candidate), so the
    # only thing left to check is that every relative constraint ALSO
    # scored above 0 under this exact assignment. One weak slot can no
    # longer get rescued by other slots landing dead-center, and one
    # near-perfect slot can no longer get vetoed by an unrelated slot
    # that just happened to average things down.
    constraints_satisfied = True
    if constraints:
        positioned_by_slot = {sid: positioned[idx] for sid, idx in best.items()}
        constraints_satisfied = all(
            _relative_constraint_score(c, positioned_by_slot) > 0.0 for c in constraints
        )
    accepted = all_filled and constraints_satisfied

    return SpellMatchResult(
        name=spell.name if accepted else None,
        score=final_score,   # informational only -- e.g. "closest: 76%" -- not used for `accepted`
        accepted=accepted,
        assignment=assignment,
    )


def match_best_spell(spells: List[SpellDefinition], scene_features: List["SceneFeature"]
                      ) -> Optional[SpellMatchResult]:
    """Tries every spell against the same scene, returns whichever
    ACCEPTED result scored highest -- or None if nothing was accepted."""
    best_result: Optional[SpellMatchResult] = None
    for spell in spells:
        result = match_spell(spell, scene_features)
        if result.accepted and (best_result is None or result.score > best_result.score):
            best_result = result
    return best_result


# -----------------------------------------------------------------------------
# Note on rotation invariance (see module docstring)
# -----------------------------------------------------------------------------
# To match a spell drawn at any rotation, angles would need to be measured
# relative to one designated "anchor" feature instead of true north:
#   angle = (compass_angle(dx, dy) - anchor_bearing) % 360
# for every feature, anchor included (so the anchor always sits at angle 0
# by definition). That needs compute_positions to know which feature is
# the anchor, and SpellFeatureSlot.min_angle/max_angle to mean "relative
# to the anchor" instead of "compass direction". Not done here, since it
# trades away the ability to require a spell be drawn upright, which most
# spells probably want.
#
# RelativeDistanceConstraint (farther/closer/inside/outside) doesn't care
# about compass direction at all, only distance and radius -- so those
# already work fine at any rotation, with or without the above.