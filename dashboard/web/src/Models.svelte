<script>
  import { onMount } from "svelte";
  import { get, del, fmtBytes, fmtGb } from "./lib/api.js";

  let assets = $state([]);
  let error = $state(null);

  onMount(reload);

  async function reload() {
    try {
      assets = await get("/api/models-assets");
      error = null;
    } catch (e) {
      error = String(e);
    }
  }

  function typeLabel(t) {
    return String(t).replace(/_/g, " ");
  }

  async function remove(assetId) {
    if (!confirm(`Delete model asset ${assetId}?`)) return;
    try {
      await del(`/api/models-assets/${assetId}`);
      await reload();
    } catch (e) {
      error = String(e);
    }
  }
</script>

<h1>Models</h1>

<div class="toolbar">
  <a class="btn" href="#/models/register">+ Register model</a>
  <span class="mut">Registered model assets — checkpoints, runnable models, endpoints and derivatives.</span>
</div>

{#if error}
  <div class="card">Error loading assets: <span class="mut">{error}</span></div>
{/if}

<div class="grid cols-3">
  {#each assets as a (a.asset_id)}
    <div class="card model-card">
      <div class="mc-head">
        <a class="mc-name" href="#/model/{a.asset_id}">{a.name}</a>
        <span class="badge {a.runnable ? 'pass' : 'type'}">{a.runnable ? "runnable" : typeLabel(a.asset_type)}</span>
      </div>
      <div class="mc-type mut">{typeLabel(a.asset_type)} · {a.family ?? "—"}</div>
      <div class="mc-meta">
        <div><span class="mut">Stored</span> {fmtBytes(a.stored_size_bytes)}</div>
        <div><span class="mut">Resident</span> {fmtGb(a.resident_estimate_bytes)}</div>
        <div><span class="mut">Arch</span> {a.architecture ?? "—"}</div>
        <div>
          <span class="mut">Atlas</span>
          <span class={a.atlas_compatible ? "ok" : "mut"}>{a.atlas_compatible ? "compatible" : "—"}</span>
        </div>
        {#if a.latest_quality_score != null}
          <div><span class="mut">Latest quality</span> {a.latest_quality_score.toFixed(3)}</div>
        {/if}
      </div>
      {#if a.warnings && a.warnings.length}
        <div class="mc-warn mut" title={a.warnings.join("\n")}>⚠ {a.warnings.length} warning(s)</div>
      {/if}
      <div class="mc-actions">
        <a class="btn small" href="#/model/{a.asset_id}">Open</a>
        <button class="btn small danger" onclick={() => remove(a.asset_id)}>Delete</button>
      </div>
    </div>
  {/each}
</div>

{#if assets.length === 0}
  <div class="card">
    <p class="mut">No model assets registered. <a href="#/models/register">Register a local checkpoint</a> or load fixtures.</p>
  </div>
{/if}
