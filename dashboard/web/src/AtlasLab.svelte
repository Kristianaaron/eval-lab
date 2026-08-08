<script>
  import { onMount, onDestroy } from "svelte";
  import { get, post } from "./lib/api.js";
  import { Activity, Play, Pause, RotateCcw, X, Database } from "@lucide/svelte";

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

  // Open a run's detail on its own page (with a back link).
  function showRun(run_id) {
    window.location.hash = `#/atlas/run/${encodeURIComponent(run_id)}`;
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
