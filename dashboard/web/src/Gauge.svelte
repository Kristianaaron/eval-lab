<script>
  // Circular tick gauge (reference image 4): a ring of 60 tick marks with a
  // thin arc for the value and a small monospace label inside.
  let { value = null, label = "", sub = "", size = 72, accent = false } = $props();

  const r = $derived(size / 2 - 6);
  const c = $derived(size / 2);
  const v = $derived(typeof value === "number" && Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : null);
  const ticks = $derived(
    Array.from({ length: 60 }, (_, i) => {
      const a = (i / 60) * Math.PI * 2 - Math.PI / 2;
      const long = i % 15 === 0;
      const len = long ? 5 : i % 5 === 0 ? 3.5 : 2;
      const r0 = r - len;
      return { x1: c + Math.cos(a) * r0, y1: c + Math.sin(a) * r0, x2: c + Math.cos(a) * r, y2: c + Math.sin(a) * r, lit: v != null && i / 60 <= v, long };
    })
  );
  const arc = $derived.by(() => {
    if (v == null || v <= 0) return "";
    const ra = r - 8;
    const end = -Math.PI / 2 + v * Math.PI * 2 * 0.9999;
    const x0 = c;
    const y0 = c - ra;
    const x1 = c + Math.cos(end) * ra;
    const y1 = c + Math.sin(end) * ra;
    return `M ${x0} ${y0} A ${ra} ${ra} 0 ${v > 0.5 ? 1 : 0} 1 ${x1} ${y1}`;
  });
</script>

<svg class="gauge" class:accent width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label} ${sub}`.trim()}>
  {#each ticks as t, i (i)}
    <line x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2} class:lit={t.lit} class:long={t.long} />
  {/each}
  {#if arc}<path d={arc} class="arc" />{/if}
  <text x={c} y={c + (sub ? 0 : 4)} text-anchor="middle" class="val">{label}</text>
  {#if sub}<text x={c} y={c + 11} text-anchor="middle" class="sub">{sub}</text>{/if}
</svg>
