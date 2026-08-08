<script>
  import { Sparkles, Cpu, HardDrive, ShieldCheck, X } from "@lucide/svelte";
  import { fly, fade } from "svelte/transition";
  import {
    scorePlans,
    GOALS,
    loadConcentration,
    redundancySummary,
    exl3Recommendation,
    modelSummary,
    pct,
  } from "./lib/recommend.js";
  import { strategyOptions, READINESS } from "./lib/strategies.js";
  import { fitSummary, fitStack, kvGiB, KV_TOKENS_PER_GIB_DEFAULT } from "./lib/fit.js";

  // `open` toggles the right tray overlay; `run` is the atlas run detail.
  let { open = false, run = null, modelSizeBytes = null, modelParams = null, onclose = () => {} } = $props();

  let goal = $state("balanced");
  let fitGiB = $state(""); // memory budget the deployment must fit in
  let ctx = $state(98304); // context length flowing through the KV cache
  let weightsNode = $state(""); // per-node weights GiB; empty = use plan resident

  const sc = $derived(scorePlans(run, goal, fitGiB ? Number(fitGiB) : null));
  const planResidentPerNode = sc.recommended?.bytes ? (sc.recommended.bytes / 1024 ** 3) / 2 : 0;
  const fit = $derived(
    fitSummary(weightsNode ? Number(weightsNode) : planResidentPerNode, Number(ctx) || 0)
  );
  const budget = $derived(fitGiB ? Number(fitGiB) : null);
  const hasBudget = $derived(budget !== null && budget > 0);
  const usedPct = $derived(hasBudget ? Math.max(0, (fit.row.used / budget) * 100) : null);
  const strat = $derived(
    strategyOptions(run, goal, fitGiB ? Number(fitGiB) : null, {
      stored_size_bytes: modelSizeBytes,
      params: modelParams,
    })
  );
  const cons = $derived(loadConcentration(run?.saliency));
  const red = $derived(redundancySummary(run?.keep_maps));
  const sum = $derived(modelSummary(run));
  const exl3 = $derived(exl3Recommendation({ stored_size_bytes: modelSizeBytes, params: modelParams }));
  const hotExperts = $derived(cons.top.slice(0, 3));
  const goalKeys = Object.keys(GOALS);

  function gb(bytes) {
    return bytes == null ? null : (bytes / 1024 ** 3).toFixed(2);
  }
  function pctNorm(gib, total) {
    return total > 0 ? Math.max(0, (gib / total) * 100) : 0;
  }
  function usedSegPct(gib) {
    const t = fit.row.weights + fit.row.kv + fit.row.overhead;
    return t > 0 ? (gib / t) * 100 : 0;
  }
  // Approximate per-node footprint after applying a strategy: takes the recommended
  // plan's resident weight footprint per node, applies the option's reduction
  // multiplier, then recomputes weights + KV + overhead for the current context.
  function optionUsedGiB(red) {
    const w = planResidentPerNode * (red ?? 1);
    return fitStack({ weightsGiB: w, contextTokens: Number(ctx) || 0 }).used;
  }
  function optionPct(red) {
    return hasBudget ? (optionUsedGiB(red) / budget) * 100 : null;
  }
  function segColor(name) {
    return (
      { Weights: "var(--accent)", "KV cache": "#fbbf24", "Activations + graphs": "#6b7280", Free: "#232a35" }[
        name
      ] ?? "var(--border)"
    );
  }
  function fitsText(p) {
    if (p.fits_budget === null) return "—";
    return p.fits_budget ? "yes" : "over";
  }
</script>

{#if open}
  <div class="rec-backdrop" role="presentation" onclick={onclose} in:fade={{ duration: 180 }} out:fade={{ duration: 160 }}></div>
  <aside
    class="rec-tray"
    role="dialog"
    aria-label="Recommendations"
    in:fly={{ x: 460, duration: 260 }}
    out:fly={{ x: 460, duration: 200 }}
  >
    <header class="rec-head">
      <h3 style="display:flex;align-items:center;gap:8px;margin:0"><Sparkles size="15" /> Recommendations</h3>
      <button class="btn small" onclick={onclose}><X size="13" /> Close</button>
    </header>
    <p class="mut rec-intro" style="font-size:14px;margin:0;line-height:1.5">
      What you can do to fit this model in your hardware. Pick what matters most and set a
      memory budget — the advice changes to match. Every figure comes from this run's trace.
    </p>

    <div class="rec-body">
      <!-- use-case inputs -->
      <div class="rec-field">
        <div class="rec-label">What matters most?</div>
        <div class="rec-goals">
          {#each goalKeys as g (g)}
            <button
              class="rec-goal {goal === g ? 'on' : ''}"
              onclick={() => (goal = g)}
              title="{GOALS[g].q*100}% quality · {GOALS[g].s*100}% speed · {GOALS[g].f*100}% fit"
            >
              {GOALS[g].label}
            </button>
          {/each}
        </div>
      </div>
      <div class="rec-field">
        <div class="rec-label">Memory budget it must fit in (GiB)</div>
        <input type="number" min="0" placeholder="e.g. 114" bind:value={fitGiB} style="width:100%" />
      </div>
      <div class="rec-field">
        <div class="rec-label">Context length (tokens) — drives the KV cache</div>
        <select style="width:100%" bind:value={ctx}>
          <option value={8192}>8K (8192)</option>
          <option value={32768}>32K (32768)</option>
          <option value={98304}>96K (98304)</option>
          <option value={131072}>128K (131072)</option>
        </select>
      </div>
      <div class="rec-field">
        <div class="rec-label">Model weights per node (GiB) — leave blank to auto</div>
        <input type="number" min="0" placeholder="auto (plan)" bind:value={weightsNode} style="width:100%" />
      </div>
      {#if !sc.hasBudget}
        <p class="mut" style="font-size:13px;margin:6px 0 0">
          No budget set — “fit-in-memory” is ignored until you enter one.
        </p>
      {/if}

      <!-- strategies: rank the full lever space against the user's goal -->
      <div class="card">
        <div class="strat-title">
          <h4 style="margin:0">Strategies to consider</h4>
          <span class="mut" style="font-size:13px">ranked for “{GOALS[goal].label}”</span>
        </div>
        {#if strat.combo?.recommended}
          <div class="combo-note">
            <strong>Quality-preserving path for fitting:</strong> {strat.combo.name}
            <p class="mut" style="font-size:13px;margin:4px 0 0;line-height:1.5">{strat.combo.why}</p>
          </div>
        {/if}
        {#each strat.list as s, i (s.key)}
          <div class="strat-row {i === 0 ? 'top' : 'dim'}">
            <div class="strat-head">
              <span class="strat-rank">{i + 1}</span>
              <span class="strat-name">{s.name}</span>
              {#if i === 0}<span class="badge pass">best for you</span>{/if}
              <span class="badge {READINESS[s.readiness].cls}">{READINESS[s.readiness].label}</span>
            </div>
            <p class="strat-what">{s.what}</p>
            <p class="strat-evidence">{s.evidence}</p>
            <div class="strat-foot">
              <span class="strat-gib">~{optionUsedGiB(s.red).toFixed(1)} GiB</span>
              {#if hasBudget && optionPct(s.red) != null}
                <span class="strat-pct">({optionPct(s.red).toFixed(0)}% of {budget} GiB)</span>
              {/if}
            </div>
          </div>
        {/each}
        <p class="mut" style="font-size:13px;margin:10px 0 0;line-height:1.5">{strat.provenance}</p>
      </div>

      <!-- fit & context: KV-aware dual-node fit (mirrors the dual-Spark recipe) -->
      <div class="card">
        <h4 style="display:flex;align-items:center;gap:8px">
          Fit &amp; context <span class="badge {fit.fits ? 'pass' : 'error'}">{fit.fits ? "fits" : "over budget"}</span>
        </h4>
        <p style="font-size:14px;margin:0 0 8px;line-height:1.55">
          At <strong>{(ctx / 1024).toFixed(0)}K tokens</strong>: weights
          ({fit.row.weights.toFixed(1)} GiB/node) + <strong>KV cache ({fit.row.kv.toFixed(1)} GiB)</strong>
          + activations/graphs ({fit.row.overhead.toFixed(1)} GiB) ={" "}
          <strong>{fit.row.used.toFixed(1)} / {fit.row.usableGiB.toFixed(0)} GiB per node</strong>.
          {fit.fits
            ? `Fits with ${fit.row.free.toFixed(1)} GiB free.`
            : `Over by ${fit.row.over.toFixed(1)} GiB — shorten context or shrink weights.`}
        </p>
        {#if hasBudget}
          <div class="budget-readout">
            <span class="budget-amt">
              {fit.row.used.toFixed(1)} GiB of <strong>{budget} GiB</strong> budget
              <span class="budget-pct">({usedPct.toFixed(0)}%)</span>
            </span>
            {#if usedPct > 100}
              <span class="error">over by {fit.row.over.toFixed(1)} GiB</span>
            {:else}
              <span class="ok">{fit.row.free.toFixed(1)} GiB free</span>
            {/if}
          </div>
          <div class="fit-bar budget {usedPct > 100 ? 'over' : ''}">
            {#if usedPct > 0}
              <div class="fit-fill" style="width:{Math.min(usedPct, 100)}%">
                <div class="fit-seg" style="width:{usedSegPct(fit.row.weights)}%;background:{segColor('Weights')}" title="Weights: {fit.row.weights.toFixed(1)} GiB"></div>
                <div class="fit-seg" style="width:{usedSegPct(fit.row.kv)}%;background:{segColor('KV cache')}" title="KV cache: {fit.row.kv.toFixed(1)} GiB"></div>
                <div class="fit-seg" style="width:{usedSegPct(fit.row.overhead)}%;background:{segColor('Activations + graphs')}" title="Activations + graphs: {fit.row.overhead.toFixed(1)} GiB"></div>
              </div>
            {/if}
          </div>
          <div class="fit-legend">
            <span><i style="background:{segColor('Weights')}"></i> Weights {fit.row.weights.toFixed(1)}G</span>
            <span><i style="background:{segColor('KV cache')}"></i> KV {fit.row.kv.toFixed(1)}G</span>
            <span><i style="background:{segColor('Activations + graphs')}"></i> Act {fit.row.overhead.toFixed(1)}G</span>
          </div>
        {:else}
          <div class="fit-bar">
            {#each fit.row.segments as seg (seg.name)}
              <div
                class="fit-seg"
                style="width:{pctNorm(seg.gib, fit.row.usableGiB)}%;background:{segColor(seg.name)}"
                title="{seg.name}: {seg.gib.toFixed(1)} GiB"
              ></div>
            {/each}
          </div>
          <div class="fit-legend">
            {#each fit.row.segments as seg (seg.name)}
              <span><i style="background:{segColor(seg.name)}"></i> {seg.name} {seg.gib.toFixed(1)}G</span>
            {/each}
          </div>
        {/if}
        <p class="mut" style="font-size:13px;margin:8px 0 0;line-height:1.5">
          KV is an estimate (~{KV_TOKENS_PER_GIB_DEFAULT.toLocaleString()} tokens/GiB, from the dual-Spark
          recipe; {kvGiB(ctx).toFixed(1)} GiB at {(ctx / 1024).toFixed(0)}K). Longest standard context that
          fits: <strong style="color:var(--text)">{(fit.maxFit / 1024).toFixed(0)}K</strong>.
        </p>
        <div class="table-scroll" style="margin-top:8px">
          <table>
            <thead><tr><th>Context</th><th>Fits</th><th>Used / node</th><th>Free</th></tr></thead>
            <tbody>
              {#each fit.across as a (a.contextTokens)}
                <tr>
                  <td>{(a.contextTokens / 1024).toFixed(0)}K</td>
                  <td><span class={a.fits ? "ok" : "error"}>{a.fits ? "yes" : "over"}</span></td>
                  <td>{a.used.toFixed(1)} / {a.usableGiB.toFixed(0)}</td>
                  <td>{a.free.toFixed(1)} GiB</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>

      <!-- plan detail: the prune sub-view (collapsed to keep the menu primary) -->
      <details class="card" open>
        <summary style="cursor:pointer">
          <span style="display:flex;align-items:center;gap:6px"><Cpu size="14" /> Recommended plan <span class="badge">detail</span></span>
        </summary>
        <div style="margin-top:8px">
        {#if sc.recommended}
          {@const r = sc.recommended}
          <p style="font-size:14px;margin:0 0 8px;line-height:1.55">
            For <strong>“{GOALS[sc.goalKey].label}”</strong> keep
            <strong>{r.keep_per_layer} of {sc.nExp} experts</strong> per layer
            (<span class="mono">{r.name}</span>): <strong>{pct(r.quality)}%</strong> of real traffic,
            <strong>{r.dropped_pct}%</strong> fewer experts
            {r.bytes ? `, ${gb(r.bytes)} GiB` : ""}.
            {#if r.fits_budget !== null}
              {r.fits_budget
                ? `Fits your ${fitGiB} GiB budget.`
                : `Warning: needs ${gb(r.bytes)} GiB, over your ${fitGiB} GiB budget.`}
            {/if}
          </p>
          {#if sc.bestQuality && sc.bestQuality.name !== r.name}
            <p class="mut" style="font-size:13px;margin:0;line-height:1.55">
              This “{GOALS[sc.goalKey].label}” choice trades something for the rest: max quality = <strong style="color:var(--text)">{sc.bestQuality.name}</strong>
              ({pct(sc.bestQuality.quality)}% traffic)
              {#if sc.bestSpeed && sc.bestSpeed.name !== r.name}
                · max speed = <strong style="color:var(--text)">{sc.bestSpeed.name}</strong> ({sc.bestSpeed.dropped_pct}% fewer experts)
              {/if}
              {#if sc.hasBudget && sc.bestFit && sc.bestFit.name !== r.name && sc.bestFit.name !== sc.bestSpeed?.name}
                · best fit = <strong style="color:var(--text)">{sc.bestFit.name}</strong>
              {/if}.
            </p>
          {/if}

          <div class="table-scroll" style="margin-top:12px">
            <table>
              <thead>
                <tr>
                  <th>Plan</th>
                  <th>Quality</th>
                  <th>Speed</th>
                  <th>Memory</th>
                  <th>Fits{fitGiB ? ` ≤${fitGiB}G` : ""}</th>
                </tr>
              </thead>
              <tbody>
                {#each sc.scored as p (p.name)}
                  <tr class={p.name === sc.recommended?.name ? "rec-row" : ""}>
                    <td class="mono">
                      {p.name}
                      {#if p.name === sc.recommended?.name}<span class="badge">rec</span>{/if}
                    </td>
                    <td>{pct(p.quality)}%</td>
                    <td>{p.dropped_pct}%</td>
                    <td>{p.bytes ? `${gb(p.bytes)} GiB` : "—"}</td>
                    <td><span class={p.fits_budget === false ? "error" : "mut"}>{fitsText(p)}</span></td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
          {/if}
        </div>
      </details>

      <!-- busiest experts -->
      <div class="card">
        <h4 style="display:flex;align-items:center;gap:6px"><ShieldCheck size="14" /> Protect the busiest experts</h4>
        {#if hotExperts.length}
          <p style="font-size:14px;margin:0 0 8px;line-height:1.55">
            e{hotExperts.map((t) => t.expert).join(", e")} carry <strong>{pct(cons.topShare)}%</strong>
            of traffic — keep them full-width; quieter experts are the prune candidates.
          </p>
        {/if}
        <p class="mut" style="font-size:13px;margin:0;line-height:1.55">
          Protected everywhere: <strong style="color:var(--text)">{red.protectedCount}</strong> ·
          fully redundant: <strong style="color:var(--text)">{red.redundant}</strong>
          {red.nLayers ? ` · ${red.nLayers} layers` : ""}.
        </p>
      </div>

      <!-- EXL3 -->
      <div class="card">
        <h4 style="display:flex;align-items:center;gap:6px"><HardDrive size="14" /> Next: EXL3 storage</h4>
        {#if exl3}
          <p style="font-size:14px;margin:0 0 8px;line-height:1.55">
            Stored at <strong>{exl3.achieved.toFixed(1)} bits/weight</strong>; EXL3 toward
            <strong>{exl3.target_bpw} bpw</strong> → <strong>{pct(exl3.shrink)}% smaller</strong>.
          </p>
          <p class="mut" style="font-size:13px;margin:0">Next milestone — needs a quantizer wired to the checkpoint.</p>
        {:else}
          <p style="font-size:14px;margin:0 0 8px;line-height:1.55">EXL3 stores the model in fewer bits per weight.</p>
          <p class="mut" style="font-size:13px;margin:0">Not computed on this run — added once a quantizer is connected.</p>
        {/if}
      </div>

      <details style="margin-top:14px">
        <summary class="mut" style="cursor:pointer;font-size:13px">In one line</summary>
        <p class="mut" style="font-size:13px;margin:8px 0 0;line-height:1.55">
          {sum.traceTokens} tokens → {sum.nLayers} layers × {sum.nExp} experts
          {#if sum.topExpert != null}· busiest expert e{sum.topExpert} = {sum.topSharePct}% of traffic{/if}.
        </p>
      </details>
    </div>
  </aside>
{/if}

<style>
  .rec-backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.55); z-index: 50; }
  .rec-tray {
    position: fixed; top: 0; right: 0; height: 100vh; width: min(660px, 100vw);
    background: var(--bg); border-left: 1px solid var(--border); z-index: 51;
    display: flex; flex-direction: column; box-shadow: -12px 0 32px rgba(0,0,0,.35);
  }
  .rec-head { display: flex; align-items: center; justify-content: space-between; padding: 18px 22px 10px; }
  .rec-head h3, .rec-body h4 { font-size: 16px; font-weight: 600; }
  .rec-body .strat-title h4 { margin: 0; }
  .rec-intro { padding: 0 22px 14px; }
  .rec-body { padding: 0 22px 28px; overflow-y: auto; }
  .rec-field { margin-bottom: 14px; }
  .rec-field:last-of-type { margin-bottom: 4px; }
  .rec-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; margin: 0 0 6px; }
  .rec-goals { display: flex; gap: 6px; flex-wrap: wrap; }
  .rec-goal {
    background: var(--panel-2); color: var(--text); border: 1px solid var(--border);
    border-radius: 6px; padding: 6px 12px; font-size: 13px; cursor: pointer;
  }
  .rec-goal:hover { border-color: var(--accent); }
  .rec-goal.on { background: rgba(79,140,255,.16); color: var(--accent); border-color: var(--accent); font-weight: 600; }
  .rec-row td { background: rgba(79, 140, 255, 0.06); }
  .rec-body .card:first-of-type { margin-top: 12px; }
  .card + .card { margin-top: 14px; }
  .strat-title { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 10px; gap: 8px; }
  .combo-note {
    background: var(--panel-2);
    border: none;
    border-radius: 10px; padding: 12px 14px; margin-bottom: 12px; font-size: 14px;
  }
  .strat-row { padding: 10px 2px; border-bottom: 1px solid var(--border); }
  .strat-row:last-of-type { border-bottom: none; padding-bottom: 0; }
  .strat-row.top { background: transparent; }
  .strat-row.dim { opacity: 0.5; }
  .strat-row.dim:hover { opacity: 1; }
  .strat-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .strat-rank { color: var(--muted); font-family: "JetBrains Mono", ui-monospace, monospace; font-size: 12px; }
  .strat-name { font-weight: 600; }
  .strat-what { font-size: 13px; margin: 4px 0 2px; line-height: 1.5; }
  .strat-evidence { font-size: 13px; color: var(--muted); margin: 0; line-height: 1.5; }
  .strat-foot { display: flex; justify-content: flex-end; align-items: baseline; gap: 5px; margin-top: 6px; font-size: 12px; }
  .strat-gib { font-family: "JetBrains Mono", ui-monospace, monospace; color: var(--accent); font-weight: 600; }
  .strat-pct { color: var(--muted); }
  .budget-readout { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; flex-wrap: wrap; margin: 2px 0 6px; font-size: 14px; }
  .budget-amt { font-weight: 600; }
  .budget-pct { color: var(--muted); font-weight: 400; }
  .fit-bar { display: flex; gap: 2px; height: 16px; border-radius: 3px; overflow: hidden; background: var(--panel); margin: 4px 0 8px; }
  .fit-bar.budget { height: 20px; background: var(--panel); }
  .fit-bar.budget.over { box-shadow: 0 0 0 2px var(--error, #ef4444); }
  .fit-fill { display: flex; height: 100%; overflow: hidden; background: var(--accent); transition: width .2s ease; }
  .fit-seg { height: 100%; display: inline-block; min-width: 1px; }
  .fit-legend { display: flex; gap: 12px; flex-wrap: wrap; font-size: 12px; color: var(--muted); }
  .fit-legend i { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 4px; vertical-align: -1px; }
</style>
