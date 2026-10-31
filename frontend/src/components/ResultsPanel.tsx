import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { useFlow } from "../store";
import { api } from "../api";
import { shortType } from "./Fields";
import type { NodeResult, PreviewData } from "../types";

const PAGE = 200;

function cell(v: any) {
  if (v === null || v === undefined) return null;
  if (typeof v === "object") return JSON.stringify(v);
  if (typeof v === "number" && !Number.isInteger(v)) return String(Number(v.toFixed(6)));
  return String(v);
}

function stat(v: any) {
  if (v === null || v === undefined) return "";
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 4 });
  return String(v);
}

export default function ResultsPanel() {
  const selectedId = useFlow((s) => s.selectedId);
  const node = useFlow((s) => s.nodes.find((n) => n.id === s.selectedId));
  const spec = useFlow((s) => (node ? s.tools[node.data.type] : undefined));
  const version = useFlow((s) => s.version);
  const lastRun = useFlow((s) => s.lastRun);
  const mergeResult = useFlow((s) => s.mergeResult);
  const select = useFlow((s) => s.select);
  const [tab, setTab] = useState<"data" | "columns" | "messages">("data");
  const [port, setPort] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<PreviewData | null>(null);
  const [result, setResult] = useState<NodeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);
  const seq = useRef(0);

  useEffect(() => {
    setPort(null);
    setOffset(0);
    setData(null);
    setResult(null);
  }, [selectedId]);

  useEffect(() => {
    setOffset(0);
  }, [port, version]);

  useEffect(() => {
    if (!selectedId || tab === "messages") return;
    const id = ++seq.current;
    setLoading(true);
    const t = setTimeout(() => {
      api
        .preview(useFlow.getState().toWorkflow(), selectedId, port, offset, PAGE, tab === "columns")
        .then((r) => {
          if (id !== seq.current) return;
          setData(r.data);
          setResult(r.result);
          setError("");
          mergeResult(selectedId, r.result);
        })
        .catch((e) => id === seq.current && setError(String(e.message ?? e)))
        .finally(() => id === seq.current && setLoading(false));
    }, 450);
    return () => clearTimeout(t);
  }, [selectedId, port, offset, version, tab, lastRun, tick, mergeResult]);

  const outputs = spec?.outputs ?? [];
  const activePort = port ?? outputs[0]?.name ?? null;

  return (
    <section className="results">
      <div className="results-bar">
        <div className="tabs">
          <button className={tab === "data" ? "active" : ""} onClick={() => setTab("data")}>
            Data
          </button>
          <button className={tab === "columns" ? "active" : ""} onClick={() => setTab("columns")}>
            Columns
          </button>
          <button className={tab === "messages" ? "active" : ""} onClick={() => setTab("messages")}>
            Messages{lastRun?.errors ? <span className="count err">{lastRun.errors}</span> : null}
          </button>
        </div>
        {tab !== "messages" && outputs.length > 1 && (
          <div className="ports">
            {outputs.map((p) => (
              <button key={p.name} className={activePort === p.name ? "active" : ""} onClick={() => setPort(p.name)}>
                {p.label || p.name}
                {result?.outputs?.[p.name] && <span className="muted"> {result.outputs[p.name].rows.toLocaleString()}</span>}
              </button>
            ))}
          </div>
        )}
        {tab !== "messages" && node && (
          <div className="results-info">
            {loading && <span className="spinner small" />}
            {data && (
              <span>
                {data.total.toLocaleString()} rows × {data.columns.length} columns
                {spec && !spec.outputs.length ? " (input)" : ""}
                {result?.elapsed_ms ? ` · ${result.elapsed_ms} ms` : result?.cached ? " · cached" : ""}
              </span>
            )}
            {data && tab === "data" && data.total > PAGE && (
              <span className="pager">
                <button className="icon-btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                  <ChevronLeft size={14} />
                </button>
                {(offset + 1).toLocaleString()}–{Math.min(offset + PAGE, data.total).toLocaleString()}
                <button className="icon-btn" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>
                  <ChevronRight size={14} />
                </button>
              </span>
            )}
            <button className="icon-btn" title="Refresh" onClick={() => setTick(tick + 1)}>
              <RefreshCw size={14} />
            </button>
          </div>
        )}
      </div>
      <div className="results-body">
        {tab === "messages" ? (
          <Messages onPick={select} />
        ) : !node ? (
          <div className="muted pad">Select a tool to see its data.</div>
        ) : error ? (
          <div className="error-box">{error}</div>
        ) : result && result.status !== "ok" ? (
          <div className={result.status === "error" ? "error-box" : "warn-box"}>
            <pre>{result.error}</pre>
          </div>
        ) : !data ? (
          <div className="muted pad">{loading ? "Loading…" : result?.message || "No data."}</div>
        ) : tab === "data" ? (
          <Grid data={data} />
        ) : (
          <Profile data={data} />
        )}
        {result?.warnings?.length ? <div className="warn-box">{result.warnings.join("\n")}</div> : null}
      </div>
    </section>
  );
}

function Grid({ data }: { data: PreviewData }) {
  return (
    <div className="grid-wrap">
      <table className="grid">
        <thead>
          <tr>
            <th className="rownum">#</th>
            {data.columns.map((c, i) => (
              <th key={i} title={`${c.name} (${c.dtype})`}>
                <div className="col-name">{c.name}</div>
                <div className="col-type">{shortType(c.dtype)}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row, r) => (
            <tr key={r}>
              <td className="rownum">{data.offset + r + 1}</td>
              {row.map((v, i) => {
                const text = cell(v);
                return (
                  <td key={i} className={text === null ? "null" : typeof v === "number" ? "num" : ""} title={text ?? "null"}>
                    {text ?? "null"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Profile({ data }: { data: PreviewData }) {
  return (
    <div className="grid-wrap">
      <table className="grid profile">
        <thead>
          <tr>
            <th>Column</th>
            <th>Type</th>
            <th>Nulls</th>
            <th>Distinct</th>
            <th>Min</th>
            <th>Max</th>
            <th>Mean / most common</th>
          </tr>
        </thead>
        <tbody>
          {data.columns.map((c, i) => (
            <tr key={i}>
              <td>{c.name}</td>
              <td className="muted">{c.dtype}</td>
              <td className={c.nulls ? "num warn" : "num"}>
                {stat(c.nulls)}
                {c.nulls ? <span className="muted"> ({((100 * c.nulls) / Math.max(data.total, 1)).toFixed(1)}%)</span> : null}
              </td>
              <td className="num">{stat(c.unique)}</td>
              <td>{stat(c.min)}</td>
              <td>{stat(c.max)}</td>
              <td>{c.mean !== null && c.mean !== undefined ? stat(c.mean) : c.top !== undefined ? `${stat(c.top)} (${stat(c.top_count)})` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Messages({ onPick }: { onPick: (id: string) => void }) {
  const nodes = useFlow((s) => s.nodes);
  const results = useFlow((s) => s.results);
  const tools = useFlow((s) => s.tools);
  const lastRun = useFlow((s) => s.lastRun);
  const stale = useFlow((s) => s.stale);
  if (!lastRun) return <div className="muted pad">Run the workflow to see messages.</div>;
  return (
    <ul className="messages">
      {stale && <li className="muted">The workflow changed since the last run.</li>}
      {nodes.map((n) => {
        const r = results[n.id];
        if (!r) return null;
        return (
          <li key={n.id} className={r.status} onClick={() => onPick(n.id)}>
            <span className={`dot ${r.status}`} />
            <strong>
              #{n.id} {n.data.label || tools[n.data.type]?.label}
            </strong>
            <span>{r.status === "ok" ? r.message : r.error.split("\n")[0]}</span>
            {r.warnings.map((w, i) => (
              <span key={i} className="warn-text">
                {w}
              </span>
            ))}
            {r.status === "ok" && <span className="muted">{r.cached ? "cached" : `${r.elapsed_ms} ms`}</span>}
          </li>
        );
      })}
    </ul>
  );
}
