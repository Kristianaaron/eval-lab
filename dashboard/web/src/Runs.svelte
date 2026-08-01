<script>
  import { get, fmtPassed } from "./lib/api.js";

  let overview = $state(null);
  let runs = $state([]);
  let model = $state("");
  let task = $state("");
  let status = $state("");
  let error = $state(null);

  $effect(() => {
    get("/api/overview")
      .then((d) => (overview = d))
      .catch(() => {});
    reload();
  });

  function reload() {
    const params = new URLSearchParams();
    if (model) params.set("model_id", model);
    if (task) params.set("task_id", task);
    if (status) params.set("status", status);
    get(`/api/runs?${params}`)
      .then((d) => (runs = d))
      .catch((e) => (error = String(e)));
  }
</script>

<h1>Runs</h1>

<div class="filters">
  <select bind:value={model} onchange={reload}>
    <option value="">all models</option>
    {#each (overview?.models ?? []) as m (m)}
      <option value={m}>{m}</option>
    {/each}
  </select>
  <select bind:value={task} onchange={reload}>
    <option value="">all tasks</option>
    {#each (overview?.tasks ?? []) as t (t)}
      <option value={t}>{t}</option>
    {/each}
  </select>
  <select bind:value={status} onchange={reload}>
    <option value="">all statuses</option>
    {#each ["completed", "error", "draft"] as s (s)}
      <option value={s}>{s}</option>
    {/each}
  </select>
</div>

{#if error}
  <div class="card">Error: <span class="mut">{error}</span></div>
{/if}

<div class="card">
  <table>
    <thead>
      <tr>
        <th>Run</th><th>Created</th><th>Task</th><th>Model</th><th>Suite</th><th class="right">Score</th><th>Status</th>
      </tr>
    </thead>
    <tbody>
      {#each runs as r (r.run_id)}
        <tr>
          <td class="mono"><a href="#/run/{r.run_id}">{r.run_id}</a></td>
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
