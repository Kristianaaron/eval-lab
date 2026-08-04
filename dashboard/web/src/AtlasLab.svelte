<script>
  import { onMount } from "svelte";
  import { get, post } from "./lib/api.js";

  let status = $state(null);
  let install = $state(null);
  let url = $state("");
  let working = $state(false);
  let error = $state(null);
  let notice = $state(null);

  // imported atlas runs (bridge consumer)
  let runs = $state([]);
  let runsLoading = $state(false);
  let runsError = $state(null);
  let detail = $state(null);
  let detailError = $state(null);

  async function loadRuns() {
    runsLoading = true;
    runsError = null;
    try {
      runs = await get("/api/atlas-bridge/runs");
    } catch (e) {
      runsError = String(e);
    } finally {
      runsLoading = false;
    }
  }

  async function doImport(run_id) {
    runsError = null;
    try {
      await post("/api/atlas-bridge/import", { run_id });
      detail = null;
      await loadRuns();
    } catch (e) {
      runsError = String(e);
    }
  }

  async function showRun(run_id) {
    detail = null;
    detailError = null;
    try {
      detail = await get(`/api/atlas-bridge/runs/${encodeURIComponent(run_id)}`);
    } catch (e) {
      detailError = String(e);
    }
  }

  async function load() {
    error = null;
    notice = null;
    try {
      status = await get("/api/atlas");
      if (status.connected && status.reachable) url = status.url;
      else if (!status.connected) url = status.url || "http://127.0.0.1:8200/";
      if (!install) install = await get("/api/atlas/install");
    } catch (e) {
      error = String(e);
    }
    loadRuns();
  }

  async function doConnect() {
    working = true;
    error = null;
    try {
      status = await post("/api/atlas/connect?url=" + encodeURIComponent(url));
      if (status.error) notice = `Could not reach the Atlas at that URL: ${status.error}`;
    } catch (e) {
      error = String(e);
    } finally {
      working = false;
    }
  }

  async function doDisconnect() {
    working = true;
    try {
      status = await post("/api/atlas/disconnect");
    } catch (e) {
      error = String(e);
    } finally {
      working = false;
    }
  }

  onMount(load);
</script>

<h1>Atlas Lab <span class="badge">{status?.connected && status?.reachable ? "connected" : "disconnected"}</span></h1>
<p class="mut">
  The Atlas engine measures which internal components are responsible for behaviours.
  It is a separate app; this flow installs, connects, and integrates it into eval-lab so
  your calibration data flows into Atlas and derivatives come back for held-out evaluation.
</p>

{#if error}
  <div class="card">Error: <span class="mut">{error}</span></div>
{/if}

{#if notice && !status?.connected}
  <div class="card warn">{notice}</div>
{/if}

<!-- STEP 1: not installed -->
{#if status && !status.installed}
  <section class="card">
    <h2>Step 1 · Install the Atlas engine</h2>
    <p class="mut">The <code>model-atlas</code> package isn't installed on this host yet.</p>
    <ol>
      <li>Install the package:</li>
      <li><pre class="mono">{install?.install_command}</pre></li>
      <li>Start the Atlas dashboard server:</li>
      <li><pre class="mono">{install?.serve_command}</pre></li>
    </ol>
    <p class="mut">
      Docs: <a href={install?.home} target="_blank" rel="noreferrer">{install?.home}</a>
    </p>
    <button class="btn" on:click={load}>I've installed it — refresh</button>
  </section>

<!-- STEP 2: installed but not connected -->
{:else if status && !status.connected}
  <section class="card">
    <h2>Step 2 · Connect to the Atlas</h2>
    <p class="mut">
      {#if status.reachable}
        <span class="ok">The Atlas is running</span>
      {:else}
        <span class="warn">The Atlas server isn't reachable yet</span> — start it with
        <pre class="mono">{install?.serve_command}</pre>
      {/if}
    </p>
    <label class="mut" for="atlas-url">Atlas dashboard URL</label>
    <input id="atlas-url" bind:value={url} class="mono" style="width:360px" />
    <div style="margin-top:10px">
      <button class="btn primary" on:click={doConnect} disabled={working || !url}>
        {working ? "Connecting…" : "Connect & integrate"}
      </button>
    </div>
  </section>

<!-- STEP 3: connected -->
{:else if status && status.connected}
  <section class="card">
    <h2>Connected · Atlas integrated</h2>
    <table>
      <tbody>
        <tr><th>Status</th><td>{status.reachable ? (status.http_status ? "reachable (HTTP " + status.http_status + ")" : "reachable") : "unreachable"}</td></tr>
        <tr><th>Dashboard</th><td class="mono">{status.url}</td></tr>
        <tr><th>Instrument</th><td>{status.reachable ? "connected" : "reachable"}</td></tr>
      </tbody>
    </table>
    <p class="mut">
      eval-lab and Atlas exchange data: your task corpus feeds Atlas calibration, and Atlas
      derivatives can be evaluated on held-out data back here.
    </p>
    <div class="grid cols-3" style="margin-top:12px">
      <a class="btn primary" href={status.url} target="_blank" rel="noreferrer">Open Atlas Lab</a>
      <a class="btn" href="/atlas">Jump to /atlas</a>
      <button class="btn danger" on:click={doDisconnect} disabled={working}>Disconnect</button>
    </div>
  </section>
{/if}


<!-- Imported atlas runs (atlas-bridge consumer) -->
<section class="card" style="margin-top:16px">
  <h2 style="display:flex;align-items:center;gap:10px">
    Imported atlas runs
    <button class="btn small" on:click={loadRuns} disabled={runsLoading}>{runsLoading ? "Loading…" : "Refresh"}</button>
  </h2>
  <p class="mut">
    Atlas export dirs found on this host (<code>atlas_runs/&lt;id&gt;/</code>), imported into
    eval-lab. Keep-maps preserve source expert identity so prune topologies stay auditable.
  </p>
  {#if runsError}
    <div class="card error">{runsError}</div>
  {/if}
  {#if !runsLoading && !runs.length && !runsError}
    <p class="mut">No atlas runs found yet — run <code>model-atlas export</code> to produce one.</p>
  {/if}
  <div class="table-scroll">
    <table>
      <thead><tr><th>Run</th><th>Arch</th><th>Status</th><th>Plans</th><th>Derivative</th><th></th><th></th></tr></thead>
      <tbody>
        {#each runs as r (r.run_id)}
          <tr>
            <td class="mono">{r.run_id}</td>
            <td class="mut">{r.arch ?? "—"}</td>
            <td>{r.status ?? "—"}</td>
            <td>{r.n_plans ?? "—"}</td>
            <td>{r.has_derivative ? "yes" : "—"}</td>
            <td><button class="btn small" on:click={() => doImport(r.run_id)}>Import</button></td>
            <td><button class="btn small" on:click={() => showRun(r.run_id)}>Details</button></td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</section>

{#if detailError}
  <div class="card error" style="margin-top:10px">{detailError}</div>
{/if}
{#if detail}
  <section class="card" style="margin-top:10px">
    <h2>Atlas run <span class="mono">{detail.run_id}</span>
      <span class="badge">{detail.status ?? "—"}</span>
      <a class="btn small" href="#/experiments" style="float:right">Create experiment</a>
    </h2>
    <table>
      <tbody>
        <tr><th>Arch</th><td class="mono">{detail.arch ?? "—"}</td></tr>
        <tr><th>Tasks (calibration)</th><td>{detail.n_tasks ?? "—"}</td></tr>
        <tr><th>Candidate plans</th><td>{detail.n_plans ?? "—"}</td></tr>
        <tr><th>Derivative</th><td>{detail.has_derivative ? "built" : "—"}</td></tr>
      </tbody>
    </table>

    <h3>Candidate plans / keep-maps</h3>
    {#each detail.plans as p (p.name)}
      <div class="card" style="margin:8px 0">
        <strong class="mono">{p.name}</strong>
        {#if p.strategy}<span class="badge">{p.strategy}</span>{/if}
        {#each p.keep_maps as km (p.name + ":" + km.layer_index)}
          <div style="margin:6px 0">
            <span class="mut">layer {km.layer_index} · top-{km.top_k} kept:</span>
            {#each km.entries as e (p.name + ":" + km.layer_index + ":" + e.unit.source_unit_id)}
              {#if e.kept}
                <span class="chip on" title="{e.unit.unit_kind} {e.unit.source_unit_id} · saliency {e.saliency ?? '—'}">{e.unit.unit_kind}·{e.unit.source_unit_id}</span>
              {/if}
            {/each}
          </div>
        {/each}
      </div>
    {/each}

    <h3>Saliency (layer · expert · label)</h3>
    <div class="table-scroll">
      <table>
        <thead><tr><th>Layer</th><th>Expert</th><th>Label</th><th>Mean</th><th>Total</th></tr></thead>
        <tbody>
          {#each (detail.saliency ?? []).slice(0, 200) as s (s.layer + ":" + s.expert + ":" + s.label)}
            <tr><td>{s.layer}</td><td>{s.expert}</td><td class="mono">{s.label}</td><td>{s.mean?.toFixed?.(4) ?? "—"}</td><td>{s.total_value?.toFixed?.(4) ?? "—"}</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>
{/if}
