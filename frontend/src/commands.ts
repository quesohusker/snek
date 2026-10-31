import { useMemo } from "react";
import { useReactFlow } from "@xyflow/react";
import { useFlow } from "./store";
import { api } from "./api";
import type { Menu, MenuItem } from "./components/Menubar";
import type { ProjectInfo } from "./types";

function confirmDiscard() {
  return !useFlow.getState().dirty || confirm("Discard unsaved changes?");
}

export async function runWorkflow(fresh = false) {
  const s = useFlow.getState();
  if (s.running || !s.nodes.length) return;
  s.setRunning(true);
  try {
    if (fresh) await api.clearCache();
    const r = await api.run(s.toWorkflow());
    useFlow.getState().setResults(r.results, r.elapsed_ms);
  } catch (e) {
    alert(`Run failed: ${(e as Error).message}`);
  } finally {
    useFlow.getState().setRunning(false);
  }
}

export async function saveWorkflow() {
  const s = useFlow.getState();
  if (!s.name) return s.setDialog("saveAs");
  await api.saveWorkflow(s.name, s.toWorkflow());
  s.markSaved(s.name);
}

export async function openWorkflow(name: string) {
  if (!confirmDiscard()) return;
  const wf = await api.loadWorkflow(name);
  useFlow.getState().load(wf, name);
  useFlow.getState().setDialog(null);
}

export function newWorkflow() {
  if (confirmDiscard()) useFlow.getState().load({ version: 1, nodes: [], edges: [] }, null);
}

export async function switchProject(action: () => Promise<ProjectInfo>) {
  if (!confirmDiscard()) return false;
  const info = await action();
  const s = useFlow.getState();
  s.setProject(info);
  s.load({ version: 1, nodes: [], edges: [] }, null);
  s.setDialog(null);
  s.loadRecent();
  return true;
}

export function revealProject() {
  const project = useFlow.getState().project;
  if (project) api.reveal(project.path);
}

function recentProjectItems(project: ProjectInfo | null): MenuItem[] {
  if (!project) return [];
  const others: MenuItem[] = project.recent.filter((p) => p.path !== project.path).map((p) => ({ label: p.name, onSelect: () => switchProject(() => api.openProject(p.path)) }));
  if (project.is_examples) return others;
  const examples: MenuItem = { label: "Snek examples", onSelect: () => switchProject(() => api.openProject(project.examples)) };
  return others.length ? [...others, { type: "separator" }, examples] : [examples];
}

export function useMenus(): Menu[] {
  const { fitView, zoomIn, zoomOut } = useReactFlow();
  const count = useFlow((s) => s.nodes.length);
  const running = useFlow((s) => s.running);
  const recent = useFlow((s) => s.recent);
  const project = useFlow((s) => s.project);
  const hasSelection = useFlow((s) => s.nodes.some((n) => n.selected) || s.edges.some((e) => e.selected));
  const setDialog = useFlow((s) => s.setDialog);
  const selectAll = useFlow((s) => s.selectAll);
  const deleteSelected = useFlow((s) => s.deleteSelected);

  return useMemo<Menu[]>(
    () => [
      {
        label: "File",
        items: [
          { label: "New project…", onSelect: () => setDialog("newProject") },
          { label: "Open project folder…", onSelect: () => setDialog("openProject") },
          {
            label: "Recent projects",
            submenu: recentProjectItems(project),
          },
          { label: "Show project in Finder", onSelect: revealProject, disabled: !project },
          { type: "separator" },
          { label: "New workflow", onSelect: newWorkflow },
          { label: "Open workflow…", onSelect: () => setDialog("open") },
          { label: "Open recent", submenu: recent.map((name) => ({ label: name, onSelect: () => openWorkflow(name) })) },
          { type: "separator" },
          { label: "Save", shortcut: "⌘S", onSelect: saveWorkflow },
          { label: "Save as…", onSelect: () => setDialog("saveAs") },
          { type: "separator" },
          { label: "Export", submenu: [{ label: "Python script…", onSelect: () => setDialog("export"), disabled: !count }] },
        ],
      },
      {
        label: "Edit",
        items: [
          { label: "Select all tools", onSelect: selectAll, disabled: !count },
          { label: "Delete selected", shortcut: "Del", onSelect: deleteSelected, disabled: !hasSelection },
        ],
      },
      {
        label: "Workflow",
        items: [
          { label: "Run", shortcut: "⌘↵", onSelect: () => runWorkflow(), disabled: !count || running },
          { label: "Clear cache and run", onSelect: () => runWorkflow(true), disabled: !count || running },
        ],
      },
      {
        label: "View",
        items: [
          { label: "Fit to screen", onSelect: () => fitView({ padding: 0.2, maxZoom: 1.1, duration: 200 }) },
          { label: "Zoom in", onSelect: () => zoomIn({ duration: 150 }) },
          { label: "Zoom out", onSelect: () => zoomOut({ duration: 150 }) },
        ],
      },
    ],
    [count, running, recent, project, hasSelection, setDialog, selectAll, deleteSelected, fitView, zoomIn, zoomOut],
  );
}
