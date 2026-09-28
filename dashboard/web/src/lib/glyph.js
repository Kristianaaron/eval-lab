// Deterministic "alien" pixel glyphs: a 7×7 mirrored grid of filled cells,
// half-cells and small circles derived from a seed string. Used as the mark
// next to model names, the brand and the favicon (see index.html).

function hash32(str) {
  // FNV-1a, then a final avalanche so short seeds still spread well.
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  h ^= h >>> 16;
  h = Math.imul(h, 0x7feb352d);
  h ^= h >>> 15;
  h = Math.imul(h, 0x846ca68b);
  h ^= h >>> 16;
  return h >>> 0;
}

export function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function seedFrom(str) {
  return hash32(String(str ?? ""));
}

// Cell kinds: 0 empty · 1 full square · 2 half cell (side encoded in `side`) · 3 circle
export function glyphCells(seed) {
  const rnd = mulberry32(seedFrom(seed));
  const cells = [];
  // left 4 columns (x = 0..3) are generated; columns 4..6 mirror 2..0.
  for (let y = 0; y < 7; y++) {
    for (let x = 0; x < 4; x++) {
      const r = rnd();
      // Density rises toward the centre so the shape reads as a nucleus with dendrites.
      const centrality = 1 - (Math.abs(3 - y) / 3) * 0.5 - ((3 - x) / 3) * 0.35;
      const on = r < 0.28 + 0.42 * centrality;
      if (!on) continue;
      const k = rnd();
      const kind = k < 0.55 ? 1 : k < 0.8 ? 2 : 3;
      const tone = rnd() < 0.72 ? 0 : 1;
      const side = Math.floor(rnd() * 4); // 0 top · 1 right · 2 bottom · 3 left
      cells.push({ x, y, kind, tone, side });
      if (x < 3) cells.push({ x: 6 - x, y, kind, tone, side: side === 1 ? 3 : side === 3 ? 1 : side });
    }
  }
  // Guarantee a nucleus so no seed renders empty.
  if (!cells.some((c) => c.x === 3 && c.y === 3)) cells.push({ x: 3, y: 3, kind: 3, tone: 1, side: 0 });
  return cells;
}

export function glyphShapes(seed) {
  return glyphCells(seed).map((c) => {
    if (c.kind === 1) return { tag: "rect", x: c.x, y: c.y, w: 1, h: 1, tone: c.tone };
    if (c.kind === 3) return { tag: "circle", cx: c.x + 0.5, cy: c.y + 0.5, r: 0.34, tone: c.tone };
    // half cell
    if (c.side === 0) return { tag: "rect", x: c.x, y: c.y, w: 1, h: 0.5, tone: c.tone };
    if (c.side === 2) return { tag: "rect", x: c.x, y: c.y + 0.5, w: 1, h: 0.5, tone: c.tone };
    if (c.side === 3) return { tag: "rect", x: c.x, y: c.y, w: 0.5, h: 1, tone: c.tone };
    return { tag: "rect", x: c.x + 0.5, y: c.y, w: 0.5, h: 1, tone: c.tone };
  });
}

// Standalone SVG markup (favicon / non-Svelte contexts).
export function glyphSvg(seed, { size = 32, primary = "#5ee7d3", secondary = "#b48cff", background = null } = {}) {
  const body = glyphShapes(seed)
    .map((s) => {
      const fill = s.tone === 0 ? primary : secondary;
      return s.tag === "rect"
        ? `<rect x="${s.x}" y="${s.y}" width="${s.w}" height="${s.h}" fill="${fill}"/>`
        : `<circle cx="${s.cx}" cy="${s.cy}" r="${s.r}" fill="${fill}"/>`;
    })
    .join("");
  const bg = background ? `<rect width="7" height="7" fill="${background}"/>` : "";
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 7 7" width="${size}" height="${size}" shape-rendering="crispEdges">${bg}${body}</svg>`;
}
