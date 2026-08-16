# Contributing

Working agreements for a 2–3 person team on a shared Godot project. These
exist because Godot's file formats punish parallel work in specific,
predictable ways — every rule below is here to prevent a merge conflict
that costs an afternoon.

---

## 1. Pin the engine version

**Everyone runs the exact same Godot patch version.**

> Project Godot version: `4.x.y` — **fill this in at 0.1.2 and do not drift.**

Scene (`.tscn`) and resource (`.tres`) formats shift between 4.x minor
versions. A teammate on a different minor silently rewrites files on save,
and the diff looks like "everything changed." If someone must upgrade,
the whole team upgrades in the same commit.

## 2. Branching

- `main` is always launchable. If `main` is broken, fixing it is the
  highest-priority task for whoever broke it.
- Feature branches: `track-a/spell-caster`, `track-b/signature-hash`,
  `track-c/room-kit`. Prefix with your track so the branch list reads as
  the plan.
- Small, frequent merges. A branch open longer than two days on a project
  this size is a merge conflict being deferred, not avoided.
- Rebase or merge — pick one as a team and stick to it. Do not mix.

## 3. Scene ownership

**Every `.tscn` has exactly one owner. Do not edit someone else's scene
without asking.**

`.tscn` is a text format, but it is not a *mergeable* text format: node
paths, sub-resource ids and property ordering all shift when the editor
rewrites a file. Two people editing the same scene produces a conflict
that is faster to redo by hand than to resolve.

| Scene | Owner |
|---|---|
| `player.tscn` | *(assign at 0.1.5)* |
| `spell_caster.tscn` | |
| `enemy_base.tscn` | |
| room kit scenes | |

Need a change in a scene you do not own? Ask the owner, or take ownership
explicitly for the duration and say so.

## 4. `project.godot` is a shared resource

Autoloads (0.1.3), the input map (0.1.4), physics layers, and rendering
settings all live in this single file, and nearly every phase adds to it.

**Rules:**
- Announce in chat *before* you edit it.
- Batch your changes: add all your autoloads and actions in one sitting,
  one commit.
- Never merge someone else's `project.godot` conflict by hand-picking
  lines. Take one side, then re-apply the other's changes through the
  editor UI.

## 5. Physics layers and input actions are named, not numbered

Set layer *names* in Project Settings the day you first need a layer.
`collision_layer = 4` in a script is unreadable and unmergeable; a named
layer is both. Same for input actions — no raw keycodes in gameplay code.

## 6. Code

- Follow the [GDScript style guide](https://docs.godotengine.org/en/stable/tutorials/scripting/gdscript/gdscript_styleguide.html):
  `snake_case` for files, functions and variables, `PascalCase` for
  classes and nodes.
- **Everything is explicitly typed** — variables, parameters, returns, loop
  variables. Both `var x = 5` and `var x := 5` are compile errors, by
  project setting. See `docs/conventions.md` §"Static typing" for the
  enforced warning list and the two patterns that need care.
- **No gameplay logic in `_input`.** Input sets intent; systems act on it.
  This is ADR 0002 and it is what keeps coop retrofittable.
- Spells resolve through the `SpellData` struct, never imperatively.
  See `docs/adr/0002-spell-data-contract.md`.
- Prefer signals over direct node references across systems. `get_node("../../Player")`
  is a merge conflict and a refactor hazard at once.
- Tunable numbers belong in a `Resource`, not a constant. Playtests change
  numbers; they should not require a code change or a rebuild.

## 7. Prototypes and tests

The `proto/` directory holds the engine-free reference implementation and
the two fun-spikes. It is not dead code — `glyph_core.js` is the
specification the GDScript port must match.

```bash
node proto/glyph_core.test.js
```

Run it before touching anything in `proto/`. When the pipeline is ported
to GDScript, port these assertions alongside it; they are the spec.

Adding a spell pattern? Run the search first — it reports the safety
margin, and a margin below 2 means one mis-stepped edge casts the wrong
spell:

```bash
node proto/find_pattern.js --len 3,4,5
```

## 8. Commits

Present tense, scoped by what changed:

```
spell: add signature canonicalisation
level: greybox rooms 1-3
fix: earth wall no longer spawns inside door volumes
```

Do not commit `.godot/`, builds, or raw telemetry CSVs — see `.gitignore`.

## 9. Assets

Every borrowed asset goes in `CREDITS.md` **in the same commit that adds
the file**. Reconstructing licences later is an archaeology dig, and
"we'll sort it before release" is how projects end up unable to ship.
