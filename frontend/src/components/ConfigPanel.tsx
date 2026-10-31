import { useEffect, useRef, useState } from "react";
import { useFlow } from "../store";
import { api } from "../api";
import { CATEGORY_COLORS, ToolIcon } from "../icons";
import { Field, type FieldCtx } from "./Fields";
import { keyLabel } from "../paths";
import KeyBox from "./KeyBox";
import type { NodeResult } from "../types";

export default function ConfigPanel() {
  const selectedId = useFlow((s) => s.selectedId);
  const node = useFlow((s) => s.nodes.find((n) => n.id === s.selectedId));
  const spec = useFlow((s) => (node ? s.tools[node.data.type] : undefined));
  const version = useFlow((s) => s.version);
  const updateConfig = useFlow((s) => s.updateConfig);
  const setLabel = useFlow((s) => s.setLabel);
  const focusLabel = useFlow((s) => s.focusLabel);
  const labelRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (focusLabel) setTimeout(() => labelRef.current?.select(), 30);
  }, [focusLabel]);
  const [tab, setTab] = useState<"config" | "code">("config");
  const [schema, setSchema] = useState<NodeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);

  useEffect(() => {
    setSchema(null);
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    const id = ++seq.current;
    setLoading(true);
    const t = setTimeout(() => {
      api
        .schema(useFlow.getState().toWorkflow(), selectedId)
        .then((r) => id === seq.current && setSchema(r.result))
        .catch((e) => id === seq.current && setSchema({ status: "error", error: String(e.message ?? e) } as NodeResult))
        .finally(() => id === seq.current && setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [selectedId, version]);

  if (!node || !spec) {
    return (
      <aside className="config">
        <div className="config-empty">
          <h3>No tool selected</h3>
          <p>Click a tool on the canvas to set it up.</p>
          <h4>Shortcuts</h4>
          <ul>
            <li>
              <kbd>{keyLabel("mod+↵")}</kbd> run the workflow
            </li>
            <li>
              <kbd>{keyLabel("mod+S")}</kbd> save
            </li>
            <li>
              <kbd>{keyLabel("mod+Z")}</kbd> undo, <kbd>{keyLabel("mod+shift+Z")}</kbd> redo
            </li>
            <li>
              <kbd>{keyLabel("mod+C")}</kbd> <kbd>{keyLabel("mod+V")}</kbd> copy and paste tools
            </li>
            <li>Right-click a tool or the canvas for more</li>
          </ul>
          <p className="muted">Help ▸ Keyboard shortcuts lists them all.</p>
          <h4>Expressions</h4>
          <p>
            Filter and Formula take pandas expressions. Write a column as <code>[Column Name]</code>. You can use <code>np</code>, <code>pd</code> and <code>iif(cond, a, b)</code>.
          </p>
        </div>
      </aside>
    );
  }

  const config = node.data.config;
  const ctx: FieldCtx = { columns: (port = spec.inputs[0]?.name ?? "in") => schema?.inputs?.[port]?.columns ?? [] };
  const upstreamProblem = schema?.status === "skipped";

  return (
    <aside className="config">
      <header className="config-head">
        <span className="config-icon" style={{ background: CATEGORY_COLORS[spec.category] }}>
          <ToolIcon type={spec.type} size={18} />
        </span>
        <div>
          <div className="config-title">
            {spec.label} <span className="muted">#{node.id}</span>
          </div>
          <input ref={labelRef} className="config-label" placeholder="Add a name" value={node.data.label} onChange={(e) => setLabel(node.id, e.target.value)} />
        </div>
      </header>
      <div className="tabs">
        <button className={tab === "config" ? "active" : ""} onClick={() => setTab("config")}>
          Configure
        </button>
        <button className={tab === "code" ? "active" : ""} onClick={() => setTab("code")}>
          Python
        </button>
        {loading && <span className="spinner small" />}
      </div>
      <div className="config-body">
        {tab === "config" ? (
          <>
            <p className="muted desc">{spec.description}</p>
            {spec.needs && (
              <p className="needs-box">
                <strong>Input needed:</strong> {spec.needs}
              </p>
            )}
            {spec.connection && <KeyBox name={spec.connection} />}
            {spec.inputs.length > 0 && (
              <div className="input-summary">
                {spec.inputs.map((p) => {
                  const info = schema?.inputs?.[p.name];
                  return (
                    <span key={p.name}>
                      {p.label || "Input"}: {info ? `${info.rows.toLocaleString()} rows × ${info.columns.length} cols${info.count && info.count > 1 ? ` from ${info.count} links` : ""}` : "not connected"}
                    </span>
                  );
                })}
              </div>
            )}
            {upstreamProblem && <div className="warn-box">An upstream tool has an error. Fix it to see columns here.</div>}
            {schema?.status === "waiting" && <div className="warn-box">This workflow came from a file and holds Python code. Press Run once to run it; columns appear here after that.</div>}
            {spec.fields.map((f) => (
              <Field key={f.key} field={f} value={config[f.key]} config={config} onChange={(v) => updateConfig(node.id, { [f.key]: v })} ctx={ctx} />
            ))}
            {schema?.status === "error" && <div className="error-box">{schema.error}</div>}
          </>
        ) : (
          <>
            <p className="muted desc">This is the pandas code this tool runs. Export Python in the toolbar to get the whole workflow as one script.</p>
            <pre className="code-view">{schema?.code || (schema?.error ? `# ${schema.error}` : "")}</pre>
          </>
        )}
      </div>
    </aside>
  );
}
