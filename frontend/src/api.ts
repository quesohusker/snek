import type { FsListing, NodeResult, PreviewData, ToolSpec, WorkflowFile } from "./types";

async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const data = await res.json();
      message = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      message = `${res.status} ${res.statusText}`;
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export type RunResponse = { results: Record<string, NodeResult>; elapsed_ms: number };
export type SchemaResponse = { result: NodeResult; upstream: Record<string, string> };
export type PreviewResponse = { result: NodeResult; port: string | null; data: PreviewData | null; upstream: Record<string, string> };

export const api = {
  tools: () => call<{ tools: ToolSpec[]; categories: string[] }>("GET", "/api/tools"),
  run: (workflow: WorkflowFile) => call<RunResponse>("POST", "/api/run", { workflow }),
  summaries: (workflow: WorkflowFile) => call<{ summaries: Record<string, string> }>("POST", "/api/summaries", { workflow }),
  schema: (workflow: WorkflowFile, node: string) => call<SchemaResponse>("POST", "/api/schema", { workflow, node }),
  preview: (workflow: WorkflowFile, node: string, port: string | null, offset: number, limit: number, profile: boolean) =>
    call<PreviewResponse>("POST", "/api/preview", { workflow, node, port, offset, limit, profile }),
  exportCode: (workflow: WorkflowFile, name: string) => call<{ code: string }>("POST", "/api/export", { workflow, name }),
  listWorkflows: () => call<{ workflows: { name: string; modified: string }[]; folder: string }>("GET", "/api/workflows"),
  loadWorkflow: (name: string) => call<WorkflowFile>("GET", `/api/workflows/${encodeURIComponent(name)}`),
  saveWorkflow: (name: string, workflow: WorkflowFile) => call<{ ok: boolean; path: string }>("PUT", `/api/workflows/${encodeURIComponent(name)}`, workflow),
  fs: (path: string) => call<FsListing>("GET", `/api/fs?path=${encodeURIComponent(path)}`),
  clearCache: () => call<{ ok: boolean }>("POST", "/api/cache/clear"),
};
