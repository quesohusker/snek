import { useEffect, useLayoutEffect, useRef, useState, type MouseEvent } from "react";
import { createPortal } from "react-dom";
import { CATEGORY_COLORS } from "../icons";
import type { ToolSpec } from "../types";

type Anchor = { left: number; right: number; top: number };

const WIDTH = 320;
const GAP = 10;

function ToolCard({ spec, anchor }: { spec: ToolSpec; anchor: Anchor }) {
  const ref = useRef<HTMLDivElement>(null);
  const [top, setTop] = useState(anchor.top);
  useLayoutEffect(() => {
    const height = ref.current?.offsetHeight ?? 0;
    setTop(Math.max(8, Math.min(anchor.top, window.innerHeight - height - 8)));
  }, [anchor]);
  const left = anchor.right + GAP + WIDTH < window.innerWidth ? anchor.right + GAP : Math.max(8, anchor.left - GAP - WIDTH);
  const color = CATEGORY_COLORS[spec.category] ?? "var(--cat-dev)";
  return (
    <div ref={ref} className="tool-card" role="tooltip" style={{ left, top, width: WIDTH, ["--card-color" as string]: color }}>
      <div className="tool-card-head">
        <strong>{spec.label}</strong>
        <span>{spec.group ? `${spec.category} › ${spec.group}` : spec.category}</span>
      </div>
      {spec.needs && (
        <div className="tool-card-needs">
          <span className="tool-card-label">Input needed</span>
          {spec.needs}
        </div>
      )}
      <div className="tool-card-desc">{spec.description}</div>
    </div>
  );
}

export function useToolCard(spec: ToolSpec | undefined) {
  const [anchor, setAnchor] = useState<Anchor | null>(null);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const show = (e: MouseEvent<HTMLElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setAnchor({ left: r.left, right: r.right, top: r.top }), 300);
  };
  const hide = () => {
    window.clearTimeout(timer.current);
    setAnchor(null);
  };
  const card = spec && anchor ? createPortal(<ToolCard spec={spec} anchor={anchor} />, document.body) : null;
  return { show, hide, card };
}
