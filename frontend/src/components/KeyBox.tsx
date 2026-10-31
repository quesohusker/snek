import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { api, type ConnectionKey } from "../api";
import { useFlow } from "../store";

export default function KeyBox({ name }: { name: string }) {
  const [info, setInfo] = useState<ConnectionKey | null>(null);
  const [value, setValue] = useState("");
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState("");
  const load = () => api.connections().then((c) => setInfo(c.keys.find((k) => k.name === name) ?? { name, saved: false, hint: "", env: "", from_env: false }));
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [name]);
  const changed = () => useFlow.setState((s) => ({ version: s.version + 1, stale: true }));
  const save = async () => {
    try {
      await api.saveConnection(name, value);
      setValue("");
      setEditing(false);
      setError("");
      await load();
      changed();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const remove = async () => {
    await api.deleteConnection(name);
    await load();
    changed();
  };
  if (!info) return null;
  const label = info.declared?.label ?? `${name} API key`;
  if ((info.saved || info.from_env) && !editing) {
    return (
      <div className="key-box ok">
        <Check size={14} /> {label} {info.saved ? `saved (${info.hint})` : `from ${info.env}`}
        <span className="spacer" />
        <button className="link-btn" onClick={() => setEditing(true)}>
          Change
        </button>
        {info.saved && (
          <button className="link-btn" onClick={remove}>
            Remove
          </button>
        )}
      </div>
    );
  }
  return (
    <div className="key-box">
      <div className="key-box-head">
        <strong>{label}</strong>
        {info.declared?.url && (
          <a href={info.declared.url} target="_blank" rel="noreferrer">
            Get a free key
          </a>
        )}
      </div>
      <div className="key-row">
        <input type="password" autoComplete="off" value={value} placeholder="Paste your key" onChange={(e) => setValue(e.target.value)} onKeyDown={(e) => e.key === "Enter" && value.trim() && save()} />
        <button className="primary" disabled={!value.trim()} onClick={save}>
          Save key
        </button>
        {editing && <button onClick={() => setEditing(false)}>Cancel</button>}
      </div>
      {info.declared?.help && <p className="muted">{info.declared.help}</p>}
      {error && <div className="error-box">{error}</div>}
    </div>
  );
}
