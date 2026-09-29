<script>
  // Live evaluation nerve: the suite of an evaluation job as a taxonomy.
  // Finished tasks show their score, the task under evaluation carries the
  // pulse, queued tasks are open rings. With no jobId it follows the active
  // evaluation job, else the most recent one. Polls only while a job runs.
  import { onDestroy, onMount } from "svelte";
  import { get } from "./lib/api.js";
  import { byDomain } from "./lib/tree.js";
  import { when } from "./lib/fmt.js";
  import Taxonomy from "./Taxonomy.svelte";

  let { jobId = null, width = 900, height = 250, compact = false } = $props();

  const ACTIVE = ["queued", "running", "pausing", "paused", "resuming"];
  let tree = $state(null);
  let empty = $state(false);
  let timer = null;

  async function pick() {
    if (jobId) return jobId;
    const jobs = await get("/api/eval-jobs");
    if (!jobs.length) return null;
    const active = jobs.find((j) => ACTIVE.includes(j.state));
    if (active) return active.job_id;
    return [...jobs].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))[0].job_id;
  }

  async function refresh() {
    try {
      const id = await pick();
      if (!id) {
        empty = true;
        tree = null;
        return;
      }
      tree = await get(`/api/eval-jobs/${encodeURIComponent(id)}/tree`);
      empty = false;
    } catch {
      /* transient */
    }
  }

  onMount(() => {
    refresh();
    // Poll quickly while something runs, slowly otherwise (to notice new jobs).
    let fast = null;
    const tick = async () => {
      await refresh();
      clearTimeout(timer);
      timer = setTimeout(tick, tree?.active ? 1500 : 10000);
    };
    timer = setTimeout(tick, 1500);
    return () => clearTimeout(fast);
  });
  onDestroy(() => clearTimeout(timer));

  const root = $derived(
    tree ? { id: "suite", label: tree.suite_name.replace(/^Benchmark — /, "").replace(/^Eval /, ""), children: byDomain(tree.tasks) } : null
  );
</script>

{#if tree && root}
  <div class="jt">
    {#if !compact}
      <div class="jt-meta">
        <span><b>{tree.model_id}</b></span>
        <span class:live={tree.active}>{tree.active ? "evaluating" : tree.state}</span>
        <span>{tree.done}/{tree.total ?? tree.tasks.length} tasks</span>
        <span>{when(tree.created_at)}</span>
        {#if !jobId}<a href="#/evaluation/job/{tree.job_id}">job {tree.job_id} →</a>{/if}
      </div>
    {/if}
    <Taxonomy {root} {width} {height} readoutIdle={tree.active ? "waiting for the next task" : "hover a tip to trace its path"} />
  </div>
{:else if empty}
  <div class="term"><span class="term-prompt">eval-lab ~ ❯</span> no evaluation jobs yet · <a href="#/evaluation">run one</a> and its suite appears here as it is evaluated</div>
{/if}
