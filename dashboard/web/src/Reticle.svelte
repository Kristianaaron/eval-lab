<script>
  // Reticle gauge (reference image: concentric HUD rings). Every ring encodes
  // something from the data it is given — nothing is drawn only for effect:
  //
  //   outer tick band   `ticks` fine marks; the first `tickFill` fraction is lit
  //                     (e.g. pass rate), long marks every quarter
  //   segment ring      one arc segment per item in `segments` (tasks / runs),
  //                     filled with the heat palette by its score; hollow = no run
  //   primary arc       `value` (0…1) with an end dot; tweened in on mount
  //   inner rings       one thin arc per entry in `rings` (e.g. benchmark groups)
  //   crosshair labels  `captions` at N / E / S / W
  //   sweep cursor      a slow radial cursor that reads the segments one by one:
  //                     the segment under it brightens and its label + score are
  //                     printed in the readout line
  //   centre dot        pulses only while `active` (jobs running)
  //
  // Motion honours prefers-reduced-motion (static final state) and pauses when
  // the tab is hidden.
  import { onMount, untrack } from "svelte";
  import { fmtScore, heat } from "./lib/fmt.js";

  let {
    value = null,
    label = "",
    sub = "",
    size = 96,
    accent = false,
    ticks = 96,
    tickFill = null,
    segments = [],
    rings = [],
    captions = null,
    active = false,
    readout = true,
    sweepPeriodS = 28,
    onscan = null,
  } = $props();

  const TAU = Math.PI * 2;
  const c = $derived(size / 2);
  const large = $derived(size >= 140);
  const rTick = $derived(c - (large ? 14 : 4));
  const rSeg = $derived(rTick - (large ? 12 : 9));
  const segW = $derived(large ? 5 : 3.5);
  const rArc = $derived(rSeg - (large ? 12 : 9));
  const ringGap = $derived(large ? 7 : 4.5);

  const v = $derived(clamp(value));
  const tf = $derived(tickFill == null ? v : clamp(tickFill));

  // progress 0…1 for the mount tween; sweep angle in radians.
  let progress = $state(1);
  let sweep = $state(-Math.PI / 2);
  let hover = $state(null);

  function clamp(x) {
    return typeof x === "number" && Number.isFinite(x) ? Math.min(1, Math.max(0, x)) : null;
  }
  function pt(r, a) {
    return [c + Math.cos(a) * r, c + Math.sin(a) * r];
  }
  function arcPath(r, a0, a1) {
    if (a1 - a0 <= 0) return "";
    const span = Math.min(a1 - a0, TAU * 0.9999);
    const [x0, y0] = pt(r, a0);
    const [x1, y1] = pt(r, a0 + span);
    return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 ${span > Math.PI ? 1 : 0} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
  }

  const tickMarks = $derived(
    Array.from({ length: ticks }, (_, i) => {
      const a = (i / ticks) * TAU - Math.PI / 2;
      const q = i % (ticks / 4) === 0;
      const m = i % (ticks / 12) === 0;
      const len = q ? (large ? 7 : 5) : m ? (large ? 4.5 : 3.5) : large ? 2.5 : 2;
      const [x1, y1] = pt(rTick - len, a);
      const [x2, y2] = pt(rTick, a);
      return { x1, y1, x2, y2, q, m, lit: tf != null && i / ticks < tf * progress };
    })
  );

  const segArcs = $derived.by(() => {
    const n = segments.length;
    if (!n) return [];
    const gap = n > 60 ? 0.008 : n > 24 ? 0.014 : 0.03;
    const slice = TAU / n;
    return segments.map((s, i) => {
      const a0 = -Math.PI / 2 + i * slice + gap / 2;
      const a1 = a0 + Math.max(slice - gap, 0.004);
      const sv = clamp(s.value);
      const shown = i / n < progress;
      const mid = (a0 + a1) / 2;
      return { i, s, sv, d: arcPath(rSeg, a0, a1), colour: sv == null ? null : heat(sv), shown, mid, a0, a1 };
    });
  });

  const primaryArc = $derived(v == null ? "" : arcPath(rArc, -Math.PI / 2, -Math.PI / 2 + v * progress * TAU));
  const primaryEnd = $derived(v == null ? null : pt(rArc, -Math.PI / 2 + v * progress * TAU));

  const ringArcs = $derived(
    rings.map((r, i) => {
      const rr = rArc - ringGap * (i + 1);
      const rv = clamp(r.value);
      return { r: rr, label: r.label, value: rv, d: rv == null ? "" : arcPath(rr, -Math.PI / 2, -Math.PI / 2 + rv * progress * TAU), track: arcPath(rr, -Math.PI / 2, -Math.PI / 2 + TAU * 0.9999) };
    })
  );

  // The segment currently under the sweep cursor (or the hovered one).
  const scanned = $derived.by(() => {
    if (hover != null) return segArcs[hover] ?? null;
    if (!segArcs.length) return null;
    let a = sweep;
    while (a < -Math.PI / 2) a += TAU;
    while (a >= TAU - Math.PI / 2) a -= TAU;
    return segArcs.find((s) => a >= s.a0 - 0.002 && a < s.a1 + 0.002) ?? null;
  });

  const sweepLine = $derived.by(() => {
    const [x1, y1] = pt(large ? rArc + 2 : rSeg - segW - 1, sweep);
    const [x2, y2] = pt(rTick, sweep);
    return { x1, y1, x2, y2 };
  });
  const sweepTrail = $derived(arcPath(rTick + 1, sweep - 0.35, sweep));

  const caps = $derived(captions && captions.length === 4 ? captions : null);

  onMount(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      progress = 1;
      return;
    }
    progress = 0;
    const t0 = performance.now();
    const period = Math.max(4, sweepPeriodS) * 1000;
    let raf = 0;
    const frame = (t) => {
      const el = t - t0;
      if (el < 1400) {
        const x = el / 1400;
        progress = 1 - Math.pow(1 - x, 3);
      } else {
        progress = 1;
      }
      sweep = -Math.PI / 2 + ((el % period) / period) * TAU;
      raf = requestAnimationFrame(frame);
    };
    const onVis = () => {
      if (document.hidden) cancelAnimationFrame(raf);
      else raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVis);
    };
  });

  const readoutText = $derived.by(() => {
    if (!scanned) return segments.length ? "scanning" : "";
    const val = scanned.sv == null ? "no run" : fmtScore(scanned.sv, 2);
    return `${scanned.s.label ?? scanned.s.id ?? ""} · ${val}`;
  });

  // Let a parent print the readout in its own layout (small gauges).
  $effect(() => {
    const text = readoutText;
    const hovered = hover != null;
    untrack(() => {
      if (typeof onscan === "function") onscan({ text, item: scanned?.s ?? null, hovered });
    });
  });
</script>

<div class="reticle-wrap" style={`width:${size}px`}>
  <svg class="reticle" class:accent class:large width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label} ${sub}`.trim()}>
    <!-- outer tick band -->
    {#each tickMarks as t, i (i)}
      <line x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2} class:q={t.q} class:m={t.m} class:lit={t.lit} />
    {/each}
    <!-- crosshair stubs at N / E / S / W -->
    {#each [0, 1, 2, 3] as k (k)}
      {@const a = -Math.PI / 2 + (k * TAU) / 4}
      {@const [x1, y1] = pt(rSeg + segW / 2 + 1.5, a)}
      {@const [x2, y2] = pt(rTick - (large ? 8 : 6), a)}
      <line class="cross" x1={x1} y1={y1} x2={x2} y2={y2} />
    {/each}
    <!-- segment ring: one arc per task / run -->
    {#if segArcs.length}
      <circle cx={c} cy={c} r={rSeg} class="seg-track" />
      {#each segArcs as s (s.i)}
        <path
          d={s.d}
          class="seg"
          class:hollow={s.colour == null}
          class:scan={scanned && scanned.i === s.i}
          style={`stroke:${s.colour ?? "transparent"};stroke-width:${segW};opacity:${s.shown ? 1 : 0}`}
          role={s.s.href ? "link" : undefined}
          onmouseenter={() => (hover = s.i)}
          onmouseleave={() => (hover = null)}
          onclick={() => s.s.href && (window.location.hash = s.s.href.replace(/^#/, ""))}
        >
          <title>{s.s.label ?? s.s.id} · {s.sv == null ? "no run" : fmtScore(s.sv)}</title>
        </path>
      {/each}
    {/if}
    <!-- primary value arc -->
    <circle cx={c} cy={c} r={rArc} class="arc-track" />
    {#if primaryArc}<path d={primaryArc} class="arc" />{/if}
    {#if primaryEnd}<circle cx={primaryEnd[0]} cy={primaryEnd[1]} r={large ? 2.2 : 1.6} class="arc-end" />{/if}
    <!-- inner rings: one per group -->
    {#each ringArcs as r, i (i)}
      <path d={r.track} class="ring-track" />
      {#if r.d}<path d={r.d} class="ring" />{/if}
    {/each}
    <!-- sweep cursor -->
    {#if segArcs.length}
      <path d={sweepTrail} class="sweep-trail" />
      <line x1={sweepLine.x1} y1={sweepLine.y1} x2={sweepLine.x2} y2={sweepLine.y2} class="sweep" />
    {/if}
    <!-- centre -->
    <circle cx={c} cy={c} r={large ? 2 : 1.4} class="core" class:active />
    {#if active}<circle cx={c} cy={c} r={large ? 2 : 1.4} class="core-pulse" />{/if}
    <text x={c} y={c - (large ? 6 : sub ? 0 : 3.5) + (large ? 0 : 0)} text-anchor="middle" class="val" style={large ? "font-size:22px" : ""}>{label}</text>
    {#if sub}<text x={c} y={c + (large ? 12 : 11)} text-anchor="middle" class="sub">{sub}</text>{/if}
    <!-- captions at the cardinal points -->
    {#if caps && large}
      <text x={c} y={c - rTick - 5} text-anchor="middle" class="cap">{caps[0]}</text>
      <text x={c} y={c + rTick + 11} text-anchor="middle" class="cap">{caps[2]}</text>
    {/if}
  </svg>
  {#if readout && segments.length}
    <div class="reticle-readout" class:accent={hover != null}><span class="reticle-readout-dot"></span>{readoutText}</div>
  {/if}
  {#if large && (rings.length || caps)}
    <div class="reticle-legend">
      {#if caps}<span>{caps[1]}</span><span>{caps[3]}</span>{/if}
      {#each ringArcs as r, i (i)}<span title="inner ring {i + 1}"><i style={`opacity:${1 - i * 0.18}`}></i>{r.label} <b>{r.value == null ? "—" : fmtScore(r.value, 2)}</b></span>{/each}
    </div>
  {/if}
</div>
