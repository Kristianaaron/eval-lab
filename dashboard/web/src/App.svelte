<script>
  import { onMount } from "svelte";
  import Overview from "./Overview.svelte";
  import Runs from "./Runs.svelte";
  import RunDetail from "./RunDetail.svelte";

  function parse(hash) {
    const h = (hash || "").replace(/^#/, "");
    if (h.startsWith("/run/")) return { name: "run", id: h.slice(5) };
    if (h === "/runs") return { name: "runs" };
    return { name: "overview" };
  }

  let route = $state(parse(window.location.hash));

  function onHash() {
    route = parse(window.location.hash);
  }

  onMount(() => {
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  });

  function nav(cls, target) {
    if (route.name === target) return cls + " active";
    return cls;
  }
</script>

<nav class="bar">
  <a class="brand" href="#/">eval-lab</a>
  <a class="nav {route.name === 'overview' ? 'active' : ''}" href="#/">Overview</a>
  <a class="nav {route.name === 'runs' ? 'active' : ''}" href="#/runs">Runs</a>
</nav>

<main>
  {#if route.name === "overview"}
    <Overview />
  {:else if route.name === "runs"}
    <Runs />
  {:else}
    <RunDetail runId={route.id} />
  {/if}
</main>
