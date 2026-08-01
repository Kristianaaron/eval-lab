<script>
  export let title = "";
  export let milestone = "";
  export let note = "";
</script>

<h1>{title}</h1>
<div class="card notice">
  <strong>Milestone {milestone}.</strong> {note}
</div>
<div class="card">
  <p class="mut">
    This area is part of a later milestone in the eval-harness GUI build-out and is
    intentionally not implemented yet. Milestone 1 (model assets, inspection,
    action eligibility) is complete; this keeps the navigation surface stable while
    the flow is built.
  </p>
</div>
