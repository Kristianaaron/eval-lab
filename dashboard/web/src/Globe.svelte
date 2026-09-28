<script>
  // Point-mesh wireframe sphere (reference image 1): ~600 points clustered
  // into a few dense regions, each joined to its nearest neighbours by thin
  // lines. Drawn once to a canvas; static, monochrome.
  import { onMount } from "svelte";
  import { mulberry32, seedFrom } from "./lib/glyph.js";

  let { size = 320, points = 600, seed = "eval-lab", alpha = 1 } = $props();
  let canvas = $state(null);

  onMount(() => {
    const rnd = mulberry32(seedFrom(seed));
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const R = size / 2 - 4;
    const cx = size / 2;
    const cy = size / 2;

    // Cluster centres on the sphere: points survive with probability rising
    // near a centre, which gives the continent-like density of the reference.
    const centres = [];
    for (let i = 0; i < 5; i++) {
      const u = rnd() * 2 - 1;
      const th = rnd() * Math.PI * 2;
      const s = Math.sqrt(1 - u * u);
      centres.push([s * Math.cos(th), s * Math.sin(th), u, 0.35 + rnd() * 0.5]);
    }
    const pts = [];
    const golden = Math.PI * (3 - Math.sqrt(5));
    const candidates = points * 3;
    for (let i = 0; i < candidates && pts.length < points; i++) {
      const y = 1 - (i / (candidates - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      const th = golden * i + (rnd() - 0.5) * 0.4;
      const p = [r * Math.cos(th), y, r * Math.sin(th)];
      let d = 0.08;
      for (const c of centres) {
        const dot = p[0] * c[0] + p[1] * c[1] + p[2] * c[2];
        d += c[3] * Math.exp(-(1 - dot) * 5);
      }
      if (rnd() < d) pts.push(p);
    }

    // Tilt so the poles are not on the axes, then orthographic projection.
    const tilt = 0.45;
    const spin = 0.6;
    const proj = pts.map(([x, y, z]) => {
      const x1 = x * Math.cos(spin) - z * Math.sin(spin);
      const z1 = x * Math.sin(spin) + z * Math.cos(spin);
      const y2 = y * Math.cos(tilt) - z1 * Math.sin(tilt);
      const z2 = y * Math.sin(tilt) + z1 * Math.cos(tilt);
      return [cx + x1 * R, cy - y2 * R, z2];
    });

    // Nearest-neighbour links (k = 3) in 3D.
    const links = [];
    for (let i = 0; i < pts.length; i++) {
      const near = [];
      for (let j = 0; j < pts.length; j++) {
        if (i === j) continue;
        const dx = pts[i][0] - pts[j][0];
        const dy = pts[i][1] - pts[j][1];
        const dz = pts[i][2] - pts[j][2];
        const d = dx * dx + dy * dy + dz * dz;
        if (near.length < 4) near.push([d, j]);
        else {
          let w = 0;
          for (let k = 1; k < 4; k++) if (near[k][0] > near[w][0]) w = k;
          if (d < near[w][0]) near[w] = [d, j];
        }
      }
      for (const [, j] of near) if (j > i) links.push([i, j]);
    }

    ctx.clearRect(0, 0, size, size);
    // limb
    ctx.strokeStyle = `rgba(232,228,216,${0.14 * alpha})`;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, Math.PI * 2);
    ctx.stroke();
    // back hemisphere first, then front
    for (const pass of [0, 1]) {
      ctx.lineWidth = pass ? 0.7 : 0.5;
      for (const [i, j] of links) {
        const a = proj[i];
        const b = proj[j];
        const front = (a[2] + b[2]) / 2 > 0;
        if ((pass === 1) !== front) continue;
        ctx.strokeStyle = `rgba(232,228,216,${(front ? 0.22 : 0.06) * alpha})`;
        ctx.beginPath();
        ctx.moveTo(a[0], a[1]);
        ctx.lineTo(b[0], b[1]);
        ctx.stroke();
      }
      for (const p of proj) {
        const front = p[2] > 0;
        if ((pass === 1) !== front) continue;
        ctx.fillStyle = `rgba(232,228,216,${(front ? 0.85 : 0.22) * alpha})`;
        ctx.beginPath();
        ctx.arc(p[0], p[1], front ? 1 : 0.7, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  });
</script>

<canvas bind:this={canvas} class="globe" style={`width:${size}px;height:${size}px`} aria-hidden="true"></canvas>
