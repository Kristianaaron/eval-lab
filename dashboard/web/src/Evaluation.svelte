<script>
  import RunDetail from "./RunDetail.svelte";
  import Runs from "./Runs.svelte";

  export let runId = null;
</script>

<h1>Evaluation</h1>
<div class="card notice">
  <strong>Milestone 2.</strong> The guided evaluation launch wizard (suite selection,
  run configuration summary, task progress, telemetry, result page) is next. Existing
  run records below remain viewable.
</div>

{#if runId}
  <RunDetail runId={runId} />
{:else}
  <Runs />
{/if}
