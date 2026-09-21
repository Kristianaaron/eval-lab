<script>
  import { onMount } from "svelte";
  import { get, post } from "./lib/api.js";
  import { ArrowUpRight, CheckCircle2, ExternalLink, Info, Workflow } from "@lucide/svelte";

  let status = $state(null);
  let install = $state(null);
  let url = $state("");
  let working = $state(false);
  let error = $state(null);
  let notice = $state(null);
  let bridgeRuns = $state([]);
  let runsError = $state(null);

  const DEFAULT_URL = "http://127.0.0.1:8011/";

  async function loadConnect() {
    try {
      status = await get("/api/cebu");
      url = status.url || DEFAULT_URL;
      install = await get("/api/cebu/install");
    } catch (e) {
      error = String(e);
    }
  }

  async function loadBridgeRuns() {
    try {
      bridgeRuns = await get("/api/cebu-bridge/runs");
    } catch (e) {
      runsError = String(e);
    }
  }

  async function connect() {
    working = true;
    error = null;
    notice = null;
    try {
      status = await post("/api/cebu/connect?url=" + encodeURIComponent(url));
      if (status.error) notice = `Could not reach Cebu Profiler at that URL: ${status.error}`;
    } catch (e) {
      error = String(e);
    } finally {
      working = false;
    }
  }

  async function disconnect() {
    working = true;
    try {
      status = await post("/api/cebu/disconnect");
      url = status.url || DEFAULT_URL;
    } catch (e) {
      error = String(e);
    } finally {
      working = false;
    }
  }

  onMount(() => {
    loadConnect();
    loadBridgeRuns();
  });
</script>

<h1>Cebu Profiler</h1>
<p class="mut">
  Cebu Profiler owns model profiling, calibration, evidence generation, quantization analysis,
  and derivative planning. Eval Lab consumes those outputs to run capability benchmarks and
  hold-out evaluation.
</p>

{#if error}
  <div class="card error">Error: <span class="mut">{error}</span></div>
{/if}
{#if notice}
  <div class="card warn" style="margin-top:10px">{notice}</div>
{/if}

<div class="cebu-info-grid" style="margin-top:16px">
  <section class="card cebu-hero-card">
    <div class="cebu-card-kicker"><Workflow size="14" /> Profiling pipeline</div>
    <h2>Profile the model in Cebu Profiler</h2>
    <p class="mut">
      Choose the checkpoint, storage location, calibration workflow, and profiling options in
      Cebu’s dedicated lab. Jobs persist there and the completed evidence bundle remains linked
      to the source model.
    </p>
    <div class="cebu-pipeline-steps">
      <span><b>1</b> Select model</span>
      <span><b>2</b> Profile &amp; measure</span>
      <span><b>3</b> Review evidence</span>
      <span><b>4</b> Export output</span>
    </div>
    <div class="cebu-hero-actions">
      <a class="beam-btn" href={status?.url || url || DEFAULT_URL} target="_blank" rel="noreferrer">
        <ExternalLink size="14" /> Open Cebu Profiler
      </a>
      {#if status?.reachable}
        <span class="cebu-connection-ok"><CheckCircle2 size="14" /> Connected</span>
      {/if}
    </div>
  </section>

  <section class="card cebu-role-card">
    <div class="cebu-card-kicker"><Info size="14" /> Eval Lab’s role</div>
    <h2>Benchmark the evidence here</h2>
    <p class="mut">
      Once Cebu exports a profile or derivative, Eval Lab imports it and makes the next action
      explicit: benchmark the model, compare runs, or create a held-out experiment.
    </p>
    <a class="tile-link" href="#/experiments">Open experiments <ArrowUpRight size="13" /></a>
    <a class="tile-link" href="#/explorer">Browse evaluation runs <ArrowUpRight size="13" /></a>
  </section>
</div>

<section class="card cebu-connection-card" style="margin-top:16px">
  <div class="cebu-section-head">
    <div>
      <h2>Connection</h2>
      <p class="mut">Eval Lab connects to Cebu’s separately served dashboard; it does not duplicate the profiling pipeline.</p>
    </div>
    <span class="badge {status?.reachable ? 'pass' : ''}">{status?.reachable ? "reachable" : "not connected"}</span>
  </div>
  {#if status?.reachable}
    <div class="cebu-connection-row">
      <span class="mono">{status.url}</span>
      <button class="btn small danger" on:click={disconnect} disabled={working}>Disconnect</button>
    </div>
  {:else}
    <div class="cebu-connect-row">
      <input aria-label="Cebu Profiler URL" bind:value={url} class="mono" />
      <button class="btn primary" on:click={connect} disabled={working || !url}>
        {working ? "Connecting…" : "Connect"}
      </button>
    </div>
    <p class="mut cebu-install-note">
      {install?.serve_command || "Start Cebu Profiler separately, then connect its dashboard URL here."}
    </p>
  {/if}
</section>

<section class="card cebu-outputs-card" style="margin-top:16px">
  <div class="cebu-section-head">
    <div>
      <h2>Cebu outputs in Eval Lab</h2>
      <p class="mut">Imported profile evidence and derivatives available for benchmarking.</p>
    </div>
    <a class="tile-link" href="#/experiments">Manage outputs <ArrowUpRight size="13" /></a>
  </div>
  {#if runsError}
    <p class="mut">{runsError}</p>
  {:else if !bridgeRuns.length}
    <p class="mut cebu-empty">No Cebu profile outputs imported yet. Open Cebu Profiler to create the first one.</p>
  {:else}
    <div class="cebu-output-list">
      {#each bridgeRuns.slice(0, 5) as run (run.run_id)}
        <div class="cebu-output-row">
          <div>
            <strong>{run.run_id}</strong>
            <span class="mut">{run.arch || "unknown architecture"} · {run.n_tasks ?? 0} tasks · {run.n_plans ?? 0} plans</span>
          </div>
          <span class="badge {run.status === 'completed' ? 'pass' : ''}">{run.status || "imported"}</span>
        </div>
      {/each}
    </div>
  {/if}
</section>
