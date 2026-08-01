<script>
  import { get, fmtBytes } from "./lib/api.js";

  let overview = $state(null);
  let assets = $state([]);
  let env = $state(null);
  let jobs = $state([]);
  let error = $state(null);

  $effect(() => {
    get("/api/overview").then((d) => (overview = d)).catch((e) => (error = String(e)));
    get("/api/models-assets").then((d) => (assets = d)).catch(() => {});
    get("/api/environment").then((d) => (env = d)).catch(() => {});
    get("/api/jobs").then((d) => (jobs = d)).catch(() => {});
  });

  const counts = $derived.by(() => {
    const runnable = assets.filter((a) => a.runnable).length;
    const source = assets.filter((a) => a.asset_type === "source_checkpoint").length;
    return { total: assets.length, runnable, source };
  });
  const activeJobs = $derived.by(() =>
    jobs.filter((j) => ["queued", "running", "pausing", "paused", "resuming"].includes(j.state)).length
  );
  const recentFailed = $derived.by(() =>
    jobs.filter((j) => j.state === "failed" || j.state === "failed_recoverable").length
  );
</script>

<div class="card overview-panel">
  <h1>Overview</h1>
  <div class="ov-stats">
    <div class="ov-stat"><div class="k">Registered models</div><div class="v">{counts.total}</div></div>
    <div class="ov-stat"><div class="k">Runnable models</div><div class="v" style="color:var(--green)">{counts.runnable}</div></div>
    <div class="ov-stat"><div class="k">Source checkpoints</div><div class="v">{counts.source}</div></div>
    <div class="ov-stat"><div class="k">Active eval jobs</div><div class="v">{activeJobs}</div></div>
    <div class="ov-stat"><div class="k">Failed jobs</div><div class="v" style="color:var(--red)">{recentFailed}</div></div>
    <div class="ov-stat"><div class="k">Total runs</div><div class="v">{overview?.total_runs ?? "—"}</div></div>
  </div>
</div>

<div class="card run-tile" style="margin-bottom:16px">
  <a class="run-title" href="#/evaluation" style="display:block">Run a new eval</a>
  <p class="mut" style="margin:6px 0 0">Choose a registered model, pick the domains you want, then launch or save the selection as a suite.</p>
</div>

<div class="card">
  <h3>Hardware / environment</h3>
  <table>
    <tbody>
      <tr><td class="mut">Software</td><td class="mono">{env?.software_version ?? "—"}</td></tr>
      <tr><td class="mut">Nodes</td><td>{env?.nodes ?? "—"} × DGX Spark</td></tr>
      <tr><td class="mut">Unified memory (target)</td><td>{env?.unified_memory_gb ?? "—"} GB</td></tr>
      <tr><td class="mut">NVMe available</td><td>{env?.nvme_available_bytes != null ? fmtBytes(env.nvme_available_bytes) : "—"}</td></tr>
      <tr><td class="mut">GPU present</td><td>{env?.gpu_present == null ? "—" : env.gpu_present ? "yes" : "no"}</td></tr>
      {#if error}
        <tr><td class="mut">API status</td><td class="error">{error}</td></tr>
      {:else}
        <tr><td class="mut">API status</td><td><span class="ok">ok</span></td></tr>
      {/if}
    </tbody>
  </table>
  <p class="mut" style="margin-top:8px">Operational view — model, job and hardware state, not decorative analytics.</p>
</div>

{#if assets.length}
  <div class="card">
    <h3>Registered models</h3>
    <table>
      <thead><tr><th>Model</th><th>Type</th><th>Runnable</th><th>Atlas</th><th class="right">Quality</th></tr></thead>
      <tbody>
        {#each assets as a (a.asset_id)}
          <tr>
            <td><a href="#/model/{a.asset_id}">{a.name}</a></td>
            <td class="mut">{a.asset_type.replace(/_/g, " ")}</td>
            <td>{a.runnable ? "yes" : "no"}</td>
            <td>{a.atlas_compatible ? "yes" : "—"}</td>
            <td class="right">{a.latest_quality_score?.toFixed(3) ?? "—"}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}
