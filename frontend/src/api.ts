import type { FsListing, NodeResult, PreviewData, ProjectInfo, SnekSettings, ToolSpec, UpdateInfo, WorkflowFile } from "./types";

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
  chart: (workflow: WorkflowFile, node: string, port: string | null) => call<{ specs: unknown[] }>("POST", "/api/chart", { workflow, node, port }),
  table: (workflow: WorkflowFile, node: string, port: string | null) => call<{ text: string; rows: number; total: number }>("POST", "/api/table", { workflow, node, port }),
  aiInfo: () => call<AIInfo>("GET", "/api/ai"),
  aiContext: (request: string) => call<{ text: string; catalog_chars: number }>("POST", "/api/ai/context", { request }),
  aiWorkflow: (request: string, model: string) => call<AIResult>("POST", "/api/ai/workflow", { request, model }),
  connections: () => call<Connections>("GET", "/api/connections"),
  saveConnection: (name: string, key: string) => call<Connections>("PUT", "/api/connections", { name, key }),
  deleteConnection: (name: string) => call<Connections>("DELETE", `/api/connections/${encodeURIComponent(name)}`),
  exportCode: (workflow: WorkflowFile, name: string) => call<{ code: string }>("POST", "/api/export", { workflow, name }),
  listWorkflows: () => call<{ workflows: { name: string; modified: string }[]; folder: string }>("GET", "/api/workflows"),
  settings: () => call<SnekSettings>("GET", "/api/settings"),
  saveSettings: (changes: Partial<SnekSettings>) => call<SnekSettings>("PUT", "/api/settings", changes),
  autosave: (workflow: WorkflowFile, name: string) => call<{ ok: boolean; path: string }>("POST", "/api/autosave", { workflow, name }),
  openFile: (path: string) => call<{ workflow: WorkflowFile; path: string; name: string }>("POST", "/api/file/open", { path }),
  saveFile: (path: string, workflow: WorkflowFile) => call<{ ok: boolean; path: string; name: string }>("POST", "/api/file/save", { path, workflow }),
  loadWorkflow: (name: string) => call<WorkflowFile>("GET", `/api/workflows/${encodeURIComponent(name)}`),
  saveWorkflow: (name: string, workflow: WorkflowFile) => call<{ ok: boolean; path: string }>("PUT", `/api/workflows/${encodeURIComponent(name)}`, workflow),
  fs: (path: string) => call<FsListing>("GET", `/api/fs?path=${encodeURIComponent(path)}`),
  update: (force = false) => call<UpdateInfo>("GET", `/api/update?force=${force}`),
  updateSettings: (enabled: boolean) => call<UpdateInfo>("POST", "/api/update/settings", { enabled }),
  shutdown: () => call<{ ok: boolean }>("POST", "/api/shutdown"),
  clearCache: () => call<{ ok: boolean }>("POST", "/api/cache/clear"),
  resolve: (path: string, fmt: string) => call<{ path: string; exists: boolean; folder_exists: boolean }>("GET", `/api/resolve?path=${encodeURIComponent(path)}&fmt=${encodeURIComponent(fmt)}`),
  project: () => call<ProjectInfo>("GET", "/api/project"),
  openProject: (path: string) => call<ProjectInfo>("POST", "/api/project/open", { path }),
  newProject: (parent: string, name: string) => call<ProjectInfo>("POST", "/api/project/new", { parent, name }),
  upload: async (file: File) => {
    const r = await fetch(`/api/upload?name=${encodeURIComponent(file.name)}`, { method: "POST", body: file });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.detail ?? r.statusText);
    return body as { path: string; name: string };
  },
  reveal: (path: string) => call<{ ok: boolean; path: string }>("POST", "/api/reveal", { path }),
};

export type Connections = { keys: { name: string; saved: boolean; hint: string; env: string; from_env: boolean }[]; file: string };

export type AIInfo = { models: { value: string; label: string }[]; model: string; key_saved: boolean; key_hint: string; key_from_env: boolean };

export type AIResult = { workflow: WorkflowFile; summary: string; errors: Record<string, string>; problems: string[]; rounds: number; model: string; usage: { input: number; output: number; cache_read: number } };
