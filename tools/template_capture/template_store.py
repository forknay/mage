"""
Template Persistence for the $Q Recognizer
===========================================
Each template lives as its OWN JSON file (RAW, unprocessed strokes -- not
the normalized point-cloud and not the LUT) inside a shared templates
directory (default: templates/). Every record also carries an optional
`image_path` pointing at a PNG snapshot of the canvas at capture time.

templates/circle.json:
{
  "name": "circle",
  "level": 1,
  "min_score": 0.6,
  "image_path": "template_images/circle.png",
  "strokes": [
    {"points": [{"x": 12.3, "y": 45.6}, {"x": 12.8, "y": 46.1}, ...]}
  ]
}

Strokes are stored as a list of point-lists (one entry per physically
separate pen-stroke) rather than a flat point list tagged with a
stroke_id -- Point carries no stroke identity of its own (see
gesture_types.py), so "which points belong together" is expressed by JSON
nesting instead of a repeated `stroke_id` field on every point.

Layout of this file:
  1. (De)serialization helpers -- Point/Stroke <-> dict, name -> file path
  2. File I/O                  -- load/save individual template records
  3. Template cache            -- OPTIMIZATION FIX #4, see config.py's
                                   "Template cache" section for the design
  4. Wiring records into a live QRecognizer
"""

import glob
import hashlib
import json
import os
import re
from typing import TYPE_CHECKING, Dict, List, Optional

from gesture_types import Point, Stroke
from config import (
    DEFAULT_TEMPLATES_DIR,
    DEFAULT_TEMPLATE_IMAGES_DIR,
    DEFAULT_MIN_SCORE,
    DEFAULT_TEMPLATE_CACHE_DIR,
    DEFAULT_USE_TEMPLATE_CACHE,
)

if TYPE_CHECKING:
    from recognizer import QRecognizer


# =============================================================================
# 1. (De)serialization helpers
# =============================================================================

def _point_to_dict(p: Point) -> dict:
    return {"x": p.x, "y": p.y}


def _dict_to_point(d: dict) -> Point:
    return Point(float(d["x"]), float(d["y"]))


def _stroke_to_dict(s: Stroke) -> dict:
    return {"points": [_point_to_dict(p) for p in s.points]}


def _dict_to_stroke(d: dict) -> Stroke:
    return Stroke(points=[_dict_to_point(p) for p in d["points"]])


def _legacy_points_to_strokes(points: List[dict]) -> List[Stroke]:
    """Convert legacy point-based template records into stroke objects."""
    strokes_by_id: Dict[int, List[Point]] = {}
    stroke_order: List[int] = []
    for point in points:
        stroke_id = int(point.get("stroke_id", 0))
        if stroke_id not in strokes_by_id:
            strokes_by_id[stroke_id] = []
            stroke_order.append(stroke_id)
        strokes_by_id[stroke_id].append(_dict_to_point(point))

    return [Stroke(points=strokes_by_id[stroke_id]) for stroke_id in stroke_order]


def _record_to_strokes(record: dict) -> List[Stroke]:
    if "strokes" in record:
        return [_dict_to_stroke(d) for d in record["strokes"]]
    if "points" in record:
        return _legacy_points_to_strokes(record["points"])
    raise KeyError("Template record must contain either 'strokes' or 'points'.")


def slugify(name: str) -> str:
    """Turns a template name into a filesystem-safe file stem."""
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip().lower())
    return slug or "template"


def _template_path(name: str, templates_dir: str) -> str:
    return os.path.join(templates_dir, f"{slugify(name)}.json")


# =============================================================================
# 2. File I/O
# =============================================================================

def load_template_records(templates_dir: str = DEFAULT_TEMPLATES_DIR) -> List[dict]:
    """
    Reads every *.json file in `templates_dir` and returns them as a list of
    records. Returns [] if the directory doesn't exist yet (nothing captured).
    """
    if not os.path.isdir(templates_dir):
        return []

    records = []
    for path in sorted(glob.glob(os.path.join(templates_dir, "*.json"))):
        with open(path, "r") as f:
            records.append(json.load(f))
    return records


def save_template_record(record: dict, templates_dir: str = DEFAULT_TEMPLATES_DIR) -> str:
    """Writes a single template record to its own JSON file. Returns the path written."""
    os.makedirs(templates_dir, exist_ok=True)
    path = _template_path(record["name"], templates_dir)
    with open(path, "w") as f:
        json.dump(record, f, indent=2)
    return path


def append_template(
    name: str,
    level: int,
    strokes: List[Stroke],
    image_path: Optional[str] = None,
    min_score: Optional[float] = None,
    templates_dir: str = DEFAULT_TEMPLATES_DIR,
) -> str:
    """
    Writes one template out as its own JSON file inside `templates_dir`
    (creating the directory if needed). Since the filename is derived from
    the template name, re-capturing a template under the same name naturally
    overwrites its file rather than piling up duplicates.

    `min_score`, if given, is the per-template acceptance threshold (see
    template_store.py's module docstring); if omitted, it isn't written to
    the record at all, and `apply_records` will fall back to
    config.DEFAULT_MIN_SCORE at load time.
    """
    record = {
        "name": name,
        "level": level,
        "image_path": image_path,
        "strokes": [_stroke_to_dict(s) for s in strokes],
    }
    if min_score is not None:
        record["min_score"] = min_score
    return save_template_record(record, templates_dir)


# =============================================================================
# 3. Template cache (OPTIMIZATION FIX #4)
# =============================================================================
# See config.py's "Template cache" section for the design rationale. In
# short: each cache entry stores a template's already-preprocessed points +
# LUT, tagged with two fingerprints (of the raw strokes+level, and of the
# QRecognizer settings that affect preprocessing). A load only reuses a
# cache entry if BOTH fingerprints still match; otherwise it's treated as a
# miss and the template is recomputed (and the cache rewritten) normally.
# Correctness therefore never depends on remembering to invalidate anything
# by hand -- a stale entry simply stops matching.

def _stable_hash(payload: dict) -> str:
    """
    Deterministic hash of a JSON-serializable dict. `sort_keys=True` makes
    the encoding independent of dict insertion order, so equal content
    always hashes the same regardless of how it was built.
    """
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _template_strokes_signature(strokes: List[Stroke], level: int) -> str:
    """
    Fingerprint of a template's raw (unprocessed) strokes + level -- the
    cache-key half that changes whenever the template itself is edited or
    re-captured under the same name.
    """
    return _stable_hash({"level": level, "strokes": [_stroke_to_dict(s) for s in strokes]})


def _recognizer_signature(rec: "QRecognizer") -> str:
    """
    Fingerprint of the QRecognizer settings that affect preprocessing/LUT
    output -- the cache-key half that changes whenever
    num_resample_points/frame_size/lut_size/touch_threshold are retuned,
    automatically invalidating every cached template at once (rather than
    silently handing back preprocessing done under different settings).
    """
    return _stable_hash({
        "n": rec.n,
        "frame_size": rec.frame_size,
        "lut_size": rec.lut_size,
        "touch_threshold": rec.touch_threshold,
    })


def _cache_path(name: str, cache_dir: str) -> str:
    return os.path.join(cache_dir, f"{slugify(name)}.json")


def _load_cache_entry(name: str, cache_dir: str, strokes_sig: str, config_sig: str) -> Optional[dict]:
    """
    Returns the cached {points, lut, level, aspect_ratio} for `name` if a
    cache file exists AND both its stored fingerprints still match the ones
    passed in, else None. Any read/parse problem is also treated as a miss
    rather than an error -- the cache is a pure speed optimization, so the
    worst case of anything going wrong here is just "recompute it".
    """
    path = _cache_path(name, cache_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r") as f:
            entry = json.load(f)
        if entry.get("strokes_sig") != strokes_sig or entry.get("config_sig") != config_sig:
            return None  # Strokes were edited or QRecognizer settings changed -- stale, recompute.
        return {
            "points": [_dict_to_point(d) for d in entry["points"]],
            "lut": entry["lut"],
            "level": entry["level"],
            "aspect_ratio": entry["aspect_ratio"],
        }
    except (OSError, ValueError, KeyError):
        return None


def _write_cache_entry(name: str, cache_dir: str, strokes_sig: str, config_sig: str, template) -> None:
    """
    Writes `template`'s already-preprocessed points + LUT out to the cache,
    tagged with the two fingerprints that must both still match for a
    future load to reuse it (see `_load_cache_entry`).

    `template` is the `recognizer.Template` instance `QRecognizer.
    add_template` just appended -- accessed only via `.points`/`.xs`/`.ys`/
    `.lut`/`.level`/`.aspect_ratio` (duck-typed rather than imported, so
    this module keeps its existing TYPE_CHECKING-only dependency on
    recognizer.py instead of gaining a real one). `template.points` here is
    already the flat, post-preprocessing point cloud -- preprocessing
    resamples strokes down into one continuous run, so there's no stroke
    structure left to preserve at this stage.
    """
    try:
        os.makedirs(cache_dir, exist_ok=True)
        lut = template.lut.tolist() if hasattr(template.lut, "tolist") else template.lut
        entry = {
            "strokes_sig": strokes_sig,
            "config_sig": config_sig,
            "level": template.level,
            "aspect_ratio": template.aspect_ratio,
            "points": [_point_to_dict(p) for p in template.points],
            "lut": lut,
        }
        with open(_cache_path(name, cache_dir), "w") as f:
            json.dump(entry, f)
    except OSError:
        pass  # Cache is a pure speed optimization -- a failed write should never break template loading.


# =============================================================================
# 4. Wiring records into a live QRecognizer
# =============================================================================

def apply_records(rec: "QRecognizer", records: List[dict],
                   cache_dir: Optional[str] = None) -> None:
    """
    Registers every record in `records` onto an existing QRecognizer
    instance.

    If `cache_dir` is given (OPTIMIZATION FIX #4), each record first checks
    the template cache for an entry whose fingerprints both still match --
    see the "Template cache" section above -- and if found, registers it
    via the fast `add_precomputed_template` path instead of recomputing
    preprocessing + the LUT from scratch. A cache miss (first load, edited
    strokes, or changed QRecognizer settings) falls back to the normal
    `add_template` path and writes a fresh cache entry for next time.
    Passing `cache_dir=None` (the default) skips the cache entirely and
    always does a full recompute, matching the original behavior exactly.
    """
    config_sig = _recognizer_signature(rec) if cache_dir else None

    for r in records:
        level = r["level"]
        min_score = r.get("min_score", DEFAULT_MIN_SCORE)
        strokes = _record_to_strokes(r)

        if cache_dir:
            strokes_sig = _template_strokes_signature(strokes, level)
            cached = _load_cache_entry(r["name"], cache_dir, strokes_sig, config_sig)
            if cached is not None:
                rec.add_precomputed_template(
                    r["name"], cached["points"], cached["lut"],
                    cached["level"], cached["aspect_ratio"], min_score,
                )
                continue

        rec.add_template(r["name"], strokes, level=level, min_score=min_score)

        if cache_dir:
            _write_cache_entry(r["name"], cache_dir, strokes_sig, config_sig, rec.templates[-1])


def load_templates_into(rec: "QRecognizer", templates_dir: str = DEFAULT_TEMPLATES_DIR,
                         cache_dir: Optional[str] = DEFAULT_TEMPLATE_CACHE_DIR,
                         use_cache: bool = DEFAULT_USE_TEMPLATE_CACHE) -> int:
    """
    Loads and registers every template JSON file found in `templates_dir`
    onto `rec` -- this is the "import all these JSON files on startup" entry
    point. Returns how many were loaded.

    Pass `use_cache=False` (or `cache_dir=None`) to force every template
    through the full recompute path regardless of the config.py default --
    e.g. while debugging preprocessing itself, where you want to be sure
    you're looking at freshly-derived output rather than a cached copy.
    """
    records = load_template_records(templates_dir)
    apply_records(rec, records, cache_dir=cache_dir if use_cache else None)
    return len(records)