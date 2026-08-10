/*
 * glyph_core.js — the lattice spell pipeline, engine-free.
 *
 * This is the reference implementation of masterplan tasks 2.1.3, 2.1.4,
 * 2.2.1, 2.2.2 and 2.2.3. It is deliberately written to port 1:1 into
 * GDScript: plain functions, integer math, no closures in the hot paths,
 * no JS-only idioms. Develop and tune here (instant iteration), port when
 * it is right.
 *
 * GDScript port mapping:
 *   const DIRS = [[q,r],...]     ->  const DIRS := [Vector2i(q,r), ...]
 *   {q, r}                       ->  Vector2i
 *   arrays of int                ->  PackedInt32Array
 *   signature strings            ->  String (Dictionary key)
 *
 * ---------------------------------------------------------------------
 * Why axial integer coordinates
 * ---------------------------------------------------------------------
 * The HTML prototype stores lattice points as pixels and tests adjacency
 * with a float tolerance (`abs(dist - S) < S * 0.15`). That works for a
 * demo but it is a latent source of "why did this edge not register"
 * bugs, and it makes unit tests fuzzy.
 *
 * Here every lattice point is an integer pair (q, r) and adjacency is an
 * exact table lookup. Pixels only exist at the input boundary
 * (pixelToAxial) and the render boundary (axialToPixel). Everything in
 * between — direction extraction, canonicalisation, matching — is exact
 * integer math that cannot drift, cannot need tuning, and is trivially
 * testable.
 *
 *   x = spacing * (q + r/2)
 *   y = spacing * r * sqrt(3)/2
 */

(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.GlyphCore = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const SQRT3_2 = Math.sqrt(3) / 2;

  /* ------------------------------------------------------------------
   * Lattice
   * ------------------------------------------------------------------ */

  // The 6 neighbours of any lattice point, in axial coords.
  // Index is the direction id; angle is 60 degrees * id, measured
  // clockwise from east because canvas/screen y grows downward.
  const DIRS = [
    [1, 0],   // 0    0deg  E
    [0, 1],   // 1   60deg  SE
    [-1, 1],  // 2  120deg  SW
    [-1, 0],  // 3  180deg  W
    [0, -1],  // 4  240deg  NW
    [1, -1],  // 5  300deg  NE
  ];

  function axialToPixel(q, r, spacing) {
    return { x: spacing * (q + r / 2), y: spacing * r * SQRT3_2 };
  }

  // Nearest lattice point to a pixel. Uses cube rounding — rounding q and
  // r independently picks the wrong point near cell boundaries.
  function axialRound(qf, rf) {
    let rx = Math.round(qf);
    let ry = Math.round(-qf - rf);
    let rz = Math.round(rf);
    const dx = Math.abs(rx - qf);
    const dy = Math.abs(ry - (-qf - rf));
    const dz = Math.abs(rz - rf);
    if (dx > dy && dx > dz) rx = -ry - rz;
    else if (dy > dz) ry = -rx - rz;
    else rz = -rx - ry;
    return { q: rx, r: rz };
  }

  function pixelToAxial(x, y, spacing) {
    const rf = y / (spacing * SQRT3_2);
    const qf = x / spacing - rf / 2;
    return axialRound(qf, rf);
  }

  // Squared pixel distance from a pixel to a lattice point — used for the
  // snap-radius test at input time.
  function pixelDistSq(x, y, q, r, spacing) {
    const p = axialToPixel(q, r, spacing);
    const dx = p.x - x, dy = p.y - y;
    return dx * dx + dy * dy;
  }

  // Direction id from point a to point b, or -1 if they are not adjacent.
  // Exact: no tolerance, no floating point.
  function dirBetween(aq, ar, bq, br) {
    const dq = bq - aq, dr = br - ar;
    for (let i = 0; i < 6; i++) {
      if (DIRS[i][0] === dq && DIRS[i][1] === dr) return i;
    }
    return -1;
  }

  function stepFrom(q, r, dir) {
    return { q: q + DIRS[dir][0], r: r + DIRS[dir][1] };
  }

  /* ------------------------------------------------------------------
   * 2.1.3 — path to direction sequence
   * ------------------------------------------------------------------ */

  // path: [{q, r}, ...]  ->  [dirId, ...], or null if any step is not a
  // single lattice edge. Input capture should make null impossible; it is
  // returned rather than thrown so the caller can fizzle gracefully.
  function pathToDirs(path) {
    if (!path || path.length < 2) return null;
    const dirs = [];
    for (let i = 1; i < path.length; i++) {
      const d = dirBetween(path[i - 1].q, path[i - 1].r, path[i].q, path[i].r);
      if (d < 0) return null;
      dirs.push(d);
    }
    return dirs;
  }

  // Turn sequence: signed turn between consecutive directions.
  // 0 straight, +/-1 = 60deg, +/-2 = 120deg, 3 = full reverse.
  // Not used for matching (the direction sequence is strictly more
  // information) but useful for debug readouts and for describing a
  // pattern to a human.
  function dirsToTurns(dirs) {
    const turns = [];
    for (let i = 1; i < dirs.length; i++) {
      let t = (dirs[i] - dirs[i - 1]) % 6;
      if (t < 0) t += 6;
      turns.push(t <= 3 ? t : t - 6);
    }
    return turns;
  }

  /* ------------------------------------------------------------------
   * 2.1.4 — canonical signature
   * ------------------------------------------------------------------
   * A glyph must be the same spell regardless of:
   *   - where on the lattice it was drawn   (free: we only store directions)
   *   - which way up it was drawn           (rotation)
   *   - whether it was drawn mirrored       (reflection)
   *   - which end the player started from   (reversal)
   *
   * Reversal invariance is included deliberately. Without it, drawing a
   * correct shape starting from the wrong corner fails, which is exactly
   * the mistake a panicking player makes. It costs design space that four
   * alpha spells do not need.
   *
   * NOT invariant to scale: a triangle with two edges per side is a
   * different signature from one with a single edge per side. That is
   * intentional — it is most of the design space a 6-direction lattice
   * has, and it makes a grimoire worth reading.
   */

  function rotate(dirs, k) {
    const out = [];
    for (let i = 0; i < dirs.length; i++) out.push((dirs[i] + k) % 6);
    return out;
  }

  // Reflection across the east-west axis: angle -> -angle.
  function mirror(dirs) {
    const out = [];
    for (let i = 0; i < dirs.length; i++) out.push((6 - dirs[i]) % 6);
    return out;
  }

  // Walk the same path from the other end: reverse order, flip each
  // direction by 180 degrees.
  function reverse(dirs) {
    const out = [];
    for (let i = dirs.length - 1; i >= 0; i--) out.push((dirs[i] + 3) % 6);
    return out;
  }

  // Rotate so the first direction is 0. Rotation invariance falls out of
  // this for free, since rotating the glyph adds a constant to every
  // direction and the subtraction cancels it.
  function normalizeRotation(dirs) {
    if (dirs.length === 0) return [];
    return rotate(dirs, (6 - dirs[0]) % 6);
  }

  function lexLess(a, b) {
    const n = Math.min(a.length, b.length);
    for (let i = 0; i < n; i++) {
      if (a[i] !== b[i]) return a[i] < b[i];
    }
    return a.length < b.length;
  }

  // The canonical form: the lexicographically smallest rotation-normalised
  // representative of the glyph's 4-element symmetry group.
  function canonical(dirs) {
    if (!dirs || dirs.length === 0) return [];
    const candidates = [
      normalizeRotation(dirs),
      normalizeRotation(mirror(dirs)),
      normalizeRotation(reverse(dirs)),
      normalizeRotation(mirror(reverse(dirs))),
    ];
    let best = candidates[0];
    for (let i = 1; i < candidates.length; i++) {
      if (lexLess(candidates[i], best)) best = candidates[i];
    }
    return best;
  }

  // Hashable key for the pattern dictionary.
  function signature(dirs) {
    return canonical(dirs).join('');
  }

  /* ------------------------------------------------------------------
   * 2.2.3 — near-miss distance
   * ------------------------------------------------------------------
   * Edit distance on canonical forms is NOT usable here: if the player's
   * error is in the *first* edge, rotation normalisation anchors to the
   * wrong direction and every subsequent element shifts, so a one-edge
   * mistake reads as a total mismatch.
   *
   * Instead compare the raw drawn sequence against the raw pattern under
   * all 24 symmetries (6 rotations x mirror x reversal) and take the best.
   * 24 x Levenshtein on ~6-element arrays x a handful of patterns is
   * nothing, and it degrades correctly for errors anywhere in the glyph.
   */

  function variants(dirs) {
    const out = [];
    const bases = [dirs, mirror(dirs), reverse(dirs), mirror(reverse(dirs))];
    for (let b = 0; b < bases.length; b++) {
      for (let k = 0; k < 6; k++) out.push(rotate(bases[b], k));
    }
    return out;
  }

  function levenshtein(a, b) {
    const n = a.length, m = b.length;
    if (n === 0) return m;
    if (m === 0) return n;
    let prev = [];
    for (let j = 0; j <= m; j++) prev.push(j);
    for (let i = 1; i <= n; i++) {
      const cur = [i];
      for (let j = 1; j <= m; j++) {
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        cur.push(Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost));
      }
      prev = cur;
    }
    return prev[m];
  }

  // Smallest edit distance between two glyphs over all symmetries.
  // 0 means identical up to symmetry.
  function minVariantDistance(a, b) {
    const va = variants(a);
    let best = Infinity;
    for (let i = 0; i < va.length; i++) {
      const d = levenshtein(va[i], b);
      if (d < best) best = d;
      if (best === 0) break;
    }
    return best;
  }

  /* ------------------------------------------------------------------
   * 2.2.2 — power = speed x economy
   * ------------------------------------------------------------------
   * The lattice has no fuzzy "draw quality" axis, but it still has a skill
   * axis, and both halves of it are exact integers rather than a tuned
   * curve:
   *
   *   speed    how fast, against a per-pattern par time
   *   economy  how cleanly routed — backtracks and re-traversal attempts
   *
   * Economy counts *attempts*, not results: input capture already refuses
   * to re-use an edge and erases on backtrack, so the only record that a
   * player fumbled is how many times they tried. Instrument at input time.
   */

  const DEFAULT_SCORING = {
    powerFloor: 0.4,   // worst possible cast still does 40% damage
    powerRange: 0.9,   // perfect cast reaches 1.3x
    maxTimeFactor: 2.5, // at par * 2.5 the speed score hits zero
  };

  function clamp01(v) {
    return v < 0 ? 0 : (v > 1 ? 1 : v);
  }

  function speedScore(elapsedSec, parSec, cfg) {
    const c = cfg || DEFAULT_SCORING;
    if (parSec <= 0) return 1;
    const maxTime = parSec * c.maxTimeFactor;
    if (elapsedSec <= parSec) return 1;
    return clamp01((maxTime - elapsedSec) / (maxTime - parSec));
  }

  function economyScore(edgeCount, wastedMoves) {
    if (edgeCount <= 0) return 0;
    return edgeCount / (edgeCount + wastedMoves);
  }

  function power(speed, economy, cfg) {
    const c = cfg || DEFAULT_SCORING;
    return c.powerFloor + c.powerRange * clamp01(speed) * clamp01(economy);
  }

  /* ------------------------------------------------------------------
   * 2.2.1 — the alpha pattern dictionary
   * ------------------------------------------------------------------
   * Becomes a Godot Resource. Authored here so it can be validated by the
   * separation test before anyone opens the editor.
   *
   * parSec values are placeholders until P1 produces real timings; the
   * tempo spike overwrites them.
   */

  const ALPHA_PATTERNS = [
    {
      id: 'fireball',
      name: 'Fireball',
      dirs: [0, 2, 4],           // closed triangle
      parSec: 1.1,
      note: 'Shortest pattern in the set — it is the spell you cast under pressure.',
    },
    {
      id: 'lightning',
      name: 'Lightning',
      dirs: [0, 1, 0, 1],        // zigzag
      parSec: 1.4,
      note: 'Reads as a bolt; the only open (non-closed) pattern in the alpha set.',
    },
    {
      id: 'earth_wall',
      name: 'Earth Wall',
      dirs: [0, 0, 0, 0, 0],     // straight line
      parSec: 1.2,
      note: 'A line is a wall. Chosen by find_pattern.js: the only shape reaching ' +
            'margin 3 against the rest of the set, and despite having the most ' +
            'edges it has zero turns, so it is the fastest thing here to trace.',
    },
    {
      id: 'ward',
      name: 'Ward',
      dirs: [0, 1, 2, 3, 4, 5],  // closed hexagon
      parSec: 2.0,
      note: 'The lattice shape. Slowest to draw — a ward is a commitment, not a panic button.',
    },
  ];

  function buildDictionary(patterns) {
    const bySig = {};
    for (let i = 0; i < patterns.length; i++) {
      bySig[signature(patterns[i].dirs)] = patterns[i];
    }
    return bySig;
  }

  /* ------------------------------------------------------------------
   * Recognition entry point — the whole pipeline in one call.
   * Returns the SpellData contract from ADR 0002.
   * ------------------------------------------------------------------ */

  function recognize(path, elapsedSec, wastedMoves, patterns, cfg) {
    const dirs = pathToDirs(path);
    if (dirs === null) {
      return { ok: false, reason: 'broken_path', spellId: null, power: 0 };
    }
    if (dirs.length < 3) {
      return { ok: false, reason: 'too_short', spellId: null, power: 0, dirs: dirs };
    }

    const sig = signature(dirs);
    const dict = buildDictionary(patterns);
    const hit = dict[sig];

    if (!hit) {
      // No exact match — find the nearest known pattern for feedback.
      let nearest = null, nearestDist = Infinity;
      for (let i = 0; i < patterns.length; i++) {
        const d = minVariantDistance(dirs, patterns[i].dirs);
        if (d < nearestDist) { nearestDist = d; nearest = patterns[i]; }
      }
      return {
        ok: false,
        reason: 'no_match',
        spellId: null,
        power: 0,
        dirs: dirs,
        signature: sig,
        nearestId: nearest ? nearest.id : null,
        nearestDist: nearestDist,
      };
    }

    const speed = speedScore(elapsedSec, hit.parSec, cfg);
    const economy = economyScore(dirs.length, wastedMoves);
    return {
      ok: true,
      reason: 'match',
      spellId: hit.id,
      signature: sig,
      dirs: dirs,
      speed: speed,
      economy: economy,
      power: power(speed, economy, cfg),
      elapsedSec: elapsedSec,
      wastedMoves: wastedMoves,
    };
  }

  /* ------------------------------------------------------------------
   * Dictionary safety check
   * ------------------------------------------------------------------
   * The rule that makes the set safe: every pair of patterns must be at
   * least edit distance 2 apart under all symmetries. At distance 1 a
   * single mis-stepped edge silently casts the wrong spell, which is the
   * lattice equivalent of the recognition failure this whole design was
   * chosen to avoid.
   *
   * Run this every time a pattern is added. It is the reason adding
   * spells at beta stays safe.
   */
  function separationMatrix(patterns) {
    const rows = [];
    let minDist = Infinity;
    for (let i = 0; i < patterns.length; i++) {
      const row = [];
      for (let j = 0; j < patterns.length; j++) {
        if (i === j) { row.push(0); continue; }
        const d = minVariantDistance(patterns[i].dirs, patterns[j].dirs);
        row.push(d);
        if (d < minDist) minDist = d;
      }
      rows.push(row);
    }
    return { rows: rows, minDist: minDist, safe: minDist >= 2 };
  }

  return {
    DIRS: DIRS,
    SQRT3_2: SQRT3_2,
    DEFAULT_SCORING: DEFAULT_SCORING,
    ALPHA_PATTERNS: ALPHA_PATTERNS,
    axialToPixel: axialToPixel,
    axialRound: axialRound,
    pixelToAxial: pixelToAxial,
    pixelDistSq: pixelDistSq,
    dirBetween: dirBetween,
    stepFrom: stepFrom,
    pathToDirs: pathToDirs,
    dirsToTurns: dirsToTurns,
    rotate: rotate,
    mirror: mirror,
    reverse: reverse,
    normalizeRotation: normalizeRotation,
    canonical: canonical,
    signature: signature,
    variants: variants,
    levenshtein: levenshtein,
    minVariantDistance: minVariantDistance,
    speedScore: speedScore,
    economyScore: economyScore,
    power: power,
    buildDictionary: buildDictionary,
    recognize: recognize,
    separationMatrix: separationMatrix,
  };
});
