<script>
  import { get, post, fmtBytes } from "./lib/api.js";

  let path = $state("");
  let name = $state("");
  let inspecting = $state(false);
  let inspection = $state(null);
  let error = $state(null);
  let registered = $state(null);

  async function runInspect() {
    error = null;
    inspection = null;
    if (!path.trim()) {
      error = "Enter a checkpoint directory path.";
      return;
    }
    inspecting = true;
    try {
      const r = await post("/api/models-assets/inspect", { path, memory_gb: 256 });
      inspection = r.inspection;
    } catch (e) {
      error = String(e);
    } finally {
      inspecting = false;
    }
  }

  async function doRegister() {
    error = null;
    inspecting = true;
    try {
      const r = await post("/api/models-assets", {
        path,
        name: name.trim() || null,
        memory_gb: 256,
      });
      registered = r.record;
      window.location.hash = `#/model/${r.record.asset_id}`;
    } catch (e) {
      error = String(e);
    } finally {
      inspecting = false;
    }
  }

  function issueLevel(cls) {
    return cls === "info" ? "mut" : cls === "warning" ? "warn" : "error";
  }
</script>

<h1>Register a local checkpoint</h1>
<p class="mut">
  Choose a source checkpoint directory. eval-lab inspects metadata and SafeTensors
  headers only — it never loads full tensor payloads for an initial classification.
</p>

<div class="card">
  <h3>1 · Source</h3>
  <label>
    Checkpoint directory
    <input bind:value={path} placeholder="/models/Kimi-K3" style="width:100%" />
  </label>
  <label>
    Display name (optional)
    <input bind:value={name} placeholder="Kimi K3 (dev copy)" style="width:100%" />
  </label>

  <div class="toolbar" style="margin-top:12px">
    <button class="btn" disabled={inspecting} onclick={runInspect}>Inspect checkpoint</button>
    {#if inspection}
      <button class="btn primary" disabled={inspecting} onclick={doRegister}>Register model</button>
    {/if}
  </div>
</div>

{#if inspecting}
  <div class="card">Inspecting…</div>
{/if}
{#if error}
  <div class="card">Error: <span class="mut">{error}</span></div>
{/if}

{#if inspection}
  {@const ins = inspection}
  <div class="card">
    <h3>2 · Inspection result</h3>
    <span class="badge {ins.valid ? 'pass' : 'error'}">{ins.valid ? "Valid" : "Invalid"}</span>
    <span class="badge {ins.atlas_compatible ? 'pass' : 'type'}">
      {ins.atlas_compatible ? "Atlas compatible" : "Not atlas compatible"}
    </span>
    <span class="badge {ins.runnable_here ? 'pass' : 'error'}">
      {ins.runnable_here ? "Fits local run" : "Oversized for local run"}
    </span>
    <table style="margin-top:10px">
      <tbody>
        <tr><td class="mut">Model type</td><td>{ins.model_type ?? "—"}</td></tr>
        <tr><td class="mut">Architecture</td><td class="mono">{ins.architecture ?? "—"}</td></tr>
        <tr><td class="mut">Layers</td><td>{ins.num_hidden_layers ?? "—"}</td></tr>
        <tr><td class="mut">Routed experts</td><td>{ins.num_local_experts ?? "—"}</td></tr>
        <tr><td class="mut">Top-k routing</td><td>{ins.num_experts_per_tok ?? "—"}</td></tr>
        <tr><td class="mut">Quantization</td><td>{ins.quantization_format ?? "—"}</td></tr>
        <tr><td class="mut">Shards</td><td>{ins.shard_count}</td></tr>
        <tr><td class="mut">Files</td><td>{ins.file_count}</td></tr>
        <tr><td class="mut">Stored size</td><td>{fmtBytes(ins.stored_size_bytes)}</td></tr>
        <tr><td class="mut">Params (est.)</td><td>{ins.params_estimate != null ? (ins.params_estimate / 1e9).toFixed(2) + " B" : "—"}</td></tr>
        <tr><td class="mut">Resident (est.)</td><td>{fmtBytes(ins.resident_estimate_bytes)}</td></tr>
      </tbody>
    </table>
    {#if ins.issues && ins.issues.length}
      <h4>Inspection notes</h4>
      <ul>
        {#each ins.issues as i (i.message)}
          <li class={issueLevel(i.level)}>{i.message}</li>
        {/each}
      </ul>
    {/if}
    {#if ins.atlas_compatible}
      <p class="ok" style="margin-top:8px">
        Recommended next action: <a href="#/atlas">Build atlas</a> — this checkpoint can be analysed layerwise.
      </p>
    {/if}
  </div>
{/if}
