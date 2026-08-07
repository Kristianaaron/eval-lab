// Plain-language recommendation engine over an atlas-run's measured artifacts.
// Pure functions (no DOM) so they are unit-testable in Node against real runs.
// All numbers derive from measured saliency / plans / keep-maps — never invented.

export function pct(f) {
  const v = Math.round((f ?? 0) * 100);
  return Number.isFinite(v) ? v : 0;
}

// number of distinct experts (routed banks) in a layer
export function expertsPerLayer(saliency) {
  return new Set((saliency ?? []).map((r) => r.expert)).size;
}

// fraction of routed-token load carried by the top-`k` (by activation count)
// experts within each layer, averaged as total-kept/total.
export function routingRetained(saliency, k) {
  const byLayer = new Map();
  for (const s of saliency ?? []) {
    if (!byLayer.has(s.layer)) byLayer.set(s.layer, []);
    byLayer.get(s.layer).push(s);
  }
  let kept = 0;
  let total = 0;
  for (const rows of byLayer.values()) {
    const load = rows.map((r) => r.activation_count ?? 0);
    const t = load.reduce((a, b) => a + b, 0);
    const sorted = load.slice().sort((a, b) => b - a);
    kept += sorted.slice(0, k).reduce((a, b) => a + b, 0);
    total += t;
  }
  return total ? kept / total : 1;
}

// ---- usecase-aware, multi-objective recommendation scoring ----
// Every plan is scored on three measured axes:
//   quality = fraction of real routed traffic still covered
//   speed   = fraction of experts removed (fewer experts to run)
//   fit     = how well the plan fits the USER's memory budget (see `fitBudgetGiB`)
// The user's goal weights these; the highest weighted score wins. Deterministic
// (no inference), yet the pick changes with the data AND the chosen priorities.
export const GOALS = {
  quality: { label: "Maximum quality", q: 1.0, s: 0.0, f: 0.0 },
  balanced: { label: "Balanced", q: 0.55, s: 0.25, f: 0.2 },
  speed: { label: "Speed first", q: 0.25, s: 0.55, f: 0.2 },
  fit: { label: "Fit in memory", q: 0.35, s: 0.15, f: 0.5 },
};

/**
 * `fitBudgetGiB` is the memory (GiB) the deployment must fit in. When provided,
 * `fit` is 1 for any plan at or under that budget and degrades with how far it
 * exceeds it. When omitted (unknown constraint), fit is neutral (0) and the
 * recommendation leans on quality/speed, with a hint to supply a budget.
 */
export function scorePlans(run, goalKey = "balanced", fitBudgetGiB = null) {
  const saliency = run?.saliency ?? [];
  const plans = (run?.plans ?? []).filter((p) => (p.keep_per_layer ?? 0) > 0);
  const nExp = expertsPerLayer(saliency) || run?.topology?.num_local_experts || 0;
  const w = GOALS[goalKey] ?? GOALS.balanced;
  const budgetBytes = fitBudgetGiB ? fitBudgetGiB * 1024 ** 3 : null;
  const scored = plans.map((p) => {
    const k = p.keep_per_layer;
    const retained = routingRetained(saliency, k);
    const dropped = nExp ? 1 - k / nExp : 0;
    const bytes = (p.resident_bytes_a ?? 0) + (p.resident_bytes_b ?? 0);
    const fits = budgetBytes !== null ? bytes <= budgetBytes : null;
    const fit =
      budgetBytes === null
        ? 0
        : fits
          ? 1
          : Math.max(0, budgetBytes / (bytes || 1)); // degrades with overage
    const quality = retained;
    const speed = dropped;
    const combined = w.q * quality + w.s * speed + w.f * fit;
    return {
      name: p.name,
      strategy: p.strategy,
      keep_per_layer: k,
      quality,
      speed,
      fit,
      retained,
      dropped_pct: pct(dropped),
      bytes,
      fits_budget: fits,
      combined,
    };
  });
  scored.sort((a, b) => b.combined - a.combined || b.quality - a.quality || b.dropped_pct - a.dropped_pct);
  const recommended = scored[0] ?? null;
  const second = scored[1] ?? null;
  const gap = recommended && second ? recommended.combined - second.combined : 1;
  const confidence = gap >= 0.1 ? "high" : gap >= 0.03 ? "medium" : "close";
  // best plan per single axis, so the user sees why the chosen one balances
  const bestQuality = byAxis(scored, (x) => x.quality);
  const bestSpeed = byAxis(scored, (x) => x.speed);
  const bestFit = byAxis(scored, (x) => x.fit);
  return {
    scored,
    recommended,
    second,
    confidence,
    nExp,
    goalKey,
    weights: w,
    bestQuality,
    bestSpeed,
    bestFit,
    hasBudget: budgetBytes !== null,
  };
}

function byAxis(scored, f) {
  if (!scored.length) return null;
  return [...scored].sort((a, b) => f(b) - f(a))[0];
}

// How concentrated routing is: does a small set of experts do most of the work?
// High concentration => specialized hot experts worth preserving full width,
// and cold experts that are strong prune candidates.
export function loadConcentration(saliency) {
  const exp = {};
  for (const s of saliency ?? []) {
    exp[s.expert] = (exp[s.expert] ?? 0) + (s.activation_count ?? 0);
  }
  const total = Object.values(exp).reduce((a, b) => a + b, 0);
  const rows = Object.entries(exp)
    .map(([e, c]) => ({ expert: +e, count: c, share: total ? c / total : 0 }))
    .sort((a, b) => b.count - a.count);
  const topShare = rows.slice(0, 3).reduce((a, b) => a + b.share, 0);
  return { total, top: rows.slice(0, 5), topShare };
}

// Protected (kept in every layer) vs fully-redundant (never kept) experts from
// the primary keep-map.
export function redundancySummary(keepMaps) {
  const kept = new Map();
  for (const km of keepMaps ?? []) {
    for (const e of km.entries ?? []) {
      const id = e.unit?.source_unit_id;
      if (id == null) continue;
      if (!kept.has(id)) kept.set(id, new Set());
      if (e.kept) kept.get(id).add(km.layer_index);
    }
  }
  const nLayers = keepMaps?.length ?? 0;
  let protectedCount = 0;
  let redundant = 0;
  for (const layers of kept.values()) {
    if (nLayers > 0 && layers.size === nLayers) protectedCount += 1;
    else if (layers.size === 0) redundant += 1;
  }
  return { protectedCount, redundant, nLayers };
}

// Storage recommendation from measured size + parameter count: what bits/weight
// the model is stored at today, and what a target (EXL3 ~3.25 bpw) would save.
export function exl3Recommendation({ stored_size_bytes, params, target_bpw = 3.25 }) {
  if (!stored_size_bytes || !params) return null;
  const achieved = (stored_size_bytes * 8) / params;
  const targetBytes = (params * target_bpw) / 8;
  const shrink = targetBytes < stored_size_bytes ? 1 - targetBytes / stored_size_bytes : 0;
  return { achieved, target_bpw, targetBytes, shrink };
}

// Overall, non-jargon summary sentence describing the model from the run data.
export function modelSummary(run) {
  const nExp = expertsPerLayer(run?.saliency);
  const nLayers = run?.saliency ? new Set(run.saliency.map((r) => r.layer)).size : 0;
  const cons = loadConcentration(run?.saliency);
  return {
    nExp,
    nLayers,
    topExpert: cons.top[0]?.expert ?? null,
    topSharePct: pct(cons.top[0]?.share ?? 0),
    top3SharePct: pct(cons.topShare),
    traceTokens: run?.trace_count ?? 0,
  };
}
