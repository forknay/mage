# Project conventions

Masterplan tasks 0.1.3 and 0.1.4. Decided up front so nobody has to guess,
and so `project.godot` gets edited in as few sittings as possible
(`CONTRIBUTING.md` §4).

---

## Folder structure

```
res://
  project.godot      only this, icon.svg and vendored dirs live at the root
  scenes/
    player/          player.tscn, spell_caster.tscn, draw_overlay.tscn
    spells/          fireball.tscn, lightning.tscn, ward.tscn, earth_wall.tscn
    enemies/         enemy_base.tscn, melee.tscn, ranged.tscn, miniboss.tscn
    level/           room kit pieces, the assembled level
      props/         chest.tscn, torch.tscn, levers, pickups
    ui/              hud.tscn, grimoire.tscn, menus, end screens
  scripts/
    autoload/        spell_registry.gd, audio_bus.gd, telemetry.gd
    glyph/           the draw canvas: glyph_plane.gd, glyph_canvas.gd,
                     spell_recognizer.gd
    components/      health.gd, interactable.gd
    spell_engine/    the native C++ recogniser, built by Jenova
  resources/
    tuning/          scoring.tres, balance.tres, tempo.tres
    materials/       the flat-shaded palette set
  assets/
    spell_engine/
      templates/     one JSON per recognised shape
      spells/        one JSON per spell layout
    audio/  models/  fonts/
```

`scripts/glyph/spell_recognizer.gd` is the only file that names the native
`GodotSpellEngine` class, which is what lets the project open on a machine
where Jenova cannot build it — see `CONTRIBUTING.md` §7. Call the recogniser
through `SpellRecognizer`; do not reach past it.

The spell data deliberately lives under `assets/`, not `resources/`: it is
read by the C++ engine through `std::filesystem` from paths relative to the
working directory, so it never becomes a Godot `Resource` and must not be
moved into a `.pck`-only location. `docs/design/spells.md` has the formats.

Rules:

- **Scene and its script live together.** `player.tscn` next to `player.gd`,
  not split across `scenes/` and `scripts/`. The exception is `scripts/` for
  code with no scene of its own (autoloads, components, the glyph canvas,
  the C++ engine).
- **Nothing tunable is hardcoded.** Numbers that a playtest might change go
  in `resources/tuning/` as a `Resource`, so they are editable in the
  inspector without a rebuild.
- **The entry scene is the assembled level**, `scenes/level/main.tscn`. It is
  what `run/main_scene` points at, and it owns the GridMap and the
  `NavigationRegion3D` that `main.gd` bakes. It is not a "boot" scene — when
  a menu flow arrives (7.x), that becomes the entry point and this stays the
  level.
- **Props are level content**, so they live in `scenes/level/props/`, not in a
  top-level `props/`. A prop is anything placed *into* a room that is not the
  room itself: chests, torches, levers, pickups.
- **The project root holds `project.godot`, `icon.svg`, and vendored
  directories only** (`Jenova/`). Anything else that lands there is unsorted
  by definition — Godot drops new imports at the root, so sweep it.

### Imported models and their textures

`.glb` files go in `assets/models/`, and **the textures Godot extracts from
them stay in the same folder as the `.glb`**.

This is not a preference, it is how the glTF importer works: embedded images
are written out beside the source file as `<glb_basename>_<image_name>.png`,
so `tileset.glb` produces `tileset_atlas.png` and `tileset_atlas_n.png`, and
`slime_low-poly.glb` produces `slime_low-poly_0.png`. Move one of those into
a textures folder and Godot silently re-extracts it next to the `.glb` on the
next import, leaving you with two copies and a `.tres` pointing at the one
that is now orphaned.

Tell them apart before you move anything: a texture that has a matching
`.glb` prefix is generated and is not yours to place. Hand-authored textures
with no `.glb` behind them get `assets/textures/`, which does not exist yet
because we have none.

### Moving files

Move and rename **inside the Godot editor**, never in Explorer or with
`git mv` alone. The editor rewrites every `res://` path that pointed at the
file; the filesystem does not. If a move has already happened outside the
editor, every `.tscn`, `.tres`, `.import` and `project.godot` referencing it
has to be fixed by hand — `grep -rn 'res://' --include=*.tscn --include=*.tres
--include=*.import` finds them all, and `.import` files carry a `source_file`
that must be fixed too.

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

## Static typing

**Every declaration carries an explicit type.** Variables, constants,
parameters, return types, and `for` loop variables.

```gdscript
var speed: float = 3.0            # yes
var strokes: Array[PackedVector2Array] = []
for stroke: PackedVector2Array in canvas.strokes:
func can_see_player() -> bool:

var speed = 3.0                   # no — untyped
var speed := 3.0                  # no — inferred, not written down
```

This is enforced, not suggested. `project.godot` sets these GDScript
warnings to **Error**, so an untyped declaration fails to compile rather than
scrolling past in the output panel:

| Warning | Level | Catches |
|---|---|---|
| `untyped_declaration` | Error | `var x = 5`, untyped params and returns |
| `inferred_declaration` | Error | `var x := 5` |
| `unsafe_property_access` | Error | `.foo` on a `Variant` |
| `unsafe_method_access` | Error | `.foo()` on a `Variant` |
| `unsafe_cast` | Error | casts the compiler cannot check |
| `unsafe_void_return` | Error | returning the result of a `void` call |
| `unsafe_call_argument` | Warning | passing a `Variant` to a typed parameter |

Two consequences worth knowing before they surprise you:

- **`:=` is banned even though the style guide allows it.** Inference gives
  you the same static type, so this costs nothing at runtime — it is a
  readability rule. Debugging a `Vector3`/`Vector2` mix-up in a physics
  function is much faster when the type is on the line you are reading than
  when it is three assignments up the call chain.
- **`is` does not narrow a type.** After `if event is InputEventMouseMotion:`
  the compiler still sees an `InputEvent`, so `event.relative` is an unsafe
  property access and will not compile. Assign to a typed local first:

  ```gdscript
  if event is InputEventMouseMotion:
      var motion: InputEventMouseMotion = event
      rotate_y(-motion.relative.x * mouse_sensitivity)
  ```

`unsafe_call_argument` is the one left at Warning. `GlyphPlane.raycast()`
genuinely returns `Variant` — a miss has to be distinguishable from a hit and
`Vector2` has no null — so the one honest `Variant` in the codebase would
otherwise need a cast at every call site to buy nothing. Null-check it and
assign to a typed local, as `spell_caster._sample_pen()` does.

If a future dependency makes a rule unworkable, change the level in
`project.godot` `[debug]` and say why in the commit. Do not silence it with
`@warning_ignore` at the call site — that hides it from everyone else.

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
| `anchor` | Left ctrl, **hold** | Pins the draw canvas in the air so the crosshair can draw on it. Released, the canvas turns with the view instead, so a half-drawn glyph can be carried around |
| `draw` | Left mouse, **hold** | Draws one stroke per hold, only while `anchor` is held; the canvas stays open between strokes |
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
