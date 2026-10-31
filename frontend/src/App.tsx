import { useEffect, useRef, useState } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import { useFlow } from "./store";
import { api } from "./api";
import Toolbar from "./components/Toolbar";
import CategoryBar from "./components/CategoryBar";
import Dialogs from "./components/Dialogs";
import { autosaveNow } from "./commands";
import Shortcuts from "./components/Shortcuts";
import Palette from "./components/Palette";
import Canvas from "./components/Canvas";
import ConfigPanel from "./components/ConfigPanel";
import ResultsPanel from "./components/ResultsPanel";
import type { WorkflowFile } from "./types";

const STORAGE_KEY = "snek.current";
const HEIGHT_KEY = "snek.resultsHeight";

function readStorage<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    return;
  }
}

export default function App() {
  const [ready, setReady] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [height, setHeight] = useState(() => readStorage<number>(HEIGHT_KEY) ?? 300);
  const version = useFlow((s) => s.version);
  const stopped = useFlow((s) => s.stopped);
  const autosaveMinutes = useFlow((s) => s.settings?.autosave_minutes ?? 0);
  const dragging = useRef(false);
  const panels = useFlow((s) => s.panels);

  useEffect(() => {
    Promise.all([api.tools(), api.project()])
      .then(([{ tools, categories }, project]) => {
        useFlow.getState().setTools(tools, categories);
        useFlow.getState().setProject(project);
        const saved = readStorage<{ name: string | null; workflow: WorkflowFile; dirty: boolean; project?: string; filePath?: string | null }>(STORAGE_KEY);
        const toOpen = new URLSearchParams(window.location.search).get("open");
        if (toOpen) {
          window.history.replaceState(null, "", window.location.pathname);
          api
            .openFile(toOpen)
            .then((r) => useFlow.getState().load(r.workflow, r.name, r.path))
            .catch((e) => alert(`Could not open ${toOpen}: ${e.message}`));
        } else if (saved?.workflow && saved.project === project.path) {
          useFlow.getState().load(saved.workflow, saved.name, saved.filePath ?? null);
          useFlow.setState(saved.dirty ? { dirty: true, savedSig: "" } : { dirty: false });
        }
        useFlow.getState().loadRecent();
        api
          .settings()
          .then((st) => useFlow.getState().setSettings(st))
          .catch(() => undefined);
        api
          .update()
          .then((u) => useFlow.getState().setUpdate(u))
          .catch(() => undefined);
        setReady(true);
      })
      .catch((e) => setLoadError(String(e.message ?? e)));
  }, []);

  useEffect(() => {
    if (!ready) return;
    const t = setTimeout(() => {
      const s = useFlow.getState();
      writeStorage(STORAGE_KEY, { name: s.name, workflow: s.toWorkflow(), dirty: s.dirty, project: s.project?.path, filePath: s.filePath });
      api
        .summaries(s.toWorkflow())
        .then((r) => useFlow.getState().setSummaries(r.summaries))
        .catch(() => undefined);
    }, 250);
    return () => clearTimeout(t);
  }, [version, ready]);

  useEffect(() => {
    if (!ready) return;
    return useFlow.subscribe((s, prev) => {
      if (s.nodes !== prev.nodes || s.name !== prev.name || s.dirty !== prev.dirty || s.project !== prev.project || s.filePath !== prev.filePath) {
        writeStorage(STORAGE_KEY, { name: s.name, workflow: s.toWorkflow(), dirty: s.dirty, project: s.project?.path, filePath: s.filePath });
      }
    });
  }, [ready]);

  useEffect(() => {
    if (!ready || autosaveMinutes <= 0) return;
    const timer = window.setInterval(autosaveNow, autosaveMinutes * 60_000);
    return () => window.clearInterval(timer);
  }, [ready, autosaveMinutes]);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      setHeight(Math.min(Math.max(window.innerHeight - e.clientY, 120), window.innerHeight - 200));
    };
    const onUp = () => {
      if (dragging.current) {
        dragging.current = false;
        document.body.classList.remove("resizing");
        setHeight((h) => {
          writeStorage(HEIGHT_KEY, h);
          return h;
        });
      }
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  if (stopped)
    return (
      <div className="boot">
        <h2>Snek has stopped</h2>
        <p className="muted">You can close this tab. Start Snek again to keep working; your saved workflows are in your project folder.</p>
      </div>
    );
  if (loadError) return <div className="boot error-box">Cannot reach the Snek server: {loadError}</div>;
  if (!ready) return <div className="boot muted">Loading…</div>;

  return (
    <ReactFlowProvider>
      <Shortcuts />
      <div className="app">
        <Toolbar />
        <CategoryBar />
        <div className={`main${panels.palette ? "" : " no-palette"}${panels.config ? "" : " no-config"}`}>
          {panels.palette && <Palette />}
          <div className={`center${panels.results ? "" : " no-results"}`} style={{ gridTemplateRows: panels.results ? `minmax(0, 1fr) 6px ${height}px` : "minmax(0, 1fr)" }}>
            <Canvas />
            <div
              className="splitter"
              onMouseDown={() => {
                dragging.current = true;
                document.body.classList.add("resizing");
              }}
            />
            <ResultsPanel />
          </div>
          {panels.config && <ConfigPanel />}
        </div>
        <Dialogs />
      </div>
    </ReactFlowProvider>
  );
}
