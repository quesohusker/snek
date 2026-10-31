import { Play, Worm } from "lucide-react";
import { useFlow } from "../store";
import { runWorkflow, useMenus } from "../commands";
import Menubar from "./Menubar";

export default function Toolbar() {
  const name = useFlow((s) => s.name);
  const dirty = useFlow((s) => s.dirty);
  const running = useFlow((s) => s.running);
  const lastRun = useFlow((s) => s.lastRun);
  const stale = useFlow((s) => s.stale);
  const count = useFlow((s) => s.nodes.length);
  const loadRecent = useFlow((s) => s.loadRecent);
  const menus = useMenus();

  return (
    <header className="toolbar">
      <div className="brand">
        <Worm size={18} /> Snek
      </div>
      <Menubar menus={menus} onOpen={(label) => label === "File" && loadRecent()} />
      <div className="wf-name" title={name ?? "Unsaved workflow"}>
        {name ?? "Untitled"}
        {dirty && <span className="dirty" title="Unsaved changes" />}
      </div>
      <button className="primary run" onClick={() => runWorkflow()} disabled={running || !count} title="Run (⌘ Enter)">
        {running ? <span className="spinner small light" /> : <Play size={15} />} Run
      </button>
      <div className="run-status">
        {lastRun && !running && (
          <span className={stale ? "muted" : ""}>
            {lastRun.errors ? <span className="err-text">{lastRun.errors} error{lastRun.errors > 1 ? "s" : ""} · </span> : null}
            {lastRun.ok} ok · {lastRun.elapsed < 1000 ? `${lastRun.elapsed} ms` : `${(lastRun.elapsed / 1000).toFixed(1)} s`}
            {stale ? " · changed" : ""}
          </span>
        )}
      </div>
    </header>
  );
}
