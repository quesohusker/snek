import { useEffect, useState } from "react";
import { Copy, Download } from "lucide-react";
import { useFlow } from "../store";
import { api } from "../api";
import { openWorkflow } from "../commands";
import Modal from "./Modal";

export default function Dialogs() {
  const dialog = useFlow((s) => s.dialog);
  const setDialog = useFlow((s) => s.setDialog);
  const close = () => setDialog(null);
  if (dialog === "open") return <OpenDialog onClose={close} />;
  if (dialog === "saveAs") return <SaveDialog onClose={close} />;
  if (dialog === "export") return <ExportDialog onClose={close} />;
  return null;
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
      await api.saveWorkflow(name.trim(), useFlow.getState().toWorkflow());
      useFlow.getState().markSaved(name.trim());
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
