<script>
  import { onMount } from "svelte";
  import { get, post } from "./lib/api.js";

  let status = $state(null);
  let install = $state(null);
  let url = $state("");
  let working = $state(false);
  let error = $state(null);
  let notice = $state(null);

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

