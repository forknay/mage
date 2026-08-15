"""
Spell Definition Persistence
=============================
Mirrors template_store.py's shape but for SpellDefinition records instead
of Template records: each spell lives as its own JSON file inside a shared
spells directory (default: spells/). Unlike templates, there's no
preprocessing/LUT to cache -- a SpellDefinition IS the file's content,
essentially verbatim (see spell_matcher.py's SpellDefinition/
SpellSceneFeatureSlot for what each field means).

spells/pentagram_seal.json:
{
  "name": "pentagram_seal",
  "min_score": 0.75,
  "SceneFeatures": [
    {"id": 0, "shape": "star_5", "distance": 0.0, "tolerance_dist": 0.1},
    {"id": 1, "shape": "triangle", "distance": 0.75, "tolerance_dist": 0.15,
     "min_angle": 315, "max_angle": 45, "tolerance_angle": 20}
  ]
}

Layout of this file:
  1. (De)serialization helpers -- SpellSceneFeatureSlot <-> dict, name -> path
  2. File I/O                  -- save/load individual spell records
  3. Convenience               -- load every spell in a directory, ready
                                   to hand to spell_matcher.match_best_spell
"""

import glob
import json
import os
import re
from typing import List, Optional

from config import DEFAULT_SPELLS_DIR, DEFAULT_SPELL_MIN_SCORE
from spell_matcher import SpellDefinition, SpellSceneFeatureSlot


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


def _slot_to_dict(slot: SpellSceneFeatureSlot) -> dict:
    d = {
        "id": slot.id,
        "shape": slot.shape,
        "distance": slot.distance,
        "tolerance_dist": slot.tolerance_dist,
    }
    # Only write angle fields when the slot actually uses them, so
    # position-only spell files stay uncluttered (and so
    # SpellSceneFeatureSlot.angle_constrained() round-trips correctly: a
    # missing key decodes back to None, not an accidental 0/0 sector).
    if slot.angle_constrained():
        d["min_angle"] = slot.min_angle
        d["max_angle"] = slot.max_angle
        d["tolerance_angle"] = slot.tolerance_angle
    return d


def _dict_to_slot(d: dict) -> SpellSceneFeatureSlot:
    return SpellSceneFeatureSlot(
        id=int(d["id"]),
        shape=d["shape"],
        distance=float(d["distance"]),
        tolerance_dist=float(d.get("tolerance_dist", 0.1)),
        min_angle=d.get("min_angle"),
        max_angle=d.get("max_angle"),
        tolerance_angle=float(d.get("tolerance_angle", 20.0)),
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
        "SceneFeatures": [_slot_to_dict(s) for s in spell.SceneFeatures],
    }
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
    to hand to spell_matcher.match_best_spell(spells, scene_SceneFeatures).
    """
    spells = []
    for r in load_spell_records(spells_dir):
        spells.append(SpellDefinition(
            name=r["name"],
            SceneFeatures=[_dict_to_slot(d) for d in r["SceneFeatures"]],
            min_score=float(r.get("min_score", DEFAULT_SPELL_MIN_SCORE)),
        ))
    return spells