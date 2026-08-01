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
</script>

{#if error}
  <div class="card">Error: <span class="mut">{error}</span></div>
{:else if !detail}
  <div class="card">Loading…</div>
{:else}
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
    <button class="link" onclick={() => (window.location.hash = "#/runs")}>← Runs</button>
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

  <div class="card" style="margin-bottom:16px">
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

  <div class="card" style="margin-bottom:16px">
    <h3>Telemetry</h3>
    <div bind:this={chartEl} style="width:100%;height:260px"></div>
  </div>

  <div class="card">
    <h3>Trace ({trace.length} events)</h3>
    <div style="max-height:400px;overflow:auto">
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
    </div>
  </div>
{/if}
