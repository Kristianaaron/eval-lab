// Build the hierarchies drawn by Taxonomy.svelte from real task lists.

import { fmtScore } from "./fmt.js";

const DOMAIN_LABELS = {
  toolcall: "tool calling",
  longcontext: "long context",
  mathematics: "maths",
  general: "general",
};

export function domainOf(taskId) {
  return String(taskId).split(".", 1)[0];
}

export function domainLabel(d) {
  return DOMAIN_LABELS[d] ?? d.replaceAll("_", " ");
}

export function taskLabel(taskId) {
  const parts = String(taskId).split(".");
  return parts.length > 2 ? parts.slice(1, -1).join(".") : parts.join(".");
}

// tasks: [{task_id, score, passed, run_id, status}] → children grouped by domain.
// A single domain collapses so the tree never shows a limb that carries no split.
export function byDomain(tasks, leafId = (t) => t.task_id, ns = "") {
  const groups = new Map();
  for (const t of tasks) {
    const d = domainOf(t.task_id);
    if (!groups.has(d)) groups.set(d, []);
    groups.get(d).push({
      id: leafId(t),
      label: taskLabel(t.task_id),
      taskId: t.task_id,
      value: typeof t.score === "number" ? t.score : null,
      passed: t.passed ?? null,
      status: t.status ?? (t.run_id ? "done" : "pending"),
      href: t.run_id ? `#/explorer/run/${t.run_id}` : null,
    });
  }
  if (groups.size === 1) return [...groups.values()][0];
  // A domain with one task would be a limb that carries no split: the task
  // hangs directly off the parent instead, labelled with its domain.
  return [...groups.entries()].map(([d, leaves]) =>
    leaves.length === 1
      ? { ...leaves[0], label: `${domainLabel(d)} / ${leaves[0].label}` }
      : { id: `${ns}d:${d}`, label: domainLabel(d), children: leaves }
  );
}

export function leafSummary(leaf) {
  if (leaf.status === "running") return "evaluating now";
  if (leaf.status === "pending") return "queued";
  if (leaf.value == null) return "no run";
  return `${fmtScore(leaf.value, 2)} · ${leaf.passed ? "pass" : "fail"}`;
}
