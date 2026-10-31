import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useFlow } from "../store";

export default function ChartView({ node, port, refresh }: { node: string; port: string | null; refresh: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    const views: { finalize: () => void }[] = [];
    (async () => {
      try {
        const [{ specs }, embed] = await Promise.all([api.chart(useFlow.getState().toWorkflow(), node, port), import("vega-embed")]);
        if (cancelled || !ref.current) return;
        ref.current.replaceChildren();
        const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
        for (const spec of specs) {
          const el = document.createElement("div");
          el.className = "chart-item";
          ref.current.appendChild(el);
          const result = await embed.default(el, spec as never, {
            theme: dark ? "dark" : undefined,
            config: { background: "transparent" },
            actions: { export: true, source: false, compiled: false, editor: false },
          });
          if (cancelled) result.finalize();
          else views.push(result);
        }
        setError("");
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
      views.forEach((v) => v.finalize());
    };
  }, [node, port, refresh]);
  return (
    <div className="chart-view">
      {error && <div className="error-box">{error}</div>}
      <div ref={ref} />
    </div>
  );
}
