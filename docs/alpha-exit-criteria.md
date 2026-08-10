# Alpha exit criteria

Masterplan task 0.2.5. **Written before the work starts, so it cannot be
renegotiated at the end when everyone is tired and wants to ship.**

The alpha is done when every line below is true. Not "mostly true."

---

## The five gates

### 1. A stranger finishes the level in under 20 minutes with no dev help

No hints, no "oh you have to hold right-click," no reaching over to take
the mouse. If they need help, the game needs a fix, not the tester.

*Measured:* stopwatch, in the 8.4 blind playtest. Two strangers, not one.

### 2. ≥70% of their casts are the spell they intended

*Measured:* the 3.2.5 telemetry CSV, not by watching faces.

```
hit_rate = rows where matched_spell != "" / total rows
```

Below 70%, the dials come out in this order — cheapest and least
destructive first:

1. Increase snap radius
2. Coarsen the lattice (fewer, larger cells)
3. Shorten the patterns (re-run `find_pattern.js` to keep separation ≥ 2)
4. Promote the grimoire to permanent HUD hints

Note this measures *intent*, so a pattern the player has misremembered
counts as a failure. That is correct — a spell they cannot recall is a
spell they do not have.

### 3. Zero softlocks across three full playthroughs

Including one playthrough that **deliberately abuses the earth wall**: cast
it in every doorway, in the puzzle room, and against the miniboss arena
door while it is locked. This is the single most likely softlock in the
game (masterplan 3.3.5) and it will not be found by playing normally.

### 4. Win and lose both reachable, both exit cleanly to the menu

- Death → "You died" → restart → the level is genuinely reset, including
  the spellbook pickup (masterplan 6.3).
- Miniboss killed → exit door → end screen with run stats → menu.
- No orphaned nodes, no leaked signal connections, no audio still playing
  over the menu.

### 5. Windows and Linux builds launch from a clean machine with no console errors

"Clean machine" means one that has never had Godot installed. A build that
only runs on a dev box is not a build.

macOS is explicitly out of scope for alpha — unsigned builds are
Gatekeeper-blocked and notarisation is half a day, not the 45 minutes the
original plan budgeted.

---

## Explicitly NOT alpha criteria

Listed so nobody quietly adds them at the end:

- Balance being *good*. It needs to be completable, not tuned.
- Art beyond the flat-shaded greybox palette (ADR 0003).
- Any spell beyond the four.
- Coop, procgen, saving, meta-progression.
- macOS or web builds.
- Audio beyond the ~10 SFX and the drawing tone.
- Frame rate targets beyond "does not visibly stutter in the worst room."

---

## Pre-flight checklist

Run this immediately before calling the alpha done:

- [ ] `node proto/glyph_core.test.js` passes
- [ ] The pattern separation matrix still reports minimum ≥ 2
- [ ] Telemetry CSV is being written and is readable
- [ ] Escape cancels a draw but pauses otherwise, in both orders
- [ ] Earth wall despawns on a timer even if the player never leaves the room
- [ ] Death during a draw does not leave the overlay open
- [ ] Death while a spell is charged does not fire it on respawn
- [ ] Pause during a draw releases the mouse and does not lose the stroke
- [ ] Every borrowed asset is in `CREDITS.md`

The last four are the edge cases where a draw-mode overlay and a game-state
change overlap. They are cheap to check and expensive to find in a
playtest.
