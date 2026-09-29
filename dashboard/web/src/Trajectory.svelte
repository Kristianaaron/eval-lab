<script>
  // Agent trajectory: one agent run read from its trace, drawn as a nerve.
  //
  //   trunk          the model's turns in order (x = step, not wall time)
  //   trunk width    context the model saw at that turn (prompt tokens);
  //                  uniform when the backend does not report tokens
  //   branch         one per tool call, leaving the turn that issued it
  //   up / down      read-only tools (file_read, list_files) go up; tools
  //                  with side effects (shell, file_write) go down
  //   branch length  tool duration, log scale
  //   tip            ink burst = call succeeded; open accent ring = failed
  //   final node     the oracle result: burst size = aggregate score
  //
  // Motion: the run replays once in step order (the signal travels the trunk
  // and grows each branch as its call happens); "replay" runs it again.
  import { onDestroy, untrack } from "svelte";
  import { sprout, burst, hashStr } from "./lib/organic.js";
  import { fmtCount, fmtScore } from "./lib/fmt.js";

  let { events = [], result = null, width = 900, height = 250 } = $props();

  const READ_ONLY = new Set(["file_read", "list_files"]);
  const PAD = { l: 26, r: 120, t: 18, b: 30 };
  // Whole replay lasts at most ~4.5 s however long the run was.
  const stepS = $derived(L ? Math.min(0.32, 4.5 / Math.max(L.items.length, 1)) : 0.32);

  let hover = $state(null);
  let playKey = $state(0);
  let playhead = $state(-1);
  let timer = null;

  function argHead(tool, args) {
    if (!args) return "";
    const raw = tool === "shell" ? args.command : args.path ?? (tool === "list_files" ? "." : JSON.stringify(args));
    const s = String(raw ?? "").replace(/\s+/g, " ");
    return s.length > 64 ? s.slice(0, 63) + "…" : s;
  }

  const parsed = $derived.by(() => {
    const turns = [];
    let cur = null;
    let prevT = null;
    let end = null;
    for (const e of events) {
      const t = Number(e.time_monotonic_ns ?? 0);
      const p = e.payload ?? {};
      if (e.event_type === "agent_turn_start") {
        cur = { turn: p.turn ?? turns.length, tools: [], tokens: null, finish: null };
        turns.push(cur);
      } else if (e.event_type === "model_completion" && cur) {
        cur.tokens = typeof p.prompt_tokens === "number" ? p.prompt_tokens : null;
        cur.finish = p.finish_reason ?? null;
      } else if (e.event_type === "tool_result" && cur) {
        cur.tools.push({ tool: p.tool, args: p.arguments, ok: !!p.ok, exit: p.exit_code, error: p.error, out: p.output_head ?? "", ms: prevT != null ? Math.max(0, (t - prevT) / 1e6) : 0 });
      } else if (e.event_type === "run_completion") {
        end = p;
      }
      prevT = t;
    }
    return { turns, end };
  });

  const L = $derived.by(() => {
    const { turns, end } = parsed;
    if (!turns.length) return null;
    const units = turns.reduce((a, t) => a + 1 + t.tools.length, 0) + 1;
    const innerW = width - PAD.l - PAD.r;
    const x = (u) => PAD.l + (innerW * u) / Math.max(units - 1, 1);
    const mid = PAD.t + (height - PAD.t - PAD.b) / 2;
    const reach = (height - PAD.t - PAD.b) / 2 - 10;
    const maxMs = Math.max(1, ...turns.flatMap((t) => t.tools.map((c) => c.ms)));
    const maxTok = Math.max(0, ...turns.map((t) => t.tokens ?? 0));
    const items = [];
    const trunk = [];
    const branches = [];
    let u = 0;
    let prevX = x(0);
    turns.forEach((t, ti) => {
      const tx = x(u);
      const w = maxTok > 0 && t.tokens != null ? 0.9 + 3.6 * Math.sqrt(t.tokens / maxTok) : 1.6;
      const idx = items.length;
      items.push({ kind: "turn", i: idx, t, x: tx, y: mid, label: `t${t.turn} · model · ${t.finish ?? "—"} · ${t.tokens == null ? "tokens n/a" : `${fmtCount(t.tokens)} ctx tokens`}` });
      if (ti > 0) trunk.push({ x0: prevX, x1: tx, w: trunk.length ? trunk[trunk.length - 1].wNext : w, wNext: w, i: idx });
      else trunk.push({ x0: tx, x1: tx, w, wNext: w, i: idx });
      trunk[trunk.length - 1].wNext = w;
      t.tools.forEach((c, k) => {
        const bx = x(u + 1 + k);
        const up = READ_ONLY.has(c.tool);
        const len = 14 + (reach - 14) * (Math.log1p(c.ms) / Math.log1p(maxMs));
        const by = up ? mid - len : mid + len;
        const bi = items.length;
        const item = {
          kind: "tool", i: bi, c, up, x: bx, y: by,
          d: sprout(tx + (bx - tx) * 0.25, mid, bx, by),
          label: `${c.tool} · ${argHead(c.tool, c.args)} · ${c.ok ? "ok" : `exit ${c.exit ?? "?"}${c.error ? ` · ${c.error}` : ""}`} · ${c.ms < 1000 ? `${Math.round(c.ms)} ms` : `${(c.ms / 1000).toFixed(1)} s`}`,
          out: String(c.out ?? "").split("\n").find((l) => l.trim()) ?? "",
        };
        items.push(item);
        branches.push(item);
      });
      prevX = tx;
      u += 1 + t.tools.length;
    });
    const fx = x(units - 1);
    const agg = typeof result?.aggregate === "number" ? result.aggregate : null;
    const fi = items.length;
    const status = end?.status ?? result?.agent_status ?? result?.status ?? "completed";
    items.push({ kind: "final", i: fi, x: fx, y: mid, agg, passed: !!result?.passed, status, label: `final · ${status} · score ${agg == null ? "—" : fmtScore(agg, 2)} · ${result?.passed ? "pass" : "fail"}` });
    trunk.push({ x0: prevX, x1: fx, w: trunk[trunk.length - 1].wNext, wNext: 1, i: fi });
    const calls = branches.length;
    const failed = branches.filter((b) => !b.c.ok).length;
    return { items, trunk, branches, mid, units, calls, failed, turns: turns.length, fx, spacing: innerW / Math.max(units - 1, 1) };
  });

  function trunkD(s) {
    return `M${s.x0.toFixed(1)},${L.mid} L${s.x1.toFixed(1)},${L.mid}`;
  }

  function play() {
    clearInterval(timer);
    playhead = -1;
    playKey += 1;
    if (!L) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce) { playhead = L.items.length - 1; return; }
    timer = setInterval(() => {
      playhead += 1;
      if (playhead >= L.items.length - 1) clearInterval(timer);
    }, stepS * 1000);
  }

  // Replay once whenever a new trace arrives (play() writes state it also reads).
  $effect(() => {
    if (L) untrack(() => play());
  });
  onDestroy(() => clearInterval(timer));

  const current = $derived(hover ?? (L && playhead >= 0 ? L.items[Math.min(playhead, L.items.length - 1)] : null));
</script>

{#if L}
  <div class="tj">
    <div class="tj-head">
      <span>{L.turns} turn{L.turns === 1 ? "" : "s"} · {L.calls} tool call{L.calls === 1 ? "" : "s"} · <b class:bad={L.failed > 0}>{L.failed} failed</b></span>
      <button class="link-button" type="button" onclick={play}>replay</button>
    </div>
    {#key playKey}
      <svg class="tj-svg" style={`--step:${stepS}s`} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet" role="img" aria-label={`agent trajectory: ${L.turns} turns, ${L.calls} tool calls`}>
        <text x={PAD.l - 6} y={PAD.t + 8} class="tj-axis" text-anchor="start">reads ↑</text>
        <text x={PAD.l - 6} y={height - PAD.b - 2} class="tj-axis" text-anchor="start">writes / commands ↓</text>
        {#each L.trunk as s (s.i)}
          <path d={trunkD(s)} pathLength="1" class="tj-trunk" style={`--k:${s.i};stroke-width:${((s.w + s.wNext) / 2).toFixed(2)}`} />
        {/each}
        {#each L.branches as b (b.i)}
          <g class="tj-branch" style={`--k:${b.i}`} onmouseenter={() => (hover = b)} onmouseleave={() => (hover = null)} role="img" aria-label={b.label}>
            <path d={b.d} pathLength="1" class="tj-limb" />
            <path d={b.d} class="tj-hit" />
            {#if b.c.ok}
              <path d={burst(b.x, b.y, 3, 7, hashStr(b.label))} class="tj-burst" />
              <circle cx={b.x} cy={b.y} r="1.5" class="tj-core" />
            {:else}
              <circle cx={b.x} cy={b.y} r="3.4" class="tj-fail" />
            {/if}
            {#if L.spacing > 26}<text x={b.x} y={b.up ? b.y - 8 : b.y + 14} text-anchor="middle" class="tj-tip">{b.c.tool}</text>{/if}
            {#if current === b}<circle cx={b.x} cy={b.y} r="7" class="tj-hl" />{/if}
          </g>
        {/each}
        {#each L.items.filter((it) => it.kind === "turn") as t (t.i)}
          <g class="tj-node" style={`--k:${t.i}`}>
            <circle cx={t.x} cy={L.mid} r="2.4" class="tj-turn" class:on={current === t} />
            <text x={t.x} y={L.mid + 16} text-anchor="middle" class="tj-axis">t{t.t.turn}</text>
          </g>
        {/each}
        {#each L.items.filter((it) => it.kind === "final") as f (f.i)}
          <g class="tj-node" style={`--k:${f.i}`}>
            {#if f.agg != null && f.agg > 0}
              <path d={burst(f.x, L.mid, 3 + 9 * f.agg, 6 + Math.round(12 * f.agg), 7)} class="tj-burst big" />
            {/if}
            <circle cx={f.x} cy={L.mid} r={2.5 + 2.5 * (f.agg ?? 0)} class="tj-final" class:fail={!f.passed} />
            <text x={f.x + 16} y={L.mid - 4} class="tj-end">{f.agg == null ? "—" : fmtScore(f.agg, 2)}</text>
            <text x={f.x + 16} y={L.mid + 9} class="tj-axis">{f.passed ? "pass" : "fail"} · {f.status}</text>
          </g>
        {/each}
        {#if current && current.kind !== "tool"}<circle cx={current.x} cy={L.mid} r="6.5" class="tj-hl" />{/if}
      </svg>
    {/key}
    <div class="tj-read" class:on={!!current}>
      <span class="reticle-readout-dot"></span>
      <span>{current ? current.label : "replaying…"}</span>
    </div>
    {#if current?.kind === "tool" && current.out}<div class="tj-out mono">{current.out}</div>{/if}
    <div class="tx-legend">trunk = turns in order · width = context tokens · up = reads · down = writes/commands · length = duration (log) · ○ = failed call</div>
  </div>
{/if}
