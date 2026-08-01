export async function get(path) {
  const res = await fetch(path);
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
