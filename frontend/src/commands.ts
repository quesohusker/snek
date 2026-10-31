import { useMemo } from "react";
import { useReactFlow } from "@xyflow/react";
import { useFlow } from "./store";
import { api } from "./api";
import type { Menu, MenuItem } from "./components/Menubar";
import type { ProjectInfo } from "./types";
import { FILE_MANAGER } from "./paths";

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
  try {
    if (s.filePath) {
      const r = await api.saveFile(s.filePath, s.toWorkflow());
      s.markSaved(r.name, r.path);
      return;
    }
    if (!s.name) return s.setDialog("saveAs");
    const r = await api.saveWorkflow(s.name, s.toWorkflow());
    s.markSaved(s.name, r.path);
  } catch (e) {
    alert(`Save failed: ${(e as Error).message}`);
  }
}

function stamp() {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}${pad(d.getMinutes())}`;
}

export async function autosaveNow() {
  const s = useFlow.getState();
  if (!s.dirty || !s.nodes.length || s.autosave.version === s.version) return;
  const mode = s.settings?.autosave_mode ?? "file";
  const version = s.version;
  try {
    if (mode === "file" && s.filePath) {
      const r = await api.saveFile(s.filePath, s.toWorkflow());
      s.markSaved(r.name, r.path);
    } else if (mode === "file" && s.name) {
      const r = await api.saveWorkflow(s.name, s.toWorkflow());
      s.markSaved(s.name, r.path);
    } else {
      const name = s.name ?? s.autosave.name ?? `Untitled ${stamp()}`;
      await api.autosave(s.toWorkflow(), name);
      useFlow.setState((st) => ({ autosave: { ...st.autosave, name: st.name ? st.autosave.name : name } }));
    }
    useFlow.setState((st) => ({ autosave: { ...st.autosave, at: new Date().toISOString(), error: "", version } }));
  } catch (e) {
    useFlow.setState((st) => ({ autosave: { ...st.autosave, error: (e as Error).message } }));
  }
}

export async function openFile(path: string) {
  if (!confirmDiscard()) return;
  try {
    const r = await api.openFile(path);
    useFlow.getState().load(r.workflow, r.name, r.path);
    useFlow.getState().setDialog(null);
  } catch (e) {
    alert(`Could not open ${path}: ${(e as Error).message}`);
  }
}

export async function saveToFile(path: string) {
  const s = useFlow.getState();
  try {
    const r = await api.saveFile(path, s.toWorkflow());
    s.markSaved(r.name, r.path);
    s.setDialog(null);
  } catch (e) {
    alert(`Save failed: ${(e as Error).message}`);
  }
}

export async function openWorkflow(name: string) {
  if (!confirmDiscard()) return;
  try {
    const wf = await api.loadWorkflow(name);
    const project = useFlow.getState().project;
    useFlow.getState().load(wf, name, project ? `${project.workflows}/${name}.snek` : null);
    useFlow.getState().setDialog(null);
  } catch (e) {
    alert(`Could not open ${name}: ${(e as Error).message}`);
  }
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

export async function quitSnek() {
  if (!confirmDiscard()) return;
  await api.shutdown().catch(() => undefined);
  useFlow.setState({ stopped: true });
}

export const REPO = "https://github.com/quesohusker/snek";

export async function checkForUpdates() {
  const s = useFlow.getState();
  s.setDialog("about");
  s.setUpdate(await api.update(true));
}

export async function toggleUpdateChecks() {
  const current = useFlow.getState().update?.enabled ?? true;
  useFlow.getState().setUpdate(await api.updateSettings(!current));
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
  const update = useFlow((s) => s.update);

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
          { label: `Show project in ${FILE_MANAGER}`, onSelect: revealProject, disabled: !project },
          { type: "separator" },
          { label: "New workflow", onSelect: newWorkflow },
          { label: "Open workflow…", onSelect: () => setDialog("open") },
          { label: "Open file…", onSelect: () => setDialog("openFile") },
          { label: "Open autosaves…", onSelect: () => setDialog("openAutosave") },
          { label: "Open recent", submenu: recent.map((name) => ({ label: name, onSelect: () => openWorkflow(name) })) },
          { type: "separator" },
          { label: "Save", shortcut: "⌘S", onSelect: saveWorkflow },
          { label: "Save as…", onSelect: () => setDialog("saveAs") },
          { label: "Save to file…", onSelect: () => setDialog("saveFile") },
          { type: "separator" },
          { label: "Export", submenu: [{ label: "Python script…", onSelect: () => setDialog("export"), disabled: !count }] },
          { type: "separator" },
          { label: "Quit Snek", onSelect: quitSnek },
        ],
      },
      {
        label: "Edit",
        items: [
          { label: "Select all tools", onSelect: selectAll, disabled: !count },
          { label: "Delete selected", shortcut: "Del", onSelect: deleteSelected, disabled: !hasSelection },
          { type: "separator" },
          { label: "Settings…", onSelect: () => setDialog("settings") },
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
      {
        label: "Help",
        items: [
          { label: "Check for updates…", onSelect: checkForUpdates },
          { label: `${update?.enabled === false ? "" : "✓ "}Check for updates automatically`, onSelect: toggleUpdateChecks },
          { type: "separator" },
          { label: "Snek on GitHub", onSelect: () => window.open(REPO, "_blank") },
          { label: "Report a problem", onSelect: () => window.open(`${REPO}/issues/new`, "_blank") },
          { label: "About Snek", onSelect: () => setDialog("about") },
        ],
      },
    ],
    [count, running, recent, project, update, hasSelection, setDialog, selectAll, deleteSelected, fitView, zoomIn, zoomOut],
  );
}
