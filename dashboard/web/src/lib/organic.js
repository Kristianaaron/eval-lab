// Geometry for the vein-style marks. These only draw; every position,
// width and opacity passed in comes from data.

const f = (n) => (Math.round(n * 100) / 100).toString();

// Vertical S-curve from a parent node up/down to a child node.
export function vein(x0, y0, x1, y1) {
  const dy = y1 - y0;
  return `M${f(x0)},${f(y0)} C${f(x0)},${f(y0 + dy * 0.55)} ${f(x1)},${f(y1 - dy * 0.45)} ${f(x1)},${f(y1)}`;
}

// Same curve without the leading move, for chaining segments into one path.
export function veinTail(x0, y0, x1, y1) {
  const dy = y1 - y0;
  return ` C${f(x0)},${f(y0 + dy * 0.55)} ${f(x1)},${f(y1 - dy * 0.45)} ${f(x1)},${f(y1)}`;
}

// Branch leaving a horizontal trunk and curling out to a tip.
export function sprout(x0, y0, x1, y1) {
  const dx = x1 - x0;
  const dy = y1 - y0;
  return `M${f(x0)},${f(y0)} C${f(x0 + dx * 0.15)},${f(y0 + dy * 0.55)} ${f(x1 - dx * 0.1)},${f(y1 - dy * 0.25)} ${f(x1)},${f(y1)}`;
}

// Ink burst: `n` spokes of deterministic, slightly uneven length around a point.
export function burst(cx, cy, r, n, seed = 0) {
  let d = "";
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2 + (seed % 11) * 0.21;
    const len = r * (1.1 + (((i * 7 + seed) % 5) / 4) * 0.7);
    d += `M${f(cx)},${f(cy)} L${f(cx + Math.cos(a) * len)},${f(cy + Math.sin(a) * len)} `;
  }
  return d;
}

export function hashStr(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return (h >>> 0) % 997;
}
