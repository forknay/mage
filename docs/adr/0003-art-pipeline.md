# ADR 0003 — CSG/GridMap greybox, Blender for props only

**Status:** Accepted (masterplan 0.2.3) · **Date:** 2026-07-25

## Context

The alpha needs one handcrafted level of 7–8 rooms. Two ways to build it:

- **Blender modular kit** — author wall/floor/corner meshes in Blender,
  import, assemble in Godot. Looks considerably better.
- **Godot CSG / GridMap** — block the level out with primitives directly in
  the engine.

The team is 2–3 people. Whoever does art is also doing other things, and a
Blender kit puts the entire level phase behind that one person's queue.

## Decision

**CSG/GridMap for all level geometry. Blender only for the five props:**
torch, door, lever, pedestal, and the pickup meshes (health, spellbook).

The flat-shaded look the game is going for barely benefits from authored
meshes — it is carried by palette, lighting and silhouette, not by
geometry detail. So the Blender kit buys little of what actually makes the
game look like something, while costing the schedule a hard dependency.

Props are the exception because a torch or a lever *is* its silhouette,
and there is no way to make a CSG lever read as a lever.

## Constraint that makes this non-throwaway

**Every room is built on a grid with standard door-socket positions.**

This is what keeps the greybox from being wasted work: procedural
generation is a core pillar at beta (Barony-style room pool), and a room
kit with consistent door sockets is procgen-ready by construction. Break
the grid discipline and the beta procgen work starts from zero.

Conventions live in `docs/design/level.md` and are not negotiable
per-room.

## Consequences

**Gained**

- Level work starts on day one of Track C and never blocks on art.
- Iteration is instant — no export/import round trip to move a wall.
- CSG is trivially editable by whoever is nearest, not only by the art
  person.
- The room kit is a procgen kit at beta for free, provided the grid rule
  holds.

**Lost**

- Visual ceiling. The alpha will look like a greybox with a good palette.
  This is the correct trade for an alpha whose open questions are all
  about *feel*, not looks.
- CSG has real performance costs at scale. Irrelevant at 7–8 rooms;
  revisit if the room count grows before the beta art pass.

**Watch for**

- CSG nodes stay editable at runtime, which is a tempting trap. Bake to
  `MeshInstance3D` before the navmesh bake (5.2.2) if the profiler at 8.3
  flags geometry cost.
- Do not let "greybox" become an excuse for bad proportions. Room scale,
  door width and ceiling height are gameplay values — the miniboss arena
  needs room to dodge, and that is decided here, not at the art pass.
