import { useState, type DragEvent, type ReactNode } from "react";
import { useReactFlow } from "@xyflow/react";
import { ChevronRight, Star } from "lucide-react";
import { useFlow } from "../store";
import { useMenus } from "../commands";
import { CATEGORY_COLORS, ToolIcon } from "../icons";
import type { MenuItem } from "./Menubar";
import type { ToolSpec } from "../types";

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

function Group({ label, open, onToggle, depth, children }: { label: string; open: boolean; onToggle: () => void; depth: number; children: ReactNode }) {
  return (
    <div className="tree-group">
      <button className={`tree-head depth-${depth}`} style={{ paddingLeft: 4 + depth * 12 }} onClick={onToggle} aria-expanded={open}>
        <ChevronRight size={12} className={`tree-chevron${open ? " open" : ""}`} />
        <span>{label}</span>
      </button>
      {open && <div className="tree-children">{children}</div>}
    </div>
  );
}

const TAB_HINTS: Record<string, string> = {
  Favorites: "Star any tool to pin it here.",
  All: "Every tool, grouped by category.",
};

export default function Palette() {
  const toolList = useFlow((s) => s.toolList);
  const categories = useFlow((s) => s.categories);
  const tab = useFlow((s) => s.paletteTab);
  const favorites = useFlow((s) => s.favorites);
  const toggleFavorite = useFlow((s) => s.toggleFavorite);
  const addNode = useFlow((s) => s.addNode);
  const selectedId = useFlow((s) => s.selectedId);
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

  const onAddTool = (type: string) => {
    const canvas = document.querySelector(".canvas")?.getBoundingClientRect();
    const center = canvas ? screenToFlowPosition({ x: canvas.left + canvas.width / 2 - 28, y: canvas.top + canvas.height / 2 - 28 }) : undefined;
    const id = addNode(type, selectedId ? undefined : center);
    const node = useFlow.getState().nodes.find((n) => n.id === id);
    if (!node || !canvas) return;
    const p = flowToScreenPosition(node.position);
    if (p.x < canvas.left || p.x + 112 > canvas.right || p.y < canvas.top || p.y + 80 > canvas.bottom) {
      setCenter(node.position.x + 56, node.position.y + 40, { zoom: getZoom(), duration: 300 });
    }
  };

  const toolRow = (t: ToolSpec, showCategory = false) => {
    const fav = favorites.includes(t.type);
    const color = CATEGORY_COLORS[t.category] ?? "var(--cat-dev)";
    return (
      <div key={t.type} className="tool-row">
        <button className="palette-item" draggable onDragStart={(e) => onDragStart(e, t.type)} onClick={() => onAddTool(t.type)} title={t.description}>
          <span className="palette-icon" style={{ background: color }}>
            <ToolIcon type={t.type} size={15} />
          </span>
          <span className="palette-text">
            <span className="palette-label">{t.label}</span>
            <span className="palette-desc">{showCategory ? `${t.category} · ` : ""}{t.description}</span>
          </span>
        </button>
        <button className={`star${fav ? " on" : ""}`} onClick={() => toggleFavorite(t.type)} title={fav ? "Remove from Favorites" : "Add to Favorites"} aria-label={fav ? `Remove ${t.label} from Favorites` : `Add ${t.label} to Favorites`}>
          <Star size={13} fill={fav ? "currentColor" : "none"} />
        </button>
      </div>
    );
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

  const byType = new Map(toolList.map((t) => [t.type, t]));
  const matches = q ? toolList.filter((t) => `${t.label} ${t.description} ${t.category}`.toLowerCase().includes(q)) : [];
  const visibleMenus = menus.map((m) => ({ ...m, items: filterItems(m.items, q) })).filter((m) => m.items.length);

  let body: ReactNode;
  if (q) {
    body = matches.length ? matches.map((t) => toolRow(t, true)) : <div className="muted pad">No tools match.</div>;
  } else if (tab === "Favorites") {
    const favs = favorites.map((f) => byType.get(f)).filter((t): t is ToolSpec => !!t);
    body = favs.length ? favs.map((t) => toolRow(t)) : <div className="muted pad">No favorites yet. Click the star next to any tool.</div>;
  } else if (tab === "All") {
    body = categories.map((c) => {
      const items = toolList.filter((t) => t.category === c);
      if (!items.length) return null;
      return (
        <section key={c}>
          <h4 className="palette-section" style={{ color: CATEGORY_COLORS[c] }}>
            {c}
          </h4>
          {items.map((t) => toolRow(t))}
        </section>
      );
    });
  } else {
    body = toolList.filter((t) => t.category === tab).map((t) => toolRow(t));
  }

  const heading = q ? `Search: ${matches.length} tool${matches.length === 1 ? "" : "s"}` : tab;
  const color = CATEGORY_COLORS[tab];

  return (
    <aside className="palette">
      <input className="palette-search" placeholder="Search all tools and commands" value={query} onChange={(e) => setQuery(e.target.value)} />
      <div className="palette-heading" style={color && !q ? { color } : undefined}>
        {heading}
      </div>
      <div className="palette-hint">{q ? "Results from every category." : (TAB_HINTS[tab] ?? "Drag onto the canvas, or click to add after the selected tool.")}</div>
      <div className="palette-tools">{body}</div>
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
    </aside>
  );
}
