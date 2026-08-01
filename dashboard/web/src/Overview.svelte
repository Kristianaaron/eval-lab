<script>
  import { get } from "./lib/api.js";

  let overview = $state(null);
  let models = $state(null);
  let error = $state(null);

  $effect(() => {
    get("/api/overview")
      .then((d) => (overview = d))
      .catch((e) => (error = String(e)));
    get("/api/models")
      .then((d) => (models = d))
      .catch(() => {});
  });

  const byStatus = $derived.by(() => (overview ? Object.entries(overview.by_status) : []));

  function fmtDuration(m) {
    if (m.median_duration_s == null) return "—";
    const s = m.median_duration_s;
    if (s < 1) return `${(s * 1000).toFixed(0)}ms`;
    if (s < 60) return `${s.toFixed(2)}s`;
    return `${(s / 60).toFixed(2)}m`;
  }
</script>

<h1>Overview</h1>

{#if error}
  <div class="card">Error loading overview: <span class="mut">{error}</span></div>
{:else if !overview}
  <div class="card">Loading…</div>
{:else}
  <div class="grid cols-3" style="margin-bottom:16px">
    <div class="card stat"><div class="k">Total runs</div><div class="v">{overview.total_runs}</div></div>
    <div class="card stat"><div class="k">Passed</div><div class="v" style="color:var(--green)">{overview.passed}</div></div>
    <div class="card stat"><div class="k">Avg aggregate</div><div class="v">{overview.avg_aggregate_score ?? "—"}</div></div>
    <div class="card stat"><div class="k">Failed</div><div class="v" style="color:var(--red)">{overview.failed}</div></div>
    <div class="card stat"><div class="k">Models</div><div class="v">{overview.models.length}</div></div>
    <div class="card stat"><div class="k">Tasks</div><div class="v">{overview.tasks.length}</div></div>
  </div>

  <div class="grid cols-3">
    <div class="card">
      <h3>By status</h3>
      <table>
        <thead><tr><th>Status</th><th class="right">Count</th></tr></thead>
        <tbody>
          {#each byStatus as [status, count] (status)}
            <tr><td>{status}</td><td class="right">{count}</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
    <div class="card">
      <h3>Models</h3>
      <table>
        <thead><tr><th>Model</th><th class="right">Runs</th><th class="right">Med run</th></tr></thead>
        <tbody>
          {#each (models ?? []) as m (m.model_id)}
            <tr>
              <td>{m.model_id}</td>
              <td class="right">{m.run_count}</td>
              <td class="right">{fmtDuration(m)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      {#if models && models.length === 0}<p class="mut">No model runs yet.</p>{/if}
    </div>
    <div class="card">
      <h3>Tasks</h3>
      <ul class="mono">{#each overview.tasks as t (t)}<li>{t}</li>{/each}</ul>
    </div>
  </div>
{/if}
