<script>
  import { onMount } from "svelte";
  import Overview from "./Overview.svelte";
  import Models from "./Models.svelte";
  import ModelDetail from "./ModelDetail.svelte";
  import RegisterModel from "./RegisterModel.svelte";
  import Evaluation from "./Evaluation.svelte";
  import AtlasLab from "./AtlasLab.svelte";
  import Experiments from "./Experiments.svelte";
  import Comparisons from "./Comparisons.svelte";

  function parse(hash) {
    const h = (hash || "").replace(/^#/, "");
    if (h === "/models") return { name: "models" };
    if (h === "/models/register") return { name: "register" };
    if (h.startsWith("/model/")) return { name: "model", id: h.slice("/model/".length) };
    if (h === "/evaluation") return { name: "evaluation" };
    if (h === "/evaluation/run" || h.startsWith("/evaluation/run/"))
      return { name: "run", id: h.slice("/evaluation/run/".length) };
    if (h === "/atlas") return { name: "atlas" };
    if (h === "/experiments") return { name: "experiments" };
    if (h === "/comparisons") return { name: "comparisons" };
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
    { key: "overview", label: "Overview", href: "#/" },
    { key: "models", label: "Models", href: "#/models" },
    { key: "evaluation", label: "Evaluation", href: "#/evaluation" },
    { key: "atlas", label: "Atlas Lab", href: "#/atlas" },
    { key: "experiments", label: "Experiments", href: "#/experiments" },
    { key: "comparisons", label: "Comparisons", href: "#/comparisons" },
  ];
</script>

<nav class="bar">
  <a class="brand" href="#/">eval-lab</a>
  {#each areas as a (a.key)}
    <a
      class="nav"
      class:active={route.name === a.key || (a.key === "models" && (route.name === "model" || route.name === "register"))}
      href={a.href}
    >
      {a.label}
    </a>
  {/each}
</nav>

<main>
  {#if route.name === "overview"}
    <Overview />
  {:else if route.name === "models"}
    <Models />
  {:else if route.name === "register"}
    <RegisterModel />
  {:else if route.name === "model"}
    <ModelDetail assetId={route.id} />
  {:else if route.name === "evaluation"}
    <Evaluation runId={route.name === "run" ? route.id : null} />
  {:else if route.name === "atlas"}
    <AtlasLab />
  {:else if route.name === "experiments"}
    <Experiments />
  {:else}
    <Comparisons />
  {/if}
</main>
