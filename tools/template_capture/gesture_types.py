"""
Shared Data Types for the $Q Recognizer Pipeline
==================================================
Every dataclass shared across the pipeline (merge_intersecting_strokes.py,
recognizer.py, spell_matcher.py, template_store.py, ...) lives here, so
there's exactly one definition of each to import instead of every module
declaring its own copy.

NOTE ON THE MODULE NAME: this file is deliberately NOT named `types.py`.
Python's standard library already has a top-level `types` module (used
internally by `functools`, `enum`, `dataclasses`, and -- critically --
`numpy`). A local `types.py` sitting on `sys.path` shadows that stdlib
module for the whole process, which breaks `numpy` the moment it's
imported (it fails while resolving `enum`/`functools`, which themselves
`import types` and expect the *real* one). `gesture_types` avoids the
collision entirely while keeping the same "one shared types module" idea
the refactor was going for.

Stroke, added here, is the refactor's real new piece, and now owns stroke
identity outright: a Point is just (x, y) -- it has no idea which pen-
stroke it belongs to. That's Stroke's job: "the points that make up one
physically continuous pen-stroke" is now represented by literal Python
containment (a Point being an element of a Stroke.points list) instead of
an `int` tag repeated on every single point. Wherever the pipeline used to
work with "a flat List[Point] where consecutive same-stroke_id points are
one drawn stroke", it now works with List[Stroke] directly -- see
merge_intersecting_strokes.py and recognizer.py, both rewritten around
this. A point can only ever be reached "as part of a stroke" (via
`some_stroke.points`), matching how the pipeline actually thinks about
strokes.
"""

import itertools
import numpy as np
from typing import List, Optional, Tuple
from dataclasses import dataclass, field

from config import DEFAULT_MIN_SCORE


@dataclass
class Point:
    """A single (x, y) sample. Carries no stroke identity of its own --
    which stroke a point belongs to is entirely determined by which
    Stroke.points list it lives in."""
    x: float
    y: float


# Monotonic counter backing Stroke.seq -- see Stroke's docstring for why
# this exists instead of a per-Point tag.
_stroke_seq_counter = itertools.count()


@dataclass
class Stroke:
    """
    One physically continuous pen-stroke: everything recorded between a
    single mouse-down and mouse-up (or, for a merged/touch-clustered
    group, the concatenated points of every stroke in that cluster -- see
    merge_intersecting_strokes.merge_intersecting_strokes). This is the
    sole owner of stroke identity in the pipeline now: two points are
    "part of the same stroke" exactly when they're both in the same
    Stroke's `points` list, full stop -- there's no separate id to fall
    out of sync with that.

    `seq` is a monotonically increasing creation-order counter, assigned
    automatically. It exists purely so QRecognizer's incremental
    add_stroke API can re-establish chronological order across strokes
    pulled from different sources (a brand new stroke plus several reused
    Feature.strokes) when recomputing a touched region -- it is bookkeeping
    on the Stroke, not an identity tag smeared across its points.
    """
    points: List[Point]
    seq: int = field(default_factory=lambda: next(_stroke_seq_counter))


@dataclass
class Template:
    """Represents a registered gesture template."""
    name: str
    points: List[Point]
    xs: np.ndarray             # 1D float array of point's x-coordinates (for faster calculations)
    ys: np.ndarray              # same as above but for y-coordinates
    lut: np.ndarray             # 2D int array for fast O(1) candidate queries
    level: int                  # Number of physically-separate stroke units
    aspect_ratio: float = 1.0   # Raw bounding box aspect ratio before uniform scaling
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
class Feature:
    """A distinct, recognized feature (either atomic or composite) on the canvas."""
    cluster_id: int
    level: int
    result: RecognitionResult
    points: List[Point]
    # The physically-separate Stroke(s) this feature was built from --
    # one Stroke for an atomic (Level-1) feature made of a single pen-
    # stroke, several for a multi-stroke atomic unit or a composite built
    # up out of other features' strokes. Optional/defaulted since not
    # every caller needs it; populated by QRecognizer via
    # `_points_to_strokes` (see recognizer.py).
    strokes: List[Stroke] = field(default_factory=list)
    components: List["Feature"] = field(default_factory=list)
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


# Helpers
def stroke_from_points(points: List[Point]) -> Stroke:
    """
    Constructs a Stroke from a list of Points.

    Copies `points` into a new list rather than wrapping the caller's list
    by reference. Callers like test_canvas.py accumulate one mutable
    buffer (e.g. `self.current_stroke`) across the whole drawing session,
    `.clear()`-ing and refilling it for every new stroke -- if Stroke held
    that same list object, every previously-created Stroke would silently
    mutate the next time the buffer gets reused, corrupting whatever
    Feature already captured it. The individual Point objects themselves
    are never mutated in place anywhere in the pipeline (every
    transformation -- resample, scale, translate -- builds new Points), so
    a shallow copy of the list is sufficient to make this safe.
    """
    return Stroke(points=list(points))