export async function api<T = any>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api" + path, {
    method,
    headers: { "Content-Type": "application/json", "X-Hub-Request": "1" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let detail: any;
    try {
      detail = (await response.json()).detail;
    } catch {
      detail = await response.text().catch(() => response.statusText);
    }
    throw new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail),
    );
  }
  return response.json();
}
export type User = {
  id: string;
  email: string;
  role: string;
  approved: boolean;
  verified: boolean;
  env_limit: number | null;
  credential_email_at?: number | null;
};
export type Run = {
  id: string;
  name: string;
  email: string;
  status: string;
  spec: any;
  iteration: number;
  queue_position: number | null;
  server_name: string | null;
  gpu: string | null;
  gpu_mb: number;
  created: number;
  started: number | null;
  ended: number | null;
  cancel: boolean;
  error: string | null;
  execution: any;
  placement: any;
  metrics?: any[];
  artifacts?: { path: string; size: number; sha256: string }[];
  worker_online?: boolean;
  quarantined?: boolean;
  priority: number;
};
export const active = (r: Run) =>
  ["QUEUED", "STARTING", "RUNNING"].includes(r.status);
export const date = (n: number | null) =>
  n ? new Date(n * 1000).toLocaleString() : "—";
export function duration(r: Run) {
  let seconds = Math.max(
    0,
    Math.floor((r.ended || Date.now() / 1000) - (r.started || r.created)),
  );
  return seconds < 60
    ? `${seconds}s`
    : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}
