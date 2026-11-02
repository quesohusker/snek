import { useState, type DragEvent, type ReactNode } from "react";
import { useReactFlow } from "@xyflow/react";
import { ChevronRight, Sigma, Star } from "lucide-react";
import { POPULAR_TOOLS, useFlow } from "../store";
import { useMenus } from "../commands";
import { CATEGORY_COLORS, ToolIcon } from "../icons";
import type { MenuItem } from "./Menubar";
import type { FunctionDoc, ToolSpec } from "../types";
import { findFunctions, useFunctions } from "./FunctionBrowser";
import { useToolCard } from "./ToolCard";

const OPEN_KEY = "snek.sidebarOpen";

function readOpen(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(OPEN_KEY) ?? "{}");
  } catch {
    return {};
  }
}

function writeOpen(value: Record<string, boolean>) {
  try {
    localStorage.setItem(OPEN_KEY, JSON.stringify(value));
  } catch {
    return;
  }
}

function filterItems(items: MenuItem[], q: string): MenuItem[] {
  if (!q) return items;
  return items.flatMap((item): MenuItem[] => {
    if (item.type === "separator") return [];
    if (item.label.toLowerCase().includes(q)) return [item];
    if (item.submenu) {
      const sub = filterItems(item.submenu, q);
      return sub.length ? [{ ...item, submenu: sub }] : [];
    }
    return [];
  });
}

function Group({ label, open, onToggle, depth, count, children }: { label: string; open: boolean; onToggle: () => void; depth: number; count?: number; children: ReactNode }) {
  return (
    <div className={`tree-group${count !== undefined ? " tool-group" : ""}`}>
      <button className={`tree-head depth-${depth}`} style={{ paddingLeft: 4 + depth * 12 }} onClick={onToggle} aria-expanded={open}>
        <ChevronRight size={12} className={`tree-chevron${open ? " open" : ""}`} />
        <span>{label}</span>
        {count !== undefined && <span className="tab-count">{count}</span>}
      </button>
      {open && <div className="tree-children">{children}</div>}
    </div>
  );
}

function ToolButton({ tool, color, showCategory, onDragStart, onAdd }: { tool: ToolSpec; color: string; showCategory: boolean; onDragStart: (e: DragEvent, type: string) => void; onAdd: (type: string) => void }) {
  const tip = useToolCard(tool);
  return (
    <button
      className="palette-item"
      draggable
      onDragStart={(e) => {
        tip.hide();
        onDragStart(e, tool.type);
      }}
      onClick={() => onAdd(tool.type)}
      onMouseEnter={tip.show}
      onMouseLeave={tip.hide}
    >
      <span className="palette-icon" style={{ background: color }}>
        <ToolIcon type={tool.type} size={15} />
      </span>
      <span className="palette-text">
        <span className="palette-label">{tool.label}</span>
        <span className="palette-desc">{showCategory ? `${tool.category}${tool.group ? ` › ${tool.group}` : ""} · ` : ""}{tool.description}</span>
      </span>
      {tip.card}
    </button>
  );
}

const TAB_HINTS: Record<string, string> = {
  All: "Every tool, grouped by category.",
  Functions: "Spreadsheet functions with Excel's names. Click one to add a Calculate step that uses it. The Functions button under any expression box inserts one into a formula.",
};

function FunctionButton({ doc, color, onAdd }: { doc: FunctionDoc; color: string; onAdd: (doc: FunctionDoc) => void }) {
  return (
    <button className="palette-item" onClick={() => onAdd(doc)} title={`${doc.syntax}\n${doc.example} gives ${doc.result}`}>
      <span className="palette-icon" style={{ background: color }}>
        <Sigma size={15} />
      </span>
      <span className="palette-text">
        <span className="palette-label">{doc.name}</span>
        <span className="palette-desc">{doc.description}</span>
      </span>
    </button>
  );
}

export default function Palette() {
  const toolList = useFlow((s) => s.toolList);
  const categories = useFlow((s) => s.categories);
  const tab = useFlow((s) => s.paletteTab);
  const addNode = useFlow((s) => s.addNode);
  const selectedId = useFlow((s) => s.selectedId);
  const favorites = useFlow((s) => s.favorites);
  const toggleFavorite = useFlow((s) => s.toggleFavorite);
  const resetFavorites = useFlow((s) => s.resetFavorites);
  const menus = useMenus();
  const [query, setQuery] = useState("");
  const [openState, setOpenState] = useState(readOpen);
  const { screenToFlowPosition, flowToScreenPosition, setCenter, getZoom } = useReactFlow();

  const q = query.trim().toLowerCase();
  const isOpen = (key: string, fallback: boolean) => (q ? true : openState[key] ?? fallback);
  const toggle = (key: string, fallback: boolean) => {
    const next = { ...openState, [key]: !(openState[key] ?? fallback) };
    setOpenState(next);
    writeOpen(next);
  };

  const onDragStart = (e: DragEvent, type: string) => {
    e.dataTransfer.setData("application/snek-tool", type);
    e.dataTransfer.effectAllowed = "move";
  };

  const catalog = useFunctions(true);

  const onAddTool = (type: string, config?: Record<string, unknown>) => {
    const canvas = document.querySelector(".canvas")?.getBoundingClientRect();
    const center = canvas ? screenToFlowPosition({ x: canvas.left + canvas.width / 2 - 28, y: canvas.top + canvas.height / 2 - 28 }) : undefined;
    const id = addNode(type, selectedId ? undefined : center);
    if (config) useFlow.getState().updateConfig(id, config);
    const node = useFlow.getState().nodes.find((n) => n.id === id);
    if (!node || !canvas) return;
    const p = flowToScreenPosition(node.position);
    if (p.x < canvas.left || p.x + 112 > canvas.right || p.y < canvas.top || p.y + 80 > canvas.bottom) {
      setCenter(node.position.x + 56, node.position.y + 40, { zoom: getZoom(), duration: 300 });
    }
  };

  const addFunctionStep = (doc: FunctionDoc) => onAddTool("formula", { formulas: [{ column: doc.name.toLowerCase().replace(/\./g, "_"), expression: doc.example, dtype: "" }] });

  const functionRow = (doc: FunctionDoc) => (
    <div key={doc.name} className="tool-row">
      <FunctionButton doc={doc} color={CATEGORY_COLORS.Columns ?? "var(--cat-dev)"} onAdd={addFunctionStep} />
    </div>
  );

  const toolRow = (t: ToolSpec, showCategory = false) => {
    const color = CATEGORY_COLORS[t.category] ?? "var(--cat-dev)";
    const fav = favorites.includes(t.type);
    return (
      <div key={t.type} className="tool-row">
        <ToolButton tool={t} color={color} showCategory={showCategory} onDragStart={onDragStart} onAdd={onAddTool} />
        <button type="button" className={`fav-toggle${fav ? " on" : ""}`} aria-pressed={fav} title={fav ? "Remove from Favorites" : "Add to Favorites"} onClick={() => toggleFavorite(t.type)}>
          <Star size={13} fill={fav ? "currentColor" : "none"} />
        </button>
      </div>
    );
  };

  const groupedRows = (items: ToolSpec[], category: string): ReactNode => {
    const groups = [...new Set(items.map((t) => t.group || ""))];
    if (groups.length < 2) return items.map((t) => toolRow(t));
    return groups.map((g, i) => {
      const key = `tools/${category}/${g}`;
      const list = items.filter((t) => (t.group || "") === g);
      return (
        <Group key={key} label={g || "Other"} count={list.length} open={isOpen(key, i === 0)} onToggle={() => toggle(key, i === 0)} depth={0}>
          {list.map((t) => toolRow(t))}
        </Group>
      );
    });
  };

  const renderItems = (items: MenuItem[], path: string, depth: number): ReactNode =>
    items.map((item, i) => {
      if (item.type === "separator") return null;
      if (item.submenu) {
        const key = `${path}/${item.label}`;
        const sub: MenuItem[] = item.submenu.length ? item.submenu : [{ label: "Nothing here yet", disabled: true }];
        return (
          <Group key={key} label={item.label} open={isOpen(key, false)} onToggle={() => toggle(key, false)} depth={depth}>
            {renderItems(sub, key, depth + 1)}
          </Group>
        );
      }
      return (
        <button key={`${path}/${i}`} className="tree-item" style={{ paddingLeft: 22 + depth * 12 }} disabled={item.disabled || !item.onSelect} onClick={item.onSelect}>
          <span>{item.label}</span>
          {item.shortcut && <span className="menu-shortcut">{item.shortcut}</span>}
        </button>
      );
    });

  const matches = q ? toolList.filter((t) => `${t.label} ${t.description} ${t.category}`.toLowerCase().includes(q)) : [];
  const visibleMenus = menus.map((m) => ({ ...m, items: filterItems(m.items, q) })).filter((m) => m.items.length);

  const functionMatches = q && catalog ? findFunctions(catalog.functions, q, "").slice(0, 40) : [];

  let body: ReactNode;
  if (q) {
    body =
      matches.length || functionMatches.length ? (
        <>
          {matches.map((t) => toolRow(t, true))}
          {functionMatches.length > 0 && (
            <section>
              <h4 className="palette-section" style={{ color: CATEGORY_COLORS.Columns }}>
                Functions
              </h4>
              {functionMatches.map(functionRow)}
            </section>
          )}
        </>
      ) : (
        <div className="muted pad">No tools or functions match.</div>
      );
  } else if (tab === "Functions") {
    body = catalog ? (
      catalog.groups.map((g, i) => {
        const list = catalog.functions.filter((f) => f.group === g).sort((a, b) => a.name.localeCompare(b.name));
        const key = `functions/${g}`;
        return (
          <Group key={key} label={g} count={list.length} open={isOpen(key, i === 0)} onToggle={() => toggle(key, i === 0)} depth={0}>
            {list.map(functionRow)}
          </Group>
        );
      })
    ) : (
      <div className="muted pad">Loading the functions…</div>
    );
  } else if (tab === "All") {
    body = categories.map((c) => {
      const items = toolList.filter((t) => t.category === c);
      if (!items.length) return null;
      return (
        <section key={c}>
          <h4 className="palette-section" style={{ color: CATEGORY_COLORS[c] }}>
            {c}
          </h4>
          {groupedRows(items, c)}
        </section>
      );
    });
  } else {
    body = groupedRows(toolList.filter((t) => t.category === tab), tab);
  }

  const favList = favorites.map((type) => toolList.find((t) => t.type === type)).filter((t): t is ToolSpec => !!t);
  const usual = favorites.length === POPULAR_TOOLS.length && POPULAR_TOOLS.every((t) => favorites.includes(t));
  const favoritesBlock = !q && toolList.length > 0 && (
    <div className="palette-favorites">
      <Group label="Favorites" count={favList.length} open={isOpen("favorites", true)} onToggle={() => toggle("favorites", true)} depth={0}>
        {favList.length ? favList.map((t) => toolRow(t)) : <div className="muted pad">Click the star on a tool to keep it here.</div>}
        {!usual && (
          <button type="button" className="palette-restore" onClick={resetFavorites}>
            Restore popular tools
          </button>
        )}
      </Group>
    </div>
  );

  const heading = q ? `Search: ${matches.length} tool${matches.length === 1 ? "" : "s"}${functionMatches.length ? `, ${functionMatches.length} function${functionMatches.length === 1 ? "" : "s"}` : ""}` : tab;
  const color = CATEGORY_COLORS[tab];

  return (
    <aside className="palette">
      {visibleMenus.length > 0 && (
        <div className="palette-commands">
          <Group label="Commands" open={isOpen("menu", false)} onToggle={() => toggle("menu", false)} depth={0}>
            {visibleMenus.map((m) => (
              <Group key={m.label} label={m.label} open={isOpen(`menu/${m.label}`, false)} onToggle={() => toggle(`menu/${m.label}`, false)} depth={1}>
                {renderItems(m.items, `menu/${m.label}`, 2)}
              </Group>
            ))}
          </Group>
        </div>
      )}
      <input className="palette-search" placeholder="Search all tools and commands" value={query} onChange={(e) => setQuery(e.target.value)} />
      {favoritesBlock}
      <div className="palette-heading" style={color && !q ? { color } : undefined}>
        {heading}
      </div>
      <div className="palette-hint">{q ? "Results from every category, and the spreadsheet functions." : (TAB_HINTS[tab] ?? "Drag onto the canvas, or click to add after the selected tool.")}</div>
      <div className="palette-tools">{body}</div>
    </aside>
  );
}
