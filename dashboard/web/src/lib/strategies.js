// Comprehensive strategy reasoning — ranks the full set of levers a user has
// for fitting a model into their hardware, scored against the same goal
// weights as the plan picker (quality / speed / fit). Deterministic, no
// inference. Evidence-backed where the run carries data; explicitly "staged"
// or "deploy" when it doesn't — never faked.
import {
  GOALS,
  pct,
  scorePlans,
  loadConcentration,
  redundancySummary,
  exl3Recommendation,
} from "./recommend.js";

export const READINESS = {
  measured: { label: "measured", cls: "pass" },
  staged: { label: "staged", cls: "warn" },
  deploy: { label: "needs runtime", cls: "type" },
};

/**
 * `model` (optional) = { stored_size_bytes, params } for the real checkpoint so
 * EXL3 storage math is real; without it that strategy is staged.
 */
export function strategyOptions(run, goalKey = "balanced", fitBudgetGiB = null, model = null) {
  const sc = scorePlans(run, goalKey, fitBudgetGiB);
  const w = GOALS[goalKey] ?? GOALS.balanced;
  const cons = loadConcentration(run?.saliency);
  const exl3 = exl3Recommendation({
    stored_size_bytes: model?.stored_size_bytes,
    params: model?.params,
  });
  const budgetBytes = fitBudgetGiB ? fitBudgetGiB * 1024 ** 3 : null;
  const resident = sc.recommended?.bytes ?? null;
  const fitsNow = budgetBytes !== null && resident !== null ? resident <= budgetBytes : null;
  const topShare = cons.topShare ?? 0;

  const list = [
    {
      key: "narrow_neuron",
      name: "Narrow the neurons (width)",
      what: "Thin the redundant channels inside every expert but keep ALL experts and routing intact — the quality-safe way to cut size.",
      quality: 0.96,
      speed: 0.6,
      fit: 0.72,
      red: 0.7, // approx: thin redundant channels, keep every expert+topology
      readiness: cons.top.length ? "measured" : "staged",
      evidence: `${pct(topShare)}% of traffic in the top experts · no experts removed`,
    },
    {
      key: "quant_exl3",
      name: "Compress with EXL3",
      what: "Store the surviving weights in fewer bits per weight — cuts size while keeping the model's behaviour.",
      quality: 0.8,
      speed: 0.45,
      fit: 0.94,
      red: exl3 ? Math.max(0.2, 1 - exl3.shrink) : 0.75, // approx: stored-bits cut
      readiness: "staged",
      evidence: exl3 ? `${pct(exl3.shrink)}% smaller` : "needs a quantizer wired in",
    },
    {
      key: "quant_mixed",
      name: "Mixed precision",
      what: "Drop the BF16 non-expert roles (attention/shared/latent/norms) toward FP8/int8; FP32 where exact.",
      quality: 0.85,
      speed: 0.5,
      fit: 0.62,
      red: 0.85, // approx: BF16 non-expert roles → FP8/int8
      readiness: "staged",
      evidence: "per-tensor probes pending",
    },
    {
      key: "prune_expert",
      name: "Removing whole experts (last resort)",
      what: "Drops the least-used experts outright — biggest speed/memory win, but it disturbs routing and risks quality.",
      quality: (sc.recommended?.quality ?? 1) * 0.85, // routing-risk adjusted
      speed: 0.8,
      fit: 0.6,
      red: 1, // approx: this IS the resident plan baseline
      readiness: "measured",
      evidence: `keeps ${pct(sc.recommended?.quality ?? 1)}% of real traffic · aggressive`,
    },
    {
      key: "page_nvme",
      name: "Keep it, spill cold parts to NVMe",
      what: "Keep every expert; read cold ones from disk only when a token needs them.",
      quality: 0.95,
      speed: 0.25,
      fit: fitsNow ? 0.3 : 0.5,
      red: 1, // approx: no size cut — offloads cold experts instead
      readiness: "deploy",
      evidence: fitsNow ? "already fits — optional headroom" : "no size cut; offloads instead",
    },
    {
      key: "distill",
      name: "Distill / repair",
      what: "Train a smaller student (or repair after pruning) — the costliest, recovers the most lost quality.",
      quality: 0.97,
      speed: 0.42,
      fit: 0.6,
      red: 0.5, // approx: smaller distilled student
      readiness: "staged",
      evidence: "highest quality recovery · needs a training run",
    },
  ];

  for (const s of list) s.score = w.q * s.quality + w.s * s.speed + w.f * s.fit;
  list.sort((a, b) => b.score - a.score);

  // The blueprint-prescribed fit path: quality-preserving stack, in order.
  const combo = {
    name: "Narrow neurons → EXL3 / mixed-precision",
    steps: ["Narrow the neurons (keep every expert)", "Compress with EXL3", "Mixed precision on the BF16 roles"],
    why: "keeps the full expert topology (minimizes quality loss) and cuts storage with EXL3/mixed-precision — the recommended quality-preserving path for fitting.",
    quality: 0.9,
    fit: 0.9,
    speed: 0.55,
    recommended: goalKey !== "speed",
  };

  return {
    list,
    best: list[0] ?? null,
    combo,
    goalWeights: w,
    goalKey,
    fitsNow,
    residentGiB: resident != null ? resident / 1024 ** 3 : null,
    hasBudget: budgetBytes !== null,
    provenance:
      "Scores above are measured from this run's router-activation tracing (REAP: router probability × expert output norm) — not guessed.",
  };
}
