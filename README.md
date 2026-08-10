# Mage

A first-person dungeon crawler where every spell is a sigil traced by hand
on a hex lattice. Godot 4, GDScript.

**Status:** pre-production. The engine-free groundwork is done; the two fun
spikes that gate everything else are built and waiting to be run with real
people.

---

## Start here

| If you are… | Read |
|---|---|
| New to the project | [`alpha-masterplan.md`](alpha-masterplan.md) |
| About to write code | [`CONTRIBUTING.md`](CONTRIBUTING.md), [`docs/conventions.md`](docs/conventions.md) |
| Wondering why it works this way | [`docs/adr/`](docs/adr/) |
| Building the glyph pipeline | [`proto/glyph_core.js`](proto/glyph_core.js) |

## The two decisions that shape everything

**Input is a hex lattice, not freeform drawing.** Strokes snap to a
triangular grid and may only traverse adjacent edges, so recognition is
exact integer math — no thresholds, no tuning, no "it doesn't read my
handwriting." The reasoning is in
[ADR 0001](docs/adr/0001-lattice-vs-freeform.md); the short version is that
lattice failures are dials and freeform failures are walls.

**Casting produces a data struct, never a direct effect.** One
`resolve_spell()` consumes it. Costs ~10% overhead now; means coop is a
feature at beta rather than a rewrite. See
[ADR 0002](docs/adr/0002-spell-data-contract.md).

## Prototypes

Everything in `proto/` runs in a browser or Node — **no Godot required.**

```bash
node proto/glyph_core.test.js      # 51 assertions, the pipeline spec
node proto/find_pattern.js         # search for a safe new spell pattern
```

| File | What it is |
|---|---|
| [`glyph_core.js`](proto/glyph_core.js) | The whole recognition pipeline, engine-free. Written to port 1:1 to GDScript — this is the reference the port must match. |
| [`glyph_core.test.js`](proto/glyph_core.test.js) | The specification as assertions. Port these alongside the code. |
| [`find_pattern.js`](proto/find_pattern.js) | Searches the lattice for patterns maximally distinct from the existing set. Run before adding any spell. |
| [`tempo_spike.html`](proto/tempo_spike.html) | **P1** — timed tracing drill. Produces the combat tempo constant every enemy is tuned from. |
| [`memory_spike.html`](proto/memory_spike.html) | **P3** — study six sigils, reproduce them an hour later. Decides whether the grimoire is a menu or permanent HUD hints. |
| [`hex_spellcaster_prototype.html`](hex_spellcaster_prototype.html) | The original spike that started all of this. Superseded by `glyph_core.js`, kept for reference. |

### Run the spikes before writing engine code

Both are go/no-go gates, and both can overturn the lattice decision:

- **P1** passes at median ≤ 2.0s, p90 ≤ 3.5s.
- **P3** passes at 4 of 6 sigils recalled after a real one-hour delay.

They need people, not programming. That is the whole point — the riskiest
things about this design are answerable in an afternoon with four humans
and a browser.

## The four spells

| Spell | Pattern | Shape |
|---|---|---|
| Fireball | `024` | closed triangle |
| Lightning | `0101` | zigzag |
| Earth Wall | `00000` | straight line |
| Ward | `012345` | closed hexagon |

Every pair is at least **3 edits apart** across all 24 symmetries, so no
single — or even double — mis-stepped edge can cast the wrong spell. This
is asserted exhaustively in the test suite, not assumed. Details in
[`docs/design/spells.md`](docs/design/spells.md).

## Documentation

```
docs/
  adr/                    why things are the way they are
  conventions.md          folders, naming, autoloads, input map, layers
  alpha-exit-criteria.md  what "done" means — written before the work
  playtest-kit.md         recruiting, observation protocol, feedback form
  design/
    spells.md             patterns, scoring, balance and TTK targets
    level.md              grid conventions, layout, population, softlocks
    art-direction.md      palette, lighting, props
    audio.md              SFX list and the drawing tone
```
