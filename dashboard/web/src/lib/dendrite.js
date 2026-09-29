// Space-colonisation growth (Runions et al.): a tree grows from a root toward
// a set of attractor points; every attractor is a data point (a task, a run)
// and becomes a branch tip when reached. Deterministic for a given seed.

import { mulberry32, seedFrom } from "./glyph.js";

export function growTree({ seed = "eval-lab", width, height, root, targets, segment = 4, influence = 90, kill = 5, maxSteps = 900, jitter = 0.35 }) {
  const rnd = mulberry32(seedFrom(String(seed)));
  const nodes = [{ x: root.x, y: root.y, parent: -1, t: 0, tip: null, load: 0 }];
  const open = targets.map((t, i) => ({ ...t, i, reached: false }));
  let step = 0;
  while (step < maxSteps && open.some((a) => !a.reached)) {
    step++;
    const pull = new Map(); // node index -> [dx, dy, n]
    for (const a of open) {
      if (a.reached) continue;
      let best = -1;
      let bd = influence * influence;
      for (let n = 0; n < nodes.length; n++) {
        const dx = a.x - nodes[n].x;
        const dy = a.y - nodes[n].y;
        const d = dx * dx + dy * dy;
        if (d < bd) {
          bd = d;
          best = n;
        }
      }
      if (best < 0) continue;
      const dist = Math.sqrt(bd);
      if (dist <= kill) {
        a.reached = true;
        nodes[best].tip = a;
        continue;
      }
      const p = pull.get(best) ?? [0, 0, 0];
      p[0] += (a.x - nodes[best].x) / dist;
      p[1] += (a.y - nodes[best].y) / dist;
      p[2] += 1;
      pull.set(best, p);
    }
    if (!pull.size) {
      // nothing in reach: nudge the closest node straight toward the nearest attractor
      let bn = 0, ba = null, bd = Infinity;
      for (const a of open) {
        if (a.reached) continue;
        for (let n = 0; n < nodes.length; n++) {
          const d = (a.x - nodes[n].x) ** 2 + (a.y - nodes[n].y) ** 2;
          if (d < bd) { bd = d; bn = n; ba = a; }
        }
      }
      if (!ba) break;
      const dist = Math.sqrt(bd) || 1;
      pull.set(bn, [(ba.x - nodes[bn].x) / dist, (ba.y - nodes[bn].y) / dist, 1]);
    }
    for (const [n, [dx, dy, k]] of pull) {
      let vx = dx / k + (rnd() - 0.5) * jitter;
      let vy = dy / k + (rnd() - 0.5) * jitter;
      const len = Math.hypot(vx, vy) || 1;
      vx /= len;
      vy /= len;
      const nx = Math.min(width - 1, Math.max(1, nodes[n].x + vx * segment));
      const ny = Math.min(height - 1, Math.max(1, nodes[n].y + vy * segment));
      nodes.push({ x: nx, y: ny, parent: n, t: step, tip: null, load: 0 });
    }
  }
  // load = number of tips carried by each node (thickness), junctions = branch points
  const children = nodes.map(() => 0);
  for (let i = nodes.length - 1; i > 0; i--) {
    const load = (nodes[i].tip ? 1 : 0) + nodes[i].load;
    nodes[i].load = load;
    nodes[nodes[i].parent].load += load;
    children[nodes[i].parent]++;
  }
  nodes[0].load = Math.max(nodes[0].load + (nodes[0].tip ? 1 : 0), 1);
  let length = 0;
  for (let i = 1; i < nodes.length; i++) length += Math.hypot(nodes[i].x - nodes[nodes[i].parent].x, nodes[i].y - nodes[nodes[i].parent].y);
  const tips = nodes.filter((n) => n.tip);
  return {
    nodes,
    tips,
    junctions: children.filter((c) => c > 1).length,
    length,
    steps: step,
    reached: open.filter((a) => a.reached).length,
    total: open.length,
  };
}

// Path of node indices from the root to `idx` (for nerve pulses).
export function pathTo(nodes, idx) {
  const out = [];
  for (let i = idx; i >= 0; i = nodes[i].parent) out.push(i);
  return out.reverse();
}
