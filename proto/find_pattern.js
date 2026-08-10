/*
 * find_pattern.js — search the lattice for a pattern that is maximally
 * distinct from the ones already in the dictionary.
 *
 *   node proto/find_pattern.js [--len 3,4,5] [--against fireball,lightning,ward]
 *
 * Why this exists: "pick a shape that feels like the spell" is how you end
 * up with two spells one slip apart. Adding a spell at beta should start
 * here — the search reports the safety margin, then a human picks the
 * evocative one from the candidates that are actually safe.
 *
 * Margin is the minimum edit distance (over all 24 symmetries) from the
 * candidate to every existing pattern. Margin >= 2 is the hard bar: below
 * it, one mis-stepped edge silently casts the wrong spell.
 */

const G = require('./glyph_core.js');

const args = process.argv.slice(2);
function arg(name, dflt) {
  const i = args.indexOf('--' + name);
  return i >= 0 && args[i + 1] ? args[i + 1] : dflt;
}

const lengths = arg('len', '3,4,5,6').split(',').map(Number);
const againstIds = arg('against', 'fireball,lightning,ward').split(',');
const against = G.ALPHA_PATTERNS.filter(p => againstIds.indexOf(p.id) >= 0);

if (against.length === 0) {
  console.error('no matching patterns to compare against');
  process.exit(1);
}

console.log('searching lengths [' + lengths.join(', ') + '] against: ' +
  against.map(p => p.id + ' (' + p.dirs.join('') + ')').join(', ') + '\n');

// Enumerate every direction sequence of the requested lengths, collapsing
// symmetry duplicates via the canonical form.
const seen = new Set();
const candidates = [];
for (const len of lengths) {
  const total = Math.pow(6, len);
  for (let n = 0; n < total; n++) {
    const dirs = [];
    let v = n;
    for (let i = 0; i < len; i++) { dirs.push(v % 6); v = Math.floor(v / 6); }

    // An immediate 180 doubles back over the edge just drawn. Input capture
    // treats that as an erase, so such a path is unreachable in game.
    let backtracks = false;
    for (let i = 1; i < dirs.length; i++) {
      if ((dirs[i] + 3) % 6 === dirs[i - 1]) { backtracks = true; break; }
    }
    if (backtracks) continue;

    const sig = G.signature(dirs);
    if (seen.has(sig)) continue;
    seen.add(sig);
    candidates.push({ dirs: dirs, sig: sig });
  }
}

// Score each candidate by its worst-case distance to the existing set.
for (const c of candidates) {
  let margin = Infinity;
  for (const p of against) {
    const d = G.minVariantDistance(c.dirs, p.dirs);
    if (d < margin) margin = d;
  }
  c.margin = margin;
  const path = walk(c.dirs);
  const end = path[path.length - 1];
  c.closed = end.q === 0 && end.r === 0;
  c.selfTouch = hasRepeatPoint(path);
}

function walk(dirs) {
  const path = [{ q: 0, r: 0 }];
  let q = 0, r = 0;
  for (const d of dirs) {
    q += G.DIRS[d][0]; r += G.DIRS[d][1];
    path.push({ q: q, r: r });
  }
  return path;
}

// A path that revisits a point mid-draw is confusing to trace and to read
// back on the HUD. Closing the loop at the very end is fine.
function hasRepeatPoint(path) {
  const seenPts = new Set();
  for (let i = 0; i < path.length - 1; i++) {
    const k = path[i].q + ',' + path[i].r;
    if (seenPts.has(k)) return true;
    seenPts.add(k);
  }
  return false;
}

candidates.sort((a, b) =>
  b.margin - a.margin ||
  a.dirs.length - b.dirs.length ||
  (a.selfTouch === b.selfTouch ? 0 : (a.selfTouch ? 1 : -1)));

const best = candidates[0].margin;
console.log('best achievable margin: ' + best +
  '   (' + candidates.filter(c => c.margin === best).length + ' candidates)\n');

console.log('  margin  len  closed  clean  signature   dirs');
console.log('  ' + '-'.repeat(52));
const show = candidates.filter(c => c.margin >= Math.max(2, best - 1)).slice(0, 25);
for (const c of show) {
  console.log('  ' +
    String(c.margin).padStart(6) +
    String(c.dirs.length).padStart(5) +
    (c.closed ? '     yes' : '      no') +
    (c.selfTouch ? '     no' : '    yes') +
    '  ' + c.sig.padEnd(11) +
    c.dirs.join(''));
}

// How the currently-authored earth wall compares.
const current = G.ALPHA_PATTERNS.find(p => p.id === 'earth_wall');
if (current && againstIds.indexOf('earth_wall') < 0) {
  let m = Infinity;
  for (const p of against) m = Math.min(m, G.minVariantDistance(current.dirs, p.dirs));
  console.log('\ncurrently authored earth_wall (' + current.dirs.join('') +
    ') has margin ' + m + ' vs best achievable ' + best);
}
