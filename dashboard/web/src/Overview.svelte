<script>
  import { get, fmtBytes, fmtPassed } from "./lib/api.js";
  import { fmtCount, fmtScore, when } from "./lib/fmt.js";
  import Glyph from "./Glyph.svelte";
  import Globe from "./Globe.svelte";

  let overview = $state(null);
  let assets = $state([]);
  let env = $state(null);
  let jobs = $state([]);
  let recentRuns = $state([]);
  let pplRuns = $state([]);
  let error = $state(null);

  $effect(() => {
    get("/api/overview").then((d) => (overview = d)).catch((e) => (error = String(e)));
    get("/api/models-assets").then((d) => (assets = d)).catch(() => {});
    get("/api/environment").then((d) => (env = d)).catch(() => {});
    get("/api/jobs").then((d) => (jobs = d)).catch(() => {});
    get("/api/runs?limit=5").then((d) => (recentRuns = d)).catch(() => {});
    get("/api/perplexity?limit=4").then((d) => (pplRuns = d)).catch(() => {});
  });

  const counts = $derived.by(() => ({ total: assets.length, runnable: assets.filter((a) => a.runnable).length }));
  const activeJobs = $derived(jobs.filter((j) => ["queued", "running", "pausing", "paused", "resuming"].includes(j.state)));
  const passRate = $derived(overview?.total_runs ? Math.round((overview.passed / overview.total_runs) * 100) : null);
  function corpus(taskId) { return String(taskId ?? "").replace(/^perplexity\./, "").replace(/\.\d+$/, "").replaceAll("_", " "); }
</script>

<div class="ov-header">
  <div>
    <div class="ov-label">workspace</div>
    <h1>overview</h1>
    <div class="meta-line"><span>runs <b>{fmtCount(overview?.total_runs)}</b></span><span>passed <b>{fmtCount(overview?.passed)}</b></span><span>models <b>{fmtCount(overview?.models?.length)}</b></span><span>tasks <b>{fmtCount(overview?.tasks?.length)}</b></span><span>jobs <b>{activeJobs.length} active</b></span><span>v<b>{env?.software_version ?? "—"}</b></span></div>
    <p class="mut">A quick read on model readiness, hardware capacity, and the latest benchmark evidence.</p>
    <div class="term"><span class="term-prompt">eval-lab ~ ❯</span> <a href="#/evaluation">run evaluation</a> · <a href="#/benchmark">benchmark</a> · <a href="#/explorer">explorer</a></div>
  </div>
  <div class="ov-hero-art"><Globe size={300} /></div>
</div>
{#if error}<div class="card error ov-error">Could not load dashboard data: {error}</div>{/if}

<div class="ov-bento">
  <section class="card ov-tile ov-health"><div class="ov-tile-head"><span class="k">evaluation health</span><span class="mut">pass rate</span></div><div class="ov-health-value">{passRate == null ? "—" : `${passRate}%`}</div><div class="mut">pass rate across {fmtCount(overview?.total_runs)} recorded runs</div><div class="ov-meter"><span style={`width:${passRate ?? 0}%`}></span></div><div class="ov-inline"><span>{fmtCount(overview?.scored_runs ?? 0)} scored</span><span>{overview?.avg_aggregate_score != null ? `avg ${overview.avg_aggregate_score.toFixed(3)}` : "awaiting scores"}</span></div></section>

  <section class="card ov-tile ov-kpis"><div class="ov-tile-head"><span class="k">workspace pulse</span><span class="mut">as counts</span></div><div class="ov-kpi-grid"><div><strong>{fmtCount(counts.total)}</strong><span>models</span></div><div><strong>{fmtCount(counts.runnable)}</strong><span>runnable</span></div><div><strong>{fmtCount(activeJobs.length)}</strong><span>active jobs</span></div><div><strong>{fmtCount(overview?.total_runs)}</strong><span>eval runs</span></div></div></section>

  <section class="card ov-tile ov-hardware"><div class="ov-tile-head"><span class="k">hardware</span><span class="badge pass">{env?.gpu_present ? "gpu" : "cpu"}</span></div><div class="ov-hardware-main"><strong>{env?.unified_memory_gb ?? "—"} GB</strong><span>unified memory</span></div><div class="ov-facts"><span>nodes {env?.nodes ?? "—"}</span><span>free {env?.nvme_available_bytes != null ? fmtBytes(env.nvme_available_bytes) : "—"}</span><span class="mono">v{env?.software_version ?? "—"}</span></div></section>

  <section class="card ov-tile ov-models"><div class="ov-tile-head"><span class="k">model readiness</span><a class="tile-link" href="#/models">models/ →</a></div>{#if assets.length}{#each assets.slice(0, 4) as a (a.asset_id)}<a class="ov-model-row" href="#/model/{a.asset_id}"><span class="ov-dot" class:ready={a.runnable}></span><Glyph seed={a.asset_id} size={11} /><span>{a.name}</span><span class="mut">{a.runnable ? "ready" : "setup needed"}</span></a>{/each}{#if assets.length > 4}<a class="show-more" href="#/models">show all {assets.length} models →</a>{/if}{:else}<p class="mut">No models registered yet.</p><a class="show-more" href="#/models/register">register a model →</a>{/if}</section>

  <section class="card ov-tile ov-runs"><div class="ov-tile-head"><span class="k">recent eval runs</span><a class="tile-link" href="#/explorer">explorer/ →</a></div>{#if recentRuns.length}<div class="ov-run-list">{#each recentRuns as run (run.run_id)}{@const result = fmtPassed(run.passed)}<a class="ov-run-row" href="#/explorer/run/{run.run_id}"><span class="ov-run-status {result.cls}"></span><Glyph seed={run.model_id ?? "unknown"} size={11} /><span class="ov-run-main"><strong>{run.model_id ?? "Unknown model"}</strong><span class="mut">{run.task_id} · {when(run.created_at)}</span></span><span class="mono ov-run-score">{fmtScore(run.aggregate_score)}</span><span class="badge {result.cls}">{result.label}</span></a>{/each}</div><a class="show-more ov-show-more" href="#/explorer">show more eval runs →</a>{:else}<div class="ov-empty"><p class="mut">No evaluations have run yet.</p><div class="term"><span class="term-prompt">eval-lab ~ ❯</span> <a href="#/evaluation">run evaluation</a></div></div>{/if}</section>

  <section class="card ov-tile ov-ppl"><div class="ov-tile-head"><span class="k">perplexity</span><a class="tile-link" href="#/benchmark">benchmark/ →</a></div>{#if pplRuns.length}<div class="ov-run-list">{#each pplRuns as r (r.run_id)}<a class="ov-ppl-row" href="#/explorer/run/{r.run_id}"><Glyph seed={r.model_id ?? "unknown"} size={11} /><span class="ov-run-main"><strong>{r.model_id ?? "Unknown model"}</strong><span class="mut">{corpus(r.task_id)} · {when(r.created_at)}</span></span><span class="ov-ppl-val">{fmtScore(r.perplexity)}<small>{typeof r.bits_per_byte === "number" ? `${r.bits_per_byte.toFixed(3)} bits/B` : "ppl"}</small></span></a>{/each}</div><a class="show-more ov-show-more" href="#/benchmark">open the benchmark scorecard →</a>{:else}<div class="ov-empty"><p class="mut">No perplexity runs yet. Lower perplexity means the model predicts held-out text better.</p><div class="term"><span class="term-prompt">eval-lab ~ ❯</span> benchmark --endpoint … --model-name …</div></div>{/if}</section>
</div>
