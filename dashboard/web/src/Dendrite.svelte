<script>
  // Growth drawing (reference: "HC grown toward 4'115 points"). A dendritic
  // tree is grown by space colonisation toward one attractor per data point:
  //
  //   tip            one per item in `points` (a task / a run); reached tips
  //                  carry an ink burst whose size is the item's value
  //   tip height     the item's value (0 at the baseline, 1 at the top band)
  //   tip column     the item's `group` (clusters left → right in group order)
  //   limb thickness the number of tips a limb carries (its load)
  //   growth         the tree is drawn in growth order over `growS` seconds
  //   nerve pulse    a bright signal runs from the root to one tip every few
  //                  seconds; the tip it reaches is printed in the readout
  //
  // Everything is cream on the ground; no colour. Static under
  // prefers-reduced-motion, paused when the tab is hidden.
  import { onMount, untrack } from "svelte";
  import { growTree, pathTo } from "./lib/dendrite.js";
  import { fmtCount, fmtScore } from "./lib/fmt.js";

  let {
    points = [], // {id, label, value (0..1|null), group, href}
    groups = [], // ordered group keys (columns); derived from points when empty
    groupLabels = {},
    width = 720,
    height = 300,
    seed = "eval-lab",
    growS = 3.2,
    pulseEveryS = 4.5,
    title = "grown toward",
    unit = "1 tip = 1 task · height = score",
    onread = null,
  } = $props();

  const PAD = { l: 34, r: 16, t: 26, b: 34 };
  let canvas = $state(null);
  let hover = $state(null);
  let readout = $state({ text: "", item: null });
  let grown = $state(0);
  let dpr = 1;

  const cols = $derived(groups.length ? groups : [...new Set(points.map((p) => p.group ?? "all"))]);

  // Attractor layout: column by group, height by value, stable jitter by id.
  const layout = $derived.by(() => {
    if (!points.length) return null;
    const innerW = width - PAD.l - PAD.r;
    const innerH = height - PAD.t - PAD.b;
    const colW = innerW / cols.length;
    const byGroup = new Map(cols.map((g) => [g, []]));
    for (const p of points) (byGroup.get(p.group ?? "all") ?? byGroup.get(cols[0])).push(p);
    const targets = [];
    cols.forEach((g, ci) => {
      const items = byGroup.get(g) ?? [];
      items.forEach((p, k) => {
        const x = PAD.l + colW * ci + colW * ((k + 0.5) / Math.max(items.length, 1)) * 0.92 + colW * 0.04;
        const v = typeof p.value === "number" && Number.isFinite(p.value) ? Math.min(1, Math.max(0, p.value)) : null;
        // zero and unscored tips keep a hair of height so the root row stays legible
        const y = PAD.t + innerH * (1 - Math.max(v ?? 0.04, 0.03));
        targets.push({ x, y, id: p.id, label: p.label ?? p.id, value: v, href: p.href, group: g });
      });
    });
    const root = { x: PAD.l + innerW / 2, y: height - PAD.b + 6 };
    const tree = growTree({ seed: `${seed}:${points.length}`, width, height, root, targets, segment: 4, influence: Math.max(70, innerH * 0.45), kill: 4 });
    const maxLoad = Math.max(1, ...tree.nodes.map((n) => n.load));
    const apex = tree.tips.reduce((m, n) => (!m || (n.tip.value ?? -1) > (m.tip.value ?? -1) ? n : m), null);
    return { tree, targets, root, maxLoad, apex, colW, innerH };
  });

  const stats = $derived.by(() => {
    if (!layout) return null;
    const t = layout.tree;
    return { tips: t.tips.length, junctions: t.junctions, length: t.length, steps: t.steps, reached: t.reached, total: t.total };
  });

  function draw(progressNodes, pulse) {
    if (!canvas || !layout) return;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const cream = (a) => `rgba(232,228,216,${a})`;
    const { tree, maxLoad, apex } = layout;
    const nodes = tree.nodes;
    // axes: score baseline + top band, group columns
    ctx.strokeStyle = cream(0.16);
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 3]);
    for (const f of [0, 0.5, 1]) {
      const y = PAD.t + layout.innerH * (1 - f);
      ctx.beginPath();
      ctx.moveTo(PAD.l, y);
      ctx.lineTo(width - PAD.r, y);
      ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.fillStyle = cream(0.45);
    ctx.font = "9px " + getComputedStyle(canvas).fontFamily;
    ctx.textAlign = "right";
    for (const f of [0, 0.5, 1]) ctx.fillText(f.toFixed(1), PAD.l - 6, PAD.t + layout.innerH * (1 - f) + 3);
    ctx.textAlign = "center";
    cols.forEach((g, ci) => {
      const x = PAD.l + layout.colW * (ci + 0.5);
      ctx.fillText(String(groupLabels[g] ?? g), x, height - PAD.b + 22);
      ctx.fillRect(x - 0.5, height - PAD.b + 8, 1, 4);
    });
    // limbs, thickness by load
    ctx.lineCap = "round";
    for (let i = 1; i < Math.min(nodes.length, progressNodes); i++) {
      const n = nodes[i];
      const p = nodes[n.parent];
      const w = 0.6 + 1.9 * Math.sqrt(n.load / maxLoad);
      ctx.strokeStyle = cream(0.35 + 0.55 * Math.sqrt(n.load / maxLoad));
      ctx.lineWidth = w;
      ctx.beginPath();
      ctx.moveTo(p.x, p.y);
      ctx.lineTo(n.x, n.y);
      ctx.stroke();
    }
    // tips: ink bursts sized by value
    for (const n of tree.tips) {
      const idx = nodes.indexOf(n);
      if (idx >= progressNodes) continue;
      const v = n.tip.value;
      const isHover = hover && hover.id === n.tip.id;
      const isRead = readout.item && readout.item.id === n.tip.id;
      const r = v == null ? 1.2 : 1.5 + 4.5 * v;
      ctx.fillStyle = cream(v == null ? 0.25 : 0.55 + 0.45 * v);
      if (v == null) {
        ctx.strokeStyle = cream(0.3);
        ctx.lineWidth = 0.8;
        ctx.beginPath();
        ctx.arc(n.x, n.y, 2.2, 0, Math.PI * 2);
        ctx.stroke();
        continue;
      }
      // spikes: count grows with value (ink splatter)
      const spikes = 4 + Math.round(v * 10);
      ctx.strokeStyle = cream(0.35 + 0.5 * v);
      ctx.lineWidth = 0.7;
      for (let s = 0; s < spikes; s++) {
        const a = (s / spikes) * Math.PI * 2 + (idx % 7) * 0.13;
        const len = r * (1.2 + ((s * 7 + idx) % 5) / 4);
        ctx.beginPath();
        ctx.moveTo(n.x, n.y);
        ctx.lineTo(n.x + Math.cos(a) * len, n.y + Math.sin(a) * len);
        ctx.stroke();
      }
      ctx.beginPath();
      ctx.arc(n.x, n.y, r * 0.55, 0, Math.PI * 2);
      ctx.fill();
      if (isHover || isRead) {
        ctx.strokeStyle = isHover ? "#e8623c" : cream(0.9);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + 4, 0, Math.PI * 2);
        ctx.stroke();
      }
    }
    // nerve pulse: bright segment travelling root → tip
    if (pulse && pulse.path.length > 1) {
      const n = pulse.path.length;
      const head = pulse.t * (n - 1);
      const tail = Math.max(0, head - Math.max(6, n * 0.18));
      ctx.lineCap = "round";
      for (let i = Math.floor(tail) + 1; i <= Math.min(n - 1, Math.ceil(head)); i++) {
        const a = nodes[pulse.path[i - 1]];
        const b = nodes[pulse.path[i]];
        const k = (i - tail) / Math.max(1, head - tail);
        ctx.strokeStyle = `rgba(232,98,60,${0.15 + 0.85 * k})`;
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }
    }
    // callouts: apex and root
    if (apex && nodes.indexOf(apex) < progressNodes) {
      ctx.strokeStyle = cream(0.5);
      ctx.lineWidth = 1;
      ctx.setLineDash([1, 2]);
      ctx.beginPath();
      ctx.moveTo(apex.x, apex.y - 10);
      ctx.lineTo(apex.x, PAD.t - 8);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = cream(0.75);
      ctx.textAlign = apex.x > width / 2 ? "right" : "left";
      ctx.fillText(`apex ${fmtScore(apex.tip.value, 2)} · ${apex.tip.label}`, apex.x + (apex.x > width / 2 ? -6 : 6), PAD.t - 10);
    }
    ctx.textAlign = "left";
    ctx.fillStyle = cream(0.6);
    ctx.fillText(`root carries ${fmtCount(tree.nodes[0].load)}`, layout.root.x + 8, layout.root.y - 2);
  }

  function pickTip(ev) {
    if (!layout) return null;
    const rect = canvas.getBoundingClientRect();
    const x = ((ev.clientX - rect.left) / rect.width) * width;
    const y = ((ev.clientY - rect.top) / rect.height) * height;
    let best = null, bd = 12 * 12;
    for (const n of layout.tree.tips) {
      const d = (n.x - x) ** 2 + (n.y - y) ** 2;
      if (d < bd) { bd = d; best = n; }
    }
    return best;
  }

  onMount(() => {
    dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    let pulse = null;
    let nextPulse = 0;
    let rnd = 0.37;
    const t0 = performance.now();
    const frame = (now) => {
      if (!layout) { raf = requestAnimationFrame(frame); return; }
      const nodes = layout.tree.nodes;
      const el = (now - t0) / 1000;
      const progress = reduce ? 1 : Math.min(1, el / growS);
      grown = progress * growS;
      const shown = Math.ceil(nodes.length * (1 - Math.pow(1 - progress, 2)));
      if (!reduce && progress >= 1) {
        if (!pulse && el >= nextPulse && layout.tree.tips.length) {
          rnd = (rnd * 9301 + 49297) % 233280;
          const tip = layout.tree.tips[Math.floor((rnd / 233280) * layout.tree.tips.length)];
          pulse = { path: pathTo(nodes, nodes.indexOf(tip)), start: el, dur: 1.1, tip };
        }
        if (pulse) {
          pulse.t = Math.min(1, (el - pulse.start) / pulse.dur);
          if (pulse.t >= 1) {
            readout = { text: `${pulse.tip.tip.label} · ${pulse.tip.tip.value == null ? "no run" : fmtScore(pulse.tip.tip.value, 2)}`, item: pulse.tip.tip };
            pulse = null;
            nextPulse = el + pulseEveryS;
          }
        }
      }
      draw(shown, pulse);
      if (reduce && progress >= 1 && !hover) return; // static
      raf = requestAnimationFrame(frame);
    };
    const onVis = () => { cancelAnimationFrame(raf); if (!document.hidden) raf = requestAnimationFrame(frame); };
    raf = requestAnimationFrame(frame);
    document.addEventListener("visibilitychange", onVis);
    return () => { cancelAnimationFrame(raf); document.removeEventListener("visibilitychange", onVis); };
  });

  $effect(() => {
    const r = readout;
    const h = hover;
    untrack(() => typeof onread === "function" && onread(h ? { text: `${h.label} · ${h.value == null ? "no run" : fmtScore(h.value, 2)}`, item: h, hovered: true } : { ...r, hovered: false }));
  });
</script>

<div class="dendrite">
  <div class="dendrite-head">
    <span class="dendrite-title">{title} <b>{fmtCount(points.length)}</b> points</span>
    <span class="mut">{unit}</span>
  </div>
  <div class="dendrite-body">
    <canvas
      bind:this={canvas}
      style={`width:${width}px;height:${height}px`}
      onmousemove={(e) => { const t = pickTip(e); hover = t ? t.tip : null; }}
      onmouseleave={() => (hover = null)}
      onclick={(e) => { const t = pickTip(e); if (t?.tip?.href) window.location.hash = t.tip.href.replace(/^#/, ""); }}
      role="img"
      aria-label={`${title} ${points.length} points`}
    ></canvas>
    {#if stats}
      <div class="dendrite-twin">
        <div class="card-strip"><span>numeric twin</span><span class="mut">as counts</span></div>
        <div class="kv">
          <div><span>tips</span><b>{fmtCount(stats.tips)}</b></div>
          <div><span>junctions</span><b>{fmtCount(stats.junctions)}</b></div>
          <div><span>length</span><b>{fmtCount(Math.round(stats.length / 3.78))} mm</b></div>
          <div><span>grown</span><b>{grown.toFixed(1)} s</b></div>
          <div><span>reached</span><b>{fmtCount(stats.reached)} / {fmtCount(stats.total)}</b></div>
        </div>
        <div class="dendrite-read" class:accent={!!hover}><span class="reticle-readout-dot"></span><span>{hover ? `${hover.label} · ${hover.value == null ? "no run" : fmtScore(hover.value, 2)}` : readout.text || "nerve idle"}</span></div>
      </div>
    {/if}
  </div>
</div>
