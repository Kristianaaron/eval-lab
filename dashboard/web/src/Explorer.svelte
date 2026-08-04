<script>
  import { onMount } from "svelte";
  import { get, fmtPassed } from "./lib/api.js";

  let reg = $state(null);
  let overview = $state(null);
  let runs = $state([]);
  let model = $state("");
  let task = $state("");
  let status = $state("");
  let error = $state(null);
  let section = $state("runs");
  let loading = $state(false);

  async function loadRuns() {
    loading = true;
    error = null;
    try {
      const params = new URLSearchParams();
      if (model) params.set("model_id", model);
      if (task) params.set("task_id", task);
      if (status) params.set("status", status);
      runs = await get(`/api/runs?${params}`);
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  function loadAll() {
    get("/api/explorer/registries")
      .then((d) => (reg = d))
      .catch((e) => (error = String(e)));
    get("/api/overview")
      .then((d) => (overview = d))
      .catch(() => {});
    loadRuns();
  }

  onMount(loadAll);

  const sections = [
    { key: "runs", label: `Runs (${reg?.runs?.total ?? "…"})` },
    { key: "atlas", label: `Atlas runs (${reg?.atlas_runs?.length ?? "…"})` },
    { key: "experiments", label: `Experiments (${reg?.experiments?.length ?? "…"})` },
    { key: "models", label: `Model assets (${reg?.model_assets?.length ?? "…"})` },
    { key: "jobs", label: `Jobs (${reg?.jobs?.total ?? "…"})` },
    { key: "suites", label: `Suites (${reg?.suites?.length ?? "…"})` },
  ];
</script>

<h1>Explorer</h1>
<p class="mut">
  Browse every artifact the harness has recorded — runs, atlas exports, experiments,
  model assets, jobs, and suites. Filter the run corpus or drill into any run for its
  trace, telemetry, and raw stored artifacts.
</p>

{#if error}
  <div class="card">Error: <span class="mut">{error}</span></div>
{/if}

<!-- registries summary -->
{#if reg}
  <div class="grid cols-4" style="margin-bottom:20px">
    <div class="card stat">
      <div class="k">Runs</div>
      <div class="v">{reg.runs.total}</div>
      <div class="mut">
        {reg.runs.passed} pass · {reg.runs.failed} fail
        {#if reg.runs.avg_aggregate_score != null}
          · ∅ {reg.runs.avg_aggregate_score}
        {/if}
      </div>
    </div>
    <div class="card stat">
      <div class="k">Atlas runs</div>
      <div class="v">{reg.atlas_runs.length}</div>
      <div class="mut">{reg.atlas_runs.filter((r) => r.has_derivative).length} with derivative</div>
    </div>
    <div class="card stat">
      <div class="k">Experiments</div>
      <div class="v">{reg.experiments.length}</div>
    </div>
    <div class="card stat">
      <div class="k">Model assets</div>
      <div class="v">{reg.model_assets.length}</div>
      <div class="mut">{reg.model_assets.filter((m) => m.runnable).length} runnable · {reg.jobs.by_status?.["active"] ?? 0} active job(s)</div>
    </div>
  </div>
{/if}

<!-- section tabs -->
<div class="chips" style="margin-bottom:16px">
  {#each sections as s (s.key)}
    <button class="chip" class:on={section === s.key} onclick={() => (section = s.key)}>{s.label}</button>
  {/each}
</div>

<!-- RUNS -->
{#if section === "runs"}
  <div class="filters">
    <select bind:value={model} onchange={loadRuns} title="Filter by model">
      <option value="">all models</option>
      {#each (overview?.models ?? []) as m (m)}
        <option value={m}>{m}</option>
      {/each}
    </select>
    <select bind:value={task} onchange={loadRuns}>
      <option value="">all tasks</option>
      {#each (overview?.tasks ?? []) as t (t)}
        <option value={t}>{t}</option>
      {/each}
    </select>
    <select bind:value={status} onchange={loadRuns}>
      <option value="">all statuses</option>
      {#each ["completed", "error", "draft"] as s (s)}
        <option value={s}>{s}</option>
      {/each}
    </select>
    <button class="btn small" onclick={loadRuns} disabled={loading}>{loading ? "…" : "Refresh"}</button>
  </div>

  <div class="card table-scroll">
    <table>
      <thead>
        <tr><th>Run</th><th>Created</th><th>Task</th><th>Model</th><th>Suite</th><th class="right">Score</th><th>Status</th></tr>
      </thead>
      <tbody>
        {#each runs as r (r.run_id)}
          <tr>
            <td class="mono"><a href="#/explorer/run/{r.run_id}">{r.run_id}</a></td>
            <td class="mut">{String(r.created_at ?? "").slice(0, 19).replace("T", " ")}</td>
            <td class="mono">{r.task_id}</td>
            <td>{r.model_id ?? "—"}</td>
            <td class="mut">{r.suite_id ?? "—"}</td>
            <td class="right">{r.aggregate_score?.toFixed(3) ?? "—"}</td>
            <td><span class="badge {fmtPassed(r.passed).cls}">{fmtPassed(r.passed).label}</span></td>
          </tr>
        {/each}
      </tbody>
    </table>
    {#if runs.length === 0}
      <p class="mut">No runs match the filters.</p>
    {/if}
  </div>

{:else if section === "atlas"}
  <div class="card table-scroll">
    <table>
      <thead><tr><th>Atlas run</th><th>Arch</th><th>Status</th><th>Plans</th><th>Derivative</th></tr></thead>
      <tbody>
        {#each reg?.atlas_runs ?? [] as r (r.run_id)}
          <tr>
            <td class="mono"><a href="#/atlas">{r.run_id}</a></td>
            <td class="mut">{r.arch ?? "—"}</td>
            <td>{r.status ?? "—"}</td>
            <td>{r.n_plans ?? "—"}</td>
            <td>{r.has_derivative ? "yes" : "—"}</td>
          </tr>
        {/each}
      </tbody>
    </table>
    {#if !reg?.atlas_runs?.length}<p class="mut">No atlas runs recorded yet.</p>{/if}
  </div>

{:else if section === "experiments"}
  <div class="card table-scroll">
    <table>
      <thead><tr><th>Experiment</th><th>Atlas run</th><th>Plan</th><th>Objective</th><th>Kept</th><th>Status</th></tr></thead>
      <tbody>
        {#each reg?.experiments ?? [] as e (e.experiment_id)}
          <tr>
            <td class="mono"><a href="#/experiments">{e.experiment_id}</a></td>
            <td class="mono">{e.run_id ?? "—"}</td>
            <td class="mono">{e.plan_name ?? "—"}</td>
            <td>{e.objective ?? "—"}</td>
            <td>{e.total_kept ?? "—"}</td>
            <td>{e.status ?? "—"}</td>
          </tr>
        {/each}
      </tbody>
    </table>
    {#if !reg?.experiments?.length}<p class="mut">No experiments recorded yet.</p>{/if}
  </div>

{:else if section === "models"}
  <div class="card table-scroll">
    <table>
      <thead><tr><th>Asset</th><th>Name</th><th>Type</th><th>Runnable</th><th>Atlas-compatible</th></tr></thead>
      <tbody>
        {#each reg?.model_assets ?? [] as m (m.asset_id)}
          <tr>
            <td class="mono"><a href="#/model/{m.asset_id}">{m.asset_id}</a></td>
            <td>{m.name ?? "—"}</td>
            <td>{m.asset_type ?? "—"}</td>
            <td>{m.runnable ? "yes" : "no"}</td>
            <td>{m.atlas_compatible ? "yes" : "no"}</td>
          </tr>
        {/each}
      </tbody>
    </table>
    {#if !reg?.model_assets?.length}<p class="mut">No model assets registered yet.</p>{/if}
  </div>

{:else if section === "jobs"}
  <div class="card table-scroll">
    <table>
      <thead><tr><th>Kind</th><th>Status</th><th class="right">Count</th></tr></thead>
      <tbody>
        {#each Object.entries(reg?.jobs?.by_kind ?? {}) as [kind, n] (kind)}
          <tr>
            <td class="mono"><a href="#/jobs">{kind}</a></td>
            <td class="mono">{Object.entries(reg?.jobs?.by_status ?? {}).map(([s, c]) => `${s}:${c}`).join(", ") || "—"}</td>
            <td class="right">{n}</td>
          </tr>
        {/each}
      </tbody>
    </table>
    {#if !reg?.jobs?.by_kind || !Object.keys(reg.jobs.by_kind).length}
      <p class="mut">No jobs recorded yet.</p>
    {/if}
  </div>

{:else if section === "suites"}
  <div class="card table-scroll">
    <table>
      <thead><tr><th>Suite</th><th>Name</th><th>Family</th><th class="right">Tasks</th></tr></thead>
      <tbody>
        {#each reg?.suites ?? [] as s (s.id)}
          <tr>
            <td class="mono">{s.id}</td>
            <td>{s.name ?? "—"}</td>
            <td>{s.family ?? "—"}</td>
            <td class="right">{s.task_count}</td>
          </tr>
        {/each}
      </tbody>
    </table>
    {#if !reg?.suites?.length}<p class="mut">No suites found.</p>{/if}
  </div>
{/if}
