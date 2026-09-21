<script>
  import { get, fmtBytes, fmtPassed } from "./lib/api.js";
  import { Activity, ArrowUpRight, Box, Cpu, Gauge, HardDrive, Play } from "@lucide/svelte";

  let overview = $state(null);
  let assets = $state([]);
  let env = $state(null);
  let jobs = $state([]);
  let recentRuns = $state([]);
  let error = $state(null);

  $effect(() => {
    get("/api/overview").then((d) => (overview = d)).catch((e) => (error = String(e)));
    get("/api/models-assets").then((d) => (assets = d)).catch(() => {});
    get("/api/environment").then((d) => (env = d)).catch(() => {});
    get("/api/jobs").then((d) => (jobs = d)).catch(() => {});
    get("/api/runs?limit=5").then((d) => (recentRuns = d)).catch(() => {});
  });

  const counts = $derived.by(() => ({ total: assets.length, runnable: assets.filter((a) => a.runnable).length }));
  const activeJobs = $derived(jobs.filter((j) => ["queued", "running", "pausing", "paused", "resuming"].includes(j.state)));
  const passRate = $derived(overview?.total_runs ? Math.round((overview.passed / overview.total_runs) * 100) : null);
  function when(value) { return String(value ?? "").slice(0, 16).replace("T", " ") || "—"; }
  function score(value) { return typeof value === "number" ? value.toFixed(3) : "—"; }
</script>

<div class="ov-header">
  <div><div class="ov-label">Workspace overview</div><h1>Evaluation dashboard</h1><p class="mut">A quick read on model readiness, hardware capacity, and the latest benchmark evidence.</p></div>
  <a class="btn primary" href="#/evaluation"><Play size={15} /> Run an evaluation</a>
</div>
{#if error}<div class="card error ov-error">Could not load dashboard data: {error}</div>{/if}

<div class="ov-bento">
  <section class="card ov-tile ov-health"><div class="ov-tile-head"><span class="ov-icon green"><Activity size={17} /></span><span class="k">Evaluation health</span></div><div class="ov-health-value">{passRate == null ? "—" : `${passRate}%`}</div><div class="mut">pass rate across {overview?.total_runs ?? "—"} recorded runs</div><div class="ov-meter"><span style={`width:${passRate ?? 0}%`}></span></div><div class="ov-inline"><span>{overview?.scored_runs ?? 0} scored</span><span>{overview?.avg_aggregate_score != null ? `avg ${overview.avg_aggregate_score.toFixed(3)}` : "awaiting scores"}</span></div></section>

  <section class="card ov-tile ov-kpis"><div class="ov-tile-head"><span class="ov-icon blue"><Gauge size={17} /></span><span class="k">Workspace pulse</span></div><div class="ov-kpi-grid"><div><strong>{counts.total}</strong><span>models</span></div><div><strong>{counts.runnable}</strong><span>runnable</span></div><div><strong>{activeJobs.length}</strong><span>active jobs</span></div><div><strong>{overview?.total_runs ?? "—"}</strong><span>eval runs</span></div></div></section>

  <section class="card ov-tile ov-hardware"><div class="ov-tile-head"><span class="ov-icon purple"><Cpu size={17} /></span><span class="k">Hardware</span><span class="badge pass">{env?.gpu_present ? "ready" : "CPU"}</span></div><div class="ov-hardware-main"><strong>{env?.unified_memory_gb ?? "—"} GB</strong><span>unified memory</span></div><div class="ov-facts"><span><Cpu size={13} /> {env?.nodes ?? "—"} node{env?.nodes === 1 ? "" : "s"}</span><span><HardDrive size={13} /> {env?.nvme_available_bytes != null ? fmtBytes(env.nvme_available_bytes) : "—"} free</span><span class="mono">v{env?.software_version ?? "—"}</span></div></section>

  <section class="card ov-tile ov-models"><div class="ov-tile-head"><span class="ov-icon amber"><Box size={17} /></span><span class="k">Model readiness</span><a class="tile-link" href="#/models">Open <ArrowUpRight size={13} /></a></div>{#if assets.length}{#each assets.slice(0, 4) as a (a.asset_id)}<a class="ov-model-row" href="#/model/{a.asset_id}"><span class="ov-dot" class:ready={a.runnable}></span><span>{a.name}</span><span class="mut">{a.runnable ? "ready" : "setup needed"}</span></a>{/each}{#if assets.length > 4}<a class="show-more" href="#/models">Show all {assets.length} models <ArrowUpRight size={13} /></a>{/if}{:else}<p class="mut">No models registered yet.</p><a class="show-more" href="#/models/register">Register a model <ArrowUpRight size={13} /></a>{/if}</section>

  <section class="card ov-tile ov-runs"><div class="ov-tile-head"><span class="ov-icon blue"><Gauge size={17} /></span><span class="k">Recent eval runs</span><a class="tile-link" href="#/explorer">View all <ArrowUpRight size={13} /></a></div>{#if recentRuns.length}<div class="ov-run-list">{#each recentRuns as run (run.run_id)}{@const result = fmtPassed(run.passed)}<a class="ov-run-row" href="#/explorer/run/{run.run_id}"><span class="ov-run-status {result.cls}"></span><span class="ov-run-main"><strong>{run.model_id ?? "Unknown model"}</strong><span class="mut">{run.task_id} · {when(run.created_at)}</span></span><span class="mono ov-run-score">{score(run.aggregate_score)}</span><ArrowUpRight size={13} class="mut" /></a>{/each}</div><a class="show-more ov-show-more" href="#/explorer">Show more eval runs <ArrowUpRight size={13} /></a>{:else}<div class="ov-empty"><p class="mut">No evaluations have run yet.</p><a class="show-more" href="#/evaluation">Run your first evaluation <ArrowUpRight size={13} /></a></div>{/if}</section>
</div>
