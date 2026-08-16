# Mage

A first-person dungeon crawler where every spell is a sigil drawn by hand in
the air. Godot 4, GDScript, with the recognizer in C++.

**Status:** early production. Drawing and recognition work end to end — you
can draw in the world, and shapes are recognised and named on screen as you
go. Nothing is wired to damage yet: every cast fires the same placeholder
bolt.

---

## Start here

| If you are… | Read |
|---|---|
| New to the project | [`alpha-masterplan.md`](alpha-masterplan.md) — but read the banner at the top first |
| About to write code | [`CONTRIBUTING.md`](CONTRIBUTING.md), [`docs/conventions.md`](docs/conventions.md) |
| Working on spells | [`docs/design/spells.md`](docs/design/spells.md) |
| Wondering why it works this way | [`docs/adr/`](docs/adr/) |

## How casting works

**You draw freehand, in the world.** Hold `anchor` to pin a canvas in the
air in front of you, hold `draw`, and the crosshair is the pen — you draw by
looking. Several strokes make one glyph; `cast` commits it, Escape throws it
away.

**Shapes are recognised, then their layout is matched.** An
orientation-sensitive $Q point-cloud recognizer (C++, built by Jenova)
classifies each cluster of strokes into a *shape* — `star_5`, `triangle_up`
— throwing position and scale away. A second layer then matches the *layout*
of those shapes against spell definitions: which shapes, at what bearings
and distances from the drawing's centre. Both layers are data files, not
code. See [`docs/design/spells.md`](docs/design/spells.md).

**Casting produces a data struct, never a direct effect.** One
`resolve_spell()` consumes it. Costs ~10% overhead now; means coop is a
feature at beta rather than a rewrite. See
[ADR 0002](docs/adr/0002-spell-data-contract.md) — decided, not yet built.

> [ADR 0001](docs/adr/0001-lattice-vs-freeform.md) chose a hex lattice
> instead of any of this. The code went the other way; the ADR is kept as a
> record and marked accordingly.

## Tools

**The spell tester** — draw at the recognizer without launching Godot. It
compiles the same engine sources and reads the same template and spell
files, so what it says is what the game says:

```bash
powershell -File tools/spell_tester/run.ps1
```

See [`tools/spell_tester/README.md`](tools/spell_tester/README.md). This is
the loop for adding a shape or tuning a threshold.

**`proto/`** holds the lattice-era prototypes — `glyph_core.js`,
`find_pattern.js`, and the two fun-spikes. They belong to the input model
[ADR 0001](docs/adr/0001-lattice-vs-freeform.md) describes and are **not**
the spec for anything currently being built. Kept for the tempo and memory
spikes, which are still unrun and still interesting, and because
`hex_spellcaster_prototype.html` is where the project started.

## The spell content, today

Shapes the recognizer knows, from
`mage-godot/assets/spell_engine/templates/`:

`heart` · `line_horizontal` · `plus` · `star_5` · `triangle_down` ·
`triangle_up` · `triangleRune`

Spells, from `mage-godot/assets/spell_engine/spells/`:
`warded_pentagram`, `circle_and_north_caret` — **neither can match yet**,
because both want a `circle` shape that has no template. Adding shapes and
spells is [`docs/design/spells.md`](docs/design/spells.md) §5.

## Documentation

```
docs/
  adr/                    why things are the way they are
  conventions.md          folders, naming, autoloads, input map, layers
  alpha-exit-criteria.md  what "done" means — written before the work
  playtest-kit.md         recruiting, observation protocol, feedback form
  design/
    spells.md             the recognition pipeline, data formats, balance
    level.md              grid conventions, layout, population, softlocks
    art-direction.md      palette, lighting, props
    audio.md              SFX list and the drawing tone
```
