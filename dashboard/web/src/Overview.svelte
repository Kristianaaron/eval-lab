<script>
  import { get, fmtBytes } from "./lib/api.js";
  import { Play, GitCompareArrows } from "@lucide/svelte";

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

<div class="ov-label">Home landing page</div>

<div class="cta-row">
  <a class="cta-card" href="#/evaluation">
    <span class="cta-icon"><Play size={24} /></span>
    <span>
      <span class="cta-title">Run eval</span>
      <span class="cta-sub">Setup and benchmark a model</span>
    </span>
  </a>
  <a class="cta-card" href="#/comparisons">
    <span class="cta-icon"><GitCompareArrows size={24} /></span>
    <span>
      <span class="cta-title">Compare models</span>
      <span class="cta-sub">See how models compare across different domains</span>
    </span>
  </a>
</div>

<div class="card ov-statsbar">
  <div class="ov-stat"><div class="k">Registered models</div><div class="v">{counts.total}</div></div>
  <div class="ov-stat"><div class="k">Runnable models</div><div class="v" style="color:var(--green)">{counts.runnable}</div></div>
  <div class="ov-stat"><div class="k">Source checkpoints</div><div class="v">{counts.source}</div></div>
  <div class="ov-stat"><div class="k">Active eval jobs</div><div class="v">{activeJobs}</div></div>
  <div class="ov-stat"><div class="k">Failed jobs</div><div class="v" style="color:var(--red)">{recentFailed}</div></div>
  <div class="ov-stat"><div class="k">Total runs</div><div class="v">{overview?.total_runs ?? "—"}</div></div>
</div>

<div class="ov-bottom">
  <div class="card">
    <h3>Hardware / environment</h3>
    <div class="table-scroll">
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
    </div>
  </div>

  {#if assets.length}
    <div class="card">
      <h3>Registered models</h3>
      <div class="table-scroll">
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
    </div>
  {/if}
</div>
