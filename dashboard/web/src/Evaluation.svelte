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
  let suiteName = $state("");
  let selected = $state([]); // chosen domains
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

  function toggleDomain(d) {
    selected = selected.includes(d) ? selected.filter((x) => x !== d) : [...selected, d];
  }

  async function saveSuite() {
    error = null;
    if (!selected.length) {
      error = "Pick at least one domain first.";
      return;
    }
    try {
      const created = await post("/api/suites", {
        name: suiteName.trim() || "User suite",
        domains: selected,
      });
      suite = created.suite_ref;
      suiteName = "";
      await loadCfg();
      suite = created.suite_ref;
    } catch (e) {
      error = String(e);
    }
  }

  async function ensureSuite() {
    // Reuse the chosen saved suite, or build an ephemeral one from the selection.
    if (suite) return suite;
    const created = await post("/api/suites", {
      name: suiteName.trim() || "Ad-hoc eval",
      domains: selected,
    });
    suite = created.suite_ref;
    return suite;
  }

  async function launch() {
    error = null;
    try {
      const ref = await ensureSuite();
      launchedJob = await post("/api/eval-jobs", {
        model_asset_id: model,
        model_id: model,
        harness_id: harness,
        suite_ref: ref,
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
    Configure a run: choose a registered model, pick the domains you want, and either run
    the instantiated selection or save it as a reusable suite. The panel on the right
    previews your selection and launches the eval.
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

  <div class="grid cols-2" style="align-items:start">
    <!-- left: configuration -->
    <div class="card">
      <h3>Configuration</h3>
      {#if cfg}
        <label>
          Model
          <select bind:value={model}>
            {#each cfg.models as m (m.model_id)}
              <option value={m.model_id}>{m.name} ({m.model_id})</option>
            {/each}
          </select>
        </label>

        <div style="margin:12px 0">
          <div class="k" style="margin-bottom:6px">Domains</div>
          <div class="chips">
            {#each cfg.domains ?? [] as d (d)}
              <button
                type="button"
                class:chip class:on={selected.includes(d)}
                on:click={() => toggleDomain(d)}
              >
                {d}
              </button>
            {/each}
          </div>
          <p class="mut" style="font-size:12px;margin:6px 0 0">
            Pick domains; the right panel builds rows for the selected domains.
          </p>
        </div>

        <label>
          Save selection as suite
          <input bind:value={suiteName} placeholder="Suite name (optional)" />
        </label>
        <button class="btn" on:click={saveSuite}>Save suite</button>

        <label>
          Or reuse a saved suite
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
      {:else}
        <p class="mut">Loading configuration…</p>
      {/if}
    </div>

    <!-- right: run panel -->
    <div class="card run-panel">
      <button class="btn primary run-cta" on:click={launch}>
        {selected.length ? `Run new eval (${selected.length} domain${selected.length === 1 ? "" : "s"})` : "Run new eval"}
      </button>

      <table style="margin-top:14px">
        <thead>
          <tr><th>Domain</th><th>Tasks</th><th>Weight</th><th>Status</th></tr>
        </thead>
        <tbody>
          {#each selected as d (d)}
            <tr><td>{d}</td><td></td><td></td><td></td></tr>
          {:else}
            <tr>
              <td colspan="4" class="mut">No domains selected — pick domains on the left to build this preview.</td>
            </tr>
          {/each}
        </tbody>
      </table>

      {#if recent.length}
        <h4 style="margin-top:18px">Recent jobs</h4>
        <table>
          <thead><tr><th>Job</th><th>Model</th><th>State</th></tr></thead>
          <tbody>
            {#each recent.slice(0, 8) as j (j.job_id)}
              <tr>
                <td><a href="#/evaluation/job/{j.job_id}">{j.job_id}</a></td>
                <td class="mut">{j.model_id}</td>
                <td class="{jobCls(j.state)}">{j.state}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  </div>
{/if}
