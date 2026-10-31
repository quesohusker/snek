import { useEffect, useRef, useState } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import { useFlow } from "./store";
import { api } from "./api";
import Toolbar from "./components/Toolbar";
import Dialogs from "./components/Dialogs";
import { runWorkflow, saveWorkflow } from "./commands";
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
  const dragging = useRef(false);

  useEffect(() => {
    Promise.all([api.tools(), api.project()])
      .then(([{ tools, categories }, project]) => {
        useFlow.getState().setTools(tools, categories);
        useFlow.getState().setProject(project);
        const saved = readStorage<{ name: string | null; workflow: WorkflowFile; dirty: boolean; project?: string }>(STORAGE_KEY);
        if (saved?.workflow && saved.project === project.path) {
          useFlow.getState().load(saved.workflow, saved.name);
          useFlow.setState({ dirty: !!saved.dirty });
        }
        useFlow.getState().loadRecent();
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
      writeStorage(STORAGE_KEY, { name: s.name, workflow: s.toWorkflow(), dirty: s.dirty, project: s.project?.path });
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
      if (s.nodes !== prev.nodes || s.name !== prev.name || s.dirty !== prev.dirty || s.project !== prev.project) {
        writeStorage(STORAGE_KEY, { name: s.name, workflow: s.toWorkflow(), dirty: s.dirty, project: s.project?.path });
      }
    });
  }, [ready]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      if (e.key === "Enter") {
        e.preventDefault();
        runWorkflow();
      } else if (e.key === "s") {
        e.preventDefault();
        saveWorkflow();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
      <div className="app">
        <Toolbar />
        <div className="main">
          <Palette />
          <div className="center" style={{ gridTemplateRows: `minmax(0, 1fr) 6px ${height}px` }}>
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
          <ConfigPanel />
        </div>
        <Dialogs />
      </div>
    </ReactFlowProvider>
  );
}
