<script>
  import { onMount } from "svelte";
  import { get } from "./lib/api.js";

  let jobs = $state([]);
  let error = $state(null);

  onMount(load);
  async function load() {
    try {
      jobs = await get("/api/jobs");
      error = null;
    } catch (e) {
      error = String(e);
    }
  }

  function stateCls(s) {
    if (s === "completed" || s === "completed_with_warnings") return "pass";
    if (s === "failed" || s === "failed_recoverable" || s === "cancelled") return "fail";
    return "type";
  }
  function detailHref(j) {
    if (j.kind === "evaluation") return `#/evaluation/job/${j.job_id}`;
    return null;
  }
</script>

<h1>Jobs</h1>
<div class="toolbar">
  <button class="btn" onclick={load}>Refresh</button>
  <span class="mut">All long-running operations survive GUI restarts.</span>
</div>

{#if error}
  <div class="card">Error: <span class="mut">{error}</span></div>
{/if}

<div class="card">
  <table>
    <thead><tr><th>Job</th><th>Kind</th><th>State</th><th>Stage</th><th class="right">Progress</th><th>Created</th></tr></thead>
    <tbody>
      {#each jobs as j (j.job_id)}
        {@const href = detailHref(j)}
        <tr>
          <td>
            {#if href}<a href={href} class="mono">{j.job_id}</a>{:else}<span class="mono">{j.job_id}</span>{/if}
          </td>
          <td>{j.kind}</td>
          <td><span class="badge {stateCls(j.state)}">{j.state}</span>
            {#if j.interrupted}<span class="mut"> (interrupted)</span>{/if}
          </td>
          <td class="mut">{j.current_stage ?? "—"}</td>
          <td class="right">
            {#if j.progress.total != null}
              {j.progress.done} / {j.progress.total}
            {:else if j.progress.done > 0}
              {j.progress.done}
            {:else}
              —
            {/if}
          </td>
          <td class="mut">{String(j.created_at ?? "").slice(0, 19).replace("T", " ")}</td>
        </tr>
      {/each}
    </tbody>
  </table>
  {#if jobs.length === 0}<p class="mut">No jobs yet.</p>{/if}
</div>
