"""
Central Configuration for the $Q Recognizer Pipeline
======================================================
This module has ONE job: hold every constant that someone might reasonably
want to tweak while tuning the recognizer, in one place, with a comment
explaining what turning it up/down does. Nothing in here contains logic --
it's pure data so that experimenting with the model is a "change a number
here, re-run" workflow instead of a "go hunting through 5 files" workflow.

The constants are grouped by the part of the pipeline they affect:
  1. Stroke clustering       (merge_intersecting_strokes.py)
  2. Recognizer core         (recognizer.py -- QRecognizer.__init__)
  3. Level composition       (recognizer.py -- recognize_scene)
  4. Cloud-distance scoring  (recognizer.py -- _cloud_distance / _reverse_cloud_distance)
  5. Template capture        (template_capture.py)
  6. Canvas / UI             (test_canvas.py, template_capture.py)
  7. Template storage paths  (template_store.py)
  8. Template cache          (template_store.py -- precomputed LUT/points cache)

Every other module in this project should import its defaults from here
instead of hard-coding literals, so this file is the single source of
truth for "what are the current tuning parameters?".
"""

from typing import Dict


# =============================================================================
# 1. Stroke clustering (merge_intersecting_strokes.py)
# =============================================================================

# How close (in px) two strokes' points need to get before they're considered
# "physically touching" and merged into a single stroke unit. This is a pure
# proximity/contact test -- it has nothing to do with gesture "Level".
# Smaller -> strokes must nearly overlap to merge. Larger -> more forgiving
# of sloppy/gappy drawing, but risks merging strokes that were meant to stay
# separate (e.g. the stem and dot of "!").
DEFAULT_TOUCH_THRESHOLD: float = 8.0

# How close (px) a stroke's ENDPOINT (its very first or very last recorded
# point -- i.e. where the pen went down or came up) needs to get to ANY
# point on another stroke before the two are considered "touching" for
# merge purposes. This is deliberately looser than DEFAULT_TOUCH_THRESHOLD.
# When someone draws two strokes meant to meet at a corner/tip (e.g. the
# two strokes of a hand-drawn "V" or "L"), the real pixel gap between where
# stroke A lifts and stroke B touches down is routinely 10-20px -- ordinary
# mouse/touch imprecision at a stroke boundary, not sloppy drawing. Only
# the two endpoints of each stroke get this looser tolerance; the interior
# of a stroke still has to satisfy the tighter DEFAULT_TOUCH_THRESHOLD, so
# two strokes that simply run close together along their middle (e.g. the
# two separate bars of a hand-drawn "II") don't get wrongly fused just
# because they're visually near one another.
DEFAULT_ENDPOINT_TOUCH_THRESHOLD: float = 20.0

# A stroke with more than this many raw points gets THINNED before the
# expensive per-segment touch test runs (see
# merge_intersecting_strokes._decimate_points_for_touch), since consecutive
# mouse-move points captured only a pixel or two apart carry no extra
# geometric information for a proximity test running at these thresholds --
# they just multiply the O(len(A) * len(B)) cost of the segment-pair loop
# in `_strokes_touch` for no benefit. Strokes at or below this count are
# left completely untouched: short/template-sized strokes get negligible
# speedup from thinning, so there's no reason to risk changing their
# behavior at all.
DEFAULT_TOUCH_DECIMATION_MIN_POINTS: int = 24

# Divisor applied to a call's `proximity_threshold` to get the minimum
# spacing (px) enforced between consecutive points kept during touch-test
# decimation: spacing = proximity_threshold / this. Higher divisor -> finer
# spacing (closer to the original points -- safer, but less speedup).
# Lower divisor -> coarser spacing (more speedup, but a larger worst-case
# deviation between the thinned polyline and the original curve). 3.0 keeps
# that deviation comfortably under the touch threshold itself for any but
# pathologically jagged input, which is what keeps this an optimization
# rather than a behavior change in practice.
DEFAULT_TOUCH_DECIMATION_SPACING_DIVISOR: float = 3.0

# Once two strokes' (post-decimation) segment counts multiply out to more
# than this many candidate pairs, `_strokes_touch` switches from the
# per-segment-AABB-prefiltered double loop to a grid-indexed touch test
# (see merge_intersecting_strokes._strokes_touch_grid, built on
# spatial_index.SpatialGrid -- the same structure already used one level
# up for whole-stroke clustering). The grid turns the search from roughly
# O(len(A) * len(B)) into roughly O(len(A) + len(B)), but building and
# querying it costs more per-call than a tight double loop for small
# inputs, so below this many candidate pairs the simple loop stays faster
# and is used instead. 4000 sits just above the measured crossover point
# (empirically, the grid starts winning around 60-90 segments per side --
# very long or slowly-drawn strokes, well beyond ordinary short gestures).
DEFAULT_TOUCH_GRID_MIN_SEGMENT_PRODUCT: int = 4000


# =============================================================================
# 2. Recognizer core (recognizer.py -- QRecognizer.__init__)
# =============================================================================

# Number of equidistant points every stroke (candidate or template) is
# resampled down/up to before scoring. Higher -> captures finer detail
# (small loops, sharp corners) but costs more compute per comparison.
NUM_RESAMPLE_POINTS: int = 64

# Side length (px) of the square bounding box every gesture is uniformly
# scaled into before comparison, so templates and candidates are compared at
# the same size regardless of how big/small they were physically drawn.
FRAME_SIZE: float = 250.0

# Resolution of the 2D Look-Up Table used for O(1) nearest-template-point
# queries during scoring. Higher -> more precise candidate->template
# matching, at the cost of more memory/time to build each template's LUT.
LUT_SIZE: int = 32

# Default per-template acceptance threshold (see Template.min_score /
# RecognitionResult.accepted). A match must score >= this to count as a
# real recognition. Individual templates can override this value; see
# template_store.py and DEFAULT_CAPTURE_MIN_SCORE below.
DEFAULT_MIN_SCORE: float = 0.5

# Weight of the Gaussian aspect-ratio-deviation penalty (FIX 1) applied on
# top of the raw cloud-distance score. Higher -> candidates whose bounding
# box shape (width/height angle) diverges from the template's are penalized
# more aggressively; 0.0 would disable the aspect-ratio penalty entirely.
ASPECT_RATIO_WEIGHT: float = 0.15


# =============================================================================
# 3. Level composition (recognizer.py -- QRecognizer.recognize_scene)
# =============================================================================

# For each target Level > 1, how far apart (px) two lower-level SceneFeatures are
# allowed to be and still get bundled together as candidates for that
# higher-level composite gesture. Keyed by target level. A level with no
# entry here falls back to `touch_threshold` at call time.
DEFAULT_LEVEL_MERGE_THRESHOLDS: Dict[int, float] = {
    2: 60.0,
}


# =============================================================================
# 4. Cloud-distance scoring (recognizer.py -- _cloud_distance / _reverse_cloud_distance)
# =============================================================================

# Distance (px) beyond which the exponential "unmatched SceneFeature" penalty
# kicks in, in both the forward (candidate->template) and reverse
# (template->candidate) cloud-distance passes. Points closer than this are
# scored linearly; points farther than this get an extra super-linear
# penalty, since they likely represent a genuinely missing/extra stroke
# rather than ordinary drawing noise.
CLOUD_DISTANCE_PENALTY_THRESHOLD: float = 25.0

# Exponent applied to the portion of a distance that exceeds
# CLOUD_DISTANCE_PENALTY_THRESHOLD. Higher -> missing/extra strokes are
# punished more severely relative to small, everywhere-present noise.
CLOUD_DISTANCE_EXPONENT: float = 2.0

# Blend weight between the mean adjusted distance and the max adjusted
# distance (a Hausdorff-style component) when combining per-point distances
# into a single cloud distance. 0.0 -> pure average (ignores worst-case
# outliers). 1.0 -> pure worst-case (ignores everything but the single
# worst point).
CLOUD_DISTANCE_MAX_WEIGHT: float = 0.35


# =============================================================================
# 5. Template capture (template_capture.py)
# =============================================================================

# Acceptance threshold offered as the default answer when capturing a new
# template interactively (template_capture.py prompts for this and falls
# back to this value on an empty/invalid entry). Kept separate from
# DEFAULT_MIN_SCORE so the "what a freshly captured template gets by
# default" knob can be tuned independently of the recognizer's own
# built-in fallback.
DEFAULT_CAPTURE_MIN_SCORE: float = 0.6


# =============================================================================
# 6. Canvas / UI (test_canvas.py, template_capture.py)
# =============================================================================

CANVAS_WIDTH: int = 800
CANVAS_HEIGHT: int = 800

# Thickness (px) of the brush stroke drawn on-screen. Purely cosmetic --
# does not affect the raw (x, y, stroke_id) points recorded for recognition.
BRUSH_THICKNESS: int = 4

# Cycle of BGR colors used to draw bounding boxes/labels around each
# recognized SceneFeature in test_canvas.py, one color per SceneFeature index
# (wrapping around via modulo once there are more SceneFeatures than colors).
SceneFeature_COLORS = [
    (0, 255, 0),
    (0, 128, 255),
    (255, 200, 0),
    (255, 0, 255),
    (0, 255, 255),
]

# Parameters for the synthetic demo templates built in test_canvas.py's
# build_demo_recognizer(). Tweaking these changes the shape/size of the
# built-in line/dot templates used before any captured templates load.
DEMO_LINE_LENGTH: float = 300.0
DEMO_LINE_RESAMPLE_N: int = 40
DEMO_DOT_RADIUS: float = 10.0
DEMO_DOT_RESAMPLE_N: int = 12

# Size (px) of one cell in the spatial-index grid overlay drawn on the
# canvas in test_canvas.py (toggle with 'g') -- a debug visualization of how
# spatial_index.SpatialGrid buckets the canvas, so you can *see* the grid
# the "only compare nearby strokes" logic uses. Change this ONE number to
# make the drawn grid coarser/finer: the number of cells drawn is derived
# from it automatically as canvas_size / SPATIAL_GRID_VISUAL_SIZE, e.g. a
# 500px-wide canvas draws 10 cells across at 50.0, and a 1000px-wide canvas
# draws 20. This does NOT change the actual cell size spatial_index.py uses
# internally for clustering (that one is threshold-derived at call time --
# see SpatialGrid.cluster_spatially) -- it's a visual aid only.
SPATIAL_GRID_VISUAL_SIZE: float = 50.0


# =============================================================================
# 7. Template storage paths (template_store.py)
# =============================================================================

# Directory holding one JSON file per saved template (see template_store.py
# module docstring for the file format and rationale).
DEFAULT_TEMPLATES_DIR: str = "templates"

# Directory holding the human-reference PNG snapshot saved alongside each
# captured template. Never read back in for recognition.
DEFAULT_TEMPLATE_IMAGES_DIR: str = "template_images"


# =============================================================================
# 8. Template cache (template_store.py -- OPTIMIZATION FIX #4)
# =============================================================================
# Loading a template from its raw JSON means re-running preprocessing and
# rebuilding its LUT every time the app starts (QRecognizer.add_template).
# That's cheap for one template, but linear in the size of the whole
# library. The cache below stores each template's *already-preprocessed*
# points + LUT next to a fingerprint of (a) that template's raw points and
# (b) the QRecognizer settings that affect preprocessing (num_resample_points,
# frame_size, lut_size, touch_threshold). On load, if both fingerprints
# still match, the cached copy is registered directly (QRecognizer.
# add_precomputed_template) instead of recomputing anything. Editing a
# template's points (re-capturing it) or changing the recognizer's tuning
# parameters changes the corresponding fingerprint, which naturally
# invalidates just that cache entry -- there's no separate "did the cache
# go stale?" bookkeeping to keep in sync by hand.

# Directory holding one cache file per template (mirrors the
# templates/template_images split above). Kept separate from
# DEFAULT_TEMPLATES_DIR so cache files never show up in the
# `glob(templates_dir/*.json)` scan that loads real template records.
DEFAULT_TEMPLATE_CACHE_DIR: str = "template_cache"

# Master on/off switch for the template cache. True is the sensible default
# (it's a pure speed optimization with no effect on recognition results);
# set to False if you ever want to force everything through the "recompute
# from raw points" path, e.g. while debugging preprocessing itself.
DEFAULT_USE_TEMPLATE_CACHE: bool = True


# =============================================================================
# 9. Spell matching (spell_matcher.py, spell_store.py)
# =============================================================================
# A "spell" is a relational layout of already-recognized SceneFeatures (see
# spell_matcher.py's module docstring) -- position/distance-from-center
# information that QRecognizer deliberately discards while classifying
# individual shapes. These constants are the spell-matching analogues of
# DEFAULT_MIN_SCORE / DEFAULT_LEVEL_MERGE_THRESHOLDS above, just one layer
# up the stack.

# Directory holding one JSON file per saved spell (see spell_store.py's
# module docstring for the file format).
DEFAULT_SPELLS_DIR: str = "spells"

# Default per-slot allowed deviation between a spell SceneFeature's expected
# normalized distance-from-center and what was actually drawn. Distance is
# normalized to the whole drawing's bounding-box diagonal, so this
# tolerance is scale-invariant: 0.1 means "10% of the drawing's own size in
# either direction", regardless of how big or small the spell was drawn.
# Individual SpellSceneFeatureSlots can override this value.
DEFAULT_SPELL_DIST_TOLERANCE: float = 0.10

# Default soft falloff margin (degrees) used when a SceneFeature lands just
# outside its slot's required angle sector -- see spell_matcher._slot_score.
# Larger -> near-miss angles still score close to full credit; smaller ->
# angle sectors behave closer to a hard cutoff.
DEFAULT_SPELL_ANGLE_TOLERANCE: float = 20.0

# Default per-spell acceptance threshold (see SpellMatchResult.accepted). A
# spell's average per-slot score must be >= this, AND every slot must be
# filled, to count as cast. Individual SpellDefinitions can override this.
DEFAULT_SPELL_MIN_SCORE: float = 0.75

# Normalized-distance-from-center below which a SceneFeature's angle is treated
# as meaningless noise and skipped, even if its slot defines an angle
# sector -- a SceneFeature sitting essentially AT the spell's center doesn't
# have a meaningful "north/south/east/west" of it to check.
SPELL_CENTER_EPSILON: float = 0.05