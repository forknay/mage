# ADR 0002 — Spells resolve through a data struct

**Status:** Accepted (masterplan 0.2.2) · **Date:** 2026-07-25

## Context

Coop is a beta goal, not an alpha one. Writing netcode now is clearly out
of scope. But the *shape* of the casting code decides whether coop is a
feature or a rewrite later.

The failure case is specific and common: spell casting written
imperatively, where the input handler reaches into the world and applies
effects directly.

```gdscript
# The trap
func _input(event):
    if recognised_shape == "triangle":
        var enemy = get_node("../../Enemy")
        enemy.health -= 20
        $Camera3D/Particles.emitting = true
```

This cannot be made multiplayer without rewriting it. It also cannot be
unit-tested, replayed from telemetry, or reasoned about when two effects
overlap.

## Decision

**Casting produces a `SpellData` struct. A single `resolve_spell()`
consumes it. Nothing else applies spell effects.**

```
SpellData
  ok            bool     did recognition succeed
  reason        String   match | no_match | broken_path | too_short
  spell_id      String   "fireball" — looked up in SpellRegistry
  signature     String   canonical pattern hash, for telemetry
  power         float    ~0.4 .. 1.3, from speed x economy
  speed         float    0..1  component, kept for telemetry
  economy       float    0..1  component, kept for telemetry
  origin        Vector3  where the cast came from
  aim           Vector3  direction, filled at fire time (see 3.1.6)
  caster_id     int      who cast it — 0 in solo, peer id at beta
```

Three rules follow:

1. **All game events go through signals.** Systems announce; they do not
   reach into each other.
2. **No gameplay logic in `_input`.** Input produces intent. Systems act
   on intent.
3. **Recognition runs client-side; the struct crosses the wire, never the
   raw stroke.** A stroke is dozens of points at input frequency;
   `SpellData` is a couple of dozen bytes. This is decided now because it
   constrains where the pipeline may read local state — `resolve_spell()`
   must work from the struct alone, not from `get_viewport()` or the local
   camera.

## Consequences

**Costs** roughly 10% overhead now: an extra type, an extra indirection,
and the discipline not to shortcut it when a direct call would be two
lines shorter.

**Buys**

- Coop becomes "replicate a small struct" rather than a rewrite.
- Track A builds all of Phase 3 against a **stub recognizer** returning a
  hardcoded `SpellData` (task 0.2.4, day one), so the two tracks are
  genuinely parallel instead of nominally parallel.
- Telemetry (3.2.5) is nearly free — the struct already carries everything
  worth logging.
- Casts are replayable. A logged `SpellData` can be re-fired to reproduce
  a bug without redrawing anything.
- `power` arriving pre-computed means spell scenes never need to know how
  scoring works. Changing the scoring formula touches one file.

**Accepted risk:** a client computing its own `power` can lie about it.
Irrelevant for solo and for friendly coop; if this ever becomes a
competitive or public-lobby game, resolution moves server-side and the
struct becomes a *request* rather than a result. The struct boundary is
what makes that change feasible at all.

## Notes

`proto/glyph_core.js` `recognize()` already returns this shape. Its return
value is the reference for the GDScript port — keep the field names.
