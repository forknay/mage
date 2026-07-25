# Alpha Masterplan — Spell-Drawing Dungeon Crawler

**Target:** playable alpha — one handcrafted level, solo play, 4 drawable spells, combat, a puzzle room, a miniboss, win/lose loop.
**Stack:** Godot 4.x, GDScript. Architecture kept multiplayer-friendly (coop deferred to beta).
**Team:** 2–3 people. Three parallel tracks after Phase 0: **[A] Systems**, **[B] Glyph pipeline**, **[C] Art/Level**.
**Estimate:** ~70–85 task-hours total.

Legend: each leaf task ≤ 1h (implementation + testing). `[cut]` = safe to drop if behind schedule. `⚖` = tradeoff decision.

---

## Phase 0 — Foundations (~4h, everyone together)

### 0.1 Project setup
- **0.1.1** Create Git repo, Godot `.gitignore`, agree on branch workflow (feature branches → main). *(30m)*
- **0.1.2** Create Godot 4 project; pick renderer. *(30m)*
  ⚖ **Forward+ vs Compatibility:** Compatibility runs on weak laptops and allows a web export later (nice for playtests); Forward+ has better lighting. Flat-shaded style barely uses advanced lighting → **Compatibility recommended**, revisit at beta.
- **0.1.3** Folder structure (`scenes/`, `scripts/`, `assets/`, `resources/`), naming conventions, list planned autoloads (`GameState`, `SpellRegistry`, `AudioBus`). *(30m)*
- **0.1.4** Input map: move, jump, interact, `cast` (hold RMB), pause. *(30m)*

### 0.2 Architecture decisions (write 3 mini-ADRs, one paragraph each)
- **0.2.1** ⚖ **Glyph pipeline: port to GDScript vs GDExtension (C++) vs embed JS.** Port to GDScript: fastest iteration, one language, plenty fast for <1k stroke points; GDExtension only if profiling shows recognition >5ms. Embedding the JS demo is a dead end (no web view in-game). → **Port**, keep the HTML demo as reference/test oracle. *(45m — includes skimming demo code to scope the port)*
- **0.2.2** ⚖ **Multiplayer-ready patterns now vs pure solo code.** Full netcode is out, but retrofitting is brutal if spells resolve imperatively. Rule: spell casting produces a **data struct** (element, power, params, origin) that a single `resolve_spell()` consumes; all game events via signals; no gameplay logic in `_input`. Costs ~10% overhead now, saves a rewrite at beta. → **Adopt the rule.** *(45m)*
- **0.2.3** ⚖ **Art pipeline: Blender modular kit vs Godot CSG/GridMap.** CSG greybox is faster to a playable level and fine for flat-shaded style; Blender kit looks better but blocks level work on the art person. → **CSG/GridMap for alpha**, Blender props only for torch/door/pickups. *(30m)*

---

## Phase 1 — First-Person Core [Track A] (~5h)

### 1.1 Player controller
- **1.1.1** Player scene: `CharacterBody3D` + capsule + `Camera3D`, mouse capture/release. *(30m)*
- **1.1.2** WASD movement + gravity, tune speed/acceleration. *(45m)*
- **1.1.3** Mouse look with sensitivity var and pitch clamp. *(30m)*
- **1.1.4** Jump (+ simple coyote time). *(30m)* `[cut: coyote]`
- **1.1.5** Footstep/land signals emitted (audio hooks later). *(30m)* `[cut]`

### 1.2 Test environment
- **1.2.1** Greybox test room (CSG): floor, walls, ramp, pit. *(30m)*
- **1.2.2** Collision checklist pass: walls, ramps, edges, ceiling bump. *(30m)*

### 1.3 Interaction
- **1.3.1** Raycast interactor from camera + `Interactable` interface (levers, pickups use this later). *(45m)*
- **1.3.2** Debug overlay autoload: FPS, player state, last-spell readout. *(30m)*

---

## Phase 2 — Glyph Pipeline Port [Track B, parallel with 1 & 5] (~11h)

> Port order mirrors the compiler stages. The HTML demo is the test oracle: for every stage, record fixture strokes in the demo, export as JSON, assert same output in Godot.

### 2.1 Data model & preprocessing
- **2.1.1** `Stroke`/`Glyph` types (arrays of Vector2 + timestamps); JSON fixture loader. *(45m)*
- **2.1.2** Resampling to N points + unit tests vs fixtures. *(45m)*
- **2.1.3** Normalization (translate to centroid, scale to unit box) + tests. *(45m)*

### 2.2 Lexer — $P recognizer
- **2.2.1** Port $P point-cloud matching core (greedy cloud distance). *(1h)*
- **2.2.2** Port procedural template generation. *(1h)*
- **2.2.3** Template set for all 7 shapes (triangle, square, circle, arc, zigzag, star, line). *(45m)*
- **2.2.4** Classification test suite: ≥5 recorded hand-drawn fixtures per shape, target ≥90% accuracy. *(1h)*

### 2.3 Geometric backend — parameter extraction only
> Per your earlier finding: $P classifies, geometric extracts parameters. Don't re-litigate RDP as classifier.
- **2.3.1** Port Kåsa circle fit (radius/center for circles/arcs). *(45m)*
- **2.3.2** Port RDP corner extraction (corner positions for triangle/square/star). *(45m)*
- **2.3.3** Per-shape quality score (0–1) + global cleanliness multiplier; tests with deliberately sloppy fixtures. *(1h)*
  ⚖ **Quality formula tuning:** too punishing = frustrating, too lenient = mechanic is meaningless. Ship a config resource with tunable curve so playtests can adjust without code changes.

### 2.4 Parser
- **2.4.1** Containment forest from token bounding shapes + tests. *(1h)*
- **2.4.2** Edge graph (adjacency/connection between tokens) + tests. *(45m)*
  `[cut for alpha: multi-glyph combos — alpha spells can be single-shape, keep parser but only fireball-in-circle style combos if time allows]`

### 2.5 Semantics & codegen
- **2.5.1** Shape→element mapping as a Godot `Resource` (data-driven, editable in inspector). *(30m)*
- **2.5.2** `SpellData` struct + power calculation (per-shape quality × cleanliness). This is the data contract from ADR 0.2.2. *(45m)*

### 2.6 In-engine test harness
- **2.6.1** Debug scene: 2D draw canvas → shows tokens, quality, AST, resulting `SpellData` live. *(1h)*
- **2.6.2** Stroke record/replay in harness (grow the fixture set from real play). *(45m)* `[cut]`

---

## Phase 3 — Drawing & Casting In-Game [Track A, needs 2.5] (~8h)

### 3.1 Drawing overlay
- **3.1.1** Fullscreen overlay: hold `cast` → capture mouse strokes; release/confirm → send to pipeline. *(45m)*
- **3.1.2** Stroke rendering (Line2D trail with fade); clear on cast/cancel. *(45m)*
- **3.1.3** ⚖ **Movement while drawing: freeze vs slow-walk vs free.** Freeze = high risk/reward, punishing solo; free = drawing becomes spammy. → **Slow-walk (30% speed) as default**, expose as config; "must stand still" becomes a property of specific powerful spells later (matches your brainstorm). *(30m)*
- **3.1.4** Cancel (Esc) + auto-timeout on idle stroke. *(30m)*
- **3.1.5** Recognition failure feedback (glyph shatters/fizzle). *(30m)*

### 3.2 Cast pipeline
- **3.2.1** `SpellCaster` node: consumes `SpellData`, looks up `SpellRegistry`, spawns effect scene. Unknown/failed → fizzle. *(45m)*
- **3.2.2** `SpellRegistry` autoload mapping element→packed scene + base stats. *(30m)*
- **3.2.3** Cooldown/cast-rate guard (prevents draw-spam). *(30m)*

### 3.3 Alpha spell set (4 spells)
> ⚖ **Breadth vs depth:** 4 polished spells covering the archetypes (projectile, hitscan, self, summon) beats 8 rough ones — each archetype is a reusable base for beta.
- **3.3.1** Projectile base scene: speed, damage, gravity flag, hit detection, power scaling hook. *(1h)*
- **3.3.2** **Fireball** (triangle): projectile + AoE explosion, damage scales with quality. *(1h)*
- **3.3.3** **Lightning** (zigzag): hitscan ray + instant damage + beam visual. *(1h)*
- **3.3.4** **Ward/heal** (arc): self-effect archetype — brief damage-reduction shield. *(45m)*
- **3.3.5** **Earth wall** (square): spawns blocking mesh, size scales with quality, timed despawn. *(1h)*
- **3.3.6** On-cast quality feedback: power % popup + glyph flash color. *(45m)*

### 3.4 Minimal VFX
- **3.4.1** One `GPUParticles3D` recipe per element (shared material, recolored). *(1h)* `[cut to: fireball only]`

---

## Phase 4 — Combat & Enemies [Track A, needs 3.3.1] (~7h)

### 4.1 Health & damage framework
- **4.1.1** `Health` component (signals: damaged, died), damage struct with element type. *(45m)*
- **4.1.2** Player HP + death state (input lock, fade). *(45m)*
- **4.1.3** Player hurt feedback: screen flash + camera kick. *(30m)*

### 4.2 Enemies (2 types for alpha)
> ⚖ Your brainstorm has respawning/immortal/motion-sensing enemies — all beta material. Alpha needs the melee+ranged **synergy pair** only; it proves the room-combat concept.
- **4.2.1** Enemy base scene: `NavigationAgent3D`, state machine (idle/chase/attack), chase via nav. *(1h)*
- **4.2.2** Melee enemy: attack range, windup, hit. *(45m)*
- **4.2.3** Ranged enemy: projectile attack, keeps distance. *(1h)*
- **4.2.4** Line-of-sight check (raycast) gating aggro. *(30m)*
- **4.2.5** Enemy death: poof particles + optional loot drop hook. *(30m)*
- **4.2.6** Miniboss: melee base with 5× HP, faster phase under 50%, distinct color/scale. *(1h)* `[cut: phase change]`

### 4.3 Navigation
- **4.3.1** `NavigationRegion3D` bake on test room; verify pathing around earth walls (rebake or obstacle). *(45m)*
  ⚖ **Earth wall vs navmesh:** dynamic rebake is expensive; `NavigationObstacle3D` is cheap but approximate → obstacle for alpha.

---

## Phase 5 — The Level [Track C, parallel from Phase 1] (~8h)

> ⚖ **Handcrafted vs procedural for alpha:** procgen is a core pillar (Barony-style room pool), but it doubles level-phase cost and hides tuning problems. → **Handcraft one level out of modular rooms**, so the room kit and door-socket conventions are procgen-ready at beta. Enforce: every room built on a grid with standard door positions.

### 5.1 Room kit & look
- **5.1.1** Grid conventions doc (cell size, door socket positions) + 4 CSG/GridMap pieces: corridor, small room, large room, corner. *(1h)*
- **5.1.2** Flat-shaded palette material set (3–4 stone tones + accent); test glyph overlay readability against them. *(45m)*
- **5.1.3** Lighting recipe: dark ambient + torch prop (mesh + omni light + flicker). *(45m)*
- **5.1.4** Props: door, lever, pedestal, health pickup mesh, spellbook mesh. *(1h)*

### 5.2 Level assembly
- **5.2.1** Paper layout: 7–8 rooms — entry → combat ×2 → puzzle → combat → spellbook reward → miniboss → exit. *(45m)*
- **5.2.2** Greybox assembly from kit + navmesh bake. *(1h)*
- **5.2.3** Locked door + lever wiring (uses 1.3.1 interactor). *(45m)*
- **5.2.4** Puzzle room: solved with a spell (e.g., earth wall holds a pressure plate, or fireball lights a brazier). *(1h)*
  ⚖ Pick a puzzle needing a spell the player already has — no softlocks. Brazier+fireball is simplest and teaches nothing new mid-combat.
- **5.2.5** Miniboss arena: bigger room, pillars for cover, arena door locks during fight. *(45m)*

### 5.3 Population & rewards
- **5.3.1** Enemy placement: synergy pairs (melee fronting ranged), difficulty ramp across rooms. *(45m)*
- **5.3.2** Spellbook pickup unlocks 4th spell (start with 3) — proves the unlock loop from your brainstorm. *(45m)*
- **5.3.3** Health pickups placed after hard fights. *(30m)*

---

## Phase 6 — Game Loop [Track A or C] (~2.5h)

- **6.1** Main menu: title, Play, Quit, sensitivity+volume sliders. *(45m)*
- **6.2** Pause menu (resume/quit, releases mouse). *(30m)*
- **6.3** Death → "You died" → restart level (full reset via scene reload). *(30m)*
- **6.4** Win: exit door after miniboss → end screen with run stats (time, spells cast, avg quality). *(45m)*
- ~~Saving~~ — not needed, one level. `[deferred]`

---

## Phase 7 — HUD, Audio, Feel [any track] (~4h)

- **7.1** HUD: health bar, unlocked-spell glyph hints (small icons of the shapes). *(45m)*
- **7.2** Crosshair + cast-mode indicator (crosshair morphs while drawing). *(30m)*
- **7.3** SFX pass: ~10 sounds (cast, fizzle, per-spell impact, hurt, enemy die, pickup, door). Free packs are fine. *(1h)*
- **7.4** Ambient dungeon loop + reverb bus. *(30m)* `[cut]`
- **7.5** Juice pass: hitstop on kills, slight screenshake on explosion. *(45m)* `[cut]`

---

## Phase 8 — Alpha Hardening (~5h)

- **8.1** Full playthrough playtest #1 (dev), bug list triage into blocker/minor. *(1h)*
- **8.2** Fix blockers. *(1h budget, split further if needed)*
- **8.3** Perf pass: profiler on worst room; check recognition time, particle count, nav cost. *(45m)*
- **8.4** Blind playtest #2 (someone who's never played) — watch for: can they discover drawing? do glyphs recognize for a stranger's handwriting? *(1h)*
  ⚖ This is the alpha's key risk: **recognition tuned to your own strokes.** If strangers fail, loosen $P threshold and widen quality curve before anything else.
- **8.5** Export builds (Win/Linux/Mac), smoke-test each. *(45m)*
- **8.6** Ship: zip or private itch.io page + 5-question feedback form. *(30m)*

---

## Dependency & parallelism map

```
Phase 0 (all) ──┬── Track A: 1 → 3 → 4 → 6 ─┐
                ├── Track B: 2 ──────→ (3.2)  ├→ integrate on level → 7 → 8
                └── Track C: 5.1 → 5.2 → 5.3 ┘
```

Critical path: **0 → 2 → 3 → 4 → 8** (glyph pipeline gates casting). Track B is the schedule risk — start it day one, and Track A can build Phase 3 against a *stubbed* `SpellData` (hardcoded fake output) so it never blocks.

## Global tradeoffs summary

| Decision | Choice for alpha | Deferred alternative |
|---|---|---|
| Engine language | GDScript everywhere | GDExtension if recognition >5ms |
| Renderer | Compatibility | Forward+ at beta |
| Level | Handcrafted from procgen-ready kit | Room-pool procgen at beta |
| Multiplayer | Solo, data-driven spell resolution | Coop netcode at beta |
| Spells | 4, one per archetype | Combos, traps, two-player spells |
| Enemies | Melee + ranged + miniboss | Respawning/immortal/vision-gimmick |
| Drawing movement | Slow-walk, configurable | Per-spell requirements |
| Recognition | $P classify + geometric params | FFT signature third backend |
