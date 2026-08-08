<script>
  import { onMount, onDestroy } from "svelte";
  import { get, post } from "./lib/api.js";
  import { Activity, Play, Pause, RotateCcw, X, Database, Layers, Sparkles } from "@lucide/svelte";
  import RecommendationsTray from "./RecommendationsTray.svelte";

  // -- external Atlas engine (existing connect/integrate surface) -----------
  let status = $state(null);
  let install = $state(null);
  let url = $state("");
  let working = $state(false);
  let error = $state(null);
  let notice = $state(null);

  // -- build-atlas wizard ---------------------------------------------------
  let cfg = $state(null);
  let cfgError = $state(null);
  let source = $state("");
  let suiteRef = $state("");
  let depth = $state("basic");
  let budgets = $state("");
  let estimate = $state(null);
  let estimating = $state(false);
  let estimateError = $state(null);
  let launching = $state(false);

  // -- job monitor ----------------------------------------------------------
  let jobs = $state([]);
  let jobsError = $state(null);

  // -- completed runs -------------------------------------------------------
  let runs = $state([]);
  let runsError = $state(null);
  let runDetail = $state(null);
  let runDetailError = $state(null);
  let recOpen = $state(false);
  let showMonitor = $state(true);
  let monitorTab = $state("current"); // "current" | "completed"
  let modalOpen = $state(false);
  let modalTab = $state("current");

  const VISIBLE = 8; // line items that fit the panel height before "Show all"

  const activeJobs = $derived(jobs.filter((j) => ACTIVE.has(j.state)));

  function openModal(tab) {
    modalTab = tab;
    modalOpen = true;
  }

  const ACTIVE = new Set([
    "queued",
    "running",
    "pausing",
    "paused",
    "resuming",
    "cancelling",
    "draft",
  ]);
  const TERMINAL = new Set([
    "completed",
    "completed_with_warnings",
    "failed",
    "failed_recoverable",
    "cancelled",
  ]);

  async function loadConfig() {
    try {
      cfg = await get("/api/atlas/config");
      const preferred = (cfg.sources ?? []).find((s) => s.atlas_compatible);
      if (!source) source = preferred?.asset_id ?? cfg.sources?.[0]?.asset_id ?? "";
      if (!suiteRef && cfg.suites?.length) suiteRef = cfg.suites[0].suite_ref;
      if (!budgets) budgets = (cfg.default_keep_budgets ?? [8, 6, 4, 2]).join(",");
    } catch (e) {
      cfgError = String(e);
    }
  }

  function currentSource() {
    return (cfg?.sources ?? []).find((s) => s.asset_id === source);
  }

  function wizardPayload() {
    return {
      model_asset_id: source,
      suite_ref: suiteRef,
      trace_depth: depth,
      keep_budgets: budgets
        ? budgets
            .split(",")
            .map((b) => parseInt(b, 10))
            .filter((n) => !Number.isNaN(n))
        : undefined,
    };
  }

  async function doEstimate() {
    estimating = true;
    estimateError = null;
    estimate = null;
    try {
      estimate = await post("/api/atlas/estimate", wizardPayload());
    } catch (e) {
      estimateError = String(e);
    } finally {
      estimating = false;
    }
  }

  async function doLaunch() {
    launching = true;
    error = null;
    try {
      await post("/api/atlas-jobs", wizardPayload());
      await loadJobs();
      flash("Launched build-atlas job.");
    } catch (e) {
      error = String(e);
    } finally {
      launching = false;
    }
  }

  // -- job monitor ----------------------------------------------------------
  async function loadJobs() {
    try {
      jobs = await get("/api/atlas-jobs");
    } catch (e) {
      jobsError = String(e);
    }
  }

  async function jobAction(job_id, action) {
    try {
      await post(`/api/atlas-jobs/${encodeURIComponent(job_id)}/${action}`);
    } catch (e) {
      jobsError = String(e);
    }
    await loadJobs();
  }

  function jobLabel(state) {
    const map = {
      queued: "queued",
      running: "tracing",
      pausing: "pausing",
      paused: "paused",
      resuming: "resuming…",
      cancelling: "cancelling",
      cancelled: "cancelled",
      completed: "done",
      completed_with_warnings: "done (warnings)",
      failed: "failed",
      failed_recoverable: "interrupted",
      draft: "draft",
    };
    return map[state] ?? state;
  }

  function jobCls(state) {
    if (state === "completed" || state === "completed_with_warnings") return "ok";
    if (state === "failed" || state === "cancelled") return "error";
    if (state === "paused") return "type";
    return "mut";
  }

  function hasActiveJobs() {
    return jobs.some((j) => ACTIVE.has(j.state));
  }
  function activeJobsCount() {
    return jobs.filter((j) => ACTIVE.has(j.state)).length;
  }

  // -- completed runs -------------------------------------------------------
  async function loadRuns() {
    try {
      runs = await get("/api/atlas-runs");
    } catch (e) {
      runsError = String(e);
    }
  }

  async function showRun(run_id) {
    runDetail = null;
    runDetailError = null;
    try {
      runDetail = await get(`/api/atlas-runs/${encodeURIComponent(run_id)}`);
      recOpen = true; // guide the user on fitting this model after the run
      // Default the keep/routing overlay to the most aggressive plan (smallest
      // top-k), which is also the server's primary keep-map budget.
      const budgets = (runDetail.plans ?? []).map((p) => p.keep_per_layer ?? 0);
      const best = Math.min(...(budgets.length ? budgets : [0]));
      const def = (runDetail.plans ?? []).find((p) => p.keep_per_layer === best);
      planSel = def?.name ?? runDetail.plans?.[0]?.name ?? "";
    } catch (e) {
      runDetailError = String(e);
    }
  }

  // -- maps & routing visualizers ------------------------------------------
  // All three render from the measured rows already returned by the API; the
  // keep selection reproduces the tracer's own rule (top-k by total_value) so
  // what is shown matches build_plans/build_keep_maps.
  let planSel = $state("");

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
  // kept expert ids per layer for a budget, ranked by measured total_value desc.
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
  // share of routed tokens carried by an expert in a layer (frequency normalized).
  function routingShare(layer, expert) {
    let sum = 0;
    for (const s of runDetail?.saliency ?? []) if (s.layer === layer) sum += s.frequency || 0;
    if (!sum) return 0;
    return (salRow(layer, expert)?.frequency || 0) / sum;
  }

  // -- connect surface ------------------------------------------------------
  async function loadConnect() {
    try {
      status = await get("/api/atlas");
      if (status.connected && status.reachable) url = status.url;
      else if (!status.connected) url = status.url || "http://127.0.0.1:8200/";
      if (!install) install = await get("/api/atlas/install");
    } catch (e) {
      error = String(e);
    }
  }

  async function doConnect() {
    working = true;
    error = null;
    try {
      status = await post("/api/atlas/connect?url=" + encodeURIComponent(url));
      if (status.error) notice = `Could not reach the Atlas at that URL: ${status.error}`;
    } catch (e) {
      error = String(e);
    } finally {
      working = false;
    }
  }

  async function doDisconnect() {
    working = true;
    try {
      status = await post("/api/atlas/disconnect");
    } catch (e) {
      error = String(e);
    } finally {
      working = false;
    }
  }

  let flashMsg = $state(null);
  function flash(msg) {
    flashMsg = msg;
    setTimeout(() => (flashMsg = null), 2600);
  }

  let timer = null;
  function startPolling() {
    if (timer) return;
    timer = setInterval(loadJobs, 1500);
  }
  function stopPolling() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  $effect(() => {
    if (hasActiveJobs()) startPolling();
    else stopPolling();
  });

  onMount(() => {
    loadConnect();
    loadConfig();
    loadJobs();
    loadRuns();
  });
  onDestroy(stopPolling);

  // -- blueprint digest ---------------------------------------------------
  // Plain-language summaries over the measured artifacts (behaviour/semantic
  // map, traces, keep/redundancy) so a run is digestible without MoE expertise.
  const DIGEST_LABELS = Object.freeze({ code_generation: "code", mathematical_reasoning: "maths", long_context_retrieval: "long-ctx", tool_selection: "tools", planning: "planning", spatial_reasoning: "spatial", state_tracking: "state" });

  function labelLeaderLayers(label) {
    // layers (ascending) the given label's top experts are most responsible for.
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
    const kept = new Map(); // expert id -> Set(layer indices where kept)
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

<h1>Atlas Lab</h1>
<p class="mut">
  Measure which internal experts are responsible for behaviours. eval-lab's build-atlas
  wizard runs a genuine layerwise MoE trace on a small synthetic calibration model, then
  proposes prune topologies from the measured saliency — no fabricated numbers.
</p>

{#if error}
  <div class="card error">Error: <span class="mut">{error}</span></div>
{/if}
{#if flashMsg}
  <div class="card ok" style="margin-top:10px">{flashMsg}</div>
{/if}

<div class="eval-layout" style="margin-top:12px">
  <!-- LEFT: build wizard -->
  <div class="card eval-config">
    <h3><Database size="14" style="vertical-align:-2px" /> Build atlas</h3>

    {#if cfgError}
      <div class="card error">{cfgError}</div>
      <button class="btn" on:click={loadConfig}>Retry</button>
    {:else if cfg}
      <label>
        Source model
        <select bind:value={source}>
          {#each cfg.sources ?? [] as s (s.asset_id)}
            <option value={s.asset_id}>
              {s.name} ({s.asset_id}){s.atlas_compatible ? " · layerwise" : " · not layerwise"}
            </option>
          {/each}
        </select>
      </label>

      <label>
        Calibration suite
        <select bind:value={suiteRef}>
          {#each cfg.suites ?? [] as s (s.suite_ref)}
            <option value={s.suite_ref}>{s.name} · {s.task_count} tasks</option>
          {/each}
        </select>
      </label>

      <label>
        Trace depth
        <select bind:value={depth}>
          {#each cfg.trace_depths ?? [] as d (d.depth)}
            <option value={d.depth}>
              {d.depth} · {d.num_samples} samples × {d.seq_len} tokens
            </option>
          {/each}
        </select>
      </label>

      <label>
        Keep budgets (comma-separated)
        <input type="text" bind:value={budgets} placeholder="e.g. 8,6,4,2" />
      </label>

      {#if currentSource() && !currentSource().atlas_compatible}
        <p class="mut" style="font-size:12px">
          Note: this model is not classified layerwise-compatible; atlas will still trace a
          synthetic calibration twin for the selected source.
        </p>
      {/if}

      <button
        class="beam-btn"
        on:click={doLaunch}
        disabled={launching || !source || !suiteRef}
      >
        <Play size="14" style="vertical-align:-2px" /> {launching ? "Launching…" : "Build atlas"}
      </button>

      {#if !launching}
        <div style="margin-top:8px">
          <button class="link" on:click={doEstimate} disabled={estimating}>
            {estimating ? "Estimating…" : "Estimate resources"}
          </button>
        </div>
      {/if}

      {#if estimateError}
        <div class="card error" style="margin-top:10px">{estimateError}</div>
      {/if}
      {#if estimate}
        <div class="card" style="margin-top:10px">
          <h4>Resource estimate <span class="badge">estimated</span></h4>
          <table>
            <tbody>
              <tr><th>Topology</th><td>{estimate.num_layers} layers · {estimate.num_experts} experts · top-{estimate.top_k}</td></tr>
              <tr><th>Calibration</th><td>{estimate.num_samples} samples × {estimate.seq_len} tokens = {estimate.num_tokens} tokens</td></tr>
              <tr><th>Ops</th><td>{Number(estimate.estimated_ops).toExponential(2)}</td></tr>
              <tr><th>Wall time (est.)</th><td>{estimate.estimated_wall_s.toFixed(2)} s</td></tr>
              <tr><th>Mini-MoE params</th><td>{estimate.mini_moe_params.toLocaleString()}</td></tr>
              <tr><th>Trace bytes</th><td>≈ {(estimate.trace_bytes / 1024).toFixed(1)} KB</td></tr>
            </tbody>
          </table>
          <p class="mut" style="font-size:12px;margin-top:6px">{estimate.methodology}</p>
        </div>
      {/if}
    {:else}
      <p class="mut">Loading wizard…</p>
    {/if}
  </div>

  <!-- RIGHT: live monitor — same height as the left panel, tabbed, 'show all' -> modal -->
  <div class="rows-panel">
    <section class="card mon-card">
      <h3 style="margin:0 0 8px;display:flex;align-items:center;gap:8px"><Activity size="14" /> Builds</h3>
      <div class="tab-bar">
        <button class="tab-btn {monitorTab === 'current' ? 'on' : ''}" on:click={() => (monitorTab = "current")}>
          In progress <span class="badge {activeJobsCount() ? 'pass' : ''}">{activeJobsCount()}</span>
        </button>
        <button class="tab-btn {monitorTab === 'completed' ? 'on' : ''}" on:click={() => (monitorTab = "completed")}>
          Completed <span class="badge">{runs.length}</span>
        </button>
        <button class="btn small" style="margin-left:auto" on:click={monitorTab === "current" ? loadJobs : loadRuns}>
          Refresh
        </button>
      </div>

      <div class="mon-list">
        {#if monitorTab === "current"}
          {#if jobsError}<div class="card error mon-msg">{jobsError}</div>{/if}
          {#if !activeJobs.length && !jobsError}<p class="mut mon-msg">No builds in progress. Completed builds appear under Completed.</p>{/if}
          {#each activeJobs.slice(0, VISIBLE) as j (j.job_id)}
            <div class="job-row">
              <span class="mono job-id">{j.job_id}</span>
              <span class="{jobCls(j.state)} job-state">{jobLabel(j.state)}</span>
              <span class="mut job-stage">{j.current_stage ?? "—"}</span>
              <span class="mut job-src">{j.config?.model_asset_id ?? "—"}</span>
              <span class="job-actions">
                {#if j.progress?.total}
                  <span class="job-prog">{Math.round((j.progress.done / j.progress.total) * 100)}%</span>
                {/if}
                {#if j.state === "running"}
                  <button class="btn small" on:click={() => jobAction(j.job_id, "pause")}><Pause size="12" /></button>
                {:else if j.state === "paused" || j.state === "failed_recoverable"}
                  <button class="btn small" on:click={() => jobAction(j.job_id, "resume")}><RotateCcw size="12" /></button>
                {/if}
                {#if ACTIVE.has(j.state) && j.state !== "paused"}
                  <button class="btn small danger" on:click={() => jobAction(j.job_id, "cancel")}><X size="12" /></button>
                {/if}
                {#if j.config?.atlas_run_id && TERMINAL.has(j.state)}
                  <button class="btn small" on:click={() => showRun(j.config.atlas_run_id)}>View</button>
                {/if}
              </span>
            </div>
          {/each}
          {#if activeJobs.length > VISIBLE}
            <button class="btn small show-all" on:click={() => openModal("current")}>
              Show all ({activeJobs.length})
            </button>
          {/if}
        {:else}
          {#if runsError}<div class="card error mon-msg">{runsError}</div>{/if}
          {#if !runs.length && !runsError}<p class="mut mon-msg">No completed runs recorded yet.</p>{/if}
          {#each runs.slice(0, VISIBLE) as r (r.atlas_run_id)}
            <div class="job-row">
              <span class="mono job-id">{r.atlas_run_id}</span>
              <span class="{r.status === 'completed' ? 'ok' : 'mut'} job-state">{r.status ?? "—"}</span>
              <span class="mut job-stage">{r.source_arch ?? "—"}</span>
              <span class="mut job-src">{r.calibration_suite_id ?? "—"}</span>
              <span class="job-actions"><button class="btn small" on:click={() => showRun(r.atlas_run_id)}>Details</button></span>
            </div>
          {/each}
          {#if runs.length > VISIBLE}
            <button class="btn small show-all" on:click={() => openModal("completed")}>
              Show all ({runs.length})
            </button>
          {/if}
        {/if}
      </div>
    </section>
  </div>

  <!-- ALL-JOBS MODAL (mirrors the tab filter; shows the full active tab list) -->
  {#if modalOpen}
    <div class="modal-backdrop" on:click={() => (modalOpen = false)}></div>
    <div class="modal" role="dialog" aria-label="All jobs">
      <div class="modal-head">
        <h3 style="margin:0">All {modalTab === "current" ? "current jobs" : "completed runs"}</h3>
        <button class="btn small" on:click={() => (modalOpen = false)}>Close</button>
      </div>
      <div class="tab-bar" style="padding:0 18px;margin:12px 0 0">
        <button class="tab-btn {modalTab === 'current' ? 'on' : ''}" on:click={() => (modalTab = "current")}>
          In progress <span class="badge {activeJobsCount() ? 'pass' : ''}">{activeJobsCount()}</span>
        </button>
        <button class="tab-btn {modalTab === 'completed' ? 'on' : ''}" on:click={() => (modalTab = "completed")}>
          Completed <span class="badge">{runs.length}</span>
        </button>
        <button class="btn small" style="margin-left:auto" on:click={modalTab === "current" ? loadJobs : loadRuns}>Refresh</button>
      </div>
      <div class="modal-body">
        {#if modalTab === "current"}
          {#if !activeJobs.length}<p class="mut">No builds in progress.</p>{/if}
          {#each activeJobs as j (j.job_id)}
            <div class="job-row">
              <span class="mono job-id">{j.job_id}</span>
              <span class="{jobCls(j.state)} job-state">{jobLabel(j.state)}</span>
              <span class="mut job-stage">{j.current_stage ?? "—"}</span>
              <span class="mut job-src">{j.config?.model_asset_id ?? "—"}</span>
              <span class="job-actions">
                {#if j.state === "running"}
                  <button class="btn small" on:click={() => jobAction(j.job_id, "pause")}><Pause size="12" /></button>
                {:else if j.state === "paused" || j.state === "failed_recoverable"}
                  <button class="btn small" on:click={() => jobAction(j.job_id, "resume")}><RotateCcw size="12" /></button>
                {/if}
                {#if ACTIVE.has(j.state) && j.state !== "paused"}
                  <button class="btn small danger" on:click={() => jobAction(j.job_id, "cancel")}><X size="12" /></button>
                {/if}
                {#if j.config?.atlas_run_id && TERMINAL.has(j.state)}
                  <button class="btn small" on:click={() => showRun(j.config.atlas_run_id)}>View</button>
                {/if}
              </span>
            </div>
          {/each}
        {:else}
          {#if !runs.length}<p class="mut">No completed runs.</p>{/if}
          {#each runs as r (r.atlas_run_id)}
            <div class="job-row">
              <span class="mono job-id">{r.atlas_run_id}</span>
              <span class="{r.status === 'completed' ? 'ok' : 'mut'} job-state">{r.status ?? "—"}</span>
              <span class="mut job-stage">{r.source_arch ?? "—"}</span>
              <span class="mut job-src">{r.calibration_suite_id ?? "—"}</span>
              <span class="job-actions"><button class="btn small" on:click={() => showRun(r.atlas_run_id)}>Details</button></span>
            </div>
          {/each}
        {/if}
      </div>
    </div>
  {/if}
</div>

{#if runDetailError}
  <div class="card error" style="margin-top:12px">{runDetailError}</div>
{/if}
{#if runDetail}
  <section class="card" style="margin-top:12px">
    <h2>
      Atlas run <span class="mono">{runDetail.atlas_run_id}</span>
      <span class="badge">{runDetail.status}</span>
      <button class="btn small" style="float:right" on:click={() => (recOpen = true)}><Sparkles size="13" /> Recommendations</button>
      <button class="btn small" style="float:right;margin-right:8px" on:click={() => (runDetail = null)}>Close</button>
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

    <!-- BLUEPRINT DIGEST: plain-language read of trace + behaviour + keep data -->
    <section class="card" style="margin-top:12px">
      <h2 style="display:flex;align-items:center;gap:8px">
        <Layers size="15" /> Blueprint digest
        <span class="badge">read me first</span>
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
          {#each traceLeaders() as l (l.expert)}
            <span class="chip">e{l.expert} · {l.count}</span>
          {/each}
        </p>
      </div>

      <div class="card" style="margin-top:16px">
        <h4>Who is responsible for what (behaviour / semantic map)</h4>
        <p class="mut" style="font-size:13px;margin:0 0 8px">
          Top experts per capability by measured saliency; strongest layers in brackets.
        </p>
        <div class="table-scroll">
          <table>
            <thead><tr><th>Capability</th><th>Lead experts (strong layers)</th></tr></thead>
            <tbody>
              {#each digestLabels() as d (d.label)}
                <tr>
                  <td class="mono">{labelShort(d.label)}</td>
                  <td>
                    {#if d.leaders.length}
                      {#each d.leaders as l (l.expert)}
                        <span class="chip">e{l.expert}{l.layers.length ? " · L" + l.layers.join(", L") : ""}</span>
                      {/each}
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
          <span>Protected:
            {#each redundantDigest().protectedE as e (e)}<span class="chip on">e{e}</span>{:else}<span class="mut">none</span>{/each}
          </span>
          <span style="margin-left:12px">Redundant (fully pruned):
            {#each redundantDigest().redundantE as e (e)}<span class="chip">e{e}</span>{:else}<span class="mut">none</span>{/each}
          </span>
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

    <RecommendationsTray
      open={recOpen}
      run={runDetail}
      onclose={() => (recOpen = false)}
    />

    <h3 style="margin-top:28px">Maps &amp; routing</h3>

    <!-- SALIENCY MAP: layer x expert heatmap -->
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

    <!-- KEEP MAP: simple kept/pruned matrix per selected plan -->
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
          <button class="btn small {planSel === p.name ? 'primary' : ''}" on:click={() => (planSel = p.name)}>
            {planShort(p.name)}
          </button>
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
                    <td class="kmc {kset.has(e) ? 'kept' : 'prune'}"
                        title="layer {L} · expert e{e} · saliency {salRow(L, e)?.total_value?.toFixed?.(4) ?? '—'}">
                      {kset.has(e) ? '✓' : ''}
                    </td>
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

    <!-- ROUTING MAP: share of routed tokens per expert, dimmed when pruned -->
    <div class="card" style="margin-top:16px">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px">
        <strong>Routing</strong>
        <span class="mut" style="font-size:12px">
          bar = share of routed tokens per expert; <span class="rseg" style="display:inline-block;width:14px;vertical-align:-2px"></span> kept ·
          <span class="rseg dim" style="display:inline-block;width:14px;vertical-align:-2px"></span> pruned in {planSel || "plan"}
        </span>
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
          <span class="mut" style="font-size:11px;width:200px;flex:0 0 200px;text-align:right">
            {keptIds(kset)} kept
          </span>
        </div>
      {/each}
    </div>

    <!-- keep-map legend / source identity fallback -->
    {#if runDetail.keep_maps.length}
      <p class="mut" style="font-size:12px;margin-top:6px">
        Source expert identity is preserved across plans (a kept expert always traces to the
        same source unit). Primary keep-map (server, budget {runDetail.keep_maps[0]?.top_k})
        has {runDetail.keep_maps[0]?.kept_count} of {numExperts()} experts kept per layer.
      </p>
    {/if}
  </section>
{/if}

<!-- external Atlas engine (existing connect surface, de-emphasised) -->
<section class="card" style="margin-top:16px">
  <h2 style="display:flex;align-items:center;gap:10px">
    External Atlas engine
    <span class="badge">{status?.connected && status?.reachable ? "connected" : "not connected"}</span>
  </h2>
  {#if notice && !status?.connected}
    <div class="card warn">{notice}</div>
  {/if}
  {#if status && !status.installed}
    <p class="mut">The <code>model-atlas</code> package isn't installed. Install and serve it:</p>
    <p class="mono">{install?.install_command} — {install?.serve_command}</p>
    <button class="btn" on:click={loadConnect}>I've installed it — refresh</button>
  {:else if status && !status.connected}
    <label class="mut" for="atlas-url">Atlas dashboard URL</label>
    <div style="display:flex;gap:8px;margin-top:6px">
      <input id="atlas-url" bind:value={url} class="mono" style="width:320px" />
      <button class="btn primary" on:click={doConnect} disabled={working || !url}>
        {working ? "Connecting…" : "Connect"}
      </button>
    </div>
  {:else if status && status.connected}
    <table>
      <tbody>
        <tr><th>Status</th><td>{status.reachable ? "reachable" : "unreachable"}</td></tr>
        <tr><th>URL</th><td class="mono">{status.url}</td></tr>
      </tbody>
    </table>
    <div style="margin-top:8px;display:flex;gap:8px">
      <a class="btn primary" href={status.url} target="_blank" rel="noreferrer">Open Atlas Lab</a>
      <button class="btn danger" on:click={doDisconnect} disabled={working}>Disconnect</button>
    </div>
  {/if}
</section>
