import { memo } from "react";
import { X } from "lucide-react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useFlow, type ToolNode } from "../store";
import { CATEGORY_COLORS, ToolIcon } from "../icons";
import { useToolCard } from "./ToolCard";

function spread(i: number, n: number) {
  return `${((i + 1) / (n + 1)) * 100}%`;
}

function ToolNodeView({ id, data, selected }: NodeProps<ToolNode>) {
  const spec = useFlow((s) => s.tools[data.type]);
  const result = useFlow((s) => s.results[id]);
  const summary = useFlow((s) => s.summaries[id]);
  const stale = useFlow((s) => s.stale);
  const running = useFlow((s) => s.running);
  const tip = useToolCard(spec);
  if (!spec) return null;
  const color = CATEGORY_COLORS[spec.category] ?? "var(--cat-dev)";
  const status = result?.status;
  const first = spec.outputs[0]?.name;
  const info = first ? result?.outputs?.[first] : undefined;
  const ports = Math.max(spec.inputs.length, spec.outputs.length);
  const labeledOutputs = spec.outputs.length > 1;
  return (
    <div className={`step-card${labeledOutputs ? " has-ports" : ""}${selected ? " selected" : ""}${status === "error" && !stale ? " failed" : ""}`} style={{ ["--step-color" as string]: color, minHeight: Math.max(66, ports * 24 + 18) }} title={result?.error || undefined}>
      <div className="step-body" onMouseEnter={tip.show} onMouseLeave={tip.hide} onMouseDown={tip.hide}>
        <div className="step-head">
          <span className="step-icon">
            <ToolIcon type={data.type} size={14} />
          </span>
          <span className="step-title">{data.label || spec.label}</span>
          {running ? <span className="step-status running" /> : status ? <span className={`step-status ${status}${stale ? " stale" : ""}`} /> : null}
        </div>
        {summary && <div className="step-summary">{summary}</div>}
        <div className={`step-foot${stale ? " stale" : ""}`}>
          {info ? `${info.rows.toLocaleString()} rows · ${info.columns.length} columns` : spec.outputs.length ? "" : "end of the flow"}
          <span className="step-id">#{id}</span>
        </div>
        {status === "error" && !stale && <div className="step-error">{result.error.split("\n")[0]}</div>}
      </div>
      {labeledOutputs && (
        <div className="step-ports">
          {spec.outputs.map((p, i) => (
            <span key={p.name} className="step-port-label" style={{ top: spread(i, spec.outputs.length) }}>
              {p.label || p.name}
            </span>
          ))}
        </div>
      )}
      {spec.inputs.map((p, i) => (
        <Handle key={p.name} type="target" position={Position.Left} id={p.name} style={{ top: spread(i, spec.inputs.length) }} className={p.multi ? "handle multi" : "handle"} title={p.label || p.name}>
          {spec.inputs.length > 1 && <span className="handle-label left">{p.label || p.name}</span>}
        </Handle>
      ))}
      {spec.outputs.map((p, i) => (
        <Handle key={p.name} type="source" position={Position.Right} id={p.name} style={{ top: spread(i, spec.outputs.length) }} className="handle" title={p.label || p.name} />
      ))}
      <button
        className="node-delete nodrag"
        title="Delete this step"
        aria-label={`Delete ${data.label || spec.label}`}
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => {
          e.stopPropagation();
          tip.hide();
          useFlow.getState().deleteNode(id);
        }}
      >
        <X size={11} strokeWidth={2.5} />
      </button>
      {tip.card}
    </div>
  );
}

export default memo(ToolNodeView);
