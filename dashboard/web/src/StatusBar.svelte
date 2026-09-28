<script>
  // Fixed bottom status bar (reference image 3): uppercase labels with values
  // and a tiny bar sparkline of the latest run scores.
  import { onMount } from "svelte";
  import { get } from "./lib/api.js";
  import { fmtCount, fmtPct } from "./lib/fmt.js";

  let overview = $state(null);
  let jobs = $state([]);
  let recent = $state([]);

  async function refresh() {
    get("/api/overview").then((d) => (overview = d)).catch(() => {});
    get("/api/jobs").then((d) => (jobs = d)).catch(() => {});
    get("/api/runs?limit=32").then((d) => (recent = d)).catch(() => {});
  }
  onMount(() => {
    refresh();
    const t = setInterval(refresh, 30000);
    return () => clearInterval(t);
  });

  const active = $derived(jobs.filter((j) => ["queued", "running", "pausing", "paused", "resuming"].includes(j.state)).length);
  const passRate = $derived(overview?.total_runs ? overview.passed / overview.total_runs : null);
  const bars = $derived([...recent].reverse().map((r) => (typeof r.aggregate_score === "number" ? r.aggregate_score : 0)));
  const today = new Date().toISOString().slice(5, 10);
</script>

<footer class="statusbar" aria-label="Workspace status">
  <span class="sb-cell sb-brand"><b>eval-lab</b><span>↑↓ nav · ↵ open · : cmd</span></span>
  <span class="sb-cell"><b>runs</b><span>{fmtCount(overview?.total_runs)}</span></span>
  <span class="sb-cell"><b>pass</b><span>{fmtPct(passRate)}</span></span>
  <span class="sb-cell"><b>models</b><span>{fmtCount(overview?.models?.length)}</span></span>
  <span class="sb-cell"><b>tasks</b><span>{fmtCount(overview?.tasks?.length)}</span></span>
  <span class="sb-cell"><b>jobs</b><span class:accent={active > 0}>{active ? `${active} active` : "○ idle"}</span></span>
  <span class="sb-cell sb-spark"><b>last {bars.length} runs</b><span class="spark" aria-hidden="true">{#each bars as b, i (i)}<i style={`height:${Math.max(1, Math.round(b * 10))}px`}></i>{/each}</span></span>
  <span class="sb-cell sb-date"><span>→ {today}</span></span>
</footer>
