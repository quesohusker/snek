import { create } from "zustand";
import { applyEdgeChanges, applyNodeChanges, type Connection, type Edge, type EdgeChange, type Node, type NodeChange } from "@xyflow/react";
import { api } from "./api";
import type { FlowNodeData, NodeResult, ToolSpec, WorkflowFile } from "./types";

export type ToolNode = Node<FlowNodeData, "tool">;

type Position = { x: number; y: number };

export type Dialog = "open" | "saveAs" | "export" | null;

type State = {
  tools: Record<string, ToolSpec>;
  toolList: ToolSpec[];
  categories: string[];
  nodes: ToolNode[];
  edges: Edge[];
  selectedId: string | null;
  results: Record<string, NodeResult>;
  summaries: Record<string, string>;
  stale: boolean;
  running: boolean;
  lastRun: { elapsed: number; ok: number; errors: number } | null;
  name: string | null;
  dirty: boolean;
  version: number;
  loaded: number;
  dialog: Dialog;
  recent: string[];
  setDialog: (d: Dialog) => void;
  loadRecent: () => void;
  setTools: (list: ToolSpec[], categories: string[]) => void;
  onNodesChange: (changes: NodeChange<ToolNode>[]) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onConnect: (c: Connection) => void;
  canConnect: (c: Connection | Edge) => boolean;
  addNode: (type: string, position?: Position) => string;
  updateConfig: (id: string, patch: Record<string, any>) => void;
  setLabel: (id: string, label: string) => void;
  select: (id: string | null) => void;
  selectAll: () => void;
  deleteSelected: () => void;
  setResults: (results: Record<string, NodeResult>, elapsed: number) => void;
  mergeResult: (id: string, result: NodeResult) => void;
  setSummaries: (s: Record<string, string>) => void;
  setRunning: (v: boolean) => void;
  load: (file: WorkflowFile, name: string | null) => void;
  markSaved: (name: string) => void;
  toWorkflow: () => WorkflowFile;
};

export function defaultsFor(spec: ToolSpec): Record<string, any> {
  return Object.fromEntries(spec.fields.map((f) => [f.key, structuredClone(f.default)]));
}

function nextId(nodes: ToolNode[]): string {
  return String(nodes.reduce((m, n) => Math.max(m, Number(n.id) || 0), 0) + 1);
}

function edgeId(c: { source: string; sourceHandle?: string | null; target: string; targetHandle?: string | null }) {
  return `e${c.source}.${c.sourceHandle ?? "out"}-${c.target}.${c.targetHandle ?? "in"}`;
}

function reaches(edges: Edge[], from: string, to: string): boolean {
  const stack = [from];
  const seen = new Set<string>();
  while (stack.length) {
    const cur = stack.pop()!;
    if (cur === to) return true;
    if (seen.has(cur)) continue;
    seen.add(cur);
    for (const e of edges) if (e.source === cur) stack.push(e.target);
  }
  return false;
}

export const useFlow = create<State>()((set, get) => ({
  tools: {},
  toolList: [],
  categories: [],
  nodes: [],
  edges: [],
  selectedId: null,
  results: {},
  summaries: {},
  stale: true,
  running: false,
  lastRun: null,
  name: null,
  dirty: false,
  version: 0,
  loaded: 0,
  dialog: null,
  recent: [],

  setDialog: (dialog) => set({ dialog }),

  loadRecent: () => {
    api
      .listWorkflows()
      .then((r) => set({ recent: r.workflows.slice(0, 10).map((w) => w.name) }))
      .catch(() => undefined);
  },

  setTools: (list, categories) => set({ toolList: list, tools: Object.fromEntries(list.map((t) => [t.type, t])), categories }),

  onNodesChange: (changes) => {
    const structural = changes.some((c) => c.type === "remove" || c.type === "add");
    const moved = changes.some((c) => c.type === "position" && !c.dragging);
    const removed = new Set(changes.filter((c) => c.type === "remove").map((c) => (c as { id: string }).id));
    set((s) => ({
      nodes: applyNodeChanges(changes, s.nodes),
      edges: removed.size ? s.edges.filter((e) => !removed.has(e.source) && !removed.has(e.target)) : s.edges,
      selectedId: s.selectedId && removed.has(s.selectedId) ? null : s.selectedId,
      dirty: s.dirty || structural || moved,
      stale: s.stale || structural,
      version: structural ? s.version + 1 : s.version,
    }));
  },

  onEdgesChange: (changes) => {
    const structural = changes.some((c) => c.type === "remove" || c.type === "add");
    set((s) => ({
      edges: applyEdgeChanges(changes, s.edges),
      dirty: s.dirty || structural,
      stale: s.stale || structural,
      version: structural ? s.version + 1 : s.version,
    }));
  },

  canConnect: (c) => {
    if (!c.source || !c.target || c.source === c.target) return false;
    return !reaches(get().edges, c.target, c.source);
  },

  onConnect: (c) => {
    if (!get().canConnect(c)) return;
    const { nodes, tools } = get();
    const target = nodes.find((n) => n.id === c.target);
    const port = target ? tools[target.data.type]?.inputs.find((p) => p.name === c.targetHandle) : undefined;
    set((s) => {
      const keep = s.edges.filter((e) => {
        if (e.source === c.source && e.sourceHandle === c.sourceHandle && e.target === c.target && e.targetHandle === c.targetHandle) return false;
        return port?.multi || !(e.target === c.target && e.targetHandle === c.targetHandle);
      });
      const edge: Edge = { id: edgeId(c), source: c.source, sourceHandle: c.sourceHandle ?? "out", target: c.target, targetHandle: c.targetHandle ?? "in" };
      return { edges: [...keep, edge], dirty: true, stale: true, version: s.version + 1 };
    });
  },

  addNode: (type, position) => {
    const { tools, nodes, selectedId } = get();
    const spec = tools[type];
    const id = nextId(nodes);
    const anchor = nodes.find((n) => n.id === selectedId);
    const pos = anchor ? { x: anchor.position.x + 170, y: anchor.position.y } : position ?? { x: 80 + nodes.length * 30, y: 80 + nodes.length * 20 };
    const node: ToolNode = { id, type: "tool", position: pos, selected: true, data: { type, label: "", config: defaultsFor(spec) } };
    const anchorSpec = anchor ? tools[anchor.data.type] : undefined;
    const autoEdge: Edge[] =
      anchor && anchorSpec?.outputs.length && spec.inputs.length && !position
        ? [{ id: edgeId({ source: anchor.id, sourceHandle: anchorSpec.outputs[0].name, target: id, targetHandle: spec.inputs[0].name }), source: anchor.id, sourceHandle: anchorSpec.outputs[0].name, target: id, targetHandle: spec.inputs[0].name }]
        : [];
    set((s) => ({
      nodes: [...s.nodes.map((n) => ({ ...n, selected: false })), node],
      edges: [...s.edges, ...autoEdge],
      selectedId: id,
      dirty: true,
      stale: true,
      version: s.version + 1,
    }));
    return id;
  },

  updateConfig: (id, patch) =>
    set((s) => ({
      nodes: s.nodes.map((n) => (n.id === id ? { ...n, data: { ...n.data, config: { ...n.data.config, ...patch } } } : n)),
      dirty: true,
      stale: true,
      version: s.version + 1,
    })),

  setLabel: (id, label) =>
    set((s) => ({ nodes: s.nodes.map((n) => (n.id === id ? { ...n, data: { ...n.data, label } } : n)), dirty: true })),

  select: (id) => {
    if (get().selectedId === id) return;
    set((s) => ({ selectedId: id, nodes: s.nodes.map((n) => (n.selected === (n.id === id) ? n : { ...n, selected: n.id === id })) }));
  },

  selectAll: () => set((s) => ({ selectedId: null, nodes: s.nodes.map((n) => (n.selected ? n : { ...n, selected: true })) })),

  deleteSelected: () => {
    const ids = new Set(get().nodes.filter((n) => n.selected).map((n) => n.id));
    if (!ids.size && !get().edges.some((e) => e.selected)) return;
    set((s) => ({
      nodes: s.nodes.filter((n) => !ids.has(n.id)),
      edges: s.edges.filter((e) => !e.selected && !ids.has(e.source) && !ids.has(e.target)),
      selectedId: s.selectedId && ids.has(s.selectedId) ? null : s.selectedId,
      dirty: true,
      stale: true,
      version: s.version + 1,
    }));
  },

  setResults: (results, elapsed) => {
    const vals = Object.values(results);
    set({
      results,
      stale: false,
      lastRun: { elapsed, ok: vals.filter((r) => r.status === "ok").length, errors: vals.filter((r) => r.status === "error").length },
    });
  },

  mergeResult: (id, result) => set((s) => ({ results: { ...s.results, [id]: result } })),

  setSummaries: (summaries) => set({ summaries }),

  setRunning: (running) => set({ running }),

  load: (file, name) => {
    const { tools } = get();
    const nodes: ToolNode[] = file.nodes
      .filter((n) => tools[n.type])
      .map((n) => ({
        id: String(n.id),
        type: "tool",
        position: n.position ?? { x: 0, y: 0 },
        data: { type: n.type, label: n.label ?? "", config: { ...defaultsFor(tools[n.type]), ...n.config } },
      }));
    const edges: Edge[] = file.edges.map((e) => ({ ...e, id: e.id || edgeId(e), source: String(e.source), target: String(e.target) }));
    set((s) => ({ nodes, edges, name, selectedId: null, results: {}, summaries: {}, stale: true, lastRun: null, dirty: false, version: s.version + 1, loaded: s.loaded + 1 }));
  },

  markSaved: (name) => {
    set({ name, dirty: false });
    get().loadRecent();
  },

  toWorkflow: () => {
    const { nodes, edges, name } = get();
    return {
      version: 1,
      name: name ?? undefined,
      nodes: nodes.map((n) => ({ id: n.id, type: n.data.type, label: n.data.label, position: { x: Math.round(n.position.x), y: Math.round(n.position.y) }, config: n.data.config })),
      edges: edges.map((e) => ({ id: e.id, source: e.source, sourceHandle: e.sourceHandle ?? "out", target: e.target, targetHandle: e.targetHandle ?? "in" })),
    };
  },
}));
