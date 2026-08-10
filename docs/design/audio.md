# Audio — SFX list and the drawing tone

Masterplan tasks 7.3 and 7.4.

---

## 1. The drawing tone (7.4) comes first

The original plan listed ten sound effects and none of them was the sound
of *drawing* — the game's signature verb. That is the wrong priority order.
Build this one first; it is the primary juice for the mechanic the entire
design rests on.

### Spec

**A rising tone, one step per lattice edge traversed.**

| Property | Value |
|---|---|
| Base | soft sine or triangle, short attack, ~120ms decay |
| Pitch | root note, ascending one scale degree per edge |
| Scale | pentatonic — every partial pattern sounds intentional, never sour |
| Root | per-spell, so each glyph has a recognisable melodic shape |
| Backtrack | pitch steps **down** and a duller timbre |
| Rejected edge | short muted click, no pitch |
| Commit (match) | resolving chord on the root |
| Commit (no match) | unresolved, falling minor second |

**Why pentatonic:** the player will draw partial and wrong patterns
constantly. On a diatonic scale, a half-finished glyph can land on a
dissonant interval and make a normal mistake feel like a punishment. On a
pentatonic scale there are no bad intervals, so wrong-but-in-progress
sounds fine and only the *commit* sound carries the verdict.

**Why per-spell roots:** with four spells and ascending steps, each pattern
becomes a short recognisable phrase. This is free reinforcement for the
memorisation the lattice design depends on (see spike P3) — players will
learn the sound before they can articulate the shape.

The rising pitch also gives continuous feedback on progress without any UI:
you can hear how far into a pattern you are while looking at the enemy.

## 2. SFX list (7.3)

Ten sounds. Free packs are fine — **log every one in `CREDITS.md` in the
same commit that adds the file**.

| # | Sound | Notes |
|---|---|---|
| 1 | Cast — fireball | Whoosh with a low-end thump on release |
| 2 | Cast — lightning | Sharp crack, near-instant, no tail |
| 3 | Cast — ward | Soft shimmer up, sustained bed while active |
| 4 | Cast — earth wall | Grinding stone rise, ~0.5s |
| 5 | Fizzle | The no-match commit. **Must not be harsh** — the player will hear it a lot |
| 6 | Impact — explosion | Fireball detonation |
| 7 | Player hurt | Short, mid-range, plus the 4.1.3 screen flash |
| 8 | Enemy death | Poof, pitch-varied per instance so repeats do not fatigue |
| 9 | Pickup | Bright, short, unambiguous |
| 10 | Door / lever | Heavy mechanical clunk; the lever needs a satisfying throw |

### Rules

- **Pitch-randomise anything that repeats.** ±8% on enemy death, pickup and
  impact. Ten identical enemy deaths is the fastest way to make a build
  feel cheap.
- **The fizzle is the most-heard sound in the game.** Design it as
  information, not as a buzzer. A soft unresolved tone, not a klaxon.
- **Cast sounds scale with power.** The 0.4–1.3 multiplier maps to volume
  and low-end presence, so a great cast *sounds* great without a UI element.
- **Nothing louder than the drawing tone during a draw.** The draw is the
  focus; combat sound ducks slightly while the overlay is open.

## 3. Buses

| Bus | Contents | Notes |
|---|---|---|
| `Master` | | |
| `SFX` | everything in the table above | |
| `Glyph` | the drawing tone | Separate so it can duck the SFX bus |
| `Ambient` | dungeon loop (7.6, `[cut]`) | Reverb lives here |
| `UI` | menus, pickups | Never ducked |

Volume slider in the main menu (6.1) drives `Master`. If time allows, a
separate `Glyph` slider is worth more than a music slider at alpha — some
players will find the tone essential and others will find it grating.

## 4. Sourcing

Preferred, in order: **freesound.org** (check the licence per-sound — the
site mixes CC0 and CC-BY), **Kenney.nl** (CC0, no attribution needed,
consistent quality), **sonniss GDC bundles** (royalty-free, large).

Avoid anything CC-BY-NC. It is fine for a private alpha and a blocker the
moment this becomes commercial — see the licence notes in `CREDITS.md`.

The drawing tone should be **synthesised, not sampled**: it needs per-edge
pitch stepping at runtime, which a sample cannot do cleanly. An
`AudioStreamGenerator`, or a short one-shot pitched via
`pitch_scale` per step, both work.
