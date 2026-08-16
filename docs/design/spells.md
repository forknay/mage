# Spells — shapes, layouts, balance

How a drawn glyph becomes a spell, what the data files mean, and the
balance numbers the fight is tuned to.

> **This describes freeform recognition, not the lattice.** The shipped
> input model is unconstrained drawing classified by a $Q point-cloud
> recognizer — [ADR 0001](../adr/0001-lattice-vs-freeform.md) chose the
> opposite and has been overtaken by the implementation. Nothing about
> edges, signatures, edit distance or `find_pattern.js` applies any more.

---

## 1. The pipeline

| Step | Where | What happens |
|---|---|---|
| Draw | [`spell_caster.gd`](../../mage-godot/scenes/player/spell_caster.gd) | Hold `anchor`, hold `draw`; the crosshair is the pen. One hold = one stroke, several strokes per glyph |
| Record | [`glyph_plane.gd`](../../mage-godot/scripts/glyph/glyph_plane.gd), [`glyph_canvas.gd`](../../mage-godot/scripts/glyph/glyph_canvas.gd) | The pen ray is intersected with the canvas plane and stored as 2D points in an 800×800 space, thinned to 4px spacing |
| Recognise | `GodotSpellEngine` → `qrec::QRecognizer` | Each **finished** stroke is fed to the C++ engine, which re-recognises the region that stroke touched |
| Compose | same | Recognised shapes that sit close together are bundled and re-recognised as higher-level shapes |
| Match | `qrec::SpellBook` → `match_best_spell` | The whole set of recognised shapes is checked against every spell definition |
| Show | [`recognition_readout.gd`](../../mage-godot/scenes/player/recognition_readout.gd) | Names each recognised shape on screen while testing |

Two vocabularies, and they are not interchangeable:

- A **template** is one shape the recognizer knows — `star_5`, `plus`. It is
  matched by geometry alone, with **position, scale and location thrown
  away** (but *not* rotation: $Q here is orientation-sensitive, so an upside
  down triangle is a different shape).
- A **feature** is one template that has been found on the canvas, with a
  score and a place. A canvas holds several at once.
- A **spell** is a *layout* of features — exactly the information the
  recognizer discarded: which shapes, at what distances and bearings from
  the drawing's centre, and how they sit relative to each other.

That split is the whole design. "Is this a triangle" must work anywhere on
the canvas; "is this the warding pentagram" is a question about where the
triangles are.

### Recognition is incremental

`add_stroke` does not re-read the whole canvas. It finds the spatial groups
the new stroke could touch, recomputes only those, and reuses cached results
for everything else. Consequences worth knowing:

- Feedback arrives **per stroke**, not per cast. A half-drawn glyph already
  has features, which is what the on-screen readout shows.
- The engine's canvas is separate from the GDScript one. `GlyphCanvas.clear()`
  clears both; `take_strokes()` deliberately does not, and `_begin()` clears
  before each new glyph. Skip that and the next glyph is recognised on top of
  the last one's leftovers.

## 2. Templates — the shapes

One JSON file per shape in `mage-godot/assets/spell_engine/templates/`. Every
`*.json` in that folder is registered at startup; a file that fails to parse
is **skipped and logged**, not fatal, because one bad file must not silently
leave the recognizer holding a partial set.

Two file shapes are accepted, because both exist on disk:

```jsonc
// nested — one array per pen stroke
{"name": "triangle_up", "level": 1, "min_score": 0.2,
 "strokes": [[{"x": 0, "y": 0}, {"x": 40, "y": 60}], [ ... ]]}

// flat — as written by the capture tool, stroke membership per point
{"name": "plus", "level": 1, "min_score": 0.2,
 "points": [{"x": 254, "y": 389, "stroke_id": 0}, ...,
            {"x": 300, "y": 350, "stroke_id": 1}, ...]}
```

| Field | Meaning |
|---|---|
| `name` | What the feature is called everywhere else. **Spell files refer to shapes by this string**, not by filename |
| `level` | How many physically separate stroke units the shape has, after touching strokes are merged. Omit it and it is inferred; give it and a mismatch is an error |
| `min_score` | Below this, a match is not accepted. Per template, because a distinctive shape can afford to be strict and a plain one cannot |
| `strokes` / `points` | The geometry. `stroke_id` **must** be preserved — collapsing a multi-stroke shape into one stroke makes the pen-up gap look like a drawn segment and corrupts the arc-length resampling everything else is built on |

`level` is also a filter: a recognition at level 1 only ever compares against
level-1 templates. That is what keeps composed shapes from competing with
atomic ones, and it means template cost is per level, not global.

**On disk today:** `heart`, `line_horizontal`, `plus`, `star_5`,
`triangle_down`, `triangle_up`, `triangleRune` — all level 1.

## 3. Spells — the layouts

One JSON file per spell in `mage-godot/assets/spell_engine/spells/`. Unlike
templates, a spell that fails to load **is** fatal to the load pass — a
half-registered spellbook is worse than a loud failure.

```jsonc
{
  "name": "warded_pentagram",
  "min_score": 0.5,
  "features": [
    {"id": 0, "shape": "star_5", "distance": 0.0, "tolerance_dist": 0.25},
    {"id": 3, "shape": "triangle_up", "min_angle": 330, "max_angle": 30,
     "tolerance_angle": 35}
  ],
  "relative_constraints": [
    {"subject_id": 0, "reference_id": 1, "relation": "inside",
     "margin": 0.0, "tolerance": 0.18}
  ]
}
```

A **slot** (`features[]`) is one feature the spell wants:

| Field | Meaning |
|---|---|
| `id` | Unique within this spell. Only used to wire up `relative_constraints` |
| `shape` | A template `name`. A shape with no template can never fill the slot |
| `distance` | Expected distance from the **drawing's centre**, normalised by the drawing's own size, so a big glyph and a small one score the same. Omit it to score on shape alone |
| `tolerance_dist` | How far off `distance` may be before the slot stops scoring |
| `min_angle` / `max_angle` | A **compass** sector, clockwise: 0 = north, 90 = east, 180 = south, 270 = west. Wraps correctly, so `330 → 30` is "roughly north". Omit both to leave the bearing free |
| `tolerance_angle` | Degrees of slack outside the sector |

A **relative constraint** ties two filled slots together: `farther`,
`closer` (compare their distances from centre) or `inside`, `outside`
(compare a feature's position against another feature's own extent).
`margin` shifts the boundary, `tolerance` is how hard the failure is.

Matching is a backtracking search over assignments of features to slots,
scoring each slot and each constraint, keeping the best. Slots may be left
unfilled — an incomplete assignment simply scores lower. `min_score` is the
average score across slots + constraints that the spell must clear to be
accepted, and `match_spell()` returns the highest-scoring accepted spell, or
`""`.

**Not rotation invariant, on purpose.** "North" is up on the page, not up
relative to some anchor feature. Turning the whole glyph 90° makes it a
different spell — or no spell.

## 4. Tuning

Everything lives in
[`config.hpp`](../../mage-godot/scripts/spell_engine/config.hpp); these are
the ones worth reaching for first.

| Knob | Value | What it does |
|---|---|---|
| `DEFAULT_MIN_SCORE` | 0.15 | Acceptance floor for templates that do not set their own. **The main "how forgiving is recognition" dial** |
| `DEFAULT_SPELL_MIN_SCORE` | 0.75 | Same, for spells that do not set their own |
| `DEFAULT_TOUCH_THRESHOLD` | 8.0 px | How close two strokes must get to count as one shape |
| `DEFAULT_ENDPOINT_TOUCH_THRESHOLD` | 20.0 px | Same, but for a stroke's endpoints — a near miss at the tip still joins |
| `DEFAULT_LEVEL_MERGE_THRESHOLDS` | `{2: 60px}` | How far apart two features may be and still compose into a level-2 shape |
| `CLOUD_DISTANCE_PENALTY_THRESHOLD` / `_EXPONENT` | 55 px / 1.4 | What separates "sloppy" from "structurally wrong". Tune these before dropping `min_score` |
| `ASPECT_RATIO_WEIGHT` | 0.02 | How much a wrong bounding-box shape is punished. Also the early-out that lets a strong match stop the template scan early |
| `NUM_RESAMPLE_POINTS` | 64 | Points every shape is resampled to. Cost is linear in this |

There is also a debug switch at the top of `recognizer.cpp`
(`kDisableRecognitionThreshold`, currently `false`) that accepts any best
match regardless of `min_score`. It exists for template iteration; shipping
with it on means the recognizer accepts literally anything.

## 5. Adding a shape or a spell

Use the tester — it is the same engine and the same asset files, without
Godot in the loop:

```bash
powershell -File tools/spell_tester/run.ps1
```

1. **Draw the shape in the tester.** If it already recognises as something
   else with a high score, that collision is the problem to solve first —
   two templates that overlap will fight forever afterwards.
2. **Add the template JSON**, then restart the tester (templates are read
   once, at startup) and draw it a dozen times, badly on purpose. Set
   `min_score` from what you see: high enough that your sloppiest *wrong*
   shape stays out, low enough that your sloppiest *right* shape gets in.
3. **Add the spell JSON** referring to the shapes by name, and draw the whole
   layout. The panel shows every feature and the matched spell.
4. **Re-draw the neighbouring spells.** A new spell that steals another
   spell's assignment is the failure that only shows up in combination.

## 6. What is not built yet

Read this before assuming a doc describes working code:

- **Casting ignores recognition.** `spell_caster._commit()` fires the same
  placeholder bolt for every glyph. `match_spell()` is exposed to GDScript
  but nothing calls it, so no spell has an effect.
- **`SpellData` does not exist.** [ADR 0002](../adr/0002-spell-data-contract.md)
  still describes the intended boundary, but several of its fields
  (`signature`, `speed`, `economy`) were lattice concepts with no freeform
  equivalent. The `power` scaling in §7 below has no implementation and no
  agreed formula — the recognizer's 0–1 score is the obvious raw material.
- **Two shapes the spells want do not exist.** Both spell files reference
  `circle`, and `circle_and_north_caret` also wants `caret`; neither has a
  template. Until they do, neither spell can match — worth fixing before
  anything downstream is judged.

## 7. Performance

Measured on the shipped engine sources (`g++ -O2`), duplicating the real
templates up to 400. Recognition runs on the main thread when a stroke ends.

| Templates | Typical 3-stroke glyph, worst stroke | Dense 8-stroke glyph, worst stroke | Startup |
|---|---|---|---|
| 7 (today) | 0.06 ms | 0.20 ms | 4 ms |
| 50 | 0.24 ms | 0.45 ms | 24 ms |
| 200 | 0.95 ms | 1.41 ms | 86 ms |
| 400 | 2.02 ms | 3.21 ms | 156 ms |

Cost is linear in **templates at that level**, about 5 µs each, multiplied by
how many separate features are on the canvas. A 60fps frame is 16.7 ms, so
recognition has roughly three orders of magnitude of headroom: you would need
something like 2000 templates at one level before a single stroke costs a
dropped frame.

**Startup is the part that will bite first**, and it is file I/O, not maths:
registering a template costs ~0.1 ms of CPU, but *opening* hundreds of small
JSON files cost 0.4–3.5 s on a cold first read in testing. If the library
ever gets large, pack the templates into one file or ship precomputed ones
(`add_precomputed_template` already exists for this) before optimising
anything in the recognizer.

---

## 8. Balance and TTK targets

> Unchanged from the original plan and **not yet implemented** — no spell
> currently does damage. The `T` tempo constant came from a lattice-era
> spike; the freeform equivalent (how long a glyph takes to draw under
> pressure) has not been measured, so treat every number here as a
> placeholder with the right *shape*, not the right value.

### Derivation rules

These are the relationships that must hold; the numbers are consequences.

| Rule | Why |
|---|---|
| Melee closing time from aggro ≥ **1.5 T** | You must be able to finish a cast you started when it noticed you |
| Melee attack windup ≥ **0.4s** | Reaction time floor — below this a hit is unavoidable |
| Ranged fire interval ≥ **2 T** | Enough to raise an earth wall between shots, which is the counterplay |
| Miniboss fight length ≈ **10–12 casts** | Long enough to feel like a fight, short enough that one bad run is not 5 minutes wasted |
| Player survives sustained melee ≥ **8s** | A mistake costs, but does not instantly end a run |

### Player

| Stat | Value |
|---|---|
| Health | 100 |
| Move speed | 5.0 m/s |
| Move speed while drawing | 1.5 m/s (30%, masterplan 3.1.3) |

### Spells (base values, before any power multiplier)

| Spell | Damage | Notes |
|---|---|---|
| Fireball | 35 direct + 20 splash (3m radius) | Travel time ~0.4s at 18 m/s |
| Lightning | 25 | Hitscan — instant and guaranteed, hence lower |
| Earth Wall | — | 4m wide × 3m tall, 12s lifetime, **max 2 live** |
| Ward | — | 60% damage reduction, 4s |

Lightning does less than fireball because it cannot miss and has no travel
time. If playtests show fireball is strictly better, the fix is to widen that
gap, not to close it.

### Enemies

| | Melee | Ranged | Miniboss |
|---|---|---|---|
| Health | 60 | 40 | 300 |
| Move speed | 3.0 m/s | 2.5 m/s | 3.0 → 3.6 under 50% |
| Aggro range | 12m (≈ 2.2 T to close) | 16m | 20m |
| Damage | 12 | 10 | 22 |
| Attack interval | 1.2s | 3.6s (= 2 T) | 1.4s |
| Windup | 0.5s | 0.7s | 0.6s |
| Preferred range | contact | 8m | contact |

### Resulting TTK

| Target | Casts to kill | At T = 1.8s |
|---|---|---|
| Melee (60 HP) | 2 fireballs | ~3.6s + travel |
| Ranged (40 HP) | 2 lightning, or 1 fireball + splash | ~3.6s |
| Miniboss (300 HP) | ~10 fireballs | ~20s |
| **Player**, under one melee | 9 hits | ~10.8s |
| **Player**, under a synergy pair (2 melee + 1 ranged) | ~4 seconds of standing still | the pressure that makes the fight work |

That last row is the point of the whole encounter design: standing still to
draw is survivable against one enemy and fatal against a pair. Slow-walking
while drawing (3.1.3) is what turns it from a death sentence into a decision.

### What to tune first if combat feels wrong

1. **"I die while drawing"** → raise melee windup, then lower melee damage.
   Do *not* raise player health first; that flattens every other tuning knob.
2. **"Combat is trivial"** → shorten ranged fire interval toward 2 T, then add
   a second ranged enemy rather than buffing existing ones.
3. **"The miniboss is a slog"** → cut its HP. Never raise spell damage to fix
   a boss; that breaks every normal encounter at once.
4. **"My glyph didn't register"** → this is now a recognition problem, not a
   balance one. §4 above, and the tester, before anything here.
