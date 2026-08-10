# Art direction — palette, lighting, props

Masterplan tasks 5.1.2, 5.1.3, 5.1.4. The alpha is flat-shaded greybox
(ADR 0003), so the entire look is carried by palette, light and silhouette.

---

## 1. The constraint that drives everything

**The glyph overlay must stay readable against every surface in the game.**

The player draws on a translucent full-screen canvas with the world visible
underneath (masterplan 3.1.1). If a wall material and the glyph colour sit
close in value, the pattern disappears exactly when the player most needs
to see it — mid-cast, under pressure.

So the palette is chosen *against* the glyph colour, not independently of
it. Stone tones are **cool, desaturated and dark**; the glyph is **warm,
saturated and bright**. Every other colour decision follows from keeping
that separation.

## 2. Palette

| Role | Hex | Value | Use |
|---|---|---|---|
| `stone_dark` | `#2B2B28` | 17% | Floors, deep recesses |
| `stone_mid` | `#3D3D38` | 24% | Primary wall tone |
| `stone_light` | `#55554D` | 33% | Trim, pillars, ledges |
| `stone_accent` | `#46554E` | 32% | Cool green-grey, sparing — doorframes, sockets |
| `metal` | `#6B6459` | 40% | Levers, door hardware |
| — | | | |
| `glyph` | `#D4A017` | 66% | The drawn stroke |
| `glyph_dim` | `#7A6220` | 38% | Untraversed lattice dots |
| `torch` | `#FFB457` | 78% | Torch light colour |
| `hostile` | `#C25A44` | 47% | Enemy accents, damage flash |
| `heal` | `#4EA172` | 58% | Health pickups, ward shield |

**Value separation:** every stone tone sits between 17% and 40%; the glyph
sits at 66%. That ~26-point gap against the lightest surface is what
guarantees readability, and it is the number to protect if the palette gets
revised.

**Test it (5.1.2):** put a quad of all five stone tones behind the draw
overlay and confirm the stroke reads on all of them, including under full
torch light where `stone_light` is at its brightest.

### Material setup

One `StandardMaterial3D` per tone, shared across every surface. Settings:

- Shading mode: **unshaded is wrong** — use per-pixel with roughness 1.0,
  metallic 0.0. Flat-shaded means low-poly and hard normals, not unlit;
  the level needs light falloff to read depth.
- No textures at alpha. If a surface needs visual interest, it needs
  geometry or a light, not a texture.
- Enable vertex colour if the greybox needs local variation without new
  materials.

## 3. Lighting (5.1.3)

**Dark ambient, warm point sources.** The dungeon should be legible but not
evenly lit — torches are what make the flat palette read as three
dimensional.

| Setting | Value |
|---|---|
| Ambient light | `#1A1D22`, energy 0.15 |
| Fog | enabled, `#1A1D22`, density 0.008 |
| Torch `OmniLight3D` | colour `#FFB457`, energy 2.2, range 9m |
| Torch flicker | energy × noise, ±12%, ~7Hz |

Torch flicker should be **subtle**. Big flicker reads as a broken light,
not a flame, and it makes the glyph overlay's legibility fluctuate — which
is the one thing the palette exists to prevent.

Placement: one torch per corridor segment, two per small room, four per
large room. Enough that the player never draws in the dark; sparse enough
that rooms have shape.

**Arena exception:** the miniboss room gets a cooler, brighter key so the
fight reads clearly, plus rim lighting on the pillars so cover is legible
at a glance. A player breaking line of sight mid-cast needs to see where
the cover is without looking for it.

## 4. Props (5.1.4)

Five authored meshes, Blender, low-poly, hard normals, no textures — they
take the shared palette materials.

| Prop | Notes |
|---|---|
| **Torch** | Wall-mounted bracket + flame quad. The flame is a billboard, not geometry. Paired with the `OmniLight3D` above. |
| **Door** | 3m × 3m to match the socket. Needs a clear locked/unlocked read — a visible bar or glow, not just a colour change. |
| **Lever** | Two states, 45° apart, with enough throw that the animation is visible from across the room. |
| **Pedestal** | Holds the spellbook. Waist height so the pickup prompt sits near the crosshair. |
| **Pickups** | Health vial and spellbook. Both slowly rotating, both with a small emissive so they are findable in a dark room. |

**Silhouette first.** At this palette and light level, a prop is recognised
by outline before anything else. If it does not read as a lever from 10m in
silhouette, more detail will not fix it.

## 5. What is deliberately out of scope

- Textures, normal maps, PBR materials
- Character models (enemies are primitives with `hostile` accents and
  distinct silhouettes — the miniboss is the melee shape at larger scale)
- Animation beyond the lever, the door, and pickup rotation
- Decals, dirt, environmental storytelling props
- Skybox — the game is entirely interior

The alpha's open questions are all about feel. None of the above answers
one of them.
