<script>
  import { get } from "./lib/api.js";

  let overview = $state(null);
  let assets = $state([]);
  let error = $state(null);

  $effect(() => {
    get("/api/overview")
      .then((d) => (overview = d))
      .catch((e) => (error = String(e)));
    get("/api/models-assets")
      .then((d) => (assets = d))
      .catch(() => {});
  });

  const counts = $derived.by(() => {
    const runnable = assets.filter((a) => a.runnable).length;
    const source = assets.filter((a) => a.asset_type === "source_checkpoint").length;
    return { total: assets.length, runnable, source };
  });
</script>

<h1>Overview</h1>

<div class="grid cols-3" style="margin-bottom:16px">
  <div class="card stat"><div class="k">Registered models</div><div class="v">{counts.total}</div></div>
  <div class="card stat"><div class="k">Runnable models</div><div class="v" style="color:var(--green)">{counts.runnable}</div></div>
  <div class="card stat"><div class="k">Source checkpoints</div><div class="v">{counts.source}</div></div>
  <div class="card stat"><div class="k">Active atlas jobs</div><div class="v">0</div></div>
  <div class="card stat"><div class="k">Active eval jobs</div><div class="v">0</div></div>
  <div class="card stat"><div class="k">Total runs</div><div class="v">{overview?.total_runs ?? "—"}</div></div>
</div>

<div class="grid cols-2" style="margin-bottom:16px">
  <div class="card">
    <h3>Shortcuts</h3>
    <div class="act-row"><a class="act-name enabled" href="#/models/register">Register model</a></div>
    <div class="act-row"><a class="act-name enabled" href="#/evaluation">Run evaluation</a></div>
    <div class="act-row"><a class="act-name enabled" href="#/atlas">Build atlas</a></div>
    <div class="act-row"><a class="act-name enabled" href="#/experiments">Create experiment</a></div>
    <div class="act-row"><a class="act-name enabled" href="#/comparisons">Compare models</a></div>
  </div>

  <div class="card">
    <h3>Hardware / environment</h3>
    <table>
      <tbody>
        <tr><td class="mut">Nodes</td><td>2 × DGX Spark</td></tr>
        <tr><td class="mut">Unified memory (target)</td><td>256 GB</td></tr>
        <tr><td class="mut">Software</td><td class="mono">eval-lab 0.8.0+ · GUI M1</td></tr>
        {#if error}
          <tr><td class="mut">API status</td><td class="error">{error}</td></tr>
        {:else}
          <tr><td class="mut">API status</td><td><span class="ok">ok</span></td></tr>
        {/if}
      </tbody>
    </table>
    <p class="mut" style="margin-top:8px">Operational view — model, job and hardware state, not decorative analytics.</p>
  </div>
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
