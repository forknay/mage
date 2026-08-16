# ADR 0001 — Lattice recognition, not freeform

**Status:** ~~Accepted~~ **Overtaken by the implementation** (2026-08-16) ·
**Date:** 2026-07-25

> **This decision was reversed in code, not on paper.** What is on `main`
> is freeform: unconstrained strokes on a world-space canvas, classified by
> an orientation-sensitive $Q point-cloud recognizer written in C++ and
> built by Jenova, with spells defined as *layouts* of recognised shapes.
> See [`docs/design/spells.md`](../design/spells.md) for how it actually
> works.
>
> The record below is kept because it is still the clearest statement of
> what freeform costs — every risk it names (threshold-vs-collision, "the
> parser ate my spell", onboarding by shape rather than by memory) is now a
> live concern rather than an avoided one, and `min_score` tuning is exactly
> the lever it warned about. **Why the team switched is not recorded
> anywhere**; a successor ADR should capture it while the reasoning is still
> in someone's head.
>
> Nothing below describes shipped behaviour. In particular the lattice
> tooling it relies on — `proto/glyph_core.js`, `find_pattern.js`, the
> separation matrix — is no longer part of the pipeline.

**Original revisit condition:** spikes P1 and P3 — these can still overturn
it, and nothing downstream should be built until they clear.

## Context

Two incompatible input models were on the table.

**Freeform.** The player draws an unconstrained stroke; a $P point-cloud
recognizer classifies it; RDP corner extraction and a Kåsa circle fit pull
out parameters; a fuzzy 0–1 "quality" score scales spell power. This was
the original Phase 2 plan (11h, on the critical path).

**Lattice.** Input snaps to a triangular lattice and may only traverse
adjacent edges. Every turn is a multiple of 60°, so classification is exact
integer math. This is what `hex_spellcaster_prototype.html` already
demonstrates.

The two are not implementations of one design. They test different player
skills (dexterity vs recall), have different power-scaling models, and fail
in completely different ways.

## Decision

**Lattice.**

The deciding argument is not fantasy or code volume — it is the shape of
the failure mode.

- **Lattice failure is a dial.** Too slow? Coarser grid, larger snap
  radius, shorter patterns. Each is a number, tunable between playtests,
  with no knock-on effects.
- **Freeform failure is a wall.** When a stranger's triangle does not
  register, the only lever is loosening the recognition threshold — which
  simultaneously makes *every* shape more likely to be confused with every
  other shape. The fix for one problem creates a worse one, and there is no
  amount of tuning that escapes it.

This team is on its first Godot project. Take the risk you can turn a knob on.

Supporting reasons, none of which would have been sufficient alone:

- Removes ~5h from the critical path (no $P, no RDP, no circle fit, no
  quality-curve tuning).
- The prototype already works, so the riskiest component starts from a
  demonstrated base rather than a port.
- "The parser ate my spell and I died" is the worst feel in an action game.
  On a lattice a wrong cast is legibly the player's own error — you can see
  the path you traced.
- Exact integer math is trivially unit-testable. `proto/glyph_core.test.js`
  has 51 assertions and no tolerance values anywhere.

## Consequences

**Gained**

- Recognition accuracy is no longer a risk at all. The alpha's stated key
  risk at 8.4 changes from "does it recognise a stranger's handwriting" to
  "can a stranger recall and trace patterns fast enough" — a question with
  dials attached.
- Pattern separation becomes a *provable* safety property rather than a
  hope. `separationMatrix()` verifies that no single mis-stepped edge can
  cast the wrong spell; the current set clears it with margin 3.
- Adding spells at beta is a search problem with a tool
  (`proto/find_pattern.js`), not a tuning session.

**Lost**

- The fuzzy "draw it beautifully" fantasy. Power scaling is replaced by
  speed × economy — see ADR 0002 and `docs/design/spells.md`.
- Free onboarding. "Draw a triangle" teaches itself; a memorised sigil does
  not. A grimoire (7.1) is now mandatory rather than a nicety, and spike P3
  decides whether it is a menu or permanent HUD hints.
- Scale invariance. A two-edge-per-side triangle is a *different* spell
  from a one-edge one. This is deliberate — it is most of the design space
  a 6-direction lattice has — but it means patterns must be learned
  precisely, not approximately.

**New risk this creates**

Lattice tracing may simply be too slow under combat pressure. Hexcasting,
the obvious reference, is drawn in a paused menu — not while something is
running at the player. **Spike P1 exists to answer exactly this**, and its
go/no-go (median ≤ 2.0s, p90 ≤ 3.5s) gates production.

## Alternatives rejected

- **Freeform**, above.
- **Both, selectable.** Doubles the pipeline, halves the tuning attention
  each gets, and means neither input model gets designed around properly.
- **Lattice with fuzzy tolerance** (snap generously, accept near-misses).
  Reintroduces exactly the threshold-vs-collision problem that made
  freeform unattractive, while keeping none of freeform's expressiveness.
