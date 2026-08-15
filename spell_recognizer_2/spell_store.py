"""
Spell Definition Persistence
=============================
Mirrors template_store.py's shape but for SpellDefinition records instead
of Template records: each spell lives as its own JSON file inside a shared
spells directory (default: spells/). Unlike templates, there's no
preprocessing/LUT to cache -- a SpellDefinition IS the file's content,
essentially verbatim (see spell_matcher.py's SpellDefinition/
SpellFeatureSlot/RelativeDistanceConstraint for what each field means).

spells/pentagram_seal.json:
{
  "name": "pentagram_seal",
  "min_score": 0.75,
  "features": [
    {"id": 0, "shape": "star_5", "distance": 0.0, "tolerance_dist": 0.1},
    {"id": 1, "shape": "triangle", "tolerance_dist": 0.15,
     "min_angle": 315, "max_angle": 45, "tolerance_angle": 20}
  ],
  "relative_constraints": [
    {"subject_id": 1, "reference_id": 0, "relation": "farther",
     "margin": 0.05, "tolerance": 0.1}
  ]
}

Note feature id 1 ("triangle") above has no "distance" key at all -- it's
purely relationally positioned (north of center, AND farther out than the
star) via the angle sector plus the relative_constraints entry, rather
than needing a fixed absolute distance guessed up front. See
spell_matcher.SpellFeatureSlot/RelativeDistanceConstraint's docstrings for
the full semantics (including the "inside" relation, for features that
must sit inside a containing circle feature).

Layout of this file:
  1. (De)serialization helpers -- SpellFeatureSlot <-> dict,
                                    RelativeDistanceConstraint <-> dict,
                                    name -> path
  2. File I/O                  -- save/load individual spell records
  3. Convenience               -- load every spell in a directory, ready
                                   to hand to spell_matcher.match_best_spell
"""

import glob
import json
import os
import re
from typing import List, Optional

from config import DEFAULT_SPELLS_DIR, DEFAULT_SPELL_MIN_SCORE, DEFAULT_SPELL_DIST_TOLERANCE
from spell_matcher import SpellDefinition, SpellFeatureSlot, RelativeDistanceConstraint


# =============================================================================
# 1. (De)serialization helpers
# =============================================================================

def slugify(name: str) -> str:
    """Turns a spell name into a filesystem-safe file stem (same rule as
    template_store.slugify, kept independent to avoid a needless coupling
    between the two persistence modules)."""
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip().lower())
    return slug or "spell"


def _spell_path(name: str, spells_dir: str) -> str:
    return os.path.join(spells_dir, f"{slugify(name)}.json")


def _slot_to_dict(slot: SpellFeatureSlot) -> dict:
    d = {
        "id": slot.id,
        "shape": slot.shape,
    }
    # `distance` is optional on SpellFeatureSlot (see spell_matcher.py) --
    # only write it (and its tolerance, which is meaningless without it)
    # when the slot actually has a fixed expected distance, so purely
    # relationally-positioned slots (angle-only, or driven entirely by a
    # RelativeDistanceConstraint) round-trip back to distance=None instead
    # of picking up an accidental 0.0.
    if slot.distance is not None:
        d["distance"] = slot.distance
        d["tolerance_dist"] = slot.tolerance_dist
    # Only write angle fields when the slot actually uses them, so
    # position-only spell files stay uncluttered (and so
    # SpellFeatureSlot.angle_constrained() round-trips correctly: a
    # missing key decodes back to None, not an accidental 0/0 sector).
    if slot.angle_constrained():
        d["min_angle"] = slot.min_angle
        d["max_angle"] = slot.max_angle
        d["tolerance_angle"] = slot.tolerance_angle
    return d


def _dict_to_slot(d: dict) -> SpellFeatureSlot:
    raw_distance = d.get("distance")
    return SpellFeatureSlot(
        id=int(d["id"]),
        shape=d["shape"],
        distance=float(raw_distance) if raw_distance is not None else None,
        tolerance_dist=float(d.get("tolerance_dist", DEFAULT_SPELL_DIST_TOLERANCE)),
        min_angle=d.get("min_angle"),
        max_angle=d.get("max_angle"),
        tolerance_angle=float(d.get("tolerance_angle", 20.0)),
    )


def _constraint_to_dict(constraint: RelativeDistanceConstraint) -> dict:
    return {
        "subject_id": constraint.subject_id,
        "reference_id": constraint.reference_id,
        "relation": constraint.relation,
        "margin": constraint.margin,
        "tolerance": constraint.tolerance,
    }


def _dict_to_constraint(d: dict) -> RelativeDistanceConstraint:
    return RelativeDistanceConstraint(
        subject_id=int(d["subject_id"]),
        reference_id=int(d["reference_id"]),
        relation=d["relation"],
        margin=float(d.get("margin", 0.0)),
        tolerance=float(d.get("tolerance", DEFAULT_SPELL_DIST_TOLERANCE)),
    )


# =============================================================================
# 2. File I/O
# =============================================================================

def save_spell(spell: SpellDefinition, spells_dir: str = DEFAULT_SPELLS_DIR) -> str:
    """Writes one spell out as its own JSON file, creating spells_dir if
    needed. Saving under a name that already exists overwrites its file,
    exactly like template_store.save_template_record."""
    os.makedirs(spells_dir, exist_ok=True)
    record = {
        "name": spell.name,
        "min_score": spell.min_score,
        "features": [_slot_to_dict(s) for s in spell.features],
    }
    # Only written when the spell actually has any, so plain
    # absolute-position-only spells (no relational checks) keep producing
    # exactly the same file shape they always have -- this key is purely
    # additive.
    if spell.relative_constraints:
        record["relative_constraints"] = [
            _constraint_to_dict(c) for c in spell.relative_constraints
        ]
    path = _spell_path(spell.name, spells_dir)
    with open(path, "w") as f:
        json.dump(record, f, indent=2)
    return path


def load_spell_records(spells_dir: str = DEFAULT_SPELLS_DIR) -> List[dict]:
    """Reads every *.json file in `spells_dir` and returns them as raw
    dicts. Returns [] if the directory doesn't exist yet."""
    if not os.path.isdir(spells_dir):
        return []
    records = []
    for path in sorted(glob.glob(os.path.join(spells_dir, "*.json"))):
        with open(path, "r") as f:
            records.append(json.load(f))
    return records


# =============================================================================
# 3. Convenience
# =============================================================================

def load_spells(spells_dir: str = DEFAULT_SPELLS_DIR) -> List[SpellDefinition]:
    """
    Loads every spell JSON file in `spells_dir` into a ready-to-use
    List[SpellDefinition] -- the spell-side equivalent of
    template_store.load_templates_into, except there's no QRecognizer to
    wire into and no cache, so this just returns the list directly, ready
    to hand to spell_matcher.match_best_spell(spells, scene_features).

    `relative_constraints` defaults to [] for any record written before
    this field existed (or that simply doesn't need any relational
    checks), so old spell files keep loading unchanged.
    """
    spells = []
    for r in load_spell_records(spells_dir):
        spells.append(SpellDefinition(
            name=r["name"],
            features=[_dict_to_slot(d) for d in r["features"]],
            min_score=float(r.get("min_score", DEFAULT_SPELL_MIN_SCORE)),
            relative_constraints=[
                _dict_to_constraint(d) for d in r.get("relative_constraints", [])
            ],
        ))
    return spells