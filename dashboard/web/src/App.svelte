<script>
  import { onMount } from "svelte";
  import Overview from "./Overview.svelte";
  import Explorer from "./Explorer.svelte";
  import Models from "./Models.svelte";
  import ModelDetail from "./ModelDetail.svelte";
  import RunDetail from "./RunDetail.svelte";
  import RegisterModel from "./RegisterModel.svelte";
  import Evaluation from "./Evaluation.svelte";
  import AtlasLab from "./AtlasLab.svelte";
  import Experiments from "./Experiments.svelte";
  import Comparisons from "./Comparisons.svelte";
  import Jobs from "./Jobs.svelte";
  import {
    LayoutDashboard,
    Boxes,
    Gauge,
    Sparkles,
    FlaskConical,
    Scale,
    ListChecks,
    FolderSearch,
  } from "@lucide/svelte";

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
    if (h === "/atlas") return { name: "atlas" };
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

  const areas = [
    { key: "overview", label: "Overview", href: "#/", icon: LayoutDashboard },
    { key: "models", label: "Models", href: "#/models", icon: Boxes },
    { key: "explorer", label: "Explorer", href: "#/explorer", icon: FolderSearch },
    { key: "evaluation", label: "Evaluation", href: "#/evaluation", icon: Gauge },
    { key: "atlas", label: "Atlas Lab", href: "#/atlas", icon: Sparkles },
    { key: "experiments", label: "Experiments", href: "#/experiments", icon: FlaskConical },
    { key: "comparisons", label: "Comparisons", href: "#/comparisons", icon: Scale },
    { key: "jobs", label: "Jobs", href: "#/jobs", icon: ListChecks },
  ];
</script>

<div class="layout">
  <nav class="side">
    <a class="brand" href="#/">eval-lab</a>
    {#each areas as a (a.key)}
      <a
        class="nav"
        class:active={route.name === a.key || (a.key === "models" && (route.name === "model" || route.name === "register"))}
        href={a.href}
      >
        <svelte:component this={a.icon} size={16} />
        <span>{a.label}</span>
      </a>
    {/each}
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
    {:else if route.name === "atlas"}
      <AtlasLab />
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
