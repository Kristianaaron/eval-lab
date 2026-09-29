<script>
  // Taxonomy tree: a real hierarchy (suite → group → domain → task) drawn as
  // veins. Nothing here is placed for effect:
  //
  //   topology        the hierarchy itself; leaves are tasks in suite order
  //   limb width      number of tasks the limb carries
  //   limb opacity    mean score of the tasks beneath it (faint = no runs yet)
  //   tip burst       task score: spoke count and size grow with the score;
  //                   an open ring means the task has not run
  //   accent pulse    only while a job is evaluating a task: it travels from
  //                   the root to that task, and the task's ring beats
  //   hover           traces the root→task path and prints each level's mean
  //
  // Limbs grow in once on load (depth order). Reduced motion: static.
  import { vein, veinTail, burst, hashStr } from "./lib/organic.js";
  import { leafSummary } from "./lib/tree.js";
  import { fmtCount, fmtScore } from "./lib/fmt.js";

  let { root = null, width = 880, height = 280, legend = true, readoutIdle = "hover a tip to trace its path" } = $props();

  const PAD = { l: 18, r: 18, t: 58, b: 34 };
  let hover = $state(null);

  function mean(xs) {
    const v = xs.filter((x) => typeof x === "number");
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
  }

  const L = $derived.by(() => {
    if (!root) return null;
    const leaves = [];
    const nodes = [];
    let maxDepth = 1;
    const walk = (n, depth, parent) => {
      const node = { ...n, depth, parent, kids: [] };
      nodes.push(node);
      if (parent) parent.kids.push(node);
      if (!n.children?.length) {
        leaves.push(node);
        maxDepth = Math.max(maxDepth, depth);
      } else {
        for (const c of n.children) walk(c, depth + 1, node);
      }
      return node;
    };
    const r = walk(root, 0, null);
    const top = (n) => { while (n.parent && n.parent.parent) n = n.parent; return n; };
    // leaf slots, with a gap wherever the top-level limb changes
    const slots = [];
    let s = 0;
    let prev = null;
    for (const lf of leaves) {
      const t = top(lf);
      if (prev && t !== prev) s += 1.4;
      slots.push(s);
      s += 1;
      prev = t;
    }
    const span = Math.max(s - 1, 1);
    const innerW = width - PAD.l - PAD.r;
    const yAt = (d) => height - PAD.b - (height - PAD.b - PAD.t) * (d / maxDepth);
    leaves.forEach((lf, i) => {
      lf.x = PAD.l + (leaves.length === 1 ? innerW / 2 : innerW * (slots[i] / span));
      lf.y = PAD.t;
      lf.count = 1;
      lf.mean = typeof lf.value === "number" ? lf.value : null;
    });
    const post = (n) => {
      if (!n.kids.length) return;
      n.kids.forEach(post);
      n.x = n.kids.reduce((a, k) => a + k.x, 0) / n.kids.length;
      n.y = yAt(n.depth);
      n.count = n.kids.reduce((a, k) => a + k.count, 0);
      n.leafValues = n.kids.flatMap((k) => (k.kids.length ? k.leafValues : [k.value]));
      n.mean = mean(n.leafValues);
    };
    post(r);
    r.y = height - PAD.b + 4;
    const limbs = nodes
      .filter((n) => n.parent)
      .map((n) => ({
        id: n.id,
        d: vein(n.parent.x, n.parent.y, n.x, n.y),
        w: 0.7 + 3.4 * Math.sqrt(n.count / r.count),
        a: n.mean == null ? 0.12 : 0.22 + 0.78 * n.mean,
        depth: n.depth,
        node: n,
      }));
    const running = leaves.find((lf) => lf.status === "running") ?? null;
    // Dimension lines above each top-level group, spanning exactly its tips.
    const under = (n) => (n.kids.length ? n.kids.flatMap(under) : [n]);
    const spans = r.kids.map((g) => {
      const xs = under(g).map((lf) => lf.x);
      return { id: g.id, label: g.label, mean: g.mean, count: g.count, x0: Math.min(...xs), x1: Math.max(...xs) };
    });
    return { r, leaves, nodes, limbs, running, spans, maxDepth, spacing: innerW / Math.max(span, 1) };
  });

  function pathD(leaf) {
    const chain = [];
    for (let n = leaf; n; n = n.parent) chain.unshift(n);
    let d = `M${chain[0].x},${chain[0].y}`;
    for (let i = 1; i < chain.length; i++) d += veinTail(chain[i - 1].x, chain[i - 1].y, chain[i].x, chain[i].y);
    return d;
  }

  function chainText(leaf) {
    const chain = [];
    for (let n = leaf.parent; n; n = n.parent) chain.unshift(n);
    const levels = chain.map((n) => `${n.label} ${n.mean == null ? "—" : fmtScore(n.mean, 2)}`).join(" / ");
    return `${levels} / ${leaf.label} · ${leafSummary(leaf)}`;
  }

  const pulseD = $derived(L?.running ? pathD(L.running) : null);
  const hoverD = $derived(hover ? pathD(hover) : null);
  const readout = $derived(
    hover ? chainText(hover) : L?.running ? `evaluating ${L.running.taskId ?? L.running.label} · ${chainText(L.running).split(" / ").slice(0, -1).join(" / ")}` : readoutIdle
  );

  function open(leaf) {
    if (leaf?.href) window.location.hash = leaf.href.replace(/^#/, "");
  }
</script>

{#if L}
  <div class="tx">
    <svg class="tx-svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet" role="img" aria-label={`${L.r.label}: ${L.r.count} tasks`}>
      <!-- limbs: sheath + core so each reads as a vein -->
      {#each L.limbs as lb (lb.id)}
        <path d={lb.d} pathLength="1" class="tx-limb tx-sheath" style={`--d:${lb.depth};stroke-width:${(lb.w * 2.6).toFixed(2)};stroke-opacity:${(lb.a * 0.18).toFixed(3)}`} />
        <path d={lb.d} pathLength="1" class="tx-limb" style={`--d:${lb.depth};stroke-width:${lb.w.toFixed(2)};stroke-opacity:${lb.a.toFixed(3)}`} />
      {/each}
      {#if hoverD}<path d={hoverD} class="tx-trace" />{/if}
      {#if pulseD}<path d={pulseD} pathLength="1" class="tx-pulse" />{/if}

      <!-- group dimension lines (top level); sub-limb labels at their fork when there is room -->
      {#each L.spans as g (g.id)}
        {@const y = PAD.t - 16}
        <path d={`M${g.x0 - 4},${y + 4} L${g.x0 - 4},${y} L${g.x1 + 4},${y} L${g.x1 + 4},${y + 4}`} class="tx-dim" />
        {@const val = g.mean == null ? "—" : fmtScore(g.mean, 2)}
        {@const narrow = (g.label.length + val.length + String(g.count).length + 4) * 5.9 > g.x1 - g.x0 + 20}
        {#if narrow}
          <text x={(g.x0 + g.x1) / 2} y={y - 18} text-anchor="middle" class="tx-lbl">{g.label}</text>
          <text x={(g.x0 + g.x1) / 2} y={y - 6} text-anchor="middle" class="tx-lbl"><tspan class="v">{val}</tspan><tspan class="c">{"\u00a0·\u00a0"}{g.count}</tspan></text>
        {:else}
          <text x={(g.x0 + g.x1) / 2} y={y - 6} text-anchor="middle" class="tx-lbl">{g.label}{"\u00a0"}<tspan class="v">{val}</tspan><tspan class="c">{"\u00a0·\u00a0"}{g.count}</tspan></text>
        {/if}
      {/each}
      {#each L.nodes.filter((n) => n.kids.length && n.depth > 1) as n (n.id)}
        {#if n.count * L.spacing > 64}
          {@const flip = n.x > width * 0.82}
          <text x={flip ? n.x - 6 : n.x + 6} y={n.y + 3} text-anchor={flip ? "end" : "start"} class="tx-lbl sub">{n.label}{"\u00a0"}<tspan class="v">{n.mean == null ? "—" : fmtScore(n.mean, 2)}</tspan></text>
        {/if}
      {/each}
      <circle cx={L.r.x} cy={L.r.y} r="2.2" class="tx-root" />
      <text x={L.r.x} y={L.r.y + 16} text-anchor="middle" class="tx-lbl">{L.r.label}{"\u00a0"}<tspan class="v">{L.r.mean == null ? "—" : fmtScore(L.r.mean, 2)}</tspan><tspan class="c">{"\u00a0·\u00a0"}{fmtCount(L.r.count)} tasks</tspan></text>

      <!-- tips -->
      {#each L.leaves as lf, i (lf.id)}
        {@const v = lf.value}
        {@const seed = hashStr(lf.id)}
        <g class="tx-leaf" style={`--d:${L.maxDepth}`} role="link" tabindex="-1" onmouseenter={() => (hover = lf)} onmouseleave={() => (hover = null)} onclick={() => open(lf)}>
          <circle cx={lf.x} cy={lf.y} r="9" class="tx-hit" />
          {#if lf.status === "pending" || (v == null && lf.status !== "running")}
            <circle cx={lf.x} cy={lf.y} r="2.2" class="tx-open" />
          {:else if v != null}
            <path d={burst(lf.x, lf.y, 1.6 + 4.6 * v, 4 + Math.round(v * 10), seed)} class="tx-burst" style={`stroke-opacity:${(0.35 + 0.65 * v).toFixed(3)}`} />
            <circle cx={lf.x} cy={lf.y} r={(0.9 + 1.8 * v).toFixed(2)} class="tx-core" style={`fill-opacity:${(0.45 + 0.55 * v).toFixed(3)}`} />
          {/if}
          {#if lf.status === "running"}<circle cx={lf.x} cy={lf.y} r="4" class="tx-run" />{/if}
          {#if hover === lf}<circle cx={lf.x} cy={lf.y} r="7" class="tx-hl" />{/if}
        </g>
      {/each}
    </svg>
    <div class="tx-foot">
      <div class="tx-read" class:on={!!hover || !!L.running}><span class="reticle-readout-dot"></span><span>{readout}</span></div>
      {#if legend}<div class="tx-legend">width = tasks carried · opacity = mean score · tip = task score · ○ = not run</div>{/if}
    </div>
  </div>
{/if}
