<script>
  import { onMount } from "svelte";
  import { get, post } from "./lib/api.js";
  import RunDetail from "./RunDetail.svelte";
  import EvalJobDetail from "./EvalJobDetail.svelte";

  let { runId = null, jobId = null } = $props();

  let cfg = $state(null);
  let error = $state(null);
  let model = $state("");
  let suite = $state("");
  let harness = $state("direct");
  let repeat = $state(1);
  let cold = $state(false);
  let recent = $state([]);
  let launchedJob = $state(null);

  async function loadCfg() {
    try {
      cfg = await get("/api/eval-config");
      error = null;
      if (!model && cfg.models.length) model = cfg.models[0].model_id;
      if (!suite && cfg.suites.length) suite = cfg.suites[0].suite_ref;
    } catch (e) {
      error = String(e);
    }
  }
  async function loadRecent() {
    try {
      recent = await get("/api/eval-jobs");
    } catch {}
  }

  async function launch() {
    error = null;
    try {
      launchedJob = await post("/api/eval-jobs", {
        model_asset_id: model,
        model_id: model,
        harness_id: harness,
        suite_ref: suite,
        repeat_count: Number(repeat),
        cold_start: cold,
        runs_root: "runs",
      });
      await loadRecent();
    } catch (e) {
      error = String(e);
    }
  }

  function jobCls(state) {
    if (state.includes("complete")) return "pass";
    if (state.includes("fail") || state === "cancelled") return "fail";
    return "type";
  }

  onMount(() => {
    loadCfg();
    loadRecent();
  });
</script>

<h1>Evaluation</h1>

{#if runId}
  <RunDetail runId={runId} />
{:else if jobId}
  <EvalJobDetail jobId={jobId} />
{:else}
  <p class="mut">
    What can this runnable model or agent configuration do? Model and harness
    identity are recorded separately in each run manifest.
  </p>

  {#if error}
    <div class="card">Error: <span class="mut">{error}</span></div>
  {/if}

  {#if launchedJob}
    <div class="card notice">
      <strong>Launched {launchedJob.job_id}</strong> ·
      <a href="#/evaluation/job/{launchedJob.job_id}">Open monitor</a>
    </div>
  {/if}

  <div class="grid cols-2">
    <div class="card">
      <h3>1 · Configuration</h3>
      {#if cfg}
        <label>
          Model
          <select bind:value={model}>
            {#each cfg.models as m (m.model_id)}
              <option value={m.model_id}>{m.name} ({m.model_id})</option>
            {/each}
          </select>
        </label>
        <label>
          Suite
          <select bind:value={suite}>
            {#each cfg.suites as s (s.suite_ref)}
              <option value={s.suite_ref}>{s.name} — {s.task_count} task(s)</option>
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
        <div class="toolbar" style="margin-top:12px">
          <button class="btn primary" onclick={launch}>Launch evaluation</button>
        </div>
      {:else}
        <div class="mut">Loading configuration…</div>
      {/if}
    </div>

    <div class="card">
      <h3>2 · Recent evaluation jobs</h3>
      <table>
        <thead><tr><th>Job</th><th>State</th><th class="right">Progress</th></tr></thead>
        <tbody>
          {#each recent as j (j.job_id)}
            <tr>
              <td class="mono"><a href="#/evaluation/job/{j.job_id}">{j.job_id}</a></td>
              <td><span class="badge {jobCls(j.state)}">{j.state}</span></td>
              <td class="right">
                {j.progress.done}{j.progress.total != null ? ` / ${j.progress.total}` : ""}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
      {#if !recent.length}<p class="mut">No evaluation jobs yet.</p>{/if}
    </div>
  </div>
{/if}
