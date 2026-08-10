/*
 * Unit tests for glyph_core.js.  Run:  node proto/glyph_core.test.js
 *
 * These port to GUT/GdUnit alongside the GDScript port — the assertions
 * are the specification, so keep them when the code moves into Godot.
 */

const G = require('./glyph_core.js');

let pass = 0, fail = 0;
const failures = [];

function ok(cond, label) {
  if (cond) { pass++; } else { fail++; failures.push(label); }
}
function eq(a, b, label) {
  const sa = JSON.stringify(a), sb = JSON.stringify(b);
  ok(sa === sb, label + '  (got ' + sa + ', want ' + sb + ')');
}
function near(a, b, label, tol) {
  ok(Math.abs(a - b) < (tol || 1e-9), label + '  (got ' + a + ', want ' + b + ')');
}
function section(name) { console.log('\n\x1b[1m' + name + '\x1b[0m'); }

// Walk a direction sequence out from the origin into a lattice path.
function dirsToPath(dirs) {
  const path = [{ q: 0, r: 0 }];
  let q = 0, r = 0;
  for (let i = 0; i < dirs.length; i++) {
    q += G.DIRS[dirs[i]][0];
    r += G.DIRS[dirs[i]][1];
    path.push({ q: q, r: r });
  }
  return path;
}

/* ------------------------------------------------------------------ */
section('Lattice geometry');

// Every one of the 6 neighbours sits exactly `spacing` pixels away.
// If this drifts, adjacency is not a lattice and nothing downstream holds.
{
  const S = 40;
  let allUnit = true;
  for (let d = 0; d < 6; d++) {
    const p = G.axialToPixel(G.DIRS[d][0], G.DIRS[d][1], S);
    const dist = Math.sqrt(p.x * p.x + p.y * p.y);
    if (Math.abs(dist - S) > 1e-9) allUnit = false;
  }
  ok(allUnit, 'all 6 neighbours are exactly one spacing away');
}

// Directions are evenly spaced at 60 degrees.
{
  const S = 40;
  let allSpaced = true;
  for (let d = 0; d < 6; d++) {
    const p = G.axialToPixel(G.DIRS[d][0], G.DIRS[d][1], S);
    const ang = Math.atan2(p.y, p.x) * 180 / Math.PI;
    const want = d * 60;
    let diff = Math.abs(((ang - want) % 360 + 360) % 360);
    if (diff > 180) diff = 360 - diff;
    if (diff > 1e-9) allSpaced = false;
  }
  ok(allSpaced, 'direction d sits at exactly 60*d degrees');
}

// pixel -> axial -> pixel round trips over a patch of the lattice.
{
  const S = 37.5;
  let roundTrips = true;
  for (let q = -6; q <= 6; q++) {
    for (let r = -6; r <= 6; r++) {
      const p = G.axialToPixel(q, r, S);
      const back = G.pixelToAxial(p.x, p.y, S);
      if (back.q !== q || back.r !== r) roundTrips = false;
    }
  }
  ok(roundTrips, 'axial -> pixel -> axial round trips over 169 points');
}

// A pixel jittered well inside a cell still snaps to the right point.
{
  const S = 40;
  let snaps = true;
  for (let q = -4; q <= 4; q++) {
    for (let r = -4; r <= 4; r++) {
      const p = G.axialToPixel(q, r, S);
      for (let a = 0; a < 8; a++) {
        const ang = a * Math.PI / 4;
        const jx = p.x + Math.cos(ang) * S * 0.35;
        const jy = p.y + Math.sin(ang) * S * 0.35;
        const back = G.pixelToAxial(jx, jy, S);
        if (back.q !== q || back.r !== r) snaps = false;
      }
    }
  }
  ok(snaps, 'pixels jittered 35% of spacing still snap to the correct point');
}

/* ------------------------------------------------------------------ */
section('Adjacency and path extraction');

eq(G.dirBetween(0, 0, 1, 0), 0, 'dirBetween east');
eq(G.dirBetween(0, 0, 0, 1), 1, 'dirBetween south-east');
eq(G.dirBetween(0, 0, 1, -1), 5, 'dirBetween north-east');
eq(G.dirBetween(0, 0, 2, 0), -1, 'dirBetween rejects a two-step jump');
eq(G.dirBetween(0, 0, 0, 0), -1, 'dirBetween rejects a self-loop');

eq(G.pathToDirs(dirsToPath([0, 2, 4])), [0, 2, 4], 'pathToDirs recovers the sequence');
eq(G.pathToDirs([{ q: 0, r: 0 }, { q: 3, r: 0 }]), null, 'pathToDirs rejects a broken path');
eq(G.pathToDirs([{ q: 0, r: 0 }]), null, 'pathToDirs rejects a single point');

// The authored patterns are geometrically what their comments claim.
{
  const closed = ['fireball', 'ward'];
  const open = ['lightning', 'earth_wall'];
  let allClosed = true, allOpen = true;
  for (const p of G.ALPHA_PATTERNS) {
    const path = dirsToPath(p.dirs);
    const end = path[path.length - 1];
    const isClosed = end.q === 0 && end.r === 0;
    if (closed.indexOf(p.id) >= 0 && !isClosed) allClosed = false;
    if (open.indexOf(p.id) >= 0 && isClosed) allOpen = false;
  }
  ok(allClosed, 'fireball and ward are closed loops');
  ok(allOpen, 'lightning and earth wall are open paths');
}

// Earth wall is a straight line: every turn is zero. This is what makes it
// the fastest pattern to trace despite having the most edges.
{
  const wall = G.ALPHA_PATTERNS.find(p => p.id === 'earth_wall');
  const turns = G.dirsToTurns(wall.dirs);
  ok(turns.every(t => t === 0), 'earth wall has no turns at all');
}

/* ------------------------------------------------------------------ */
section('Canonical signature invariance');

// The whole point: same glyph, any orientation, same spell.
{
  let rotOk = true, mirOk = true, revOk = true, comboOk = true;
  for (const p of G.ALPHA_PATTERNS) {
    const base = G.signature(p.dirs);
    for (let k = 0; k < 6; k++) {
      if (G.signature(G.rotate(p.dirs, k)) !== base) rotOk = false;
    }
    if (G.signature(G.mirror(p.dirs)) !== base) mirOk = false;
    if (G.signature(G.reverse(p.dirs)) !== base) revOk = false;
    for (let k = 0; k < 6; k++) {
      if (G.signature(G.mirror(G.rotate(p.dirs, k))) !== base) comboOk = false;
      if (G.signature(G.reverse(G.rotate(p.dirs, k))) !== base) comboOk = false;
      if (G.signature(G.mirror(G.reverse(G.rotate(p.dirs, k)))) !== base) comboOk = false;
    }
  }
  ok(rotOk, 'signature is invariant under all 6 rotations');
  ok(mirOk, 'signature is invariant under reflection');
  ok(revOk, 'signature is invariant under drawing the path backwards');
  ok(comboOk, 'signature is invariant under every rotation/mirror/reversal combination');
}

// Scale is deliberately NOT invariant — it is most of the design space.
{
  const smallTri = [0, 2, 4];
  const bigTri = [0, 0, 2, 2, 4, 4];
  ok(G.signature(smallTri) !== G.signature(bigTri),
    'a two-edge-per-side triangle is a DIFFERENT signature from a one-edge one');
}

// All four alpha spells are distinguishable.
{
  const sigs = G.ALPHA_PATTERNS.map(p => G.signature(p.dirs));
  ok(new Set(sigs).size === sigs.length, 'all four alpha patterns have distinct signatures');
  console.log('  signatures: ' + G.ALPHA_PATTERNS.map(
    (p, i) => p.id + '=' + sigs[i]).join('  '));
}

/* ------------------------------------------------------------------ */
section('Edit distance and near-miss');

eq(G.levenshtein([1, 2, 3], [1, 2, 3]), 0, 'levenshtein identical');
eq(G.levenshtein([1, 2, 3], [1, 2]), 1, 'levenshtein one deletion');
eq(G.levenshtein([1, 2, 3], [1, 5, 3]), 1, 'levenshtein one substitution');
eq(G.levenshtein([], [1, 2]), 2, 'levenshtein from empty');

{
  const f = G.ALPHA_PATTERNS[0].dirs;
  eq(G.minVariantDistance(f, f), 0, 'a pattern is distance 0 from itself');
  eq(G.minVariantDistance(G.rotate(f, 3), f), 0, 'a rotated pattern is still distance 0');
  eq(G.minVariantDistance(G.reverse(f), f), 0, 'a reversed pattern is still distance 0');
}

/* ------------------------------------------------------------------ */
section('Dictionary separation  (the safety property)');

{
  const m = G.separationMatrix(G.ALPHA_PATTERNS);
  const ids = G.ALPHA_PATTERNS.map(p => p.id);
  const w = Math.max(...ids.map(s => s.length));
  console.log('  ' + ' '.repeat(w + 2) + ids.map(s => s.slice(0, 6).padStart(7)).join(''));
  m.rows.forEach((row, i) => {
    console.log('  ' + ids[i].padEnd(w + 2) +
      row.map(v => String(v).padStart(7)).join(''));
  });
  console.log('  minimum separation: ' + m.minDist);
  ok(m.safe, 'every pair of patterns is at least edit distance 2 apart');
}

// The theorem that makes distance >= 2 the right bar: if every pair is at
// least 2 apart, then NO single mis-stepped edge can ever turn one spell
// into another. Verified exhaustively rather than argued.
{
  const pats = G.ALPHA_PATTERNS;
  const sigOf = {};
  for (const p of pats) sigOf[G.signature(p.dirs)] = p.id;

  let collisions = 0, checked = 0;
  for (const p of pats) {
    const d = p.dirs;
    const neighbours = [];
    // substitutions
    for (let i = 0; i < d.length; i++) {
      for (let v = 0; v < 6; v++) {
        if (v === d[i]) continue;
        const c = d.slice(); c[i] = v; neighbours.push(c);
      }
    }
    // deletions
    for (let i = 0; i < d.length; i++) {
      const c = d.slice(); c.splice(i, 1); neighbours.push(c);
    }
    // insertions
    for (let i = 0; i <= d.length; i++) {
      for (let v = 0; v < 6; v++) {
        const c = d.slice(); c.splice(i, 0, v); neighbours.push(c);
      }
    }
    for (const c of neighbours) {
      if (c.length < 3) continue;
      checked++;
      const hit = sigOf[G.signature(c)];
      if (hit && hit !== p.id) collisions++;
    }
  }
  console.log('  checked ' + checked + ' single-edit mistakes across ' + pats.length + ' patterns');
  ok(collisions === 0,
    'no single-edge mistake ever casts a DIFFERENT spell (' + collisions + ' collisions)');
}

/* ------------------------------------------------------------------ */
section('Scoring');

{
  const cfg = G.DEFAULT_SCORING;
  near(G.speedScore(0.5, 1.0, cfg), 1, 'under par scores full speed');
  near(G.speedScore(1.0, 1.0, cfg), 1, 'exactly par scores full speed');
  near(G.speedScore(2.5, 1.0, cfg), 0, 'at par*2.5 speed hits zero');
  near(G.speedScore(9.9, 1.0, cfg), 0, 'way over par clamps at zero');
  ok(G.speedScore(1.75, 1.0, cfg) > 0 && G.speedScore(1.75, 1.0, cfg) < 1,
    'between par and max, speed is partial');

  near(G.economyScore(4, 0), 1, 'a clean draw scores full economy');
  near(G.economyScore(4, 4), 0.5, 'as many fumbles as edges halves economy');
  near(G.economyScore(0, 3), 0, 'no edges scores zero economy');

  near(G.power(1, 1, cfg), 1.3, 'a perfect cast reaches 1.3x');
  near(G.power(0, 0, cfg), 0.4, 'the worst cast still floors at 0.4x');
  ok(G.power(0.5, 0.5, cfg) > 0.4 && G.power(0.5, 0.5, cfg) < 1.3,
    'a middling cast lands between the floor and the ceiling');
}

/* ------------------------------------------------------------------ */
section('recognize() end to end');

{
  const pats = G.ALPHA_PATTERNS;

  const r = G.recognize(dirsToPath([0, 2, 4]), 1.0, 0, pats);
  ok(r.ok && r.spellId === 'fireball', 'a clean fast triangle casts fireball');
  near(r.power, 1.3, 'and at par with no fumbles it is a full-power cast');

  // Same glyph, drawn rotated, mirrored, backwards, slowly, sloppily.
  const awkward = G.mirror(G.reverse(G.rotate([0, 2, 4], 2)));
  const r2 = G.recognize(dirsToPath(awkward), 2.0, 3, pats);
  ok(r2.ok && r2.spellId === 'fireball', 'the same triangle upside-down and backwards still casts fireball');
  ok(r2.power < r.power, 'but slower and sloppier means less power');

  const r3 = G.recognize(dirsToPath([0, 1, 2, 3, 4, 5]), 2.0, 0, pats);
  ok(r3.ok && r3.spellId === 'ward', 'a hexagon casts ward');

  // One edge wrong: must fail, must name the near miss, must not cast.
  const r4 = G.recognize(dirsToPath([0, 2, 5]), 1.0, 0, pats);
  ok(!r4.ok && r4.reason === 'no_match', 'a one-edge-off triangle does not cast');
  eq(r4.nearestDist, 1, 'and it reports the near miss at distance 1');
  ok(r4.nearestId !== null, 'and names a nearest pattern for the 3.1.5 feedback');

  const r5 = G.recognize([{ q: 0, r: 0 }, { q: 5, r: 5 }], 1.0, 0, pats);
  ok(!r5.ok && r5.reason === 'broken_path', 'a non-adjacent path is rejected');

  const r6 = G.recognize(dirsToPath([0, 1]), 1.0, 0, pats);
  ok(!r6.ok && r6.reason === 'too_short', 'a two-edge scribble is rejected as too short');
}

/* ------------------------------------------------------------------ */
console.log('\n' + '-'.repeat(60));
if (fail === 0) {
  console.log('\x1b[32m' + pass + ' passed, 0 failed\x1b[0m');
} else {
  console.log('\x1b[31m' + pass + ' passed, ' + fail + ' FAILED\x1b[0m');
  failures.forEach(f => console.log('  \x1b[31mx\x1b[0m ' + f));
  process.exitCode = 1;
}
