# Spells — patterns, scoring, balance

Masterplan tasks 2.2.1, 2.2.2, 4.3.2. The authoritative data lives in
`proto/glyph_core.js` (`ALPHA_PATTERNS`, `DEFAULT_SCORING`); this document
explains it and holds the balance numbers that become
`resources/tuning/balance.tres`.

---

## 1. The four alpha patterns

| Spell | Pattern | Edges | Signature | Shape | Archetype |
|---|---|---|---|---|---|
| **Fireball** | `0,2,4` | 3 | `024` | closed triangle | projectile |
| **Lightning** | `0,1,0,1` | 4 | `0101` | zigzag, open | hitscan |
| **Earth Wall** | `0,0,0,0,0` | 5 | `00000` | straight line | summon |
| **Ward** | `0,1,2,3,4,5` | 6 | `012345` | closed hexagon | self |

Directions are lattice edge indices 0–5, at 60° increments clockwise from
east. See `glyph_core.js` for the axial coordinate system.

### Why these four

**Fireball is the shortest.** It is the spell cast under pressure, so it
gets the fewest edges. Three edges is the practical floor — anything
shorter cannot be distinguished from a stray drag.

**Earth Wall is a straight line**, which is both thematically exact (a line
*is* a wall) and, despite having five edges, almost certainly the fastest
pattern in the set to trace: it has **zero turns**. Edge count is a poor
proxy for draw time; turns are what cost time. P1 will confirm this.

**Ward is the slowest** on purpose. A hexagon is the lattice's signature
shape, and a defensive commitment should cost something. If P1 shows it is
so slow as to be unusable defensively, the fix is to shorten it — but check
first whether "you must anticipate danger rather than react to it" is
actually the more interesting mechanic.

### Separation — the safety property

Every pair of patterns is **edit distance ≥ 3** apart, measured across all
24 symmetries (6 rotations × mirror × reversal):

```
              fireball  lightning  earth_wall  ward
  fireball           0          3           4     3
  lightning          3          0           3     4
  earth_wall         4          3           0     5
  ward               3          4           5     0
```

**The rule: minimum separation ≥ 2.** At distance 1, a single mis-stepped
edge silently casts the wrong spell — the lattice equivalent of the
recognition failure ADR 0001 exists to avoid. The current set clears the
bar with a full point to spare, so even a *two*-edge mistake cannot cast
the wrong spell.

This is verified exhaustively, not argued: `glyph_core.test.js` enumerates
every single-edit mutation of every pattern (237 of them) and asserts none
produces a different spell's signature.

### Adding a spell

Do not hand-pick a shape. Run the search:

```bash
node proto/find_pattern.js --len 3,4,5 --against fireball,lightning,earth_wall,ward
```

It reports every candidate with its safety margin, filters out paths that
double back (unreachable, since backtracking erases) and paths that revisit
a point mid-draw (hard to trace and hard to read on the HUD). Pick the
evocative one *from the safe list*.

This is how Earth Wall was chosen: the hand-picked rhombus `0134` scored
margin 2; the search found the straight line at margin 3.

Two beta candidates are already validated and used as distractors in the P3
memory spike — `Chain` (`2,1,1,0,0`) and `Frost` (`1,3,2,0,0`). The
six-pattern set keeps minimum separation 3.

### Invariance — what counts as "the same glyph"

| Transform | Same spell? | Why |
|---|---|---|
| Drawn anywhere on the lattice | yes | Only directions are stored, never positions |
| Rotated any multiple of 60° | yes | Normalised by subtracting the first direction |
| Mirrored | yes | Compared against the reflected form |
| Drawn from the other end | **yes** | Deliberate — starting from the wrong corner is exactly the mistake a panicking player makes |
| Drawn larger (2 edges per side) | **no** | Deliberate — scale is most of the design space a 6-direction lattice has |

---

## 2. Scoring — power = speed × economy

The lattice has no fuzzy "draw quality" axis, but it still has a skill
axis, and both halves are exact integers rather than a tuned curve.

```
speed    = 1                              if elapsed <= par
         = (par*2.5 - elapsed)            normalised to 0..1, else
           / (par*2.5 - par)

economy  = edges / (edges + fumbles)

power    = 0.4 + 0.9 * speed * economy    ->  0.4 .. 1.3
```

**A fumble** is a backtrack or an attempt to re-trace an edge already used.
Count *attempts*, not results: input capture already refuses the move, so
the only record that the player struggled is how many times they tried.
Instrument this at input time — it cannot be recovered from the final path.

**Par times** are per-pattern and are placeholders until P1 supplies real
numbers. Current values: fireball 1.1s, earth wall 1.2s, lightning 1.4s,
ward 2.0s.

**Why a 0.4 floor and a 1.3 ceiling.** A floor means a bad cast is still a
cast — the spell fires, it just hurts less, so a fumbling player is never
left defenceless. The ceiling above 1.0 means mastery is rewarded rather
than merely un-punished. Both live in `DEFAULT_SCORING` and are meant to be
tuned from playtest data.

Configuration goes in `resources/tuning/scoring.tres`, not in code.

---

## 3. Balance and TTK targets

> **All enemy timings are derived from `T`, the combat tempo constant** —
> the median total cast time measured by spike P1 (masterplan 3.2.6).
> The numbers below assume **T = 1.8s** as a placeholder. When P1 reports,
> recompute rather than nudge.

### Derivation rules

These are the relationships that must hold; the numbers are consequences.

| Rule | Why |
|---|---|
| Melee closing time from aggro ≥ **1.5 T** | You must be able to finish a cast you started when it noticed you |
| Melee attack windup ≥ **0.4s** | Reaction time floor — below this a hit is unavoidable, not unfair-feeling but unfair |
| Ranged fire interval ≥ **2 T** | Enough to raise an earth wall between shots, which is the counterplay |
| Miniboss fight length ≈ **10–12 casts** | Long enough to feel like a fight, short enough that one bad run is not 5 minutes wasted |
| Player survives sustained melee ≥ **8s** | A mistake costs, but does not instantly end a run |

### Player

| Stat | Value |
|---|---|
| Health | 100 |
| Move speed | 5.0 m/s |
| Move speed while drawing | 1.5 m/s (30%, masterplan 3.1.3) |

### Spells (base values, before the 0.4–1.3 power multiplier)

| Spell | Damage | Notes |
|---|---|---|
| Fireball | 35 direct + 20 splash (3m radius) | Travel time ~0.4s at 18 m/s |
| Lightning | 25 | Hitscan — instant and guaranteed, hence lower |
| Earth Wall | — | 4m wide × 3m tall, 12s lifetime, **max 2 live** |
| Ward | — | 60% damage reduction, 4s |

Lightning does less than fireball because it cannot miss and has no travel
time. If playtests show fireball is strictly better, the fix is to widen
that gap, not to close it.

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
| Melee (60 HP) | 2 fireballs at ~0.85 power | ~3.6s + travel |
| Ranged (40 HP) | 2 lightning, or 1 fireball + splash | ~3.6s |
| Miniboss (300 HP) | ~10 fireballs | ~20s |
| **Player**, under one melee | 9 hits | ~10.8s |
| **Player**, under a synergy pair (2 melee + 1 ranged) | ~4 seconds of standing still | the pressure that makes the fight work |

That last row is the point of the whole encounter design: standing still to
draw is survivable against one enemy and fatal against a pair. Slow-walking
while drawing (3.1.3) is what turns it from a death sentence into a
decision.

### What to tune first if combat feels wrong

1. **"I die while drawing"** → raise melee windup, then lower melee damage.
   Do *not* raise player health first; that flattens every other tuning
   knob.
2. **"Combat is trivial"** → shorten ranged fire interval toward 2 T, then
   add a second ranged enemy rather than buffing existing ones.
3. **"The miniboss is a slog"** → cut its HP. Never raise spell damage to
   fix a boss; that breaks every normal encounter at once.
