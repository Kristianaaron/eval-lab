// KV-aware, dual-node memory-fit model for the 2xDGX-Spark GLM-5.2 recipe.
// Mirrors howtospark.com/recipes/glm-5-2-dual-spark-tp2 economics:
// usable ~114 GiB per node (of 121), segmented as Weights / KV cache /
// Activations+graphs / OS reserve / Free. KV scales with context length, so
// "fits" is a function of both the prune/quant plan AND the user's context.
// Pure + deterministic; nothing here runs a model.

// Measured on the dual-Spark GLM-5.2 recipe: 10 GiB KV = 96Ki context, and the
// card quotes ~11,296 tokens per GiB.
export const KV_TOKENS_PER_GIB_DEFAULT = 11296;
export const ACTIVATIONS_GIB_DEFAULT = 2.0; // activations + cudagraphs estimate
export const NODE_USABLE_GIB_DEFAULT = 114.0; // usable per node of 121 total

export function kvGiB(contextTokens, tokensPerGiB = KV_TOKENS_PER_GIB_DEFAULT) {
  return contextTokens / (tokensPerGiB || KV_TOKENS_PER_GIB_DEFAULT);
}

/**
 * Full per-node memory stack for one node (TP2 splits weights across 2 nodes),
 * evaluating whether it fits at a given context length.
 */
export function fitStack({
  weightsGiB = 0,
  contextTokens = 32768,
  tokensPerGiB = KV_TOKENS_PER_GIB_DEFAULT,
  activationsGiB = ACTIVATIONS_GIB_DEFAULT,
  usableGiB = NODE_USABLE_GIB_DEFAULT,
} = {}) {
  const weights = Math.max(0, weightsGiB);
  const kv = kvGiB(contextTokens, tokensPerGiB);
  const overhead = Math.max(0, activationsGiB);
  const used = weights + kv + overhead;
  const over = Math.max(0, used - usableGiB);
  const free = Math.max(0, usableGiB - used);
  const fits = used <= usableGiB;
  return {
    weights,
    kv,
    overhead,
    used,
    free,
    over,
    fits,
    usableGiB,
    pct: usableGiB > 0 ? (used / usableGiB) * 100 : 0,
    segments: [
      { name: "Weights", gib: weights },
      { name: "KV cache", gib: kv },
      { name: "Activations + graphs", gib: overhead },
      { name: "Free", gib: free },
    ],
  };
}

/** Fit at a set of standard context lengths for a fixed per-node weights footprint. */
export function fitAcrossContexts(weightsGiB, opts = {}) {
  const cuts = [8192, 32768, 98304, 131072]; // 8K / 32K / 96K / 128K
  return cuts.map((c) => ({ contextTokens: c, ...fitStack({ weightsGiB, contextTokens: c, ...opts }) }));
}

/** Longest standard context that still fits, and whether the requested one does. */
export function fitSummary(weightsGiB, contextTokens, opts = {}) {
  const row = fitStack({ weightsGiB, contextTokens, ...opts });
  const across = fitAcrossContexts(weightsGiB, opts);
  const maxFit = across.filter((a) => a.fits).map((a) => a.contextTokens).at(-1) ?? 0;
  return { row, across, maxFit, fits: row.fits };
}
