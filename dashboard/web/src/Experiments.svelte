<script>
  import { onMount } from "svelte";
  import { get, post, del } from "./lib/api.js";

  let experiments = $state([]);
  let runs = $state([]);
  let runPlans = $state([]);
  let showCreate = $state(false);
  let error = $state(null);
  let working = $state(false);

  let fRun = $state("");
  let fPlan = $state("");
  let fObjective = $state("");
  let fMemory = $state("");

  async function load() {
    error = null;
    try {
      experiments = await get("/api/experiments");
    } catch (e) {
      error = String(e);
    }
  }

  async function loadRuns() {
    try {
      runs = await get("/api/atlas-bridge/runs");
    } catch (e) {
      /* runs listing is best-effort; leave the create form empty */
    }
  }

  async function onRunChange() {
    fPlan = "";
    runPlans = [];
    if (!fRun) return;
    try {
      const d = await get(`/api/atlas-bridge/runs/${encodeURIComponent(fRun)}`);
      runPlans = (d.plans ?? []).map((p) => p.name);
    } catch (e) {
      runPlans = [];
    }
  }

  async function create() {
    working = true;
    error = null;
    try {
      await post("/api/experiments", {
        run_id: fRun,
        plan_name: fPlan,
        objective: fObjective,
        memory_target_bytes: fMemory ? Number(fMemory) : null,
      });
      fRun = "";
      fPlan = "";
      fObjective = "";
      fMemory = "";
      showCreate = false;
      await load();
    } catch (e) {
      error = String(e);
    } finally {
      working = false;
    }
  }

  async function remove(id) {
    try {
      await del(`/api/experiments/${encodeURIComponent(id)}`);
      await load();
    } catch (e) {
      error = String(e);
    }
  }

  onMount(() => {
    load();
    loadRuns();
  });
</script>

<h1>Experiments</h1>
<p class="mut">
  Saved prune / intervention strategies, each pinned to an imported atlas run and one candidate
  plan, preserving source expert identity from the keep-map. Create from an atlas run, then
  evaluate the linked derivative as held-out evidence.
</p>

{#if error}
  <div class="card error">{error}</div>
{/if}

<div style="margin-bottom:10px">
  <button class="btn primary" on:click={() => (showCreate = !showCreate)}>
    {showCreate ? "Cancel" : "Create experiment"}
  </button>
</div>

{#if showCreate}
  <section class="card">
    <h2>New experiment</h2>
    <label class="mut" for="exp-run">Atlas run
      <select id="exp-run" bind:value={fRun} on:change={onRunChange}>
        <option value="" disabled>choose a run…</option>
        {#each runs as r (r.run_id)}
          <option value={r.run_id}>{r.run_id}{r.has_derivative ? " · derivative built" : ""}</option>
        {/each}
      </select>
    </label>
    <label class="mut" for="exp-plan">Candidate plan
      <select id="exp-plan" bind:value={fPlan}>
        <option value="" disabled>choose a plan…</option>
        {#each runPlans as p (p)}
          <option value={p}>{p}</option>
        {/each}
      </select>
    </label>
    <label class="mut" for="exp-obj">Objective
      <input id="exp-obj" bind:value={fObjective} placeholder="e.g. retain code_generation" />
    </label>
    <label class="mut" for="exp-mem">Memory target (bytes)
      <input id="exp-mem" bind:value={fMemory} type="number" placeholder="optional" />
    </label>
    <button class="btn primary" on:click={create} disabled={working || !fRun || !fPlan}>
      {working ? "Creating…" : "Save experiment"}
    </button>
  </section>
{/if}

{#if !experiments.length}
  <p class="mut">
    No experiments yet. Import an atlas run under Atlas Lab, then create an experiment from one
    of its candidate plans.
  </p>
{/if}
{#each experiments as e (e.experiment_id)}
  <div class="card" style="margin-bottom:10px">
    <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
      <strong class="mono">{e.experiment_id}</strong>
      <span>
        <span class="badge">{e.status}</span>
        <button class="btn small danger" on:click={() => remove(e.experiment_id)}>Delete</button>
      </span>
    </div>
    <table>
      <tbody>
        <tr><th>Atlas run</th><td class="mono">{e.run_id}</td></tr>
        <tr><th>Plan</th><td class="mono">{e.plan_name} ({e.experiment_type})</td></tr>
        <tr><th>Objective</th><td>{e.objective || "—"}</td></tr>
        <tr><th>Kept experts</th><td>{e.total_kept} — {Object.entries(e.kept_per_layer).map(([l, n]) => `layer ${l}: ${n}`).join(", ")}</td></tr>
        <tr><th>Memory target</th><td>{e.memory_target_bytes ?? "—"}</td></tr>
        <tr><th>Derivative asset</th><td class="mono">{e.derivate_asset_id ?? "—"}</td></tr>
      </tbody>
    </table>
  </div>
{/each}
