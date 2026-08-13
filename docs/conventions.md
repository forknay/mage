# Project conventions

Masterplan tasks 0.1.3 and 0.1.4. Decided up front so nobody has to guess,
and so `project.godot` gets edited in as few sittings as possible
(`CONTRIBUTING.md` §4).

---

## Folder structure

```
res://
  scenes/
    player/          player.tscn, spell_caster.tscn, draw_overlay.tscn
    spells/          fireball.tscn, lightning.tscn, ward.tscn, earth_wall.tscn
    enemies/         enemy_base.tscn, melee.tscn, ranged.tscn, miniboss.tscn
    level/           room kit pieces, the assembled level, props
    ui/              hud.tscn, grimoire.tscn, menus, end screens
  scripts/
    autoload/        spell_registry.gd, audio_bus.gd, telemetry.gd
    glyph/           the GDScript port of proto/glyph_core.js
    components/      health.gd, interactable.gd
  resources/
    patterns/        pattern_dictionary.tres
    tuning/          scoring.tres, balance.tres, tempo.tres
    materials/       the flat-shaded palette set
  assets/
    audio/  models/  fonts/
```

Rules:

- **Scene and its script live together.** `player.tscn` next to `player.gd`,
  not split across `scenes/` and `scripts/`. The exception is `scripts/` for
  code with no scene of its own (autoloads, components, the glyph port).
- **Nothing tunable is hardcoded.** Numbers that a playtest might change go
  in `resources/tuning/` as a `Resource`, so they are editable in the
  inspector without a rebuild.

## Naming

Follows the [GDScript style guide](https://docs.godotengine.org/en/stable/tutorials/scripting/gdscript/gdscript_styleguide.html).

| Thing | Convention | Example |
|---|---|---|
| Files, folders | `snake_case` | `spell_caster.gd` |
| Classes (`class_name`) | `PascalCase` | `SpellData` |
| Nodes in a scene | `PascalCase` | `DrawOverlay` |
| Functions, variables | `snake_case` | `resolve_spell()` |
| Constants, enums | `CONSTANT_CASE` | `MAX_LIVE_WALLS` |
| Signals | past tense | `spell_cast`, `damaged`, `died` |
| Private members | leading underscore | `_current_path` |

Signals are past-tense because they announce that something *happened*.
`spell_cast`, not `cast_spell` — the latter reads like a command and
invites the imperative style ADR 0002 exists to prevent.

## Autoloads

Keep this list short. Every autoload is global state.

| Name | Script | Purpose |
|---|---|---|
| `SpellRegistry` | `scripts/autoload/spell_registry.gd` | spell id → packed scene + base stats (3.2.2) |
| `AudioBus` | `scripts/autoload/audio_bus.gd` | one-shot SFX playback, bus routing |
| `Telemetry` | `scripts/autoload/telemetry.gd` | append cast rows to CSV (3.2.5) |

**Deliberately not autoloads:**

- `GameState` — the original plan listed it, but death is a full scene
  reload with a re-collectable spellbook (masterplan 6.3), so there is no
  cross-scene state to hold. Adding it invites someone to put run state in
  it and quietly break the reset.
- `DebugOverlay` (1.3.2) — starts as an autoload for convenience, but it
  must be strippable from a release build. Keep it free of anything
  gameplay depends on.

## Input map

| Action | Binding | Notes |
|---|---|---|
| `move_forward` / `_back` / `_left` / `_right` | W A S D | |
| `jump` | Space | |
| `interact` | E | Raycast interactor (1.3.1) |
| `draw` | Left mouse, **hold** | Opens the draw overlay and draws one stroke per hold; the overlay stays open between strokes |
| `cast` | Right mouse | Commits every stroke drawn so far and fires the result |
| `grimoire` | Tab, hold | Pattern reference (7.1) |
| `pause` | Escape | **See the Escape rule below** |

### The Escape rule

Escape is bound to two things and Godot's input handling under
`MOUSE_MODE_CAPTURED` makes this a classic source of priority bugs. The
rule, decided once:

> **If the draw overlay is open, Escape cancels the draw and nothing else.
> Otherwise Escape pauses.**

Implement it as a single check at the top of the overlay's input handler,
consuming the event with `set_input_as_handled()`. Do not let two nodes
both listen for Escape.

## Physics layers

Name them in Project Settings the first time each is needed. Never write a
raw layer number in a script.

| Layer | Name | Contains |
|---|---|---|
| 1 | `world` | Level geometry, CSG, baked meshes |
| 2 | `player` | Player body |
| 3 | `enemy` | Enemy bodies |
| 4 | `player_projectile` | Fireballs, lightning ray targets |
| 5 | `enemy_projectile` | Ranged enemy shots |
| 6 | `interactable` | Levers, pickups, doors |
| 7 | `spell_geometry` | **Earth walls** — must block projectiles *and* break the enemy line-of-sight ray (4.2.4) |

Layer 7 exists as its own layer specifically because the earth wall's whole
purpose is stopping ranged attacks. A `NavigationObstacle3D` only nudges
pathfinding; it does not stop anything. See masterplan 3.3.5.

## Units

- **1 unit = 1 metre.** Player capsule 1.8m tall, 0.4m radius.
- Corridors 3m wide, 3.5m ceiling. Rooms 8–14m. Miniboss arena 18m.
- Gravity from `ProjectSettings.get_setting("physics/3d/default_gravity")`
  — do not redefine it per-scene.

Room dimensions are gameplay values, not art values — see
`docs/design/level.md`.
