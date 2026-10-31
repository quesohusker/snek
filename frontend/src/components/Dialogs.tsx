import { useEffect, useState } from "react";
import { Copy, Download } from "lucide-react";
import { useFlow } from "../store";
import { api } from "../api";
import { REPO, openFile, openWorkflow, saveToFile, switchProject } from "../commands";
import Modal from "./Modal";
import FilePicker from "./FilePicker";
import { FILE_MANAGER, joinPath } from "../paths";

export default function Dialogs() {
  const dialog = useFlow((s) => s.dialog);
  const setDialog = useFlow((s) => s.setDialog);
  const close = () => setDialog(null);
  if (dialog === "open") return <OpenDialog onClose={close} />;
  if (dialog === "saveAs") return <SaveDialog onClose={close} />;
  if (dialog === "export") return <ExportDialog onClose={close} />;
  if (dialog === "newProject") return <NewProjectDialog onClose={close} />;
  if (dialog === "openProject") return <OpenProjectDialog onClose={close} />;
  if (dialog === "about") return <AboutDialog onClose={close} />;
  if (dialog === "openFile") return <OpenFileDialog onClose={close} />;
  if (dialog === "saveFile") return <SaveFileDialog onClose={close} />;
  if (dialog === "settings") return <SettingsDialog onClose={close} />;
  if (dialog === "openAutosave") return <OpenAutosaveDialog onClose={close} />;
  return null;
}

function OpenFileDialog({ onClose }: { onClose: () => void }) {
  const project = useFlow((s) => s.project);
  const filePath = useFlow((s) => s.filePath);
  return <FilePicker initial={filePath ?? (project ? `${project.workflows}/` : "")} mode="open" title="Open a .snek file" onClose={onClose} onPick={openFile} />;
}

function SaveFileDialog({ onClose }: { onClose: () => void }) {
  const project = useFlow((s) => s.project);
  const filePath = useFlow((s) => s.filePath);
  const name = useFlow((s) => s.name);
  const initial = filePath ?? (project ? joinPath(project.workflows, `${name ?? "Untitled"}.snek`) : `${name ?? "Untitled"}.snek`);
  return <FilePicker initial={initial} mode="save" title="Save as a .snek file" onClose={onClose} onPick={saveToFile} />;
}

function OpenAutosaveDialog({ onClose }: { onClose: () => void }) {
  const folder = useFlow((s) => s.settings?.autosave_folder ?? "~/.snek/autosave");
  return <FilePicker initial={`${folder}/`} mode="open" title="Open an autosaved workflow" onClose={onClose} onPick={openFile} />;
}

function SettingsDialog({ onClose }: { onClose: () => void }) {
  const settings = useFlow((s) => s.settings);
  const update = useFlow((s) => s.update);
  const [minutes, setMinutes] = useState(String(settings?.autosave_minutes ?? 5));
  const [mode, setMode] = useState(settings?.autosave_mode ?? "file");
  const [checks, setChecks] = useState(update?.enabled ?? true);
  const [error, setError] = useState("");
  const save = async () => {
    try {
      const saved = await api.saveSettings({ autosave_minutes: Number(minutes), autosave_mode: mode });
      useFlow.getState().setSettings(saved);
      if (checks !== (update?.enabled ?? true)) useFlow.getState().setUpdate(await api.updateSettings(checks));
      onClose();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <Modal
      title="Settings"
      onClose={onClose}
      footer={
        <button className="primary" onClick={save}>
          Save settings
        </button>
      }
    >
      <h3 className="settings-head">Autosave</h3>
      <label className="field">
        <span>Autosave every (minutes, 0 = off)</span>
        <input type="number" min={0} max={240} value={minutes} onChange={(e) => setMinutes(e.target.value)} />
      </label>
      <label className="field">
        <span>Autosave saves</span>
        <select value={mode} onChange={(e) => setMode(e.target.value as "file" | "backup")}>
          <option value="file">My workflow file (untitled work goes to the autosave folder)</option>
          <option value="backup">Separate backup copies only</option>
        </select>
      </label>
      <p className="muted">
        Autosave folder: <code>{settings?.autosave_folder}</code>{" "}
        <button type="button" className="link-btn" onClick={() => settings && api.reveal(settings.autosave_folder).catch(() => setError("No autosaves yet."))}>
          Show in {FILE_MANAGER}
        </button>
      </p>
      <h3 className="settings-head">Updates</h3>
      <label className="field field-bool">
        <input type="checkbox" checked={checks} onChange={(e) => setChecks(e.target.checked)} />
        <span>Check GitHub once a day for a newer version</span>
      </label>
      {error && <div className="error-box">{error}</div>}
    </Modal>
  );
}

function AboutDialog({ onClose }: { onClose: () => void }) {
  const update = useFlow((s) => s.update);
  return (
    <Modal title="About Snek" onClose={onClose}>
      <p>
        <strong>Snek {update?.current ?? ""}</strong>: a visual workflow canvas for pandas. Free for personal, noncommercial use under the PolyForm Strict License 1.0.0.
      </p>
      {!update ? (
        <p className="muted">Checking for updates…</p>
      ) : update.error ? (
        <div className="warn-box">{update.error}</div>
      ) : update.update ? (
        <p>
          Snek {update.latest?.replace(/^v/, "")} is available.{" "}
          <a href={update.url ?? `${REPO}/releases/latest`} target="_blank" rel="noreferrer">
            Download it
          </a>
        </p>
      ) : update.latest ? (
        <p className="muted">You have the latest version.</p>
      ) : null}
      <p className="muted">
        Update checks ask GitHub once a day whether a newer release exists. They send nothing about you or your data. Turn them off in Help ▸ Check for updates automatically.
      </p>
      <p>
        <a href={REPO} target="_blank" rel="noreferrer">
          {REPO.replace("https://", "")}
        </a>
      </p>
    </Modal>
  );
}

function OpenProjectDialog({ onClose }: { onClose: () => void }) {
  const [error, setError] = useState("");
  return (
    <>
      <FilePicker
        initial="~/Documents"
        mode="folder"
        title="Open project folder"
        onClose={onClose}
        onPick={(path) => switchProject(() => api.openProject(path)).catch((e) => setError((e as Error).message))}
      />
      {error && (
        <Modal title="Could not open project" onClose={() => setError("")}>
          <div className="error-box">{error}</div>
        </Modal>
      )}
    </>
  );
}

function NewProjectDialog({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [parent, setParent] = useState("~/Documents/Snek Projects");
  const [browsing, setBrowsing] = useState(false);
  const [error, setError] = useState("");
  const create = () => switchProject(() => api.newProject(parent, name.trim())).catch((e) => setError((e as Error).message));
  if (browsing) {
    return (
      <FilePicker
        initial={parent}
        mode="folder"
        title="Where should the project live?"
        onClose={() => setBrowsing(false)}
        onPick={(p) => {
          setParent(p);
          setBrowsing(false);
        }}
      />
    );
  }
  return (
    <Modal
      title="New project"
      onClose={onClose}
      footer={
        <button className="primary" disabled={!name.trim()} onClick={create}>
          Create project
        </button>
      }
    >
      <p className="muted">A project is a folder for one piece of analysis. Snek creates data, output and workflows folders inside it. Relative paths in this project's workflows start from the project folder.</p>
      <label className="field">
        <span>Name</span>
        <input autoFocus value={name} placeholder="e.g. Nebraska 2025" onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && name.trim() && create()} />
      </label>
      <label className="field">
        <span>Location</span>
        <div className="file-field">
          <input value={parent} onChange={(e) => setParent(e.target.value)} spellCheck={false} />
          <button type="button" onClick={() => setBrowsing(true)}>
            Browse
          </button>
        </div>
      </label>
      {name.trim() && <p className="muted">Creates {joinPath(parent, name.trim())}</p>}
      {error && <div className="error-box">{error}</div>}
    </Modal>
  );
}

function OpenDialog({ onClose }: { onClose: () => void }) {
  const [items, setItems] = useState<{ name: string; modified: string }[] | null>(null);
  const [folder, setFolder] = useState("");
  useEffect(() => {
    api.listWorkflows().then((r) => {
      setItems(r.workflows);
      setFolder(r.folder);
    });
  }, []);
  return (
    <Modal title="Open workflow" onClose={onClose}>
      <p className="muted">{folder}</p>
      <ul className="open-list">
        {items?.map((w) => (
          <li key={w.name} onClick={() => openWorkflow(w.name)}>
            <strong>{w.name}</strong>
            <span className="muted">{w.modified.replace("T", " ")}</span>
          </li>
        ))}
        {items && !items.length && <li className="muted">No saved workflows yet.</li>}
      </ul>
    </Modal>
  );
}

function SaveDialog({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState(useFlow.getState().name ?? "");
  const [error, setError] = useState("");
  const save = async () => {
    try {
      const r = await api.saveWorkflow(name.trim(), useFlow.getState().toWorkflow());
      useFlow.getState().markSaved(name.trim(), r.path);
      onClose();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <Modal
      title="Save workflow"
      onClose={onClose}
      footer={
        <button className="primary" disabled={!name.trim()} onClick={save}>
          Save
        </button>
      }
    >
      <label className="field">
        <span>Name</span>
        <input autoFocus value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && name.trim() && save()} />
      </label>
      {error && <div className="error-box">{error}</div>}
    </Modal>
  );
}

function ExportDialog({ onClose }: { onClose: () => void }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const name = useFlow((s) => s.name) ?? "workflow";
  useEffect(() => {
    api
      .exportCode(useFlow.getState().toWorkflow(), name)
      .then((r) => setCode(r.code))
      .catch((e) => setError(e.message));
  }, [name]);
  const download = () => {
    const url = URL.createObjectURL(new Blob([code], { type: "text/x-python" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${name.replace(/[^\w-]+/g, "_")}.py`;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <Modal
      title="Export as Python"
      onClose={onClose}
      wide
      footer={
        <>
          <button onClick={() => navigator.clipboard.writeText(code)} disabled={!code}>
            <Copy size={15} /> Copy
          </button>
          <button className="primary" onClick={download} disabled={!code}>
            <Download size={15} /> Download .py
          </button>
        </>
      }
    >
      <p className="muted">A standalone script that runs the same pandas code as the canvas. It needs only pandas, numpy and the readers for your file types.</p>
      {error ? <div className="error-box">{error}</div> : <pre className="code-view tall">{code || "Generating…"}</pre>}
    </Modal>
  );
}
