# Alpha Masterplan — Lattice Spellcaster Dungeon Crawler

**Target:** playable alpha — one handcrafted level, solo play, 4 drawable spells, combat, a puzzle room, a miniboss, win/lose loop.
**Stack:** Godot 4.x, GDScript. Architecture kept multiplayer-friendly (coop deferred to beta).
**Team:** 2–3 people, **first Godot project**. Three parallel tracks after Phase 0.5: **[A] Systems**, **[B] Glyph pipeline**, **[C] Art/Level**.
**Estimate:** ~110–135 task-hours total, including a real bug budget and engine ramp-up.

Legend: each leaf task ≤ 1h unless marked. `[cut]` = safe to drop if behind schedule. `⚖` = tradeoff decision. `🔒` = hard gate, do not proceed past it.

> **Input model: hex lattice.** Strokes snap to a triangular lattice and may only traverse adjacent edges, so classification is exact integer math on 60° turns. This is what `hex_spellcaster_prototype.html` already demonstrates. The earlier freeform plan ($P recognizer + RDP + circle fit + fuzzy "quality" score) is **dropped** — see ADR 0.2.1.

> ### Already built (engine-free pass, ~9h of the plan below)
>
> | Task | Artifact |
> |---|---|
> | 0.1.1 / 0.1.5 / 0.1.6 | `.gitignore`, [`CONTRIBUTING.md`](CONTRIBUTING.md), [`CREDITS.md`](CREDITS.md) |
> | 0.1.3 / 0.1.4 | [`docs/conventions.md`](docs/conventions.md) |
> | 0.2.1 / 0.2.2 / 0.2.3 | [`docs/adr/`](docs/adr/) |
> | 0.2.5 | [`docs/alpha-exit-criteria.md`](docs/alpha-exit-criteria.md) |
> | 2.1.3 / 2.1.4 / 2.2.1 / 2.2.2 / 2.2.3 | [`proto/glyph_core.js`](proto/glyph_core.js) + 51 passing assertions |
> | P1 | [`proto/tempo_spike.html`](proto/tempo_spike.html) — **built, needs running with people** |
> | P3 | [`proto/memory_spike.html`](proto/memory_spike.html) — **built, needs running with people** |
> | 4.3.2 / 5.1.1 / 5.1.2 / 5.2.1 / 7.3 / 7.4 | [`docs/design/`](docs/design/) |
> | 8.4 / 8.6 | [`docs/playtest-kit.md`](docs/playtest-kit.md) |
>
> Remaining hours below are therefore Godot work plus running the spikes.

---

## Phase 0 — Foundations (~15h, everyone together)

### 0.1 Project setup
- **0.1.1** Create Git repo, Godot `.gitignore`, agree on branch workflow (feature branches → main). *(30m)*
- **0.1.2** Create Godot 4 project; pick renderer; **pin the exact patch version** in the README and everyone installs it. *(45m)*
  ⚖ **Forward+ vs Compatibility:** flat-shaded style barely uses advanced lighting, and Compatibility runs on weak laptops → **Compatibility**. Note: this is *not* being chosen for a web export — web plus pointer lock plus drawing input is its own minefield and no alpha task produces a web build.
  ⚠ Pin the patch version because `.tscn` format shifts between 4.x minors; a teammate on a different minor silently corrupts scenes for everyone else.
- **0.1.3** Folder structure (`scenes/`, `scripts/`, `assets/`, `resources/`), naming conventions, autoloads (`SpellRegistry`, `AudioBus`, `Telemetry`). *(30m)*
- **0.1.4** Input map: move, jump, interact, `cast` (hold RMB), `fire` (LMB), pause. *(30m)*
- **0.1.5** **Team workflow rules.** One named owner per scene file — nobody else edits `player.tscn` without asking. `project.godot` edits (autoloads, input map) are **batched and announced in chat** before pushing. Write both into `CONTRIBUTING.md`. *(30m)*
  > `.tscn` files merge badly and `project.godot` is a single file every phase touches. With three parallel tracks this conflicts within days if it isn't a rule.
- **0.1.6** `CREDITS.md`, populated from the first borrowed asset onward. *(15m + ongoing)*

### 0.2 Architecture decisions (write mini-ADRs, one paragraph each)
- **0.2.1** ⚖ **Lattice vs freeform recognition.** Freeform ($P + geometric params + quality score) has the stronger fantasy, but **its failure mode is a wall and the lattice's is a dial.** If lattice tracing is too slow you fix it with a coarser grid, a bigger snap radius, or shorter patterns. If freeform fails on a stranger's handwriting, the only lever is loosening thresholds — which makes every shape collide with every other shape. On a first Godot project, take the risk you can turn a knob on. Also removes ~5h from the critical path, and "the parser ate my spell and I died" is the worst feel in action games. → **Lattice.** *(30m)*
- **0.2.2** ⚖ **Multiplayer-ready patterns now vs pure solo code.** Full netcode is out, but retrofitting is brutal if spells resolve imperatively. Rule: casting produces a **data struct** (pattern signature, power, params, origin) that a single `resolve_spell()` consumes; all game events via signals; no gameplay logic in `_input`. Costs ~10% overhead now, saves a rewrite at beta. → **Adopt the rule.** *(45m)*
- **0.2.3** ⚖ **Art pipeline: Blender modular kit vs Godot CSG/GridMap.** CSG greybox is faster to a playable level and fine for flat-shaded style; a Blender kit looks better but blocks level work on the art person. → **CSG/GridMap for alpha**, Blender props only for torch/door/pickups. *(30m)*
- **0.2.4** **`SpellData` struct + stub recognizer — day one, before anything else.** A fake recognizer returning a hardcoded `SpellData` so Track A can build all of Phase 3 without waiting on Track B. *(45m)*
  > The dependency map assumes this stub exists but nothing was scheduled to create it, and the real struct lives three phases deep in Track B. Build the contract first or the "parallel" tracks aren't parallel.
- **0.2.5** **Alpha exit criteria**, written down now and not renegotiated later: *a stranger finishes the level in under 20 minutes with no dev help; ≥70% of their casts are the spell they intended; zero softlocks.* *(30m)*

### 0.3 Engine ramp-up
- **0.3.1** Everyone completes one Godot 3D tutorial project end to end (scene tree, signals, `CharacterBody3D`, exporting). *(8–10h, parallel, before Phase 1)*
  > Not optional and not free. The original plan budgeted zero hours for learning the engine, which is where the 70h estimate mostly went wrong.

---

## Phase 0.5 — Fun spikes 🔒 (~9h, before any production work)

> Each spike answers one question that planning cannot. All are throwaway except P4. They exist because the alpha's three biggest unknowns are about **fun**, not code, and each is cheap to test and expensive to discover late.

- **P1 — Tempo spike.** *(2h, HTML, extends the existing prototype)* Add a countdown, a target pattern to copy, and per-attempt timing. Four people × 20 attempts.
  → **Answers:** can a 6-edge pattern be traced under pressure? What is the median time-to-draw?
  → **Go/no-go:** median ≤ 2.0s, 90th percentile ≤ 3.5s. If not, turn the dials — coarser grid, larger snap radius, shorter patterns — and re-run. **The resulting number becomes the combat tempo constant (3.2.6).**
- **P2 — Aim-draw spike.** *(3h, Godot — the team's first real engine work)* Overlay canvas, camera lock, draw → charge → click-to-fire, against a static target then a moving one. Build the world-space canvas variant as a second scene sharing the same code.
  → **Answers:** does losing aim for ~1.5s read as tactical or as helpless? Is the world-space canvas worth its complexity?
  → **Go/no-go:** if the blackout feels helpless even against a slow target, the fix is shorter patterns (feeds back into P1), not abandoning the lock.
- **P3 — Memorization spike.** *(1h, index cards or the HTML page)* Show six patterns for 60 seconds. An hour later, ask people to reproduce them.
  → **Answers:** is a grimoire of memorized sigils *the fun*, or is it homework? This is the central fun risk of the entire lattice direction and it costs one hour.
  → **Go/no-go:** if 4+ of 6 come back for most people, patterns can ship unassisted. If not, the HUD carries permanent pattern hints (7.1 grows) — fine, but you want to know now rather than at 8.4.
- **P4 — Pressure slice.** *(3h, Godot, keeper code)* One room, one spell, one melee enemy that can actually kill you. Play it 30 minutes; two outsiders play it 10.
  → **Answers:** the only question that matters — drawing under real threat is either the whole game or it isn't.
  → 🔒 **Level assembly (5.2) does not start until this passes.** Track C's 5.1 room kit builds in parallel regardless, since it's reusable either way.

---

## Phase 1 — First-Person Core [Track A] (~5.5h)

### 1.1 Player controller
- **1.1.1** Player scene: `CharacterBody3D` + capsule + `Camera3D`, mouse capture/release. *(45m)*
- **1.1.2** WASD movement + gravity, tune speed/acceleration. *(1h)*
- **1.1.3** Mouse look with sensitivity var and pitch clamp. *(30m)*
- **1.1.4** Jump (+ simple coyote time). *(30m)* `[cut: coyote]`
- **1.1.5** Footstep/land signals emitted (audio hooks later). *(30m)* `[cut]`

### 1.2 Test environment
- **1.2.1** Greybox test room (CSG): floor, walls, ramp, pit. *(30m)*
- **1.2.2** Collision checklist pass: walls, ramps, edges, ceiling bump. *(30m)*

### 1.3 Interaction
- **1.3.1** Raycast interactor from camera + `Interactable` interface (levers, pickups use this later). *(45m)*
- **1.3.2** Debug overlay autoload: FPS, player state, last-cast readout. *(30m)*

---

## Phase 2 — Lattice Glyph Pipeline [Track B, parallel with 1 & 5] (~7h)

> **[`proto/glyph_core.js`](proto/glyph_core.js) is the reference implementation and is already written**, along with 51 assertions in `glyph_core.test.js` that are the specification. This phase is now a *port*, not a design task: translate the functions, port the assertions alongside them, and keep the field names in `recognize()`'s return value (they are the ADR 0002 contract).
>
> Two things in the original HTML prototype must **not** be ported: the proximity clustering (`computeClusters`) and the shape-family classifier (`classifyPath`/`classifyCycle`/`classifyComponent`). Both are superseded — see 2.1.2 and 2.1.4.
>
> **Do not port two things from the prototype:** the proximity clustering (`computeClusters`) and the shape-family classifier (`classifyPath`/`classifyCycle`/`classifyComponent`). See 2.1.4 and ADR note below.

### 2.1 Lattice & signature
- **2.1.1** `LatticeGeometry` resource: spacing, adjacency test, point generation, screen↔lattice projection with the transform **abstracted** (so the world-space canvas from P2 is a swap, not a rewrite). *(1h)*
- **2.1.2** Stroke capture: nearest-point snap, adjacency gate, backtrack-to-erase, no-reuse-of-edges. *(1h)*
  ⚖ **One glyph = one continuous drag; release commits.** The prototype clusters separate strokes by proximity, which in combat merges your previous glyph into your next one and casts something you didn't draw. Cut clustering, and the multi-token parser with it.
- **2.1.3** Turn-sequence extraction (direction sectors → signed turns). *(45m)*
- **2.1.4** **Canonical signature hash**, invariant under rotation and reflection, + unit tests. *(1h)*
  ⚖ **Exact signatures vs shape families.** The prototype classifies families (`triangle`, `hexagon`), which caps the game at ~8 spells and makes *any* 3-corner loop a fireball — accidental casts everywhere. A canonicalized turn-sequence hash is **less** code than the family classifier and scales to a real grimoire. → **Exact signatures.**

### 2.2 Spells & scoring
- **2.2.1** `PatternDictionary` resource mapping signature → spell id; 4 alpha patterns authored in-inspector. *(45m)*
- **2.2.2** **Power = speed × economy.** Time-to-draw against a per-pattern par time, multiplied by stroke economy (wasted edges and backtracks). Both exact integers; ships as a tunable `Resource`. *(45m)*
  > The lattice has no fuzzy "quality" axis, but it still has a skill axis. This preserves the power-scaling pillar the original plan wanted — the input just changes from *how neatly* to *how fast and how cleanly routed*, which is also far more legible to the player.
- **2.2.3** Nearest-pattern lookup within edit distance 1, for near-miss feedback (3.1.5). *(45m)*

### 2.3 Test harness
- **2.3.1** Debug scene: 2D lattice canvas → live readout of edges, turn sequence, signature, matched spell, speed/economy score, resulting `SpellData`. *(1h)*

---

## Phase 3 — Drawing & Casting In-Game [Track A, needs 0.2.4 stub] (~18.5h)

### 3.1 Drawing overlay
- **3.1.1** Overlay canvas: hold `cast` → translucent full-screen lattice, **camera locks**, world stays visible underneath. Canvas transform abstracted per 2.1.1. *(2h)*
  ⚖ **Aim vs draw — the central input collision.** The mouse *is* the aim device, so any draw is also an aim blackout; there is no version of this where you keep aiming while drawing. → **Camera locks during the draw; the spell then charges and fires on the next `fire` click at your current aim.** This turns the blackout from a liability into the core tactical loop: draw behind a pillar, step out, release.
  ⚖ **Deferred alternative:** the world-space canvas (plane fixed by the first stroke) is the more distinctive version and P2 prototypes it. Because the transform is abstracted it stays a one-node swap — if P2 says it's magic, take it; if not, the overlay already shipped.
- **3.1.2** Lattice + stroke rendering (dots, traversed edges, rubber-band preview). *(1h)*
- **3.1.3** ⚖ **Movement while drawing: freeze vs slow-walk vs free.** Freeze plus a camera lock is a death sentence, not risk/reward; free makes drawing spammy. → **Slow-walk (30% speed)**, exposed as config; "must stand still" becomes a property of specific powerful spells at beta. *(30m)*
- **3.1.4** Cancel + auto-timeout on idle stroke. *(30m)*
  ⚠ **Esc is double-bound** (cancel vs pause 6.2), and Esc under `MOUSE_MODE_CAPTURED` is a classic Godot input-priority bug. Rule: **Esc cancels the draw if drawing, otherwise pauses.**
- **3.1.5** **Near-miss failure feedback:** show the drawn pattern beside the nearest known pattern (via 2.2.3), not a bare fizzle. *(45m)*
  > A stranger whose glyph failed learns nothing from a puff of smoke. On a lattice the geometry is exact, so the diff is exact — this converts the most rage-inducing moment in the game into a teaching moment.
- **3.1.6** Charge → `fire` release. Targeted spells hold until the click; self/instant spells (ward) resolve immediately with no charge step. *(1h)*

### 3.2 Cast pipeline
- **3.2.1** `SpellCaster` node: consumes `SpellData`, looks up `SpellRegistry`, spawns effect scene. Unknown → fizzle. *(45m)*
- **3.2.2** `SpellRegistry` autoload mapping spell id → packed scene + base stats. *(30m)*
- **3.2.3** Cooldown/cast-rate guard (prevents draw-spam). *(30m)*
- **3.2.4** **Track B integration:** replace the 0.2.4 stub with the real pipeline. *(1.5h)*
  > The dependency map draws this arrow and budgeted zero hours for it. Integration is never free.
- **3.2.5** **Cast telemetry.** Every cast appends a CSV row: pattern drawn, matched spell or miss, draw time, edge economy, fizzled. *(45m)*
  > The single highest-value hour in this plan. Without it, the tuning decision at 8.4 — the alpha's own stated key risk — is guesswork from watching someone's face. With it, it's a spreadsheet you can sort.
- **3.2.6** **Combat tempo constant.** P1's median draw time goes into a tuning resource; enemy move speed, aggro radius and attack windup are all derived from it. *(1h)* 🔒 **Blocks all of 4.2.**
  > The original plan designed two enemies and a miniboss with no shared number for how long a cast takes. That's how you get combat that's either trivial or unplayable — and you don't find out until Phase 8.

### 3.3 Alpha spell set (4 spells)
> ⚖ **Breadth vs depth:** 4 polished spells covering the archetypes (projectile, hitscan, self, summon) beats 8 rough ones — each archetype is a reusable base for beta.
- **3.3.1** Projectile base scene: speed, damage, gravity flag, hit detection, power scaling hook. *(1h)*
- **3.3.2** **Fireball:** projectile + AoE explosion, damage scales with power. *(1h)*
- **3.3.3** **Lightning:** hitscan ray + instant damage + beam visual. *(1h)*
- **3.3.4** **Ward:** self-effect archetype — brief damage-reduction shield, no charge step. *(45m)*
- **3.3.5** **Earth wall:** spawns blocking geometry, size scales with power, timed despawn. *(1.5h)*
  ⚠ Must be a real `StaticBody3D` — it has to **stop projectiles and break the 4.2.4 line-of-sight ray**, which is the entire point of the spell. A `NavigationObstacle3D` alone only nudges pathfinding. Ship both.
  ⚠ **Softlock guard:** cap at 2 live walls, forbid spawning inside door volumes, guarantee despawn. Otherwise players seal themselves into the puzzle room or the miniboss arena, whose door locks during the fight (5.2.5).
- **3.3.6** On-cast power feedback: power % popup + glyph flash color. *(45m)*

### 3.4 Minimal VFX
- **3.4.1** One `CPUParticles3D` recipe per element (shared material, recolored). *(1h)* `[cut to: fireball only]`
  > CPU rather than GPU particles: GPU particle feature support on the Compatibility backend has gaps across 4.x, and at alpha particle counts the cost difference is irrelevant.

---

## Phase 4 — Combat & Enemies [Track A, needs 3.2.6] (~10h)

### 4.1 Health & damage framework
- **4.1.1** `Health` component (signals: damaged, died) + damage struct. *(45m)*
  > **No element field.** Nothing in the alpha resists or reacts to elements, so it's dead weight implying content that doesn't exist. Add it at beta alongside the resistances that give it meaning.
- **4.1.2** Player HP + death state (input lock, fade). *(45m)*
- **4.1.3** Player hurt feedback: screen flash + camera kick. *(30m)*

### 4.2 Enemies (2 types for alpha)
> ⚖ Respawning/immortal/motion-sensing enemies are all beta material. Alpha needs the melee+ranged **synergy pair** only; it proves the room-combat concept. All timings derive from the 3.2.6 tempo constant.
- **4.2.1** Enemy base scene: `NavigationAgent3D`, state machine (idle/chase/attack), chase via nav. *(2.5h — first contact with the nav system)*
- **4.2.2** Melee enemy: attack range, telegraphed windup, hit. *(45m)*
- **4.2.3** Ranged enemy: projectile attack, keeps distance. *(1h)*
- **4.2.4** Line-of-sight check (raycast) gating aggro — must respect earth walls. *(30m)*
- **4.2.5** Enemy death: poof particles + optional loot drop hook. *(30m)*
- **4.2.6** Miniboss: melee base with 5× HP, faster phase under 50%, distinct color/scale. *(1h)* `[cut: phase change]`

### 4.3 Navigation & balance
- **4.3.1** `NavigationRegion3D` bake on test room; verify pathing around earth walls. *(45m)*
  ⚖ **Earth wall vs navmesh:** dynamic rebake is expensive, `NavigationObstacle3D` is cheap but approximate → obstacle for pathing, real collision for projectiles and LoS (3.3.5).
- **4.3.2** **Balance resource + TTK targets:** spell damage, enemy HP, target time-to-kill, all in one editable resource. *(1h)*
  > The miniboss is the alpha's only real balance test and nothing in the original plan tuned it.

---

## Phase 5 — The Level [Track C; 5.2 gated on P4] (~13h)

> ⚖ **Handcrafted vs procedural for alpha:** procgen is a core pillar (Barony-style room pool), but it doubles level-phase cost and hides tuning problems. → **Handcraft one level out of modular rooms**, so the room kit and door-socket conventions are procgen-ready at beta. Enforce: every room on a grid with standard door positions.

### 5.1 Room kit & look *(safe to build before P4 — reusable either way)*
- **5.1.1** Grid conventions doc (cell size, door socket positions) + 4 CSG/GridMap pieces: corridor, small room, large room, corner. *(1.5h)*
- **5.1.2** Flat-shaded palette material set (3–4 stone tones + accent); test lattice overlay readability against all of them. *(45m)*
- **5.1.3** Lighting recipe: dark ambient + torch prop (mesh + omni light + flicker). *(45m)*
- **5.1.4** Props: door, lever, pedestal, health pickup mesh, spellbook mesh. *(1h)*

### 5.2 Level assembly 🔒 *(requires P4 to have passed)*
- **5.2.1** Paper layout: 7–8 rooms — teach → combat ×2 → puzzle → combat → spellbook reward → miniboss → exit. *(45m)*
- **5.2.2** Greybox assembly from kit + navmesh bake. *(3h — the first bake never works)*
- **5.2.3** Locked door + lever wiring (uses 1.3.1 interactor). *(45m)*
- **5.2.4** Puzzle room: brazier lit by **any offensive spell**, with a lever fallback. *(1h)*
  ⚖ Requiring one specific spell hard-locks exactly the player whose pattern for that spell isn't landing. Accept any offensive cast, and leave a manual lever for the player who's given up.
- **5.2.5** Miniboss arena: bigger room, pillars for cover, arena door locks during fight. *(45m)*

### 5.3 Population & rewards
- **5.3.1** Enemy placement: synergy pairs (melee fronting ranged), difficulty ramp across rooms. *(45m)*
- **5.3.2** Spellbook pickup unlocks 4th spell (start with 3), and **shows its pattern on pickup**. *(45m)*
  > Pick a non-essential spell to withhold — if the withheld spell is the puzzle's tool, the reward gates the thing that teaches it.
- **5.3.3** Health pickups placed after hard fights. *(30m)*
- **5.3.4** **First-teach room:** one prompt, one harmless target, one pattern shown on screen. *(1h)*
  > 8.4 asks "can they discover drawing?" and nothing in the original plan ever taught it. The HUD hints in 7.1 are a reminder, not an onboarding.

---

## Phase 6 — Game Loop [Track A or C] (~3h)

- **6.1** Main menu: title, Play, Quit, sensitivity + volume sliders. *(45m)*
- **6.2** Pause menu (resume/quit, releases mouse). *(30m)*
- **6.3** Death → "You died" → restart level. *(45m)*
  ⚖ **Full reset; the spellbook is re-collectable.** No run-state persistence, no `GameState` autoload. The original plan reloaded the scene, which silently wiped the 5.3.2 unlock — this makes that behaviour intentional and free.
- **6.4** Win: exit door after miniboss → end screen with run stats (time, spells cast, avg power). *(45m)*
- ~~Saving~~ — not needed, one level. `[deferred]`

---

## Phase 7 — HUD, Audio, Feel [any track] (~5.5h)

- **7.1** HUD + **grimoire**: health bar, and an in-game pattern reference. *(1.5h)*
  > Non-optional on the lattice branch — memorized sigils need somewhere to be learned. **P3 decides the form:** a menu you consult if patterns stick, permanent HUD hints if they don't.
- **7.2** Crosshair + cast-mode indicator (crosshair morphs while drawing/charged). *(30m)*
- **7.3** SFX pass: ~10 sounds (cast, fizzle, per-spell impact, hurt, enemy die, pickup, door). Free packs are fine — log every one in `CREDITS.md`. *(1h)*
- **7.4** **Drawing audio:** rising tone per lattice edge traversed. *(30m)*
  > The signature verb of the game had no sound in the original list of ten. This is the primary juice for the thing the whole design is built around.
- **7.5** **Leniency + accessibility options:** snap radius and grid density as menu sliders. *(45m)*
  > The prototype already exposes both as live controls, so this is mostly wiring existing dials to a menu — and it's the escape hatch if 8.4 goes badly.
- **7.6** Ambient dungeon loop + reverb bus. *(30m)* `[cut]`
- **7.7** Juice pass: hitstop on kills, slight screenshake on explosion. *(45m)* `[cut]`

---

## Phase 8 — Alpha Hardening (~4.5h + bug budget)

- **8.1** Full playthrough playtest #1 (dev), bug list triage into blocker/minor. *(1h)*
- **8.2** **Fix blockers.** *(bug budget: 15–20% of total ≈ 18h)*
  > The original plan budgeted one hour. No alpha in history has been one hour of bugs away from shipping.
- **8.3** Perf pass: profiler on worst room; check particle count, nav cost. *(45m)*
- **8.4** Blind playtest #2 (someone who's never played) — **review the 3.2.5 telemetry with them**, not just their reactions. *(1.5h)*
  ⚖ The alpha's key risk on this branch is no longer recognition accuracy (the lattice is exact) but **pattern recall and draw speed under pressure**. If strangers can't recall patterns, promote the grimoire to permanent HUD hints; if they're too slow, shorten patterns. Both are dials — that was the point of choosing the lattice.
- **8.5** Export builds (Win/Linux), smoke-test each. *(45m)*
  ⚖ **macOS cut for alpha.** Unsigned Mac builds are Gatekeeper-blocked on testers' machines with no obvious bypass; notarization is a half-day, not 45 minutes. Revisit at beta.
- **8.6** Ship: zip or private itch.io page + 5-question feedback form. *(30m)*

---

## Alpha exit criteria

The alpha is done when all of these are true — written in Phase 0 (0.2.5), not renegotiated at the end:

1. A stranger finishes the level in **under 20 minutes with no dev help**.
2. **≥70% of their casts are the spell they intended** (measured from the 3.2.5 telemetry, not from vibes).
3. **Zero softlocks** across three full playthroughs, including deliberate earth-wall abuse in every doorway.
4. Win and lose states both reachable and both exit cleanly to the menu.
5. Win + Linux builds launch from a clean machine with no console errors.

---

## Dependency & parallelism map

```
Phase 0 (all)
  └─ 0.3 ramp-up ─ 0.5 spikes 🔒 ─┬── Track A: 1 → 3 → 4 → 6 ─┐
     (P1 → 3.2.6)                 ├── Track B: 2 ──→ (3.2.4)   ├→ integrate → 7 → 8
     (P4 🔒 gates 5.2)            └── Track C: 5.1 → 5.2 → 5.3 ┘
```

Critical path: **0 → 0.5 → 2 → 3 → 4 → 8**. Track B still gates casting, so start it the day Phase 0.5 clears — but Track A builds all of Phase 3 against the 0.2.4 stub and is never blocked by it.

Three things now gate rather than merely inform: **P1** produces the tempo constant that 4.2 depends on, **P4** gates level assembly, and **3.2.6** gates enemy tuning. Everything else can slip without cascading.

## Global tradeoffs summary

| Decision | Choice for alpha | Deferred alternative |
|---|---|---|
| Input model | Hex lattice, exact integer classification | Freeform recognition, if the spikes reject it |
| Spell identity | Canonical signature hash (rotation + reflection invariant) | Shape families; multi-glyph combos |
| Glyph commit | One continuous drag, release commits | Multi-stroke clustering + containment parser |
| Power scaling | Speed × stroke economy | Fuzzy draw quality |
| Aim vs draw | Screen overlay, camera locks, draw → charge → fire | World-space canvas fixed by the first stroke |
| Engine language | GDScript everywhere | GDExtension if profiling demands it |
| Renderer | Compatibility (no web export claimed) | Forward+ at beta |
| Particles | `CPUParticles3D` | GPU particles once off Compatibility |
| Level | Handcrafted from procgen-ready kit | Room-pool procgen at beta |
| Multiplayer | Solo, data-driven spell resolution | Coop netcode at beta |
| Spells | 4, one per archetype | Combos, traps, two-player spells |
| Enemies | Melee + ranged + miniboss | Respawning/immortal/vision-gimmick |
| Damage typing | None | Element types + resistances |
| Drawing movement | Slow-walk, configurable | Per-spell requirements |
| Death | Full reset, spellbook re-collectable | Persistent unlocks / meta-progression |
| Platforms | Win + Linux | macOS (needs notarization), web |
