<script>
  // Pixel-grid map (reference image 2): every task is a small outlined square,
  // filled with the heat palette by score; rulers with zero-padded labels on
  // the top and left edges and a "dist" legend below.
  import { heat, pad } from "./lib/fmt.js";

  let { cells = [], cols = 12, cell = 12, gap = 3, legend = "score", href = null } = $props();

  const rows = $derived(Math.max(1, Math.ceil(cells.length / cols)));
  const left = 34; // room for the row ruler
  const top = 20; // room for the column ruler
  const step = $derived(cell + gap);
  const width = $derived(left + cols * step + 4);
  const height = $derived(top + rows * step + 26);
  const colTicks = $derived(Array.from({ length: cols }, (_, i) => i));
  const rowTicks = $derived(Array.from({ length: rows }, (_, i) => i));
  const gid = `heat-${Math.floor(Math.random() * 1e6)}`;
  const stops = ["#160b39", "#420a68", "#6b186e", "#932667", "#bc3754", "#dd513a", "#f37819", "#fca50a", "#f6d746"];
</script>

<svg class="pixmap" viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label="Task score map">
  <defs>
    <linearGradient id={gid} x1="0" x2="1" y1="0" y2="0">
      {#each stops as s, i (i)}<stop offset={`${(i / (stops.length - 1)) * 100}%`} stop-color={s} />{/each}
    </linearGradient>
  </defs>
  <!-- column ruler -->
  <line x1={left} y1={top - 4} x2={left + cols * step - gap} y2={top - 4} class="rule" />
  {#each colTicks as i (i)}
    <line x1={left + i * step + cell / 2} y1={top - 4} x2={left + i * step + cell / 2} y2={top - (i % 5 === 0 ? 9 : 6)} class="rule" />
    {#if i % 5 === 0}<text x={left + i * step + cell / 2} y={top - 11} text-anchor="middle" class="lbl">{pad(i)}</text>{/if}
  {/each}
  <!-- row ruler -->
  <line x1={left - 4} y1={top} x2={left - 4} y2={top + rows * step - gap} class="rule" />
  {#each rowTicks as i (i)}
    <line x1={left - 4} y1={top + i * step + cell / 2} x2={left - (i % 5 === 0 ? 9 : 6)} y2={top + i * step + cell / 2} class="rule" />
    <text x={left - 11} y={top + i * step + cell / 2 + 3} text-anchor="end" class="lbl">{pad(i)}</text>
  {/each}
  <!-- cells -->
  {#each cells as c, i (c.id ?? i)}
    {@const x = left + (i % cols) * step}
    {@const y = top + Math.floor(i / cols) * step}
    {@const fill = heat(c.score)}
    {#if href && c.run_id}
      <a href={href(c)}>
        <rect {x} {y} width={cell} height={cell} class="px" class:none={fill == null} style={fill ? `fill:${fill}` : ""}><title>{c.label ?? c.id} · {fill ? c.score.toFixed(3) : "no run"}</title></rect>
      </a>
    {:else}
      <rect {x} {y} width={cell} height={cell} class="px" class:none={fill == null} style={fill ? `fill:${fill}` : ""}><title>{c.label ?? c.id} · {fill ? c.score.toFixed(3) : "no run"}</title></rect>
    {/if}
  {/each}
  <!-- legend -->
  <text x={left} y={height - 6} class="lbl">{legend}</text>
  <rect x={left + 44} y={height - 14} width="72" height="7" fill={`url(#${gid})`} />
  <text x={left + 44} y={height + 4} class="lbl" style="display:none">0</text>
  <text x={left + 120} y={height - 7} class="lbl">0 … 1</text>
</svg>
