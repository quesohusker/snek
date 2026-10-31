import { create } from "zustand";
import { applyEdgeChanges, applyNodeChanges, type Connection, type Edge, type EdgeChange, type Node, type NodeChange } from "@xyflow/react";
import { api } from "./api";
import { registerToolLooks } from "./icons";
import type { FlowNodeData, NodeResult, ProjectInfo, SnekSettings, ToolSpec, UpdateInfo, WorkflowFile } from "./types";

export type ToolNode = Node<FlowNodeData, "tool">;

type Position = { x: number; y: number };

const DEFAULT_FAVORITES = ["input", "output", "browse", "select", "filter", "formula", "join", "summarize", "sort"];

function stored<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function remember(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    return;
  }
}

export type Snapshot = { nodes: ToolNode[]; edges: Edge[]; label: string };

export type ClipboardData = {
  format: "snek-clipboard";
  version: 1;
  nodes: { id: string; type: string; label: string; position: Position; config: Record<string, any> }[];
  edges: { source: string; sourceHandle: string; target: string; targetHandle: string }[];
};

const HISTORY_LIMIT = 200;

export type Dialog = "aiCreate" | "shortcuts" | "open" | "saveAs" | "export" | "openProject" | "newProject" | "about" | "openFile" | "saveFile" | "settings" | "openAutosave" | null;

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
  filePath: string | null;
  dirty: boolean;
  version: number;
  loaded: number;
  dialog: Dialog;
  recent: string[];
  project: ProjectInfo | null;
  stopped: boolean;
  update: UpdateInfo | null;
  settings: SnekSettings | null;
  autosave: { at: string | null; error: string; version: number; name: string | null };
  setSettings: (s: SnekSettings) => void;
  paletteTab: string;
  favorites: string[];
  setPaletteTab: (tab: string) => void;
  toggleFavorite: (type: string) => void;
  setUpdate: (u: UpdateInfo) => void;
  setProject: (p: ProjectInfo) => void;
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
  deleteSelected: (label?: string) => void;
  setResults: (results: Record<string, NodeResult>, elapsed: number) => void;
  mergeResult: (id: string, result: NodeResult) => void;
  setSummaries: (s: Record<string, string>) => void;
  setRunning: (v: boolean) => void;
  load: (file: WorkflowFile, name: string | null, filePath?: string | null) => void;
  markSaved: (name: string, filePath?: string | null) => void;
  toWorkflow: () => WorkflowFile;
  past: Snapshot[];
  future: Snapshot[];
  historyKey: string | null;
  historyAt: number;
  dragging: boolean;
  savedSig: string;
  clipboard: ClipboardData | null;
  pasteCount: number;
  checkpoint: (label: string, key?: string, windowMs?: number) => void;
  undo: () => void;
  redo: () => void;
  copySelection: () => ClipboardData | null;
  pasteData: (data: ClipboardData, at?: Position) => void;
  duplicateSelected: () => void;
  cutSelected: () => ClipboardData | null;
  selectNone: () => void;
  panels: Panels;
  togglePanel: (panel: keyof Panels) => void;
  focusLabel: number;
  unsavedPrompt: ((choice: "save" | "discard" | "cancel") => void) | null;
  requestRename: (id: string) => void;
};

export type Panels = { palette: boolean; results: boolean; config: boolean };

export function defaultsFor(spec: ToolSpec): Record<string, any> {
  return Object.fromEntries(spec.fields.map((f) => [f.key, structuredClone(f.default)]));
}

function signature(nodes: ToolNode[], edges: Edge[]) {
  return JSON.stringify([
    nodes.map((n) => [n.id, n.data.type, n.data.label, Math.round(n.position.x), Math.round(n.position.y), n.data.config]),
    edges.map((e) => [e.source, e.sourceHandle ?? "out", e.target, e.targetHandle ?? "in"]),
  ]);
}

function unselected<T extends { selected?: boolean }>(items: T[]): T[] {
  return items.map((i) => (i.selected ? { ...i, selected: false } : i));
}

export function isClipboardData(value: unknown): value is ClipboardData {
  return !!value && typeof value === "object" && (value as ClipboardData).format === "snek-clipboard" && Array.isArray((value as ClipboardData).nodes);
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
  filePath: null,
  dirty: false,
  version: 0,
  loaded: 0,
  dialog: null,
  recent: [],
  project: null,
  stopped: false,
  update: null,
  settings: null,
  autosave: { at: null, error: "", version: -1, name: null },
  past: [],
  future: [],
  historyKey: null,
  historyAt: 0,
  dragging: false,
  savedSig: signature([], []),
  clipboard: null,
  pasteCount: 0,
  panels: stored<Panels>("snek.panels", { palette: true, results: true, config: true }),
  focusLabel: 0,
  unsavedPrompt: null,

  togglePanel: (panel) => {
    const panels = { ...get().panels, [panel]: !get().panels[panel] };
    remember("snek.panels", panels);
    set({ panels });
  },

  requestRename: (id) => {
    get().select(id);
    set((s) => ({ panels: s.panels.config ? s.panels : { ...s.panels, config: true }, focusLabel: s.focusLabel + 1 }));
  },

  checkpoint: (label, key, windowMs = 1200) => {
    const s = get();
    const now = Date.now();
    if (key && key === s.historyKey && now - s.historyAt < windowMs) {
      set({ historyAt: now });
      return;
    }
    set({ past: [...s.past.slice(-(HISTORY_LIMIT - 1)), { nodes: s.nodes, edges: s.edges, label }], future: [], historyKey: key ?? null, historyAt: now });
  },

  undo: () => {
    const s = get();
    const last = s.past[s.past.length - 1];
    if (!last) return;
    const nodes = unselected(last.nodes);
    const edges = unselected(last.edges);
    set({
      past: s.past.slice(0, -1),
      future: [...s.future, { nodes: s.nodes, edges: s.edges, label: last.label }],
      nodes,
      edges,
      selectedId: null,
      historyKey: null,
      dirty: signature(nodes, edges) !== s.savedSig,
      stale: true,
      version: s.version + 1,
    });
  },

  redo: () => {
    const s = get();
    const next = s.future[s.future.length - 1];
    if (!next) return;
    const nodes = unselected(next.nodes);
    const edges = unselected(next.edges);
    set({
      future: s.future.slice(0, -1),
      past: [...s.past, { nodes: s.nodes, edges: s.edges, label: next.label }],
      nodes,
      edges,
      selectedId: null,
      historyKey: null,
      dirty: signature(nodes, edges) !== s.savedSig,
      stale: true,
      version: s.version + 1,
    });
  },

  copySelection: () => {
    const { nodes, edges, selectedId } = get();
    const picked = nodes.filter((n) => n.selected || n.id === selectedId);
    if (!picked.length) return null;
    const ids = new Set(picked.map((n) => n.id));
    const data: ClipboardData = {
      format: "snek-clipboard",
      version: 1,
      nodes: picked.map((n) => ({ id: n.id, type: n.data.type, label: n.data.label, position: { ...n.position }, config: structuredClone(n.data.config) })),
      edges: edges.filter((e) => ids.has(e.source) && ids.has(e.target)).map((e) => ({ source: e.source, sourceHandle: e.sourceHandle ?? "out", target: e.target, targetHandle: e.targetHandle ?? "in" })),
    };
    set({ clipboard: data, pasteCount: 0 });
    return data;
  },

  pasteData: (data, at) => {
    const { tools, nodes } = get();
    const usable = data.nodes.filter((n) => tools[n.type]);
    if (!usable.length) return;
    const same = get().clipboard === data;
    const count = same ? get().pasteCount + 1 : 1;
    const minX = Math.min(...usable.map((n) => n.position.x));
    const minY = Math.min(...usable.map((n) => n.position.y));
    const shift = at ? { x: at.x - minX, y: at.y - minY } : { x: 40 * count, y: 40 * count };
    let next = Number(nextId(nodes));
    const ids = new Map<string, string>();
    const added: ToolNode[] = usable.map((n) => {
      const id = String(next++);
      ids.set(n.id, id);
      return { id, type: "tool", selected: true, position: { x: n.position.x + shift.x, y: n.position.y + shift.y }, data: { type: n.type, label: n.label ?? "", config: { ...defaultsFor(tools[n.type]), ...structuredClone(n.config) } } };
    });
    const addedEdges: Edge[] = data.edges
      .filter((e) => ids.has(e.source) && ids.has(e.target))
      .map((e) => {
        const c = { source: ids.get(e.source)!, sourceHandle: e.sourceHandle, target: ids.get(e.target)!, targetHandle: e.targetHandle };
        return { id: edgeId(c), ...c };
      });
    get().checkpoint(added.length === 1 ? `Paste ${tools[added[0].data.type].label}` : `Paste ${added.length} tools`);
    set((s) => ({
      nodes: [...unselected(s.nodes), ...added],
      edges: [...unselected(s.edges), ...addedEdges],
      selectedId: added.length === 1 ? added[0].id : null,
      pasteCount: same ? count : s.pasteCount,
      dirty: true,
      stale: true,
      version: s.version + 1,
    }));
  },

  duplicateSelected: () => {
    const keep = get().clipboard;
    const keepCount = get().pasteCount;
    const data = get().copySelection();
    if (!data) return;
    set({ clipboard: null });
    get().pasteData(data);
    set({ clipboard: keep, pasteCount: keepCount });
  },

  cutSelected: () => {
    const data = get().copySelection();
    if (data) get().deleteSelected("Cut");
    return data;
  },

  selectNone: () => set((s) => ({ selectedId: null, nodes: unselected(s.nodes), edges: unselected(s.edges) })),

  setSettings: (settings) => set({ settings }),
  paletteTab: stored("snek.paletteTab", "Favorites"),
  favorites: stored("snek.favorites", DEFAULT_FAVORITES),

  setPaletteTab: (paletteTab) => {
    remember("snek.paletteTab", paletteTab);
    set({ paletteTab });
  },

  toggleFavorite: (type) => {
    const current = get().favorites;
    const favorites = current.includes(type) ? current.filter((t) => t !== type) : [...current, type];
    remember("snek.favorites", favorites);
    set({ favorites });
  },

  setUpdate: (update) => set({ update }),

  setProject: (project) => set({ project }),

  setDialog: (dialog) => set({ dialog }),

  loadRecent: () => {
    api
      .listWorkflows()
      .then((r) => set({ recent: r.workflows.slice(0, 10).map((w) => w.name) }))
      .catch(() => undefined);
  },

  setTools: (list, categories) => {
    registerToolLooks(list);
    set({ toolList: list, tools: Object.fromEntries(list.map((t) => [t.type, t])), categories });
  },

  onNodesChange: (changes) => {
    const structural = changes.some((c) => c.type === "remove" || c.type === "add");
    const moved = changes.some((c) => c.type === "position" && !c.dragging);
    const dragStep = changes.some((c) => c.type === "position" && c.dragging);
    if (dragStep && !get().dragging) {
      get().checkpoint("Move");
      set({ dragging: true });
    } else if (moved && !dragStep) {
      if (get().dragging) set({ dragging: false });
      else get().checkpoint("Move", "nudge");
    }
    if (structural) get().checkpoint("Delete", "delete", 100);
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
    if (structural) get().checkpoint("Delete", "delete", 100);
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
    get().checkpoint("Connect");
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
    get().checkpoint(`Add ${spec.label}`);
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

  updateConfig: (id, patch) => {
    get().checkpoint("Change settings", `config:${id}:${Object.keys(patch).join(",")}`);
    set((s) => ({
      nodes: s.nodes.map((n) => (n.id === id ? { ...n, data: { ...n.data, config: { ...n.data.config, ...patch } } } : n)),
      dirty: true,
      stale: true,
      version: s.version + 1,
    }));
  },

  setLabel: (id, label) => {
    get().checkpoint("Rename", `label:${id}`);
    set((s) => ({ nodes: s.nodes.map((n) => (n.id === id ? { ...n, data: { ...n.data, label } } : n)), dirty: true }));
  },

  select: (id) => {
    if (get().selectedId === id) return;
    set((s) => ({ selectedId: id, nodes: s.nodes.map((n) => (n.selected === (n.id === id) ? n : { ...n, selected: n.id === id })) }));
  },

  selectAll: () => set((s) => ({ selectedId: null, nodes: s.nodes.map((n) => (n.selected ? n : { ...n, selected: true })) })),

  deleteSelected: (label = "Delete") => {
    const { selectedId } = get();
    const ids = new Set(get().nodes.filter((n) => n.selected || n.id === selectedId).map((n) => n.id));
    if (!ids.size && !get().edges.some((e) => e.selected)) return;
    get().checkpoint(label);
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

  load: (file, name, filePath = null) => {
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
    set((s) => ({ nodes, edges, name, filePath, autosave: { at: null, error: "", version: -1, name: null }, selectedId: null, results: {}, summaries: {}, stale: true, lastRun: null, dirty: false, version: s.version + 1, loaded: s.loaded + 1, past: [], future: [], historyKey: null, savedSig: signature(nodes, edges) }));
  },

  markSaved: (name, filePath) => {
    set((s) => ({ name, dirty: false, filePath: filePath === undefined ? s.filePath : filePath, savedSig: signature(s.nodes, s.edges) }));
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
