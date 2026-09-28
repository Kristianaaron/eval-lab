// Formatting helpers shared by the dashboard pages.

// 2138 → "2'138" (Swiss-style thousands, as in the reference sheets)
export function fmtCount(n) {
  if (n == null || n === "" || Number.isNaN(Number(n))) return "—";
  const s = String(Math.trunc(Number(n)));
  return s.replace(/\B(?=(\d{3})+(?!\d))/g, "'");
}

// 7 → "007" for ruler labels
export function pad(n, width = 3) {
  return String(Math.max(0, Math.trunc(n))).padStart(width, "0");
}

export function fmtScore(v, digits = 3) {
  return typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : "—";
}

export function fmtPct(v) {
  return typeof v === "number" && Number.isFinite(v) ? `${Math.round(v * 100)}%` : "—";
}

export function when(v) {
  return String(v ?? "").slice(0, 16).replace("T", " ") || "—";
}

// Inferno-like heat palette: used only inside data maps and meters.
export const HEAT = ["#160b39", "#420a68", "#6b186e", "#932667", "#bc3754", "#dd513a", "#f37819", "#fca50a", "#f6d746"];

function hex(c) {
  return [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
}

// heat(0..1) → css colour interpolated across the palette
export function heat(t) {
  if (t == null || Number.isNaN(t)) return null;
  const x = Math.min(1, Math.max(0, t)) * (HEAT.length - 1);
  const i = Math.min(HEAT.length - 2, Math.floor(x));
  const f = x - i;
  const a = hex(HEAT[i]);
  const b = hex(HEAT[i + 1]);
  const c = a.map((v, k) => Math.round(v + (b[k] - v) * f));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}
