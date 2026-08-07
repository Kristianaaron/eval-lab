<script>
  import { Sparkles, Cpu, HardDrive, ShieldCheck } from "@lucide/svelte";
  import {
    pruneRecommendations,
    loadConcentration,
    redundancySummary,
    exl3Recommendation,
    modelSummary,
    pct,
  } from "./lib/recommend.js";

  // `run` = the atlas run detail (saliency/plans/keep_maps/topology).
  // `modelSizeBytes`/`modelParams` are optional (real checkpoint) and enable
  // the storage / EXL3 readout.
  let { run = null, modelSizeBytes = null, modelParams = null } = $props();

  const pr = $derived(pruneRecommendations(run));
  const cons = $derived(loadConcentration(run?.saliency));
  const red = $derived(redundancySummary(run?.keep_maps));
  const sum = $derived(modelSummary(run));
  const exl3 = $derived(exl3Recommendation({ stored_size_bytes: modelSizeBytes, params: modelParams }));
  const hotExperts = $derived(cons.top.slice(0, 3));

  function labelPlan(p) {
    if (!p) return "";
    return p.dropped_pct === 0
      ? `keeping all ${p.keep_per_layer} experts per layer`
      : `keeping ${p.keep_per_layer} of ${pr.nExp} experts per layer`;
  }
</script>

{#if run}
  <section class="card" style="margin-top:12px">
    <h2 style="display:flex;align-items:center;gap:8px">
      <Sparkles size="15" /> Recommendations
      <span class="badge">based on this run's measurements</span>
    </h2>
    <p class="mut" style="font-size:13px;margin:2px 0 10px">
      A plain-English read of what the traced data suggests. Every number below comes from
      the actual trace — nothing is estimated.
    </p>

    <div class="card" style="margin-top:16px">
      <h4 style="display:flex;align-items:center;gap:6px"><Cpu size="14" /> Pruning strategy</h4>
      {#if pr.recommended}
        {#if pr.recommended.dropped_pct === 0}
          <p style="font-size:14px;margin:0 0 6px">
            <strong>{labelPlan(pr.recommended)}</strong> — this model is tightly loaded. Pruning any experts
            below the full set would lose too much of its real traffic, so we don't recommend cutting experts yet.
            Focus on <em>neuron</em> narrowing (below) and storage (EXL3) instead.
          </p>
        {:else}
          <p style="font-size:14px;margin:0 0 6px">
            We recommend <strong>{labelPlan(pr.recommended)}</strong>: keep
            <strong> {pr.recommended.keep_per_layer} of {pr.nExp} experts</strong> per layer
            (drop <strong>{pr.recommended.dropped_pct}%</strong>) while still covering
            <strong> ~{pct(pr.recommended.retained)}%</strong> of the model's actual traffic.
          </p>
        {/if}
      {/if}
      {#if (pr.scores ?? []).length}
        <div class="table-scroll">
          <table>
            <thead><tr><th>Strategy</th><th>Experts kept / layer</th><th>Traffic kept</th><th>Experts removed</th></tr></thead>
            <tbody>
              {#each pr.scores ?? [] as s (s.name)}
                <tr class="{s.name === pr.recommended?.name ? 'rec-row' : ''}">
                  <td class="mono">
                    {s.name}
                    {#if s.name === pr.recommended?.name}<span class="badge">recommended</span>{/if}
                  </td>
                  <td>{s.keep_per_layer} / {pr.nExp}</td>
                  <td>{pct(s.retained)}%</td>
                  <td>{s.dropped_pct}%</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </div>

    <div class="card" style="margin-top:16px">
      <h4 style="display:flex;align-items:center;gap:6px"><ShieldCheck size="14" /> Preserve the busiest experts (neurons)</h4>
      {#if hotExperts.length}
        <p style="font-size:14px;margin:0 0 6px">
          The busiest three experts — e{hotExperts.map((t) => t.expert).join(", e")} — carry
          <strong>{pct(cons.topShare)}%</strong> of all routed traffic. These do most of the work, so they should
          keep their <strong>full neuron width</strong> (all internal channels). The quieter experts are the natural
          candidates for narrowing during neuron pruning.
        </p>
      {/if}
      <p class="mut" style="font-size:13px;margin:0">
        Protected in every layer: <strong style="color:var(--text)">{red.protectedCount}</strong> ·
        fully redundant (prunable everywhere): <strong style="color:var(--text)">{red.redundant}</strong>
        {red.nLayers ? ` · across ${red.nLayers} layers` : ""}.
      </p>
    </div>

    <div class="card" style="margin-top:16px">
      <h4 style="display:flex;align-items:center;gap:6px"><HardDrive size="14" /> Storage &amp; next step (EXL3)</h4>
      {#if exl3}
        <p style="font-size:14px;margin:0 0 6px">
          This checkpoint is stored at <strong>{exl3.achieved.toFixed(1)} bits per weight</strong>.
          EXL3 quantization targets around <strong>{exl3.target_bpw} bits/weight</strong>, which would make the model
          roughly <strong>{pct(exl3.shrink)}% smaller</strong> on disk.
        </p>
        <p class="mut" style="font-size:13px;margin:0">
          This is the next milestone — it launches once an EXL3 quantizer is wired to the checkpoint; this run is not
          EXL3-encoded yet.
        </p>
      {:else}
        <p style="font-size:14px;margin:0 0 6px">
          EXL3 is a compression step that stores the model more efficiently (fewer bits per weight).
        </p>
        <p class="mut" style="font-size:13px;margin:0">
          This is the next milestone. This run doesn't yet compute a per-weight budget — we'll add the readout once an
          EXL3 quantizer is connected to the checkpoint.
        </p>
      {/if}
    </div>

    <details style="margin-top:16px">
      <summary class="mut" style="cursor:pointer;font-size:13px">In one line</summary>
      <p class="mut" style="font-size:13px;margin:8px 0 0;line-height:1.6">
        This model routed <strong style="color:var(--text)">{sum.traceTokens}</strong> tokens through
        <strong style="color:var(--text)">{sum.nLayers}</strong> layers of
        <strong style="color:var(--text)">{sum.nExp}</strong> experts each.
        {#if sum.topExpert != null}The single busiest expert is <strong style="color:var(--text)">e{sum.topExpert}</strong>,
        at {sum.topSharePct}% of traffic; it should be protected in any prune.{/if}
      </p>
    </details>
  </section>
{/if}

<style>
  .rec-row td { background: rgba(79, 140, 255, 0.06); }
</style>
