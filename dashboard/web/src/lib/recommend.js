// Plain-language recommendation engine over an atlas-run's measured artifacts.
// Pure functions (no DOM) so they are unit-testable in Node against real runs.
// All numbers derive from measured saliency / plans / keep-maps — never invented.

// Target: we only recommend a more aggressive prune while it still covers this
// fraction of the model's actual routed traffic.
export const RETAIN_TARGET = 0.85;

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

// Score every plan (keep budget) by traffic kept and experts dropped; recommend
// the most aggressive plan that still retains >= RETAIN_TARGET of traffic.
export function pruneRecommendations(run) {
  const saliency = run?.saliency ?? [];
  const plans = run?.plans ?? [];
  const nExp = expertsPerLayer(saliency) || run?.topology?.num_local_experts || 0;
  const scored = plans
    .map((p) => {
      const k = p.keep_per_layer ?? nExp;
      return {
        name: p.name,
        strategy: p.strategy,
        keep_per_layer: k,
        retained: routingRetained(saliency, k),
        dropped_pct: nExp ? pct(1 - k / nExp) : 0,
      };
    })
    .filter((s) => s.keep_per_layer > 0)
    .sort((a, b) => b.keep_per_layer - a.keep_per_layer);
  // most aggressive (smallest budget) that still hits the retention target
  const recommended =
    [...scored].reverse().find((s) => s.retained >= RETAIN_TARGET) ??
    scored[scored.length - 1] ??
    null;
  return { scores: scored, recommended, target: RETAIN_TARGET, nExp };
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
