<script>
  import { onMount } from "svelte";
  import * as echarts from "echarts";
  import { get, fmtPassed } from "./lib/api.js";

  let { runId } = $props();

  let detail = $state(null);
  let trace = $state([]);
  let telemetry = $state(null);
  let error = $state(null);
  let chartEl = $state(null);
  let chart = null;
  let tab = $state("overview");

  $effect(() => {
    if (chartEl && telemetry) renderChart(telemetry);
  });

  $effect(() => {
    const id = runId ? `/${runId}` : "";
    Promise.all([
      get(`/api/runs${id}`),
      get(`/api/runs${id}/trace`),
      get(`/api/runs${id}/telemetry`).catch(() => null),
    ])
      .then(([d, t, telem]) => {
        detail = d;
        trace = t;
        telemetry = telem;
      })
      .catch((e) => (error = String(e)));
  });

  function renderChart(telem) {
    if (!chartEl) return;
    const seriesData = telem?.series ?? {};
    const key = Object.keys(seriesData)[0];
    const points = key ? seriesData[key] : [];
    if (!chart) chart = echarts.init(chartEl);
    let option;
    if (!key || points.length === 0) {
      option = {
        title: { text: "No telemetry samples", textStyle: { color: "#8b93a3", fontSize: 13 } },
      };
    } else {
      option = {
        title: { text: key, textStyle: { color: "#8b93a3", fontSize: 13 } },
        tooltip: { trigger: "axis" },
        grid: { left: 60, right: 20, top: 40, bottom: 40 },
        xAxis: { type: "category", data: points.map((p) => (p.t_ns / 1e6).toFixed(0)) },
        yAxis: { type: "value" },
        series: [{ type: "line", data: points.map((p) => p.value), smooth: true }],
      };
    }
    chart.setOption(option);
  }

  onMount(() => {
    return () => chart?.dispose();
  });

  const tabs = [
    { key: "overview", label: "Overview" },
    { key: "result", label: "Result" },
    { key: "telemetry", label: "Telemetry" },
    { key: "trace", label: `Trace (${trace.length})` },
    { key: "raw", label: "Raw" },
  ];

  function fmt(v) {
    if (v == null || v === "") return "—";
    if (typeof v === "boolean") return v ? "yes" : "no";
    if (typeof v === "object") return JSON.stringify(v);
    return String(v);
  }
</script>

{#if error}
  <div class="card">Error: <span class="mut">{error}</span></div>
{:else if !detail}
  <div class="card">Loading…</div>
{:else}
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
    <button class="link" onclick={() => (window.location.hash = "#/explorer")}>← Explorer</button>
    <h1 style="margin:0" class="mono">{runId}</h1>
    <span class="badge {fmtPassed(detail.run.passed).cls}">{fmtPassed(detail.run.passed).label}</span>
  </div>

  <div class="grid cols-3" style="margin-bottom:16px">
    <div class="card stat">
      <div class="k">Model</div>
      <div class="v" style="font-size:18px">{detail.run.model_id ?? "—"}</div>
    </div>
    <div class="card stat">
      <div class="k">Task</div>
      <div class="v mono" style="font-size:16px">{detail.run.task_id}</div>
    </div>
    <div class="card stat">
      <div class="k">Score</div>
      <div class="v">{detail.run.aggregate_score?.toFixed(3) ?? "—"}</div>
    </div>
  </div>

  <div class="chips" style="margin-bottom:16px">
    {#each tabs as t (t.key)}
      <button class="chip" class:on={tab === t.key} onclick={() => (tab = t.key)}>{t.label}</button>
    {/each}
  </div>

  {#if tab === "overview"}
    <div class="card" style="margin-bottom:16px">
      <h3>Manifest &amp; identity</h3>
      <table>
        <tbody>
          {#each Object.entries(detail.manifest ?? {}) as [k, v] (k)}
            {#if !["run_dir", "git_commit", "dirty_state_hash"].includes(k)}
              <tr>
                <th>{k}</th>
                <td class="mono">{typeof v === "object" && v !== null ? JSON.stringify(v) : fmt(v)}</td>
              </tr>
            {/if}
          {/each}
        </tbody>
      </table>
    </div>

    <div class="card">
      <h3>Scores</h3>
      <table>
        <thead><tr><th>Scorer</th><th class="right">Score</th><th>Required</th><th>Evidence</th></tr></thead>
        <tbody>
          {#each detail.scores as s (s.scorer_id)}
            <tr>
              <td class="mono">{s.scorer_id}</td>
              <td class="right">{s.score}</td>
              <td>{s.required ? "yes" : "no"}</td>
              <td class="mut mono">{s.evidence_artifacts?.join(", ") ?? ""}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else if tab === "result"}
    <div class="card" style="margin-bottom:16px">
      <h3>Result</h3>
      <table>
        <tbody>
          {#each Object.entries(detail.result ?? {}) as [k, v] (k)}
            {#if k !== "scores"}
              <tr>
                <th>{k}</th>
                <td class="mono" style="white-space:pre-wrap;word-break:break-word">
                  {typeof v === "object" && v !== null ? JSON.stringify(v, null, 2) : fmt(v)}
                </td>
              </tr>
            {/if}
          {/each}
        </tbody>
      </table>
    </div>

    <div class="card">
      <h3>Report (markdown)</h3>
      <pre class="mono" style="white-space:pre-wrap;word-break:break-word;margin:0">{detail.report ?? "—"}</pre>
    </div>
  {:else if tab === "telemetry"}
    <div class="card">
      <h3>Telemetry
        {#if telemetry}
          · <span class="mut">{telemetry.sample_count ?? 0} samples · nodes {telemetry.nodes?.join(", ") ?? "—"}</span>
        {/if}
      </h3>
      <div bind:this={chartEl} style="width:100%;height:260px"></div>
    </div>
  {:else if tab === "trace"}
    <div class="card">
      <h3>Trace ({trace.length} events)</h3>
      <div style="max-height:500px;overflow:auto">
        <table>
          <thead><tr><th>Seq</th><th>Type</th><th>Payload</th></tr></thead>
          <tbody>
            {#each trace as ev, i (ev.sequence ?? i)}
              <tr>
                <td class="mut">{ev.sequence}</td>
                <td class="mono">{ev.event_type}</td>
                <td class="mono"><code>{JSON.stringify(ev.payload)}</code></td>
              </tr>
            {/each}
          </tbody>
        </table>
        {#if trace.length === 0}<p class="mut">No trace events recorded.</p>{/if}
      </div>
    </div>
  {:else}
    <div class="card" style="margin-bottom:16px">
      <h3>Stored artifacts</h3>
      {#if detail.artifacts?.length}
        <ul class="mono">{#each detail.artifacts as a (a)}<li>{a}</li>{/each}</ul>
      {:else}
        <p class="mut">No extra artifacts beyond the standard run files.</p>
      {/if}
    </div>

    <div class="card" style="margin-bottom:16px">
      <h3>manifest.json</h3>
      <pre class="mono" style="white-space:pre-wrap;word-break:break-word;margin:0">{JSON.stringify(detail.manifest, null, 2)}</pre>
    </div>

    <div class="card" style="margin-bottom:16px">
      <h3>result.json</h3>
      <pre class="mono" style="white-space:pre-wrap;word-break:break-word;margin:0">{JSON.stringify(detail.result, null, 2)}</pre>
    </div>

    <div class="card">
      <h3>report.md</h3>
      <pre class="mono" style="white-space:pre-wrap;word-break:break-word;margin:0">{detail.report ?? "—"}</pre>
    </div>
  {/if}
{/if}
