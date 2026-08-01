export async function get(path) {
  const res = await fetch(path);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${body}`);
  }
  return res.json();
}

export async function post(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${body}`);
  }
  return res.json();
}

export async function del(path) {
  const res = await fetch(path, { method: "DELETE" });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${body}`);
  }
  return res.json();
}

export function fmtPassed(p) {
  if (p === 1 || p === true) return { cls: "pass", label: "pass" };
  if (p === 0 || p === false) return { cls: "fail", label: "fail" };
  return { cls: "error", label: String(p) };
}

export function fmtBytes(n) {
  if (n == null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  let v = Number(n);
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v >= 100 ? 0 : v >= 10 ? 1 : 2)} ${units[i]}`;
}

export function fmtGb(n) {
  if (n == null) return "—";
  return `${(Number(n) / 1024 ** 3).toFixed(1)} GB`;
}

export const ACTION_LABELS = {
  inspect_checkpoint: "Inspect checkpoint",
  evaluate_directly: "Evaluate directly",
  build_atlas: "Build atlas",
  create_keep_map: "Create keep map",
  create_experiment: "Create experiment",
  compare: "Compare",
};
