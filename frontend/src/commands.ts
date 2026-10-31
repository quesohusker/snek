import { useCallback, useMemo } from "react";
import { useReactFlow } from "@xyflow/react";
import { useFlow } from "./store";
import { api } from "./api";
import type { Menu, MenuItem } from "./components/Menubar";
import type { ProjectInfo } from "./types";
import { FILE_MANAGER, basename, dirname, keyLabel } from "./paths";
import { copyTools, cutTools, pasteTools } from "./editing";

const RECENT_FILES = "snek.recentFiles";

export function recentFiles(): string[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_FILES) ?? "[]");
  } catch {
    return [];
  }
}

function rememberFile(path: string | null | undefined) {
  if (!path) return;
  try {
    localStorage.setItem(RECENT_FILES, JSON.stringify([path, ...recentFiles().filter((p) => p !== path)].slice(0, 10)));
  } catch {
    return;
  }
}

type SaveChoice = "save" | "discard" | "cancel";

function askToSave(): Promise<SaveChoice> {
  return new Promise((resolve) => useFlow.setState({ unsavedPrompt: resolve }));
}

async function confirmDiscard() {
  if (!useFlow.getState().dirty) return true;
  const choice = await askToSave();
  useFlow.setState({ unsavedPrompt: null });
  if (choice === "cancel") return false;
  if (choice === "discard") return true;
  const s = useFlow.getState();
  if (!s.filePath && !s.name) {
    s.setDialog("saveFile");
    return false;
  }
  await saveWorkflow();
  return !useFlow.getState().dirty;
}

export async function runWorkflow(fresh = false) {
  const s = useFlow.getState();
  if (s.running || !s.nodes.length) return;
  s.setRunning(true);
  try {
    if (fresh) await api.clearCache();
    s.trustAll();
    const r = await api.run(useFlow.getState().toWorkflow());
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
      rememberFile(r.path);
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
  if (!(await confirmDiscard())) return;
  try {
    const r = await api.openFile(path);
    useFlow.getState().load(r.workflow, r.name, r.path);
    rememberFile(r.path);
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
    rememberFile(r.path);
    s.setDialog(null);
  } catch (e) {
    alert(`Save failed: ${(e as Error).message}`);
  }
}

export async function openWorkflow(name: string) {
  if (!(await confirmDiscard())) return;
  try {
    const wf = await api.loadWorkflow(name);
    const project = useFlow.getState().project;
    useFlow.getState().load(wf, name, project ? `${project.workflows}/${name}.snek` : null);
    useFlow.getState().setDialog(null);
  } catch (e) {
    alert(`Could not open ${name}: ${(e as Error).message}`);
  }
}

export async function openDroppedWorkflow(file: File) {
  if (!(await confirmDiscard())) return;
  try {
    const wf = JSON.parse(await file.text());
    useFlow.getState().load(wf, file.name.replace(/\.(snek|flow\.json)$/i, ""), null);
  } catch (e) {
    alert(`Could not open ${file.name}: ${(e as Error).message}`);
  }
}

export async function revertToSaved() {
  const s = useFlow.getState();
  if (!s.dirty || !(s.filePath || s.name)) return;
  if (!confirm("Revert to the saved version? Your unsaved changes will be lost.")) return;
  try {
    if (s.filePath) {
      const r = await api.openFile(s.filePath);
      s.load(r.workflow, r.name, r.path);
    } else if (s.name) {
      s.load(await api.loadWorkflow(s.name), s.name, s.filePath);
    }
  } catch (e) {
    alert(`Could not revert: ${(e as Error).message}`);
  }
}

export async function newWorkflow() {
  if (await confirmDiscard()) useFlow.getState().load({ version: 1, nodes: [], edges: [] }, null);
}

export async function switchProject(action: () => Promise<ProjectInfo>) {
  if (!(await confirmDiscard())) return false;
  const info = await action();
  const s = useFlow.getState();
  s.setProject(info);
  s.load({ version: 1, nodes: [], edges: [] }, null);
  s.setDialog(null);
  s.loadRecent();
  return true;
}

export async function quitSnek() {
  if (!(await confirmDiscard())) return;
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

function recentItems(workflows: string[]): MenuItem[] {
  const items: MenuItem[] = workflows.map((name) => ({ label: name, onSelect: () => openWorkflow(name) }));
  const files: MenuItem[] = recentFiles().map((path) => ({ label: `${basename(path)}  ·  ${basename(dirname(path))}`, onSelect: () => openFile(path) }));
  return items.length && files.length ? [...items, { type: "separator" }, ...files] : [...items, ...files];
}

export function useCleanUp() {
  const { fitView } = useReactFlow();
  return useCallback(() => {
    const moved = useFlow.getState().cleanUpLayout();
    setTimeout(() => fitView({ padding: 0.2, maxZoom: 1.1, duration: 250 }), moved ? 300 : 0);
  }, [fitView]);
}

export function useMenus(): Menu[] {
  const { fitView, zoomIn, zoomOut, zoomTo } = useReactFlow();
  const cleanUp = useCleanUp();
  const past = useFlow((s) => s.past);
  const future = useFlow((s) => s.future);
  const undo = useFlow((s) => s.undo);
  const redo = useFlow((s) => s.redo);
  const duplicateSelected = useFlow((s) => s.duplicateSelected);
  const selectNone = useFlow((s) => s.selectNone);
  const panels = useFlow((s) => s.panels);
  const togglePanel = useFlow((s) => s.togglePanel);
  const canRevert = useFlow((s) => s.dirty && !!(s.filePath || s.name));
  const hasTools = useFlow((s) => s.nodes.some((n) => n.selected) || !!s.selectedId);
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
          { label: "Open file…", shortcut: keyLabel("mod+O"), onSelect: () => setDialog("openFile") },
          { label: "Open autosaves…", onSelect: () => setDialog("openAutosave") },
          { label: "Open recent", submenu: recentItems(recent) },
          { label: "Close workflow", onSelect: newWorkflow },
          { type: "separator" },
          { label: "Save", shortcut: keyLabel("mod+S"), onSelect: saveWorkflow },
          { label: "Save as…", onSelect: () => setDialog("saveAs") },
          { label: "Save to file…", shortcut: keyLabel("mod+shift+S"), onSelect: () => setDialog("saveFile") },
          { label: "Revert to saved", onSelect: revertToSaved, disabled: !canRevert },
          { type: "separator" },
          { label: "Export", submenu: [{ label: "Python script…", onSelect: () => setDialog("export"), disabled: !count }] },
          { type: "separator" },
          { label: "Quit Snek", onSelect: quitSnek },
        ],
      },
      {
        label: "Edit",
        items: [
          { label: past.length ? `Undo ${past[past.length - 1].label}` : "Undo", shortcut: keyLabel("mod+Z"), onSelect: undo, disabled: !past.length },
          { label: future.length ? `Redo ${future[future.length - 1].label}` : "Redo", shortcut: keyLabel("mod+shift+Z"), onSelect: redo, disabled: !future.length },
          { type: "separator" },
          { label: "Cut", shortcut: keyLabel("mod+X"), onSelect: cutTools, disabled: !hasTools },
          { label: "Copy", shortcut: keyLabel("mod+C"), onSelect: copyTools, disabled: !hasTools },
          { label: "Paste", shortcut: keyLabel("mod+V"), onSelect: () => pasteTools() },
          { label: "Duplicate", shortcut: keyLabel("mod+D"), onSelect: duplicateSelected, disabled: !hasTools },
          { label: "Delete", shortcut: "⌫", onSelect: () => deleteSelected(), disabled: !hasSelection },
          { type: "separator" },
          { label: "Select all", shortcut: keyLabel("mod+A"), onSelect: selectAll, disabled: !count },
          { label: "Select none", shortcut: "Esc", onSelect: selectNone, disabled: !hasSelection },
          { type: "separator" },
          { label: "Settings…", onSelect: () => setDialog("settings") },
        ],
      },
      {
        label: "Workflow",
        items: [
          { label: "Run", shortcut: keyLabel("mod+↵"), onSelect: () => runWorkflow(), disabled: !count || running },
          { label: "Clear cache and run", onSelect: () => runWorkflow(true), disabled: !count || running },
          { type: "separator" },
          { label: "Create workflow with AI…", onSelect: () => setDialog("aiCreate") },
        ],
      },
      {
        label: "View",
        items: [
          { label: "Zoom in", shortcut: keyLabel("mod++"), onSelect: () => zoomIn({ duration: 150 }) },
          { label: "Zoom out", shortcut: keyLabel("mod+−"), onSelect: () => zoomOut({ duration: 150 }) },
          { label: "Actual size", shortcut: keyLabel("mod+0"), onSelect: () => zoomTo(1, { duration: 150 }) },
          { label: "Fit to screen", shortcut: keyLabel("shift+1"), onSelect: () => fitView({ padding: 0.2, maxZoom: 1.1, duration: 200 }) },
          { label: "Clean up layout", shortcut: keyLabel("shift+L"), onSelect: cleanUp, disabled: !count },
          { type: "separator" },
          { label: `${panels.palette ? "✓ " : ""}Tool palette`, onSelect: () => togglePanel("palette") },
          { label: `${panels.results ? "✓ " : ""}Results`, onSelect: () => togglePanel("results") },
          { label: `${panels.config ? "✓ " : ""}Configuration`, onSelect: () => togglePanel("config") },
        ],
      },
      {
        label: "Help",
        items: [
          { label: "Keyboard shortcuts", shortcut: keyLabel("mod+/"), onSelect: () => setDialog("shortcuts") },
          { type: "separator" },
          { label: "Check for updates…", onSelect: checkForUpdates },
          { label: `${update?.enabled === false ? "" : "✓ "}Check for updates automatically`, onSelect: toggleUpdateChecks },
          { type: "separator" },
          { label: "Snek on GitHub", onSelect: () => window.open(REPO, "_blank") },
          { label: "Report a problem", onSelect: () => window.open(`${REPO}/issues/new`, "_blank") },
          { label: "About Snek", onSelect: () => setDialog("about") },
        ],
      },
    ],
    [count, running, recent, project, update, hasSelection, hasTools, past, future, panels, canRevert, setDialog, selectAll, selectNone, deleteSelected, duplicateSelected, undo, redo, togglePanel, fitView, zoomIn, zoomOut, zoomTo, cleanUp],
  );
}
