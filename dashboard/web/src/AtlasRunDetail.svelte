<script>
  import { onMount } from "svelte";
  import { get } from "./lib/api.js";
  import { Layers, Sparkles } from "@lucide/svelte";
  import RecommendationsTray from "./RecommendationsTray.svelte";

  let { runId } = $props();

  let runDetail = $state(null);
  let error = $state(null);
  let recOpen = $state(false);
  let planSel = $state("");

  async function load() {
    error = null;
    try {
      runDetail = await get(`/api/atlas-runs/${encodeURIComponent(runId)}`);
      recOpen = true; // guide the user on fitting this model after the run
      // Default the keep/routing overlay to the most aggressive plan (smallest
      // top-k), which is also the server's primary keep-map budget.
      const budgets = (runDetail.plans ?? []).map((p) => p.keep_per_layer ?? 0);
      const best = Math.min(...(budgets.length ? budgets : [0]));
      const def = (runDetail.plans ?? []).find((p) => p.keep_per_layer === best);
      planSel = def?.name ?? runDetail.plans?.[0]?.name ?? "";
    } catch (e) {
      error = String(e);
    }
  }

  $effect(() => {
    void runId;
    load();
  });

  // -- maps & routing visualizers ------------------------------------------
  function numExperts() {
    return runDetail?.topology?.num_local_experts ?? 8;
  }
  function numLayers() {
    return runDetail?.topology?.num_hidden_layers ?? runDetail?.keep_maps?.length ?? 6;
  }
  function salRow(layer, expert) {
    return (runDetail?.saliency ?? []).find((s) => s.layer === layer && s.expert === expert);
  }
  function maxSaliency() {
    let m = 0;
    for (const s of runDetail?.saliency ?? []) if (s.total_value > m) m = s.total_value;
    return m > 0 ? m : 1;
  }
  function heatStyle(row) {
    if (!row) return "background: transparent; color: var(--muted)";
    const rel = Math.min(1, (row.total_value || 0) / maxSaliency());
    const alpha = 0.14 + 0.86 * rel;
    const fg = rel > 0.5 ? "#0b0e13" : "var(--text)";
    return `background: rgba(79,140,255,${alpha.toFixed(3)}); color: ${fg}`;
  }
  function planBudget(name) {
    return (runDetail?.plans ?? []).find((p) => p.name === name)?.keep_per_layer ?? numExperts();
  }
  function planShort(name) {
    return String(name ?? "")
      .replace(/^keep/, "top-")
      .replace("-full", " · full")
      .replace("-saliency", " · saliency");
  }
  function keptFor(k) {
    const out = [];
    for (let L = 0; L < numLayers(); L++) {
      const ranked = [];
      for (let e = 0; e < numExperts(); e++) ranked.push([e, salRow(L, e)?.total_value ?? 0]);
      ranked.sort((a, b) => b[1] - a[1]);
      out[L] = new Set(ranked.slice(0, Math.max(0, Math.min(k, numExperts()))).map((x) => x[0]));
    }
    return out;
  }
  function keptIds(kset) {
    return [...kset].sort((a, b) => a - b).map((e) => `e${e}`).join(" ");
  }
  function routingShare(layer, expert) {
    let sum = 0;
    for (const s of runDetail?.saliency ?? []) if (s.layer === layer) sum += s.frequency || 0;
    if (!sum) return 0;
    return (salRow(layer, expert)?.frequency || 0) / sum;
  }

  // -- blueprint digest -----------------------------------------------------
  const DIGEST_LABELS = Object.freeze({
    code_generation: "code",
    mathematical_reasoning: "maths",
    long_context_retrieval: "long-ctx",
    tool_selection: "tools",
    planning: "planning",
    spatial_reasoning: "spatial",
    state_tracking: "state",
  });

  function labelLeaderLayers(label) {
    const acc = {};
    for (const s of runDetail?.saliency_by_label ?? []) {
      if (s.label !== label) continue;
      acc[s.expert] = (acc[s.expert] ?? 0) + (s.total_value ?? 0);
    }
    const top = Object.entries(acc).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([e]) => +e);
    return top.map((exp) => {
      const layers = [
        ...new Set(
          (runDetail?.saliency_by_label ?? [])
            .filter((s) => s.label === label && s.expert === exp && (s.total_value ?? 0) > 0)
            .map((s) => s.layer)
        ),
      ].sort((a, b) => a - b);
      return { expert: exp, layers: layers.slice(0, 4) };
    });
  }
  function digestLabels() {
    const labels = {};
    for (const s of runDetail?.saliency_by_label ?? []) labels[s.label] = (labels[s.label] ?? 0) + 1;
    return Object.keys(labels)
      .sort()
      .map((label) => ({ label, leaders: labelLeaderLayers(label) }));
  }
  function traceLeaders(n = 5) {
    const exp = {};
    for (const s of runDetail?.saliency ?? []) exp[s.expert] = (exp[s.expert] ?? 0) + (s.activation_count ?? 0);
    return Object.entries(exp).sort((a, b) => b[1] - a[1]).slice(0, n).map(([e, c]) => ({ expert: +e, count: c }));
  }
  function redundantDigest() {
    const kept = new Map();
    for (const km of runDetail?.keep_maps ?? []) {
      for (const e of km.entries ?? []) {
        const id = e.unit?.source_unit_id;
        if (id == null) continue;
        if (!kept.has(id)) kept.set(id, new Set());
        if (e.kept) kept.get(id).add(km.layer_index);
      }
    }
    const nLayers = runDetail?.keep_maps?.length ?? 0;
    const protectedE = [];
    const redundantE = [];
    for (const [id, layers] of kept) {
      if (nLayers > 0 && layers.size === nLayers) protectedE.push(id);
      else if (layers.size === 0) redundantE.push(id);
    }
    return { protectedE: protectedE.sort((a, b) => a - b), redundantE: redundantE.sort((a, b) => a - b) };
  }
  function planTotalKept(p) {
    const vals = Object.values(p.kept_per_layer ?? {});
    const kept = vals.reduce((a, b) => a + (Number(b) || 0), 0);
    return Number.isFinite(kept) ? kept : 0;
  }
  function labelShort(label) {
    return DIGEST_LABELS[label] ?? label;
  }
</script>

<a class="mut" href="#/atlas">← Back to Atlas Lab</a>

{#if error}
  <div class="card error" style="margin-top:12px">Error: <span class="mut">{error}</span></div>
{/if}

{#if runDetail}
  <section class="card" style="margin-top:12px">
    <h2>
      Atlas run <span class="mono">{runDetail.atlas_run_id}</span>
      <span class="badge">{runDetail.status}</span>
      <button class="btn small" style="float:right" on:click={() => (recOpen = true)}><Sparkles size="13" /> Recommendations</button>
    </h2>
    <table>
      <tbody>
        <tr><th>Source checkpoint</th><td class="mono">{runDetail.source_checkpoint_id}</td></tr>
        <tr><th>Calibration suite</th><td class="mono">{runDetail.calibration_suite_id} · {runDetail.n_tasks} tasks</td></tr>
        <tr><th>Evidence level</th><td>{runDetail.evidence_level}</td></tr>
        <tr><th>Topology (synthetic)</th><td>
          {runDetail.topology?.num_hidden_layers} layers · {runDetail.topology?.num_local_experts} experts · top-{runDetail.topology?.num_experts_per_tok}
        </td></tr>
        <tr><th>Trace events</th><td>{runDetail.trace_count}</td></tr>
      </tbody>
    </table>

    <h3 style="margin-top:28px">Candidate plans (from measured saliency)</h3>
    <div class="table-scroll">
      <table>
        <thead><tr><th>Plan</th><th>Strategy</th><th>Kept / layer</th><th>Resident (F32)</th><th>Resident (BF16)</th></tr></thead>
        <tbody>
          {#each runDetail.plans as p (p.name)}
            <tr>
              <td class="mono">{p.name}</td>
              <td class="mut">{p.strategy}</td>
              <td>{Object.values(p.kept_per_layer ?? {})[0] ?? "—"}</td>
              <td>{(p.resident_bytes_a / 1024).toFixed(1)} KB</td>
              <td>{(p.resident_bytes_b / 1024).toFixed(1)} KB</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <!-- BLUEPRINT DIGEST -->
    <section class="card" style="margin-top:12px">
      <h2 style="display:flex;align-items:center;gap:8px">
        <Layers size="15" /> Blueprint digest <span class="badge">read me first</span>
      </h2>

      <div class="card" style="margin-top:16px">
        <h4>What happened (trace)</h4>
        <p style="font-size:13px;margin:2px 0 8px;display:flex;gap:16px;flex-wrap:wrap">
          <span><strong style="color:var(--text)">{runDetail.trace_count}</strong> routed tokens</span>
          <span><strong style="color:var(--text)">{runDetail.n_tasks}</strong> capability tasks</span>
          <span>
            <strong style="color:var(--text)">{runDetail.topology?.num_hidden_layers ?? 0}</strong> layers ×
            <strong style="color:var(--text)">{runDetail.topology?.num_local_experts ?? 0}</strong> experts
          </span>
        </p>
        <p style="font-size:13px;margin:0">
          Heaviest experts by routed tokens:
          {#each traceLeaders() as l (l.expert)}<span class="chip">e{l.expert} · {l.count}</span>{/each}
        </p>
      </div>

      <div class="card" style="margin-top:16px">
        <h4>Who is responsible for what (behaviour / semantic map)</h4>
        <p class="mut" style="font-size:13px;margin:0 0 8px">Top experts per capability by measured saliency; strongest layers in brackets.</p>
        <div class="table-scroll">
          <table>
            <thead><tr><th>Capability</th><th>Lead experts (strong layers)</th></tr></thead>
            <tbody>
              {#each digestLabels() as d (d.label)}
                <tr>
                  <td class="mono">{labelShort(d.label)}</td>
                  <td>
                    {#if d.leaders.length}
                      {#each d.leaders as l (l.expert)}<span class="chip">e{l.expert}{l.layers.length ? " · L" + l.layers.join(", L") : ""}</span>{/each}
                    {:else}<span class="mut">—</span>{/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>

      <div class="card" style="margin-top:16px">
        <h4>How much can we prune (keep / redundancy)</h4>
        <p class="mut" style="font-size:13px;margin:0 0 8px">
          Primary keep map (top-{runDetail.keep_maps?.[0]?.top_k ?? "?"}): experts kept in every layer are <em>protected</em>;
          experts kept in no layer are <em>redundant</em> here.
        </p>
        <p style="font-size:13px;margin:0">
          Protected:
          {#each redundantDigest().protectedE as e (e)}<span class="chip on">e{e}</span>{:else}<span class="mut">none</span>{/each}
          &nbsp;·&nbsp; Redundant (fully pruned):
          {#each redundantDigest().redundantE as e (e)}<span class="chip">e{e}</span>{:else}<span class="mut">none</span>{/each}
        </p>
        <p class="mut" style="font-size:13px;margin:8px 0 0">
          Kept experts across all layers per plan:
          {#each runDetail.plans as p (p.name)}<span class="mono" style="margin-right:10px">{p.name}: {planTotalKept(p)}</span>{/each}
        </p>
      </div>

      <details style="margin-top:16px">
        <summary class="mut" style="cursor:pointer;font-size:13px">How to read this</summary>
        <ul class="mut" style="font-size:13px;margin:8px 0 0;padding-left:18px;line-height:1.6">
          <li><strong style="color:var(--text)">Trace</strong> — every routed token through a (layer, expert) during calibration. High counts signal hot experts.</li>
          <li><strong style="color:var(--text)">Behaviour / semantic map</strong> — which experts a capability routes to most; an expert leading several capabilities is multipurpose.</li>
          <li><strong style="color:var(--text)">Keep map</strong> — the prune decision (top-k experts per layer by measured saliency). Protected experts serve every layer; redundant experts never rank high enough to keep.</li>
          <li>Intensity maps below show the same measured data per layer × expert — the digest above is just the plain-language summary.</li>
        </ul>
      </details>
    </section>

    <RecommendationsTray open={recOpen} run={runDetail} onclose={() => (recOpen = false)} />

    <h3 style="margin-top:28px">Maps &amp; routing</h3>

    <!-- SALIENCY MAP -->
    <div class="card" style="margin-top:16px">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px">
        <strong>Saliency map</strong>
        <span class="mut" style="font-size:12px">cell intensity ∝ total_value (measured)</span>
        <span class="mut" style="font-size:11px;margin-left:auto">low</span>
        <span class="swatch low"></span><span class="swatch mid"></span><span class="swatch high"></span>
        <span class="mut" style="font-size:11px">high</span>
      </div>
      <div class="table-scroll" style="overflow-x:auto">
        <table class="heat">
          <thead><tr><th></th>{#each Array(numExperts()) as _, e (e)}<th>e{e}</th>{/each}</tr></thead>
          <tbody>
            {#each Array(numLayers()) as _, L (L)}
              <tr>
                <td class="mut">L{L}</td>
                {#each Array(numExperts()) as _, e (e)}
                  {@const row = salRow(L, e)}
                  <td class="hcell" style={heatStyle(row)}
                      title="expert e{e} · total_value {row?.total_value?.toFixed?.(4) ?? '—'} · freq {row?.frequency?.toFixed?.(4) ?? '—'} · activations {row?.activation_count ?? '—'}">
                    {row?.total_value?.toFixed?.(2) ?? '—'}
                  </td>
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>

    <!-- KEEP MAP -->
    <div class="card" style="margin-top:16px">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px">
        <strong>Keep map</strong>
        <span class="mut" style="font-size:12px">
          <span class="chip on" style="padding:1px 6px">✓ kept</span> vs
          <span class="chip" style="padding:1px 6px">✕ pruned</span> — per layer, by measured saliency
        </span>
      </div>
      <div style="display:flex;gap:6px;margin:8px 0;flex-wrap:wrap">
        {#each runDetail.plans as p (p.name)}
          <button class="btn small {planSel === p.name ? 'primary' : ''}" on:click={() => (planSel = p.name)}>{planShort(p.name)}</button>
        {/each}
      </div>
      {#if planSel}
        <div class="table-scroll" style="overflow-x:auto">
          <table class="keepmap">
            <thead><tr><th></th>{#each Array(numExperts()) as _, e (e)}<th>e{e}</th>{/each}<th>kept</th></tr></thead>
            <tbody>
              {#each Array(numLayers()) as _, L (L)}
                {@const kset = keptFor(planBudget(planSel))[L]}
                <tr>
                  <td class="mut">L{L}</td>
                  {#each Array(numExperts()) as _, e (e)}
                    <td class="kmc {kset.has(e) ? 'kept' : 'prune'}" title="layer {L} · expert e{e} · saliency {salRow(L, e)?.total_value?.toFixed?.(4) ?? '—'}">{kset.has(e) ? '✓' : ''}</td>
                  {/each}
                  <td class="mut">{kset.size}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        <p class="mut" style="font-size:12px;margin-top:6px">
          Kept per layer under <span class="mono">{planSel}</span>:
          {#each Array(numLayers()) as _, L (L)}
            {@const kset = keptFor(planBudget(planSel))[L]}
            <span class="mono">L{L}: {keptIds(kset)}</span>{L < numLayers() - 1 ? " · " : ""}
          {/each}
        </p>
      {/if}
    </div>

    <!-- ROUTING MAP -->
    <div class="card" style="margin-top:16px">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px">
        <strong>Routing</strong>
        <span class="mut" style="font-size:12px">bar = share of routed tokens per expert</span>
      </div>
      {#each Array(numLayers()) as _, L (L)}
        {@const kset = keptFor(planBudget(planSel))[L]}
        <div style="margin:6px 0;display:flex;align-items:center;gap:8px">
          <span class="mut mono" style="width:30px;flex:0 0 30px">L{L}</span>
          <div class="routing">
            {#each Array(numExperts()) as _, e (e)}
              {@const share = routingShare(L, e)}
              <span class="rseg {kset.has(e) || !planSel ? '' : 'dim'}"
                    style="width:{Math.max(2, share * 100)}%"
                    title="e{e} · {Math.round(share * 100)}% of routed tokens in layer {L}"></span>
            {/each}
          </div>
          <span class="mut" style="font-size:11px;width:200px;flex:0 0 200px;text-align:right">{keptIds(kset)} kept</span>
        </div>
      {/each}
    </div>
  </section>
{/if}
