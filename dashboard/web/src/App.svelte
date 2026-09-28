<script>
  import { onMount } from "svelte";
  import Overview from "./Overview.svelte";
  import Explorer from "./Explorer.svelte";
  import Models from "./Models.svelte";
  import ModelDetail from "./ModelDetail.svelte";
  import RunDetail from "./RunDetail.svelte";
  import RegisterModel from "./RegisterModel.svelte";
  import Evaluation from "./Evaluation.svelte";
  import Benchmark from "./Benchmark.svelte";
  import AtlasLab from "./AtlasLab.svelte";
  import AtlasRunDetail from "./AtlasRunDetail.svelte";
  import Experiments from "./Experiments.svelte";
  import Comparisons from "./Comparisons.svelte";
  import Jobs from "./Jobs.svelte";
  import StatusBar from "./StatusBar.svelte";
  import Globe from "./Globe.svelte";

  function parse(hash) {
    const h = (hash || "").replace(/^#/, "");
    if (h.startsWith("/explorer/run/")) return { name: "explorer", runId: h.slice("/explorer/run/".length) };
    if (h === "/explorer") return { name: "explorer" };
    if (h === "/models") return { name: "models" };
    if (h === "/models/register") return { name: "register" };
    if (h.startsWith("/model/")) return { name: "model", id: h.slice("/model/".length) };
    if (h.startsWith("/evaluation/run/")) return { name: "evaluation", runId: h.slice("/evaluation/run/".length) };
    if (h.startsWith("/evaluation/job/")) return { name: "evaluation", jobId: h.slice("/evaluation/job/".length) };
    if (h === "/evaluation") return { name: "evaluation" };
    if (h === "/benchmark" || h.startsWith("/benchmark/")) {
      return { name: "benchmark", modelId: decodeURIComponent(h.slice("/benchmark/".length)) || null };
    }
    if (h === "/cebu") return { name: "cebu" };
    if (h.startsWith("/cebu/run/")) return { name: "cebu-run", runId: h.slice("/cebu/run/".length) };
    if (h === "/experiments") return { name: "experiments" };
    if (h === "/comparisons") return { name: "comparisons" };
    if (h === "/jobs") return { name: "jobs" };
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

  // Entries are written like paths, in the spirit of a project spine.
  const areas = [
    { key: "overview", label: "overview/", href: "#/" },
    { key: "models", label: "models/", href: "#/models" },
    { key: "explorer", label: "explorer/", href: "#/explorer" },
    { key: "evaluation", label: "evaluation/", href: "#/evaluation" },
    { key: "benchmark", label: "benchmark/", href: "#/benchmark" },
    { key: "cebu", label: "cebu/", href: "#/cebu" },
    { key: "experiments", label: "experiments/", href: "#/experiments" },
    { key: "comparisons", label: "comparisons/", href: "#/comparisons" },
    { key: "jobs", label: "jobs/", href: "#/jobs" },
  ];
</script>

<div class="layout">
  <nav class="side">
    <a class="brand" href="#/">
      <Globe size={30} points={160} alpha={1} />
      <span>eval-lab<span class="brand-sub">~ evaluation console</span></span>
    </a>
    {#each areas as a (a.key)}
      <a
        class="nav"
        class:active={route.name === a.key || (a.key === "models" && (route.name === "model" || route.name === "register")) || (a.key === "cebu" && route.name === "cebu-run")}
        href={a.href}
      >
        <span>{a.label}</span>
      </a>
    {/each}
    <a class="nav extern" href="http://{location.hostname}:8011/" target="_blank">
      <span>cebu-profiler ↗</span>
    </a>
  </nav>

  <main class="main">
    {#if route.name === "overview"}
      <Overview />
    {:else if route.name === "explorer" && route.runId}
      <RunDetail runId={route.runId} />
    {:else if route.name === "explorer"}
      <Explorer />
    {:else if route.name === "models"}
      <Models />
    {:else if route.name === "register"}
      <RegisterModel />
    {:else if route.name === "model"}
      <ModelDetail assetId={route.id} />
    {:else if route.name === "evaluation"}
      <Evaluation runId={route.runId} jobId={route.jobId} />
    {:else if route.name === "benchmark"}
      <Benchmark modelId={route.modelId} />
    {:else if route.name === "cebu"}
      <AtlasLab />
    {:else if route.name === "cebu-run"}
      <AtlasRunDetail runId={route.runId} />
    {:else if route.name === "experiments"}
      <Experiments />
    {:else if route.name === "comparisons"}
      <Comparisons />
    {:else if route.name === "jobs"}
      <Jobs />
    {:else}
      <Overview />
    {/if}
  </main>
</div>
<StatusBar />
