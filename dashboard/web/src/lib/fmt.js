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

// Minimal-colour value scale: the text colour at increasing opacity. A value
// of 0 is nearly transparent, 1 is solid. Used for every data map and meter.
export const TEXT_RGB = "232, 228, 216";
export const HEAT = Array.from({ length: 9 }, (_, i) => `rgba(${TEXT_RGB}, ${(0.08 + (0.92 * i) / 8).toFixed(3)})`);

// heat(0..1) → css colour: opacity encodes the value
export function heat(t) {
  if (t == null || Number.isNaN(t)) return null;
  const a = 0.08 + 0.92 * Math.min(1, Math.max(0, t));
  return `rgba(${TEXT_RGB}, ${a.toFixed(3)})`;
}
