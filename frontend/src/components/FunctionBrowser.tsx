import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { FunctionCatalog, FunctionDoc } from "../types";

let cache: FunctionCatalog | null = null;
let pending: Promise<FunctionCatalog> | null = null;

function loadFunctions(): Promise<FunctionCatalog> {
  if (cache) return Promise.resolve(cache);
  pending ??= api.functions().then((data) => (cache = data));
  return pending;
}

export function useFunctions(enabled: boolean): FunctionCatalog | null {
  const [data, setData] = useState<FunctionCatalog | null>(cache);
  useEffect(() => {
    if (!enabled || cache) return;
    let live = true;
    loadFunctions()
      .then((d) => live && setData(d))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [enabled]);
  return data;
}

export function findFunctions(list: FunctionDoc[], query: string, group: string, limit = 60): FunctionDoc[] {
  const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
  const scored = list
    .filter((f) => !group || f.group === group)
    .map((f) => {
      const name = f.name.toLowerCase();
      const hay = `${name} ${f.description.toLowerCase()} ${f.words.toLowerCase()}`;
      if (!tokens.every((t) => hay.includes(t))) return null;
      const rank = tokens.length && name.startsWith(tokens[0]) ? 0 : tokens.length && name.includes(tokens[0]) ? 1 : 2;
      return { f, rank };
    })
    .filter((x): x is { f: FunctionDoc; rank: number } => x !== null)
    .sort((a, b) => a.rank - b.rank || a.f.name.localeCompare(b.f.name));
  return scored.slice(0, limit).map((x) => x.f);
}

export default function FunctionBrowser({ catalog, onPick }: { catalog: FunctionCatalog; onPick: (name: string) => void }) {
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState("");
  const rows = useMemo(() => findFunctions(catalog.functions, query, group), [catalog, query, group]);
  return (
    <div className="fx-panel">
      <input autoFocus placeholder="Search by name or what it does, such as remove spaces" value={query} onChange={(e) => setQuery(e.target.value)} />
      <div className="fx-groups">
        {["", ...catalog.groups].map((g) => (
          <button key={g || "all"} type="button" className={`chip${group === g ? " on" : ""}`} onClick={() => setGroup(g)}>
            {g || "All"}
          </button>
        ))}
      </div>
      <div className="fx-list">
        {rows.length === 0 && <div className="muted pad">No function matches.</div>}
        {rows.map((f) => (
          <button key={f.name} type="button" className="fx-row" onClick={() => onPick(f.name)} title="Click to insert">
            <span className="fx-name">{f.name}</span>
            <span className="fx-desc">{f.description}</span>
            <code className="fx-syntax">{f.syntax}</code>
            <span className="fx-example">
              <code>{f.example}</code> <span className="muted">gives</span> <code>{f.result}</code>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
