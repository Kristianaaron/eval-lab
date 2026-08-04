<script>
  import { onMount, onDestroy } from "svelte";
  import { get, post } from "./lib/api.js";
  import RunDetail from "./RunDetail.svelte";
  import EvalJobDetail from "./EvalJobDetail.svelte";

  let { runId = null, jobId = null } = $props();

  let cfg = $state(null);
  let loading = $state(false);
  let error = $state(null);

  let model = $state("");
  let harness = $state("direct");
  let repeat = $state(1);
  let cold = $state(false);

  // right-panel rows: one per selected domain, tracking its own eval job
  let rows = $state([]); // {domain, jobId, suiteRef, state, score}
  let running = $state(false);
  let recent = $state([]);

  const TERMINAL = new Set([
    "completed",
    "completed_with_warnings",
    "failed",
    "failed_recoverable",
    "cancelled",
  ]);

  async function loadCfg() {
    loading = true;
    error = null;
    try {
      cfg = await get("/api/eval-config");
      if (!model && cfg.models.length) model = cfg.models[0].model_id;
      if (!harness && cfg.harnesses.length) harness = cfg.harnesses[0].harness_id;
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  async function loadRecent() {
    try {
      recent = await get("/api/eval-jobs");
    } catch {}
  }

  function hasDomain(d) {
    return rows.some((r) => r.domain === d);
  }

  function toggleDomain(d) {
    if (hasDomain(d)) {
      rows = rows.filter((r) => r.domain !== d);
    } else {
      rows = [...rows, { domain: d, jobId: null, suiteRef: null, state: "pending", score: null }];
    }
  }

  function removeDomain(d) {
    rows = rows.filter((r) => r.domain !== d);
  }

  async function launch() {
    error = null;
    if (!rows.length) {
      error = "Pick at least one domain first.";
      return;
    }
    running = true;
    try {
      // one eval job per selected domain so each row has a real lifecycle
      for (const row of rows) {
        if (row.state !== "pending") continue; // don't duplicate already-launched rows
        const { suite_ref } = await post("/api/suites", {
          name: `Eval ${row.domain}`,
          domains: [row.domain],
        });
        row.suiteRef = suite_ref;
        row.state = "queued";
        const job = await post("/api/eval-jobs", {
          model_asset_id: model,
          model_id: model,
          harness_id: harness,
          suite_ref,
          repeat_count: Number(repeat),
          cold_start: cold,
          runs_root: "runs",
        });
        row.jobId = job.job_id;
        row.state = "evaluating";
      }
      pollOnce();
      loadRecent();
    } catch (e) {
      error = String(e);
    } finally {
      running = false;
    }
  }

  function jobStage(state) {
    if (TERMINAL.has(state)) return "terminal";
    return "active";
  }

  function rowFromJob(row, job) {
    if (jobStage(job.state) === "terminal") {
      const done = job.state === "completed" || job.state === "completed_with_warnings";
      row.state = done ? "completed" : job.state === "cancelled" ? "cancelled" : "failed";
      if (done) row.score = null; // score fetched right after
      return;
    }
    row.state = "evaluating";
    row.stage = job.current_stage ?? null;
    row.progress = job.progress ?? null;
  }

  async function pollOnce() {
    const active = rows.filter(
      (r) => r.jobId && !TERMINAL.has(r.state) && r.state !== "failed" && r.state !== "cancelled"
    );
    for (const row of active) {
      try {
        const job = await get(`/api/eval-jobs/${encodeURIComponent(row.jobId)}`);
        rowFromJob(row, job);
        if (row.state === "completed") {
          row.score = await fetchScore(job.result?.run_ids ?? []);
        }
      } catch {
        /* transient poll failure — retried next tick */
      }
    }
  }

  async function fetchScore(runIds) {
    if (!runIds || !runIds.length) return null;
    const scored = [];
    for (const rid of runIds) {
      try {
        const d = await get(`/api/runs/${encodeURIComponent(rid)}`);
        const a = d?.manifest?.aggregate_score;
        if (typeof a === "number" && Number.isFinite(a)) scored.push(a);
      } catch {
        /* skip a transient run fetch failure */
      }
    }
    if (!scored.length) return null;
    return scored.reduce((a, b) => a + b, 0) / scored.length;
  }

  function statusMeta(row) {
    if (row.state === "completed") return { label: "done", cls: "pass" };
    if (row.state === "failed") return { label: "failed", cls: "fail" };
    if (row.state === "cancelled") return { label: "cancelled", cls: "type" };
    if (row.state === "evaluating") return { label: "evaluating", cls: "type" };
    if (row.state === "queued") return { label: "queued", cls: "type" };
    return { label: "pending", cls: "type" };
  }

  let timer = null;
  function startPolling() {
    if (timer) return;
    timer = setInterval(pollOnce, 1500);
  }
  function stopPolling() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  $effect(() => {
    const hasActive = rows.some((r) => r.state === "evaluating" || r.state === "queued");
    if (hasActive) startPolling();
    else stopPolling();
  });

  onMount(() => {
    loadCfg();
    loadRecent();
  });
  onDestroy(stopPolling);
</script>

<h1>Evaluation</h1>

{#if runId}
  <RunDetail runId={runId} />
{:else if jobId}
  <EvalJobDetail jobId={jobId} />
{:else}
  <p class="mut">
    Configure a run on the left, then pick the domains you want. Each chosen domain becomes a
    row you can track through evaluation; when you're ready, run the eval.
  </p>

  {#if error}
    <div class="card error">{error}</div>
  {/if}

  <div class="eval-layout">
    <!-- left: configuration -->
    <div class="card eval-config">
      <h3>Configuration</h3>
      {#if loading}
        <p class="mut">Loading configuration…</p>
      {:else if cfg}
        <label>
          Model
          <select bind:value={model}>
            {#each cfg.models as m (m.model_id)}
              <option value={m.model_id}>{m.name} ({m.model_id})</option>
            {/each}
          </select>
        </label>

        <label>
          Harness
          <select bind:value={harness}>
            {#each cfg.harnesses as h (h.harness_id)}
              <option value={h.harness_id}>{h.name}</option>
            {/each}
          </select>
        </label>

        <label>
          Repeat count
          <input type="number" min="1" bind:value={repeat} />
        </label>

        <label><input type="checkbox" bind:checked={cold} /> Cold start</label>

        <div style="margin:8px 0">
          <div class="k" style="margin-bottom:6px">Domains</div>
          <div class="chips">
            {#each cfg.domains ?? [] as d (d)}
              <button
                type="button"
                class="chip"
                class:on={hasDomain(d)}
                on:click={() => toggleDomain(d)}
              >
                {d}{hasDomain(d) ? " ✓" : ""}
              </button>
            {/each}
          </div>
          <p class="mut" style="font-size:12px;margin:6px 0 0">
            Pick domains — each one adds a row on the right.
          </p>
        </div>

        <button class="btn primary" on:click={launch} disabled={running || !rows.length}>
          {running ? "Launching…" : `Run new eval (${rows.length} domain${rows.length === 1 ? "" : "s"})`}
        </button>

        {#if recent.length}
          <h4 style="margin-top:16px">Recent jobs</h4>
          <table>
            <thead><tr><th>Job</th><th>Model</th><th>State</th></tr></thead>
            <tbody>
              {#each recent.slice(0, 6) as j (j.job_id)}
                <tr>
                  <td><a href="#/evaluation/job/{j.job_id}">{j.job_id}</a></td>
                  <td class="mut">{j.model_id}</td>
                  <td class="{j.state.includes('complete') ? 'ok' : j.state.includes('fail') || j.state === 'cancelled' ? 'error' : 'mut'}">{j.state}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      {:else}
        <p class="mut">Unable to load configuration.</p>
        <button class="btn" on:click={loadCfg}>Retry</button>
      {/if}
    </div>

    <!-- right: domain rows (empty state until a domain is chosen) -->
    <div class="rows-panel">
      {#if !rows.length}
        <div class="rows-empty">
          <p>No domains selected yet.</p>
          <p class="mut" style="margin-top:6px">Pick a domain on the left to build an evaluation row.</p>
        </div>
      {:else}
        {#each rows as row (row.domain)}
          <div class="card" style="display:flex;align-items:center;gap:14px;padding:12px 16px">
            <span class="mono" style="font-weight:600;flex:1">{row.domain}</span>
            <span class="mut" style="width:90px;text-align:right">
              {#if row.state === "completed"}
                <strong class="mono">{row.score == null ? "—" : row.score.toFixed(3)}</strong>
              {:else}
                <span class="mut">—</span>
              {/if}
            </span>
            <span class="badge {statusMeta(row).cls}">{statusMeta(row).label}</span>
            {#if row.jobId && TERMINAL.has(row.state)}
              <a class="btn small" href="#/evaluation/job/{row.jobId}">View</a>
            {:else if row.state === "evaluating"}
              <span class="mut">…</span>
            {/if}
            <button class="btn small danger" on:click={() => removeDomain(row.domain)}>Remove</button>
          </div>
        {/each}
        <p class="mut" style="font-size:12px">
          Strong domain(s) will evaluate in separate jobs; status + aggregate score per row.
        </p>
      {/if}
    </div>
  </div>
{/if}
