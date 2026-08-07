<script>
  import { get, fmtBytes, fmtGb, ACTION_LABELS } from "./lib/api.js";
  import { exl3Recommendation, pct } from "./lib/recommend.js";

  let { assetId } = $props();

  let data = $state(null);
  let error = $state(null);

  $effect(() => {
    get(`/api/models-assets/${assetId}`)
      .then((d) => (data = d))
      .catch((e) => (error = String(e)));
  });

  function typeLabel(t) {
    return String(t).replace(/_/g, " ");
  }

  function actionHref(action) {
    if (action === "build_atlas") return "#/atlas";
    if (action === "evaluate_directly") return "#/evaluation";
    if (action === "create_keep_map") return "#/experiments";
    if (action === "inspect_checkpoint") return "#/models/register";
    if (action === "compare") return "#/comparisons";
    return "#/models";
  }

  let exl3 = $derived(
    exl3Recommendation({
      stored_size_bytes: data?.record?.stored_size_bytes,
      params: data?.record?.param_metadata?.params_estimate,
    })
  );
  let pm = $derived(data?.record?.param_metadata ?? {});
</script>

{#if error}
  <div class="card">Error: <span class="mut">{error}</span></div>
{:else if !data}
  <div class="card">Loading model…</div>
{:else}
  {@const a = data.record}
  {@const acts = data.actions?.actions ?? {}}
  <a class="mut" href="#/models">← Models</a>

  <h1>{a.name}</h1>
  <span class="badge {a.runnable ? 'pass' : 'type'}">{a.runnable ? "runnable" : typeLabel(a.asset_type)}</span>
  <span class="badge {a.validation_state === 'valid' ? 'pass' : 'error'}">{a.validation_state}</span>

  <div class="grid cols-2">
    <div class="card">
      <h3>Asset</h3>
      <table>
        <tbody>
          <tr><td class="mut">ID</td><td class="mono">{a.asset_id}</td></tr>
          <tr><td class="mut">Type</td><td>{typeLabel(a.asset_type)}</td></tr>
          <tr><td class="mut">Family</td><td>{a.family ?? "—"}</td></tr>
          <tr><td class="mut">Architecture</td><td class="mono">{a.architecture ?? "—"}</td></tr>
          <tr><td class="mut">Revision</td><td class="mono">{a.revision ?? "—"}</td></tr>
          <tr><td class="mut">Path</td><td class="mono">{a.path ?? "—"}</td></tr>
          <tr><td class="mut">Quantization</td><td>{a.quantization_format ?? "—"}</td></tr>
          <tr><td class="mut">Stored size</td><td>{fmtBytes(a.stored_size_bytes)}</td></tr>
          <tr><td class="mut">Resident (est.)</td><td>{fmtGb(a.resident_estimate_bytes)}</td></tr>
          {#if a.parent_asset_id}
            <tr><td class="mut">Parent</td><td><a href="#/model/{a.parent_asset_id}">{a.parent_asset_id}</a></td></tr>
          {/if}
          {#if a.latest_quality_score != null}
            <tr><td class="mut">Latest quality</td><td>{a.latest_quality_score.toFixed(3)}</td></tr>
          {/if}
          <tr><td class="mut">Registered</td><td>{String(a.registered_at ?? "").slice(0, 19).replace("T", " ")}</td></tr>
        </tbody>
      </table>
    </div>

    <div>
      <div class="card">
        <h3>Available actions</h3>
        {#each Object.entries(acts) as [key, act] (key)}
          <div class="act-row">
            <a
              class="act-name {act.available ? 'enabled' : 'disabled'}"
              href={act.available ? actionHref(key) : undefined}
            >
              {ACTION_LABELS[key] ?? key}
            </a>
            {#if act.available}
              <span class="ok">available</span>
            {:else}
              <span class="mut">unavailable</span>
              <p class="act-reason mut">{act.reason}</p>
            {/if}
          </div>
        {/each}
        <p class="mut" style="margin-top:10px">
          At least one action is disabled with an explanation — e.g. direct
          evaluation of an oversized source checkpoint stays off until a runnable
          endpoint exists.
        </p>
      </div>

      {#if a.warnings && a.warnings.length}
        <div class="card" style="margin-top:16px">
          <h3>Warnings</h3>
          <ul>{#each a.warnings as w (w)}<li class="mut">{w}</li>{/each}</ul>
        </div>
      {/if}
    </div>
  </div>

  {#if exl3}
    <div class="card" style="margin-top:16px">
      <h3>Storage &amp; next step (EXL3)</h3>
      <p style="font-size:14px;margin:0 0 6px">
        This checkpoint is stored at <strong>{exl3.achieved.toFixed(1)} bits per weight</strong>.
        Quantizing with EXL3 toward <strong>{exl3.target_bpw} bits/weight</strong> would make it roughly
        <strong>{pct(exl3.shrink)}% smaller</strong> on disk.
      </p>
      {#if pm.num_hidden_layers || pm.num_local_experts}
        <p class="mut" style="font-size:13px;margin:0">
          Context: {pm.num_hidden_layers ? `${pm.num_hidden_layers} layers` : ""}
          {pm.num_local_experts ? ` · ${pm.num_local_experts} routed experts` : ""}
          (from the checkpoint census). EXL3 encoding is the next milestone — it needs a quantizer wired to this
          checkpoint.
        </p>
      {/if}
    </div>
  {/if}

  {#if (a.precision_roles ?? []).length}
    <div class="card" style="margin-top:16px">
      <h3>Measured precision map</h3>
      <p class="mut" style="font-size:13px;margin:0 0 8px">
        Achieved bits per weight by role, read from the checkpoint headers (no tensors loaded).
        Roles at 16 bpw are the best targets for precision reduction / EXL3.
      </p>
      <div class="table-scroll">
        <table>
          <thead><tr><th>Role</th><th>Bits / weight</th><th>Stored</th></tr></thead>
          <tbody>
            {#each a.precision_roles as r (r.role)}
              <tr>
                <td class="mono">{r.role}</td>
                <td>{r.achieved_bpw != null ? Number(r.achieved_bpw).toFixed(2) : "—"}</td>
                <td>{fmtBytes(Number(r.stored_bytes ?? 0))}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {/if}

  <div class="card" style="margin-top:16px">
    <h3>Provenance</h3>
    <p class="mut">
      Source: {a.source_experiment_id ?? a.parent_asset_id ?? "none registered"} ·
      Atlas run: {a.source_atlas_run_id ?? "none"} ·
      Last atlas run: {a.last_atlas_run_id ?? "none"}
    </p>
  </div>
{/if}
