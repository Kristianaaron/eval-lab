<script>
  import { onDestroy, onMount } from "svelte";
  import { get, post, fmtPassed } from "./lib/api.js";

  let { jobId } = $props();

  let job = $state(null);
  let error = $state(null);
  let timer = null;

  const ACTIVE = ["draft", "queued", "running", "launching_model", "warming_model", "running_tasks", "scoring", "generating_report", "pausing", "paused"];

  async function refresh() {
    try {
      job = await get(`/api/eval-jobs/${jobId}`);
      error = null;
      if (job && ACTIVE.includes(job.state)) start();
    } catch (e) {
      error = String(e);
    }
  }
  function start() {
    if (timer) return;
    timer = setInterval(refresh, 1200);
  }
  function stop() {
    if (timer) { clearInterval(timer); timer = null; }
  }
  function stateCls(s) {
    if (s === "completed" || s === "completed_with_warnings") return "pass";
    if (s === "failed" || s === "failed_recoverable" || s === "cancelled") return "fail";
    return "type";
  }
  async function cancel() {
    await post(`/api/eval-jobs/${jobId}/cancel`, {});
    await refresh();
  }
  const pct = $derived.by(() => {
    if (!job || !job.progress.total) return 0;
    return Math.round((job.progress.done / job.progress.total) * 100);
  });
  onMount(refresh);
  onDestroy(stop);
</script>

<a class="mut" href="#/evaluation">← Evaluation</a>

{#if error}
  <div class="card">Error: <span class="mut">{error}</span></div>
{:else if !job}
  <div class="card">Loading job…</div>
{:else}
  {@const j = job}
  <h1>Eval job <span class="mono">{j.job_id}</span></h1>
  <div class="card">
    <div class="toolbar">
      <span class="badge {stateCls(j.state)}">{j.state}</span>
      <span class="mut">stage: {j.current_stage ?? "—"}</span>
      {#if j.interrupted}<span class="badge fail">interrupted</span>{/if}
    </div>
    {#if j.progress.total != null}
      <div class="progress"><div class="bar" style="width:{pct}%"></div></div>
      <div class="mut">{j.progress.done} / {j.progress.total} tasks · current: {j.progress.detail ?? "—"}</div>
    {/if}
    {#if j.error}
      <p class="error">{j.error}</p>
    {/if}
    {#if ACTIVE.includes(j.state)}
      <div class="toolbar" style="margin-top:12px">
        <button class="btn danger" onclick={cancel} disabled={j.cancel_requested}>Cancel at next task boundary</button>
      </div>
    {/if}
    {#if j.result?.extra?.leakage_overlap?.length}
      <div class="card warn" style="margin-top:12px">
        <strong>Calibration / held-out leakage detected:</strong> this suite overlaps the
        atlas-calibration set. Results are biased and must not be treated as held-out evidence.
      </div>
    {/if}
  </div>

  <div class="card" style="margin-top:16px">
    <h3>Runs ({j.result?.run_ids?.length ?? 0})</h3>
    <table>
      <thead><tr><th class="right">#</th><th>Run</th><th>Artifact</th></tr></thead>
      <tbody>
        {#each (j.result?.run_ids ?? []) as rid, i (rid)}
          <tr>
            <td class="right mut">{i + 1}</td>
            <td class="mono"><a href="#/evaluation/run/{rid}">{rid}</a></td>
            <td class="mut">runs/{rid}/ (manifest · result · trace · report)</td>
          </tr>
        {/each}
      </tbody>
    </table>
    {#if !j.result?.run_ids?.length}<p class="mut">No completed runs yet.</p>{/if}
  </div>

  <div class="card" style="margin-top:16px">
    <h3>Configuration</h3>
    <table>
      <tbody>
        <tr><td class="mut">Model asset</td><td>{j.config.model_asset_id}</td></tr>
        <tr><td class="mut">Model id</td><td>{j.config.model_id}</td></tr>
        <tr><td class="mut">Harness</td><td>{j.config.harness_id ?? "direct"}</td></tr>
        <tr><td class="mut">Suite</td><td class="mono">{j.config.suite_ref}</td></tr>
        <tr><td class="mut">Repeat count</td><td>{j.config.repeat_count ?? 1}</td></tr>
        <tr><td class="mut">Cold start</td><td>{j.config.cold_start ? "yes" : "no"}</td></tr>
      </tbody>
    </table>
    <p class="mut" style="margin-top:8px">Full model/harness/runtime identity is recorded in each run manifest; every run remains auditable.</p>
  </div>
{/if}
