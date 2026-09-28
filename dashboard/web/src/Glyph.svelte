<script>
  // Tiny monochrome identicon in the pixel-grid style of the reference sheet:
  // a mirrored 5×5 field of 1px-outlined squares, some filled, seeded by id.
  import { mulberry32, seedFrom } from "./lib/glyph.js";

  let { seed = "", size = 12, title = "", class: klass = "" } = $props();
  const cells = $derived.by(() => {
    const rnd = mulberry32(seedFrom(seed));
    const out = [];
    for (let y = 0; y < 5; y++) {
      for (let x = 0; x < 3; x++) {
        const r = rnd();
        const kind = r < 0.38 ? 0 : r < 0.72 ? 1 : 2; // 0 empty · 1 outline · 2 filled
        if (!kind) continue;
        out.push({ x, y, kind });
        if (x < 2) out.push({ x: 4 - x, y, kind });
      }
    }
    if (!out.some((c) => c.x === 2 && c.y === 2)) out.push({ x: 2, y: 2, kind: 2 });
    return out;
  });
</script>

<svg class="glyph {klass}" viewBox="0 0 5 5" width={size} height={size} shape-rendering="crispEdges" role={title ? "img" : "presentation"} aria-hidden={title ? undefined : "true"}>
  {#if title}<title>{title}</title>{/if}
  {#each cells as c, i (i)}
    <rect x={c.x + 0.1} y={c.y + 0.1} width="0.8" height="0.8" class:fill={c.kind === 2} />
  {/each}
</svg>
