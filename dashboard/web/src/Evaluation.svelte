<script>
  import { onMount, onDestroy } from "svelte";
  import { get, post } from "./lib/api.js";
  import { ExternalLink, Info, Minus } from "@lucide/svelte";
  import RunDetail from "./RunDetail.svelte";
  import EvalJobDetail from "./EvalJobDetail.svelte";

  let { runId = null, jobId = null } = $props();

  let cfg = $state(null);
  let loading = $state(false);
  let error = $state(null);

  let model = $state("");
  let harness = $state("direct");
  let repeat = $state(1);
  let cold = $state(false);
  let domainSearch = $state("");
  let showAllDomains = $state(false);
  let infoDomain = $state(null);
  let jobDetailId = $state(null);

  // right-panel rows: one per selected domain, tracking its own eval job
  let rows = $state([]); // {domain, jobId, suiteRef, state, score}
  let running = $state(false);
  let planHidden = $state(false);

  const DOMAIN_META = {
    agentic: { label: "Agentic workflows", group: "Agent & tools", description: "Multi-step tasks that require planning, action, and verification." },
    tool_calling: { label: "Tool calling", group: "Agent & tools", description: "Function and tool selection, arguments, and grounded results." },
    planning: { label: "Planning", group: "Agent & tools", description: "Break a goal into actions and carry the plan through to completion." },
    coding: { label: "Coding", group: "Build & design", description: "Code generation, transformation, and execution." },
    code_generation: { label: "Code generation", group: "Build & design", description: "Generate working code from natural-language requirements." },
    debugging: { label: "Debugging", group: "Build & design", description: "Find root causes, fix failures, and verify the repair." },
    software_engineering: { label: "Software engineering", group: "Build & design", description: "Repository-level implementation and engineering workflows." },
    frontend: { label: "Frontend", group: "Build & design", description: "HTML, CSS, accessibility, and responsive interface work." },
    visual_design: { label: "Visual design", group: "Build & design", description: "Layout and interaction design quality." },
    formal_reasoning: { label: "Formal reasoning", group: "Reasoning & knowledge", description: "Symbolic reasoning, proofs, and structured deductions." },
    general_reasoning: { label: "General reasoning", group: "Reasoning & knowledge", description: "Everyday reasoning and multi-step problem solving." },
    mathematics: { label: "Mathematics", group: "Reasoning & knowledge", description: "Numerical and mathematical problem solving." },
    knowledge_work: { label: "Knowledge work", group: "Reasoning & knowledge", description: "Fact retrieval and practical knowledge tasks." },
    research: { label: "Research", group: "Reasoning & knowledge", description: "Evidence gathering and grounded analysis." },
    factuality: { label: "Factuality", group: "Reasoning & knowledge", description: "Answer accurately against known facts and source material." },
    instruction_following: { label: "Instruction following", group: "Reasoning & knowledge", description: "Follow exact constraints, formats, and output requirements." },
    long_context: { label: "Long context", group: "Systems & spatial", description: "Find and reason over information in long documents." },
    retrieval: { label: "Retrieval", group: "Systems & spatial", description: "Locate precise evidence across documents and logs." },
    hardware: { label: "Hardware", group: "Systems & spatial", description: "Runtime and host performance probes." },
    spatial_3d: { label: "Spatial 3D", group: "Systems & spatial", description: "Spatial transformations and 3D reasoning." },
    voxel: { label: "Voxel", group: "Systems & spatial", description: "Discrete 3D construction and transformation tasks." },
    structured_output: { label: "Structured output", group: "Output & quality", description: "Produce valid JSON and machine-readable artifacts." },
    health: { label: "Health", group: "Vertical domains", description: "Health-oriented reasoning and safe triage responses." },
    finance: { label: "Finance", group: "Vertical domains", description: "Financial arithmetic, analysis, and quantitative reasoning." },
    legal: { label: "Legal", group: "Vertical domains", description: "Extract and reason over legal language and obligations." },
    science: { label: "Science", group: "Vertical domains", description: "Scientific concepts, evidence, and unit reasoning." },
    education: { label: "Education", group: "Vertical domains", description: "Clear explanations and learner-oriented instruction." },
    multilingual: { label: "Multilingual", group: "Vertical domains", description: "Translation and cross-language instruction following." },
    safety: { label: "Safety", group: "Vertical domains", description: "Refusal boundaries and safe alternative behavior." },
  };

  const RECOMMENDED_DOMAINS = [
    "coding",
    "agentic",
    "tool_calling",
    "mathematics",
    "code_generation",
    "retrieval",
    "health",
    "finance",
  ];

  const TERMINAL = new Set([
    "completed",
    "completed_with_warnings",
    "failed",
    "failed_recoverable",
    "cancelled",
  ]);

  async function loadCfg() {
    loading = true;
    error = null;
    try {
      cfg = await get("/api/eval-config");
      if (!model && cfg.models.length) model = cfg.models[0].model_id;
      if (!harness && cfg.harnesses.length) harness = cfg.harnesses[0].harness_id;
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  function hasDomain(d) {
    return rows.some((r) => r.domain === d);
  }

  function toggleDomain(d) {
    if (hasDomain(d)) {
      rows = rows.filter((r) => r.domain !== d);
    } else {
      planHidden = false;
      rows = [...rows, { domain: d, jobId: null, suiteRef: null, state: "pending", score: null }];
    }
  }

  function removeDomain(d) {
    rows = rows.filter((r) => r.domain !== d);
  }

  function filteredDomains() {
    const query = domainSearch.trim().toLowerCase();
    return (cfg?.domains ?? []).filter((d) => {
      if (!query) return true;
      const meta = DOMAIN_META[d] ?? {};
      return [d, meta.label, meta.description, meta.group]
        .filter(Boolean)
        .some((value) => value.toLowerCase().includes(query));
    });
  }

  function domainLabel(domain) {
    return DOMAIN_META[domain]?.label ?? domain.replaceAll("_", " ");
  }

  function domainDescription(domain) {
    return DOMAIN_META[domain]?.description ?? "Benchmark tasks in this domain.";
  }

  function domainTeaching(domain) {
    const group = domainGroup(domain);
    const lessons = {
      agentic: "The model must break a goal into steps, take actions, inspect what happened, and recover when needed.",
      tool_calling: "The model must choose the right tool, construct valid arguments, use the returned observation, and stop when the task is complete.",
      planning: "The model is evaluated on whether its plan is actionable, ordered correctly, and carried through rather than merely described.",
      coding: "The model produces or changes code, so the benchmark checks both the requested behavior and whether the result actually works.",
      code_generation: "The model turns a natural-language requirement into executable code with the requested behavior and format.",
      debugging: "The model must identify the real cause of a failure, make a targeted fix, and verify that the fix works.",
      software_engineering: "The model works across files or repository context, balancing implementation quality with scope control.",
      frontend: "The model is tested on structure, CSS, accessibility, and responsive behavior—not just visual plausibility.",
      visual_design: "The model must translate a design intention into coherent layout, hierarchy, and interaction details.",
      mathematics: "The model must apply mathematical rules accurately and return an answer that can be checked against the expected result.",
      formal_reasoning: "The model is tested on whether each conclusion follows from the stated rules, premises, or constraints.",
      general_reasoning: "The model must connect multiple pieces of information and reach a defensible conclusion rather than rely on a keyword match.",
      knowledge_work: "The model retrieves and applies practical facts while following the requested output format.",
      research: "The model must locate relevant evidence, ground its answer in that evidence, and avoid inventing unsupported details.",
      factuality: "The model is rewarded for accurate claims and penalized for confident answers that are not supported by the task context.",
      instruction_following: "The benchmark checks whether the model follows exact constraints such as format, length, content, and ordering.",
      long_context: "The model must find the right information inside a large context and use it without losing the task constraints.",
      retrieval: "The model is tested on locating precise facts in documents, logs, or other supplied evidence.",
      hardware: "The preset measures runtime or host behavior, helping separate model quality from the machine used to serve it.",
      spatial_3d: "The model must reason about positions, transformations, and relationships in three dimensions.",
      voxel: "The model performs discrete 3D construction or transformations and is checked against an exact spatial result.",
      structured_output: "The model must return machine-readable output such as valid JSON or a correctly formed artifact.",
      health: "The model is tested on safe health-oriented reasoning, including recognizing urgency without overclaiming a diagnosis.",
      finance: "The model applies quantitative reasoning to financial-style questions while respecting precision and output constraints.",
      legal: "The model extracts obligations, deadlines, and conditions from legal language without adding facts that are not present.",
      science: "The model applies scientific concepts, units, and evidence-based reasoning to arrive at a checkable answer.",
      education: "The model must explain a concept accurately at the learner’s level and make the explanation easy to follow.",
      multilingual: "The model is tested on meaning preservation across languages, including following the requested translation format.",
      safety: "The model must recognize a harmful request, refuse the unsafe part, and redirect toward a safe and useful alternative.",
    };
    return lessons[domain] ?? `This preset contains ${group.toLowerCase()} tasks that measure how reliably the model completes the requested work.`;
  }

  function domainSuccess(domain) {
    const group = domainGroup(domain);
    if (group === "Agent & tools") return "A strong result uses only necessary actions, valid tool inputs, and grounded observations.";
    if (group === "Build & design") return "A strong result is functional, within scope, and verified against the requested behavior.";
    if (group === "Reasoning & knowledge") return "A strong result is correct, well-grounded, and follows the requested constraints.";
    if (group === "Systems & spatial") return "A strong result preserves the important information while producing the exact requested transformation.";
    if (group === "Output & quality") return "A strong result is valid, predictable, and safe for downstream programs to consume.";
    if (group === "Vertical domains") return "A strong result applies the domain concept carefully, states only what the evidence supports, and follows the requested format.";
    return "A strong result completes the task accurately and follows its constraints.";
  }

  function domainGroup(domain) {
    return DOMAIN_META[domain]?.group ?? "Other";
  }

  function groupedDomains() {
    const groups = new Map();
    for (const domain of filteredDomains()) {
      const group = domainGroup(domain);
      if (!groups.has(group)) groups.set(group, []);
      groups.get(group).push(domain);
    }
    return [...groups.entries()];
  }

  function recommendedDomains() {
    const available = new Set(cfg?.domains ?? []);
    const curated = RECOMMENDED_DOMAINS.filter((domain) => available.has(domain));
    return domainSearch.trim() ? filteredDomains().slice(0, 8) : curated;
  }

  function openAllDomains() {
    showAllDomains = true;
    setTimeout(() => document.querySelector('[aria-label="Search all evaluation domains"]')?.focus(), 0);
  }

  function closeAllDomains() {
    showAllDomains = false;
  }

  function openDomainInfo(domain) {
    infoDomain = domain;
  }

  function closeDomainInfo() {
    infoDomain = null;
  }

  function openJobDetail(jobId) {
    jobDetailId = jobId;
  }

  function closeJobDetail() {
    jobDetailId = null;
  }

  function handleKeydown(event) {
    if (event.key !== "Escape") return;
    if (infoDomain) closeDomainInfo();
    else if (jobDetailId) closeJobDetail();
    else if (showAllDomains) closeAllDomains();
  }

  function selectAllDomains() {
    const selected = new Set(rows.map((r) => r.domain));
    const additions = filteredDomains()
      .filter((domain) => !selected.has(domain))
      .map((domain) => ({ domain, jobId: null, suiteRef: null, state: "pending", score: null }));
    if (additions.length) planHidden = false;
    rows = [...rows, ...additions];
  }

  function clearDomains() {
    rows = rows.filter((r) => r.state !== "pending");
  }

  function selectedModel() {
    return (cfg?.models ?? []).find((m) => m.model_id === model);
  }

  function selectedHarness() {
    return (cfg?.harnesses ?? []).find((h) => h.harness_id === harness);
  }

  function completedCount() {
    return rows.filter((r) => r.state === "completed").length;
  }

  function activeCount() {
    return rows.filter((r) => r.state === "evaluating" || r.state === "queued").length;
  }

  async function launch() {
    error = null;
    if (!rows.length) {
      error = "Pick at least one domain first.";
      return;
    }
    running = true;
    try {
      // one eval job per selected domain so each row has a real lifecycle
      for (const row of rows) {
        if (row.state !== "pending") continue; // don't duplicate already-launched rows
        const { suite_ref } = await post("/api/suites", {
          name: `Eval ${row.domain}`,
          domains: [row.domain],
        });
        row.suiteRef = suite_ref;
        row.state = "queued";
        const job = await post("/api/eval-jobs", {
          model_asset_id: model,
          model_id: model,
          harness_id: harness,
          suite_ref,
          repeat_count: Number(repeat),
          cold_start: cold,
          runs_root: "runs",
        });
        row.jobId = job.job_id;
        row.state = "evaluating";
      }
      pollOnce();
    } catch (e) {
      error = String(e);
    } finally {
      running = false;
    }
  }

  function jobStage(state) {
    if (TERMINAL.has(state)) return "terminal";
    return "active";
  }

  function rowFromJob(row, job) {
    if (jobStage(job.state) === "terminal") {
      const done = job.state === "completed" || job.state === "completed_with_warnings";
      row.state = done ? "completed" : job.state === "cancelled" ? "cancelled" : "failed";
      if (done) row.score = null; // score fetched right after
      return;
    }
    row.state = "evaluating";
    row.stage = job.current_stage ?? null;
    row.progress = job.progress ?? null;
  }

  async function pollOnce() {
    const active = rows.filter(
      (r) => r.jobId && !TERMINAL.has(r.state) && r.state !== "failed" && r.state !== "cancelled"
    );
    for (const row of active) {
      try {
        const job = await get(`/api/eval-jobs/${encodeURIComponent(row.jobId)}`);
        rowFromJob(row, job);
        if (row.state === "completed") {
          row.score = await fetchScore(job.result?.run_ids ?? []);
        }
      } catch {
        /* transient poll failure — retried next tick */
      }
    }
  }

  async function fetchScore(runIds) {
    if (!runIds || !runIds.length) return null;
    const scored = [];
    for (const rid of runIds) {
      try {
        const d = await get(`/api/runs/${encodeURIComponent(rid)}`);
        const a = d?.manifest?.aggregate_score;
        if (typeof a === "number" && Number.isFinite(a)) scored.push(a);
      } catch {
        /* skip a transient run fetch failure */
      }
    }
    if (!scored.length) return null;
    return scored.reduce((a, b) => a + b, 0) / scored.length;
  }

  function statusMeta(row) {
    if (row.state === "completed") return { label: "done", cls: "pass" };
    if (row.state === "failed") return { label: "failed", cls: "fail" };
    if (row.state === "cancelled") return { label: "cancelled", cls: "type" };
    if (row.state === "evaluating") return { label: "evaluating", cls: "type" };
    if (row.state === "queued") return { label: "queued", cls: "type" };
    return { label: "pending", cls: "type" };
  }

  let timer = null;
  function startPolling() {
    if (timer) return;
    timer = setInterval(pollOnce, 1500);
  }
  function stopPolling() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  $effect(() => {
    const hasActive = rows.some((r) => r.state === "evaluating" || r.state === "queued");
    if (hasActive) startPolling();
    else stopPolling();
  });

  onMount(() => {
    loadCfg();
  });
  onDestroy(stopPolling);
</script>

<svelte:window onkeydown={handleKeydown} />

<h1>Evaluation</h1>

{#if runId}
  <RunDetail runId={runId} />
{:else if jobId}
  <EvalJobDetail jobId={jobId} />
{:else}
  <p class="mut eval-intro">Choose a model, define the evaluation scope, review the plan, then run one tracked evaluation session.</p>

  {#if error}
    <div class="card error">{error}</div>
  {/if}

  {#if loading}
    <div class="card">Loading evaluation configuration…</div>
  {:else if cfg}
    <section class="card eval-toolbar">
      <div class="eval-toolbar-heading">
        <div>
          <div class="k">Run setup</div>
          <strong>{selectedModel()?.name || "Choose a model"}</strong>
          <span class="mut">{selectedHarness()?.name || "Choose a harness"}</span>
        </div>
        <div class="eval-toolbar-actions">
          <a class="eval-history-link" href="#/explorer">Benchmark history ↗</a>
          <span class="eval-readiness {selectedModel()?.runnable ? 'ready' : ''}">
            {selectedModel()?.runnable ? "ready to run" : "check model readiness"}
          </span>
        </div>
      </div>
      <div class="eval-toolbar-fields">
        <label>Model<select bind:value={model}>{#each cfg.models as m (m.model_id)}<option value={m.model_id}>{m.name} ({m.model_id})</option>{/each}</select></label>
        <label>Harness<select bind:value={harness}>{#each cfg.harnesses as h (h.harness_id)}<option value={h.harness_id}>{h.name}</option>{/each}</select></label>
        <label class="repeat-field">Repeats<input type="number" min="1" bind:value={repeat} /></label>
        <label class="cold-field"><input type="checkbox" bind:checked={cold} /> Cold start</label>
      </div>
    </section>

    <div class="eval-workspace">
      <section class="card eval-domain-picker">
        <div class="eval-section-head">
          <div><h2>Choose evaluation domains</h2><p class="mut">Start with a recommendation or browse the full benchmark catalog.</p></div>
          <span class="eval-selection-count">{rows.length} selected</span>
        </div>
        <div class="eval-domain-tools">
          <input aria-label="Search evaluation domains" placeholder="Search domains, capabilities, or tasks…" bind:value={domainSearch} onfocus={openAllDomains} />
          <button class="btn small" type="button" onclick={openAllDomains}>See all domains</button>
        </div>
        <div class="eval-domain-search-meta">
          <span class="mut">{domainSearch.trim() ? `${filteredDomains().length} matches` : "Recommended for a first run"}</span>
          {#if domainSearch}<button class="link-button" type="button" onclick={() => (domainSearch = "")}>Clear search</button>{/if}
        </div>
        <div class="eval-domain-recommended">
          {#each recommendedDomains() as d (d)}
            <button type="button" class="chip" class:on={hasDomain(d)} title={domainDescription(d)} aria-label={`${domainLabel(d)}: ${domainDescription(d)}`} aria-pressed={hasDomain(d)} onclick={() => toggleDomain(d)}>
              {domainLabel(d)}{hasDomain(d) ? " ✓" : ""}
            </button>
          {:else}
            <p class="mut">No domains match “{domainSearch}”. Open all domains to browse the full catalog.</p>
          {/each}
        </div>
      </section>

      {#if showAllDomains}
        <div class="eval-domain-modal-backdrop" role="presentation" onclick={(event) => event.target === event.currentTarget && closeAllDomains()}>
          <div class="eval-domain-modal" role="dialog" aria-modal="true" aria-labelledby="all-domains-title">
            <div class="eval-section-head">
              <div><h2 id="all-domains-title">All evaluation domains</h2><p class="mut">Select one or more domains to add to the plan.</p></div>
              <button class="eval-plan-hide" type="button" title="Close domain catalog" aria-label="Close domain catalog" onclick={closeAllDomains}>×</button>
            </div>
            <div class="eval-domain-tools">
              <input aria-label="Search all evaluation domains" placeholder="Search domains, capabilities, or tasks…" bind:value={domainSearch} />
              <button class="btn small" type="button" onclick={selectAllDomains}>Select visible</button>
              <button class="btn small" type="button" onclick={clearDomains} disabled={!rows.some((r) => r.state === "pending")}>Clear pending</button>
            </div>
            <div class="eval-domain-search-meta">
              <span class="mut">{filteredDomains().length} domain{filteredDomains().length === 1 ? "" : "s"}</span>
              {#if domainSearch}<button class="link-button" type="button" onclick={() => (domainSearch = "")}>Clear search</button>{/if}
            </div>
            <div class="eval-domain-groups">
              {#each groupedDomains() as [group, domains] (group)}
                <div class="eval-domain-group">
                  <div class="k">{group}</div>
                  <div class="chips">
                    {#each domains as d (d)}
                      <button type="button" class="chip" class:on={hasDomain(d)} title={domainDescription(d)} aria-label={`${domainLabel(d)}: ${domainDescription(d)}`} aria-pressed={hasDomain(d)} onclick={() => toggleDomain(d)}>
                        {domainLabel(d)}{hasDomain(d) ? " ✓" : ""}
                      </button>
                    {/each}
                  </div>
                </div>
              {:else}
                <p class="mut">No domains match “{domainSearch}”.</p>
              {/each}
            </div>
          </div>
        </div>
      {/if}

      {#if rows.length > 0 && planHidden}
        <button class="eval-plan-reopen" type="button" onclick={() => (planHidden = false)}>View plan · {rows.length}</button>
      {:else}
      <section class="card eval-plan" aria-live="polite">
        <div class="eval-section-head"><div><h2>Evaluation plan</h2><p class="mut">One session, with a tracked job per domain.</p></div><div class="eval-plan-head-actions"><span class="eval-plan-total">{rows.length}</span><button class="eval-plan-hide" type="button" title="Hide evaluation plan" aria-label="Hide evaluation plan" onclick={() => (planHidden = true)}>×</button></div></div>
        {#if !rows.length}
          <div class="eval-plan-empty"><p>No domain added</p><span class="mut">Choose a recommended domain or browse all domains above.</span></div>
        {:else}
          <div class="eval-rows">
            <div class="eval-row eval-row-labels" aria-hidden="true">
              <span>Domain</span><span>Progress</span><span>Score</span><span>Status</span><span>Info</span><span></span>
            </div>
            {#each rows as row (row.domain)}
              <div class="eval-row">
                <span class="eval-row-domain" title={domainDescription(row.domain)}>
                  {domainLabel(row.domain)}
                  {#if row.jobId && TERMINAL.has(row.state)}<button class="eval-launch" type="button" title="Open benchmark result" aria-label="Open benchmark result for {domainLabel(row.domain)}" onclick={() => openJobDetail(row.jobId)}><ExternalLink size={13} /></button>{/if}
                </span>
                {#if row.state === "evaluating" && row.progress?.total}
                  <span class="eval-row-progress">{row.progress.done ?? 0}/{row.progress.total}</span>
                {:else}
                  <span class="eval-row-progress">—</span>
                {/if}
                <span class="eval-score">{row.state === "completed" ? (row.score == null ? "—" : row.score.toFixed(3)) : "—"}</span>
                <span class="eval-row-status badge {statusMeta(row).cls}">{statusMeta(row).label}</span>
                <button class="eval-info" type="button" title="About {domainLabel(row.domain)}" aria-label="About {domainLabel(row.domain)}" onclick={() => openDomainInfo(row.domain)}><Info size={13} /></button>
                {#if row.state === "pending"}<button class="eval-remove" title="Remove {row.domain}" aria-label="Remove {row.domain}" onclick={() => removeDomain(row.domain)}><Minus size={12} /></button>{:else}<span></span>{/if}
              </div>
            {/each}
          </div>
        {/if}
        <div class="eval-plan-footer">
          {#if rows.length}<span class="mut">{completedCount()} complete{activeCount() ? ` · ${activeCount()} active` : ""}</span>{/if}
          <button class="btn primary" onclick={launch} disabled={running || !rows.length}>{running ? "Launching…" : `Run evaluation${rows.length ? ` · ${rows.length} domain${rows.length === 1 ? "" : "s"}` : ""}`}</button>
        </div>
      </section>
      {/if}
    </div>

    {#if jobDetailId}
      <div class="eval-job-modal-backdrop" role="presentation" onclick={(event) => event.target === event.currentTarget && closeJobDetail()}>
        <div class="eval-job-modal" role="dialog" aria-modal="true" aria-labelledby="job-detail-title">
          <div class="eval-job-modal-head">
            <h2 id="job-detail-title">Benchmark result</h2>
            <button class="eval-plan-hide" type="button" title="Close benchmark result" aria-label="Close benchmark result" onclick={closeJobDetail}>×</button>
          </div>
          <EvalJobDetail jobId={jobDetailId} embedded={true} />
        </div>
      </div>
    {/if}

    {#if infoDomain}
      <div class="eval-domain-info-backdrop" role="presentation" onclick={(event) => event.target === event.currentTarget && closeDomainInfo()}>
        <div class="eval-domain-info" role="dialog" aria-modal="true" aria-labelledby="domain-info-title">
          <div class="eval-section-head">
            <div><div class="k">Domain explainer</div><h2 id="domain-info-title">{domainLabel(infoDomain)}</h2></div>
            <button class="eval-plan-hide" type="button" title="Close domain explainer" aria-label="Close domain explainer" onclick={closeDomainInfo}>×</button>
          </div>
          <p class="eval-domain-info-lead">{domainDescription(infoDomain)}</p>
          <div class="eval-domain-info-section"><span class="k">What this evaluates</span><p>{domainTeaching(infoDomain)}</p></div>
          <div class="eval-domain-info-section"><span class="k">What a strong result looks like</span><p>{domainSuccess(infoDomain)}</p></div>
          <div class="eval-domain-info-meta"><span class="k">Category</span><strong>{domainGroup(infoDomain)}</strong></div>
          <div class="eval-domain-info-meta"><span class="k">Benchmark ID</span><code>{infoDomain}</code></div>
        </div>
      </div>
    {/if}
  {:else}
    <div class="card"><p class="mut">Unable to load configuration.</p><button class="btn" onclick={loadCfg}>Retry</button></div>
  {/if}
{/if}
