import { useEffect, useState } from "react";
import { Copy, Download } from "lucide-react";
import { useFlow } from "../store";
import { api, type AIInfo, type AIResult, type Connections } from "../api";
import { REPO, openFile, openWorkflow, saveToFile, switchProject } from "../commands";
import Modal from "./Modal";
import FilePicker from "./FilePicker";
import KeyBox from "./KeyBox";
import { FILE_MANAGER, joinPath, keyLabel } from "../paths";

export default function Dialogs() {
  const dialog = useFlow((s) => s.dialog);
  const setDialog = useFlow((s) => s.setDialog);
  const prompt = useFlow((s) => s.unsavedPrompt);
  const close = () => setDialog(null);
  if (prompt) return <UnsavedDialog choose={prompt} />;
  if (dialog === "shortcuts") return <ShortcutsDialog onClose={close} />;
  if (dialog === "aiCreate") return <AICreateDialog onClose={close} />;
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
      <ConnectionSettings />
      <AISettings />
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

function UnsavedDialog({ choose }: { choose: (choice: "save" | "discard" | "cancel") => void }) {
  const name = useFlow((s) => s.name);
  return (
    <Modal
      title={`Save changes to “${name ?? "Untitled"}”?`}
      onClose={() => choose("cancel")}
      footer={
        <>
          <button onClick={() => choose("discard")}>Don’t save</button>
          <span className="spacer" />
          <button onClick={() => choose("cancel")}>Cancel</button>
          <button className="primary" autoFocus onClick={() => choose("save")}>
            Save
          </button>
        </>
      }
    >
      <p>Your changes will be lost if you don’t save them.</p>
    </Modal>
  );
}

const SHORTCUTS: [string, string][] = [
  ["Run the workflow", "mod+↵"],
  ["Save", "mod+S"],
  ["Save to file", "mod+shift+S"],
  ["Open file", "mod+O"],
  ["Undo", "mod+Z"],
  ["Redo", "mod+shift+Z"],
  ["Cut, copy, paste tools", "mod+X / C / V"],
  ["Duplicate", "mod+D"],
  ["Select all", "mod+A"],
  ["Select none", "Esc"],
  ["Delete selected", "⌫"],
  ["Zoom in", "mod++"],
  ["Zoom out", "mod+−"],
  ["Actual size", "mod+0"],
  ["Fit to screen", "shift+1"],
  ["Clean up layout", "shift+L"],
  ["Keyboard shortcuts", "mod+/"],
];

function ShortcutsDialog({ onClose }: { onClose: () => void }) {
  return (
    <Modal title="Keyboard shortcuts" onClose={onClose}>
      <table className="shortcut-table">
        <tbody>
          {SHORTCUTS.map(([what, keys]) => (
            <tr key={what}>
              <td>{what}</td>
              <td>
                <kbd>{keyLabel(keys)}</kbd>
              </td>
            </tr>
          ))}
          <tr>
            <td>Select several tools</td>
            <td>
              <kbd>{keyLabel("shift+click")}</kbd> or drag a box on the canvas
            </td>
          </tr>
          <tr>
            <td>Pan the canvas</td>
            <td>Scroll, or hold Space and drag</td>
          </tr>
          <tr>
            <td>Zoom with the mouse</td>
            <td>
              <kbd>{keyLabel("mod+scroll")}</kbd> or pinch
            </td>
          </tr>
          <tr>
            <td>Menu for a tool or the canvas</td>
            <td>Right-click</td>
          </tr>
        </tbody>
      </table>
      <p className="muted">Paste a table copied from Excel or a CSV onto the canvas to make a Type or Paste Data step. Drop a data file on the canvas to add an Open File step.</p>
    </Modal>
  );
}

function ConnectionSettings() {
  const [info, setInfo] = useState<Connections | null>(null);
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    api.connections().then(setInfo).catch((e) => setError(e.message));
  }, []);
  const save = async (keyName: string, value: string, clear: () => void) => {
    try {
      setInfo(await api.saveConnection(keyName, value));
      setError("");
      clear();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const remove = async (keyName: string) => setInfo(await api.deleteConnection(keyName));
  const declared = info?.keys.filter((k) => k.declared) ?? [];
  const others = info?.keys.filter((k) => k.name !== "anthropic" && !k.declared && k.saved) ?? [];
  return (
    <>
      {declared.map((k) => (
        <div key={k.name}>
          <h3 className="settings-head">{k.declared!.section}</h3>
          <KeyBox name={k.name} />
        </div>
      ))}
      <h3 className="settings-head">Data Connections</h3>
      <div className="field">
        <span>API keys, by name, for API Request and add-on tools</span>
        {others.map((k) => (
          <div key={k.name} className="key-row saved-key">
            <code>{k.name}</code>
            <span className="muted">{k.hint}</span>
            <button onClick={() => remove(k.name)}>Remove</button>
          </div>
        ))}
        <div className="key-row">
          <input value={name} placeholder="name, e.g. weather" onChange={(e) => setName(e.target.value.toLowerCase())} />
          <input type="password" autoComplete="off" value={key} placeholder="key" onChange={(e) => setKey(e.target.value)} />
          <button disabled={!name.trim() || !key.trim()} onClick={() => save(name.trim(), key, () => (setName(""), setKey("")))}>
            Add key
          </button>
        </div>
      </div>
      <p className="muted">Keys are saved on this computer only, in {info?.file ?? "~/.snek/connections.json"}. They never go into workflows or exported scripts; exported scripts read the same file or an environment variable named after the key, such as WEATHER_API_KEY.</p>
      {error && <div className="error-box">{error}</div>}
    </>
  );
}

const AI_EXAMPLES = [
  "Average body mass by species and sex from the penguins data, as a bar chart",
  "Rate the teams in the made-up football league with a 28-point margin cap, simulate the unplayed games, and chart projected wins",
  "Monthly flight counts by airline from the Q1 flights files, then forecast the next 4 weeks of daily departures",
];

function placeWorkflow(result: AIResult) {
  const s = useFlow.getState();
  const bottom = s.nodes.length ? Math.max(...s.nodes.map((n) => n.position.y)) + 180 : 60;
  const left = s.nodes.length ? Math.min(...s.nodes.map((n) => n.position.x)) : 60;
  s.pasteData(
    {
      format: "snek-clipboard",
      version: 1,
      nodes: result.workflow.nodes.map((n) => ({ id: String(n.id), type: n.type, label: n.label ?? "", position: n.position ?? { x: 0, y: 0 }, config: n.config, trusted: n.trusted })),
      edges: result.workflow.edges.map((e) => ({ source: String(e.source), sourceHandle: e.sourceHandle ?? "out", target: String(e.target), targetHandle: e.targetHandle ?? "in" })),
    },
    { x: left, y: bottom },
  );
}

function AICreateDialog({ onClose }: { onClose: () => void }) {
  const [info, setInfo] = useState<AIInfo | null>(null);
  const [request, setRequest] = useState("");
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<AIResult | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  useEffect(() => {
    api.aiInfo().then((i) => {
      setInfo(i);
      setModel(i.model);
    });
  }, []);
  const create = async () => {
    setBusy(true);
    setError("");
    try {
      const r = await api.aiWorkflow(request, model);
      placeWorkflow(r);
      setResult(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const hasKey = !!info && (info.key_saved || info.key_from_env);
  const failed = result ? Object.keys(result.errors).length : 0;
  return (
    <Modal
      title="Create a workflow with AI"
      wide
      onClose={busy ? () => undefined : onClose}
      footer={
        result ? (
          <button className="primary" onClick={onClose}>
            Done
          </button>
        ) : (
          <>
            <select value={model} onChange={(e) => setModel(e.target.value)} disabled={busy}>
              {info?.models.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
            <span className="spacer" />
            <button onClick={onClose} disabled={busy}>
              Cancel
            </button>
            <button className="primary" disabled={busy || !request.trim() || !hasKey} onClick={create}>
              {busy ? <span className="spinner small light" /> : null} {busy ? "Building…" : "Create workflow"}
            </button>
          </>
        )
      }
    >
      {result ? (
        <>
          <p>{result.summary}</p>
          <p className="muted">
            Added {result.workflow.nodes.length} tools to the canvas. Snek ran the workflow {result.rounds === 1 ? "once and found no problems" : `and sent Claude ${result.rounds - 1} round${result.rounds > 2 ? "s" : ""} of fixes`}. Undo removes it in one step.
          </p>
          {failed > 0 && <div className="warn-box">{failed} tool{failed > 1 ? "s still need" : " still needs"} attention: {Object.values(result.errors).join("; ")}</div>}
          <p className="muted">
            Used {result.usage.input.toLocaleString()} input tokens ({result.usage.cache_read.toLocaleString()} from cache) and {result.usage.output.toLocaleString()} output tokens on {result.model}.
          </p>
        </>
      ) : (
        <>
          {info && !hasKey && (
            <div className="warn-box">
              Add your Anthropic API key in Edit ▸ Settings ▸ AI first.{" "}
              <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noreferrer">
                Get a key
              </a>
            </div>
          )}
          <label className="field">
            <span>Describe what you want</span>
            <textarea autoFocus rows={5} value={request} disabled={busy} onChange={(e) => setRequest(e.target.value)} placeholder={AI_EXAMPLES[0]} />
          </label>
          <div className="ai-examples">
            {AI_EXAMPLES.map((ex) => (
              <button key={ex} className="link-btn" disabled={busy} onClick={() => setRequest(ex)}>
                {ex}
              </button>
            ))}
          </div>
          {busy && <p className="muted">Claude is designing the workflow, then Snek runs it and sends back any errors to fix. This usually takes under a minute.</p>}
          <p className="muted">
            Snek sends Claude your description, the list of tools, and the names and column names of the data files in this project. It never sends the data itself.{" "}
            <button className="link-btn" onClick={() => api.aiContext(request).then((r) => setPreview(r.text))}>
              Show exactly what is sent
            </button>
          </p>
          {preview && <pre className="ai-preview">{preview}</pre>}
          {error && <div className="error-box">{error}</div>}
        </>
      )}
    </Modal>
  );
}

function AISettings() {
  const [info, setInfo] = useState<AIInfo | null>(null);
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  const load = () => api.aiInfo().then(setInfo);
  useEffect(() => {
    load();
  }, []);
  const saveKey = async () => {
    try {
      await api.saveConnection("anthropic", key);
      setKey("");
      setError("");
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const saveModel = async (model: string) => {
    useFlow.getState().setSettings(await api.saveSettings({ ai_model: model }));
    load();
  };
  return (
    <>
      <h3 className="settings-head">AI</h3>
      <label className="field">
        <span>
          Anthropic API key, for Create workflow with AI{" "}
          <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noreferrer">
            get a key
          </a>
        </span>
        <div className="key-row">
          <input type="password" autoComplete="off" value={key} placeholder={info?.key_saved ? `Saved (${info.key_hint})` : info?.key_from_env ? "Using ANTHROPIC_API_KEY" : "Paste your key"} onChange={(e) => setKey(e.target.value)} />
          <button disabled={!key.trim()} onClick={saveKey}>
            Save key
          </button>
          {info?.key_saved && (
            <button
              onClick={async () => {
                await api.deleteConnection("anthropic");
                load();
              }}
            >
              Remove
            </button>
          )}
        </div>
      </label>
      <label className="field">
        <span>Model</span>
        <select value={info?.model ?? ""} onChange={(e) => saveModel(e.target.value)}>
          {info?.models.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </label>
      <p className="muted">Anthropic bills your account for each request. Create workflow with AI sends column names, not data.</p>
      {error && <div className="error-box">{error}</div>}
    </>
  );
}
