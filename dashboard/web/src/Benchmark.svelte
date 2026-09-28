<script>
  import { onMount, untrack } from "svelte";
  import * as echarts from "echarts";
  import "./lib/chartTheme.js";
  import { get, fmtPassed } from "./lib/api.js";
  import { fmtCount, fmtScore, fmtPct, pad, when } from "./lib/fmt.js";
  import Glyph from "./Glyph.svelte";
  import Gauge from "./Gauge.svelte";
  import PixelMap from "./PixelMap.svelte";

  let { modelId = null } = $props();

  let groups = $state([]);
  let leaderboard = $state([]);
  let cfg = $state(null);
  let model = $state("");
  let card = $state(null);
  let pplRuns = $state([]);
  let selectedRun = $state(null);
  let windows = $state(null);
  let error = $state(null);
  let loading = $state(false);
  let chartEl = $state(null);
  let chart = null;

  const GROUP_ORDER = ["core", "coding_deep", "long_context", "perplexity"];
  const SHORT = { core: "core", coding_deep: "deep coding", long_context: "long ctx", perplexity: "perplexity" };
  const CLI_HINT = "benchmark --endpoint http://host:port/v1 --model-name <name>";

  const modelOptions = $derived.by(() => {
    const seen = new Map();
    for (const r of leaderboard) seen.set(r.model_id, `${r.model_id} · ${r.total_runs} run${r.total_runs === 1 ? "" : "s"}`);
    for (const m of cfg?.models ?? []) if (!seen.has(m.model_id)) seen.set(m.model_id, `${m.model_id} · no runs`);
    return [...seen.entries()].map(([id, label]) => ({ id, label }));
  });

  // Latest perplexity run per corpus for the selected model.
  const corpora = $derived.by(() => {
    const seen = new Set();
    return pplRuns.filter((r) => (seen.has(r.task_id) ? false : (seen.add(r.task_id), true)));
  });
  const selectedCorpus = $derived(corpora.find((c) => c.run_id === selectedRun) ?? null);
  const hasData = $derived(!!card && card.scored_tasks > 0);
  const groupMeta = $derived(Object.fromEntries(groups.map((g) => [g.key, g])));
  const meanPpl = $derived.by(() => {
    const xs = Object.values(card?.perplexity ?? {}).map((p) => p.perplexity).filter((x) => typeof x === "number");
    return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
  });
  // Every benchmark task as one map cell, in group order.
  const mapCells = $derived.by(() => {
    const out = [];
    for (const key of GROUP_ORDER) {
      const ids = groupMeta[key]?.task_ids ?? Object.keys(card?.groups?.[key]?.tasks ?? {});
      for (const tid of ids) {
        const t = card?.groups?.[key]?.tasks?.[tid];
        out.push({ id: `${key}:${tid}`, label: `${SHORT[key]} · ${tid}`, score: t?.score ?? null, run_id: t?.run_id ?? null });
      }
    }
    return out;
  });
  const apex = $derived.by(() => {
    const pts = windows?.per_window ?? [];
    if (!pts.length) return null;
    return pts.reduce((m, p) => (p.perplexity > m.perplexity ? p : m), pts[0]);
  });

  async function loadBase() {
    try {
      const [g, lb, c] = await Promise.all([
        get("/api/benchmark/groups"),
        get("/api/benchmark/models"),
        get("/api/eval-config").catch(() => null),
      ]);
      groups = g;
      leaderboard = lb;
      cfg = c;
      if (!model) model = modelId || lb[0]?.model_id || c?.models?.[0]?.model_id || "";
    } catch (e) {
      error = String(e);
    }
  }

  async function loadModel(id) {
    if (!id) {
      card = null;
      pplRuns = [];
      return;
    }
    loading = true;
    error = null;
    try {
      const [c, p] = await Promise.all([
        get(`/api/benchmark/scorecard?model_id=${encodeURIComponent(id)}`),
        get(`/api/perplexity?model_id=${encodeURIComponent(id)}`).catch(() => []),
      ]);
      if (id !== untrack(() => model)) return; // a newer selection won
      card = c;
      pplRuns = p;
      selectedRun = p[0]?.run_id ?? null;
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  async function loadWindows(runId) {
    windows = null;
    if (!runId) return;
    try {
      const d = await get(`/api/runs/${encodeURIComponent(runId)}/perplexity`);
      if (runId === untrack(() => selectedRun)) windows = d;
    } catch {
      windows = { per_window: [] };
    }
  }

  function selectModel(id) {
    model = id;
    history.replaceState(null, "", `#/benchmark/${encodeURIComponent(id)}`);
  }

  $effect(() => {
    const id = modelId;
    if (id) untrack(() => { if (id !== model) model = id; });
  });
  $effect(() => {
    const id = model;
    untrack(() => loadModel(id));
  });
  $effect(() => {
    const id = selectedRun;
    untrack(() => loadWindows(id));
  });
  $effect(() => {
    if (chartEl && windows) renderChart(windows);
  });

  function renderChart(data) {
    if (!chartEl) return;
    if (!chart) chart = echarts.init(chartEl, "lab", { renderer: "canvas" });
    const pts = data.per_window ?? [];
    const mean = data.perplexity;
    const top = apex;
    chart.setOption(
      {
        animation: false,
        grid: { left: 44, right: 16, top: 26, bottom: 28 },
        tooltip: {
          trigger: "axis",
          formatter: (ps) => {
            const p = pts[ps[0]?.dataIndex] ?? {};
            return `window ${pad(p.window ?? 0)}<br/>perplexity ${(p.perplexity ?? 0).toFixed(3)}<br/>${fmtCount(p.tokens)} tokens`;
          },
        },
        xAxis: { type: "category", data: pts.map((p) => pad(p.window)), axisTick: { alignWithLabel: true, length: 4 }, axisLabel: { interval: 4 }, boundaryGap: false },
        yAxis: { type: "value", scale: true, axisLabel: { formatter: (v) => v.toFixed(1) } },
        series: [
          {
            type: "line",
            data: pts.map((p) => p.perplexity),
            smooth: false,
            symbol: "circle",
            symbolSize: 3,
            lineStyle: { color: "#e8e4d8", width: 1 },
            itemStyle: { color: "#e8e4d8" },
            markLine: mean
              ? {
                  silent: true,
                  symbol: "none",
                  lineStyle: { color: "#8a8780", type: "dashed", width: 1 },
                  label: { color: "#8a8780", fontSize: 10, position: "insideEndTop", formatter: () => `mean ${mean.toFixed(2)}` },
                  data: [{ yAxis: mean }],
                }
              : undefined,
            markPoint: top
              ? {
                  symbol: "circle",
                  symbolSize: 6,
                  itemStyle: { color: "#070707", borderColor: "#e8623c", borderWidth: 1 },
                  label: { color: "#e8623c", fontSize: 10, position: "top", offset: [0, -4], formatter: () => `apex ${top.perplexity.toFixed(1)} · w${pad(top.window)}` },
                  data: [{ coord: [pts.indexOf(top), top.perplexity] }],
                }
              : undefined,
          },
        ],
      },
      true
    );
  }

  onMount(() => {
    loadBase();
    const onResize = () => chart?.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart?.dispose();
    };
  });

  function corpusName(tid) {
    return card?.perplexity?.[tid]?.name?.replace(/^Perplexity:\s*/i, "") ?? tid.replace(/^perplexity\./, "").replace(/\.\d+$/, "").replaceAll("_", " ");
  }
  const groupNoun = (g) => `${Object.keys(g?.tasks ?? {}).length}/${g?.task_count ?? 0}`;
</script>

<div class="bm-head">
  <div>
    <h1>benchmark</h1>
    <div class="meta-line"><span>model <b>{card?.model_id ?? model ?? "—"}</b></span><span>runs <b>{fmtCount(card?.total_runs)}</b></span><span>tasks <b>{fmtCount(card?.scored_tasks)}</b></span><span>groups <b>{groups.length || 4}</b></span><span>db <b>runstore.db</b></span></div>
    <p class="mut">Standard scorecard per model — core capabilities, deep coding, long context and intrinsic perplexity — and a leaderboard across every model with runs.</p>
  </div>
  <div class="bm-select">
    <label><span class="k">model</span>
      <select value={model} onchange={(e) => selectModel(e.currentTarget.value)} aria-label="Select model">
        {#if !modelOptions.length}<option value="">no models</option>{/if}
        {#each modelOptions as m (m.id)}<option value={m.id}>{m.label}</option>{/each}
      </select>
    </label>
    <a class="btn primary" href="#/evaluation">▸ run benchmark</a>
  </div>
</div>

{#if error}<div class="card error" style="margin-bottom:16px">{error}</div>{/if}

{#if !leaderboard.length && !loading && !hasData}
  <div class="card bm-empty" style="margin-bottom:16px">
    <h3>no benchmark data yet</h3>
    <p>Run the standard benchmark from <a href="#/evaluation">Evaluation → Standard benchmarks</a>, or from a terminal:</p>
    <div class="term"><span class="term-prompt">eval-lab ~ ❯</span> {CLI_HINT}</div>
  </div>
{/if}

{#if card}
  <div class="bm-top">
    <section class="card sel">
      <div class="card-strip"><span>scorecard</span><span class="mut">latest run per task</span></div>
      <div class="bm-sel-body">
        <div class="kv">
          <div><span>model</span><b class="model-mark"><Glyph seed={card.model_id} size={11} />{card.model_id}</b></div>
          <div><span>overall score</span><b class="accent">{fmtScore(card.overall_score)}</b></div>
          <div><span>pass rate</span><b>{fmtPct(card.overall_pass_rate)}</b></div>
          <div><span>scored tasks</span><b>{fmtCount(card.scored_tasks)}</b></div>
          <div><span>runs</span><b>{fmtCount(card.total_runs)}</b></div>
          <div><span>mean perplexity</span><b>{fmtScore(meanPpl, 2)}</b></div>
          {#if card.missing_groups?.length}<div><span>no runs yet</span><b class="accent">{card.missing_groups.map((k) => SHORT[k] ?? k).join(", ")}</b></div>{/if}
        </div>
        <div class="bm-sel-gauges">
          <Gauge value={card.overall_pass_rate} label={fmtPct(card.overall_pass_rate)} sub="pass" size={84} />
          <Gauge value={card.overall_score} label={fmtScore(card.overall_score, 2)} sub="score" size={84} accent />
        </div>
      </div>
      {#if !hasData}
        <div class="term" style="margin-top:12px"><span class="term-prompt">eval-lab ~ ❯</span> {CLI_HINT}</div>
      {/if}
    </section>

    <section class="card">
      <div class="card-strip"><span>task map</span><span class="mut">1 square = 1 task · fill = score</span></div>
      {#if mapCells.length}
        <div class="pixmap-wrap"><PixelMap cells={mapCells} cols={10} href={(c) => `#/explorer/run/${c.run_id}`} legend="score" /></div>
        <div class="bm-map-key">{#each GROUP_ORDER as key (key)}<span><i></i>{SHORT[key]} <b>{groupNoun(card.groups?.[key])}</b></span>{/each}</div>
      {:else}
        <p class="mut" style="margin:12px 0 0">Suites have no tasks in this checkout.</p>
      {/if}
    </section>
  </div>

  <div class="bm-groups">
    {#each GROUP_ORDER as key (key)}
      {@const g = card.groups?.[key]}
      {@const meta = groupMeta[key]}
      {@const done = Object.keys(g?.tasks ?? {}).length}
      {@const total = meta?.task_count ?? g?.task_count ?? 0}
      <section class="card bm-group">
        <div class="card-strip"><span>{g?.label ?? meta?.name ?? key}</span><span class="mut">{done}/{total} tasks</span></div>
        <div class="bm-group-body">
          <Gauge value={g?.mean_score} label={fmtScore(g?.mean_score, 2)} sub="score" size={72} />
          <div class="kv">
            <div><span>mean score</span><b>{fmtScore(g?.mean_score)}</b></div>
            <div><span>pass rate</span><b>{fmtPct(g?.pass_rate)}</b></div>
            {#if key === "perplexity"}<div><span>mean ppl</span><b>{fmtScore(meanPpl, 2)}</b></div>{:else}<div><span>runs</span><b>{fmtCount(done)}</b></div>{/if}
          </div>
        </div>
        <div class="bm-meter" title="mean score 0 … 1"><span style={`width:${Math.round((g?.mean_score ?? 0) * 100)}%`}></span></div>
        <details class="bm-tasks">
          <summary><span>tasks</span><span class="mut">{done ? `${done} run` : "no runs"}</span></summary>
          {#each meta?.task_ids ?? Object.keys(g?.tasks ?? {}) as tid (tid)}
            {@const t = g?.tasks?.[tid]}
            <div class="bm-task-row">
              {#if t}<a href="#/explorer/run/{t.run_id}" title={tid}>{tid}</a><span class="mono">{fmtScore(t.score)}</span><span class="badge {fmtPassed(t.passed).cls}">{fmtPassed(t.passed).label}</span>
              {:else}<span class="mut" title={tid}>{tid}</span><span class="mono mut">—</span><span class="badge type">none</span>{/if}
            </div>
          {:else}
            <div class="bm-task-row"><span class="mut">suite has no tasks in this checkout</span></div>
          {/each}
        </details>
      </section>
    {/each}
  </div>

  <div class="bm-two">
    <section class="card">
      <div class="card-strip"><span>perplexity</span><span class="mut">latest run per corpus · lower is better</span></div>
      {#if corpora.length}
        <div class="bm-corpus-list">
          <div class="bm-corpus-head"><span>corpus</span><span>ppl</span><span>bits/B</span><span>tokens</span></div>
          {#each corpora as c (c.run_id)}
            <button type="button" class="bm-corpus" class:on={c.run_id === selectedRun} onclick={() => (selectedRun = c.run_id)} aria-pressed={c.run_id === selectedRun}>
              <span class="name"><strong>{corpusName(c.task_id)}</strong><span class="mut" title={when(c.created_at)}>{c.task_id}</span></span>
              <span class="mono" class:accent={c.run_id === selectedRun}>{fmtScore(c.perplexity, 2)}</span>
              <span class="mono">{fmtScore(c.bits_per_byte)}</span>
              <span class="mono">{fmtCount(c.tokens)}</span>
            </button>
          {/each}
        </div>
        <p class="bm-note">perplexity = exp(mean token NLL) over fixed windows · bits/byte normalises across tokenizers</p>
      {:else}
        <div class="bm-empty">
          <p>No perplexity runs for this model.</p>
          <div class="term"><span class="term-prompt">eval-lab ~ ❯</span> {CLI_HINT}</div>
        </div>
      {/if}
    </section>
    <section class="card">
      <div class="card-strip"><span>per-window perplexity</span>{#if selectedCorpus}<span class="mut">{corpusName(selectedCorpus.task_id)} · {windows?.windows ?? selectedCorpus.windows ?? "—"} windows · <a href="#/explorer/run/{selectedCorpus.run_id}">{selectedCorpus.run_id}</a></span>{/if}</div>
      {#if selectedCorpus}
        <div class="bm-chart" bind:this={chartEl}></div>
        {#if windows && !(windows.per_window?.length)}<p class="bm-note">this run stored no per-window metrics</p>{/if}
      {:else}
        <div class="bm-empty"><p>Select a corpus to see how perplexity evolves across the document windows.</p></div>
      {/if}
    </section>
  </div>
{:else if loading}
  <div class="card" style="margin-bottom:16px">loading scorecard…</div>
{/if}

<section class="card bm-lb">
  <div class="card-strip"><span>leaderboard</span><span class="mut">{leaderboard.length} model{leaderboard.length === 1 ? "" : "s"} · ranked by overall score · mean ppl: lower is better</span></div>
  {#if leaderboard.length}
    <div class="table-scroll">
      <table>
        <thead><tr><th class="rank">#</th><th>model</th><th>overall</th><th class="right">pass</th>{#each GROUP_ORDER as k (k)}<th class="right">{SHORT[k]}</th>{/each}<th class="right">mean ppl ↓</th><th class="right">runs</th></tr></thead>
        <tbody>
          {#each leaderboard as r, i (r.model_id)}
            <tr class:on={r.model_id === model}>
              <td class="rank">{r.model_id === model ? "▸" : ""}{pad(i + 1, 2)}</td>
              <td><span class="model-mark"><Glyph seed={r.model_id} size={11} /><a href="#/benchmark/{encodeURIComponent(r.model_id)}" onclick={(e) => { e.preventDefault(); selectModel(r.model_id); }}>{r.model_id}</a></span></td>
              <td><span class="bm-mini"><i><b style={`width:${Math.round((r.overall_score ?? 0) * 100)}%`}></b></i><span class:accent={i === 0}>{fmtScore(r.overall_score)}</span></span></td>
              <td class="right mono">{fmtPct(r.overall_pass_rate)}</td>
              {#each GROUP_ORDER as k (k)}<td class="right mono" class:mut={r.groups?.[k]?.mean_score == null}>{fmtScore(r.groups?.[k]?.mean_score)}</td>{/each}
              <td class="right mono" class:mut={r.mean_perplexity == null}>{fmtScore(r.mean_perplexity, 2)}</td>
              <td class="right mono mut">{fmtCount(r.total_runs)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else}
    <div class="bm-empty"><p>No models have benchmark runs yet.</p><div class="term"><span class="term-prompt">eval-lab ~ ❯</span> {CLI_HINT}</div></div>
  {/if}
</section>
