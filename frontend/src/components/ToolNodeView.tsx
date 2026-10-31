import { memo } from "react";
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
  return (
    <div className={`tool-node${selected ? " selected" : ""}`} title={result?.error || undefined}>
      <div className="tool-tile" style={{ background: color }} onMouseEnter={tip.show} onMouseLeave={tip.hide} onMouseDown={tip.hide}>
        <ToolIcon type={data.type} />
        {spec.inputs.map((p, i) => (
          <Handle key={p.name} type="target" position={Position.Left} id={p.name} style={{ top: spread(i, spec.inputs.length) }} className={p.multi ? "handle multi" : "handle"}>
            {p.label && <span className="handle-label left">{p.label}</span>}
          </Handle>
        ))}
        {spec.outputs.map((p, i) => (
          <Handle key={p.name} type="source" position={Position.Right} id={p.name} style={{ top: spread(i, spec.outputs.length) }} className="handle">
            {p.label && <span className="handle-label right">{p.label}</span>}
          </Handle>
        ))}
        {running ? (
          <span className="badge running" />
        ) : status ? (
          <span className={`badge ${status}${stale ? " stale" : ""}`}>{status === "ok" ? "✓" : status === "error" ? "!" : "–"}</span>
        ) : null}
      </div>
      <div className="tool-caption">
        <span className="tool-id">{id}</span> {data.label || spec.label}
      </div>
      {summary && <div className="tool-summary">{summary}</div>}
      {status === "error" && !stale && <div className="tool-error">{result.error.split("\n")[0]}</div>}
      {tip.card}
    </div>
  );
}

export default memo(ToolNodeView);
