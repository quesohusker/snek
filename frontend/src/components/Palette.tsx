import { useState, type DragEvent } from "react";
import { useReactFlow } from "@xyflow/react";
import { ChevronRight } from "lucide-react";
import { useFlow } from "../store";
import { useMenus } from "../commands";
import { CATEGORY_COLORS, ToolIcon } from "../icons";
import type { MenuItem } from "./Menubar";

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

function Group({ label, open, onToggle, depth, color, count, children }: { label: string; open: boolean; onToggle: () => void; depth: number; color?: string; count?: number; children: React.ReactNode }) {
  return (
    <div className="tree-group">
      <button className={`tree-head depth-${depth}`} style={{ paddingLeft: 4 + depth * 12, color }} onClick={onToggle} aria-expanded={open}>
        <ChevronRight size={12} className={`tree-chevron${open ? " open" : ""}`} />
        <span>{label}</span>
        {count !== undefined && <span className="tree-count">{count}</span>}
      </button>
      {open && <div className="tree-children">{children}</div>}
    </div>
  );
}

export default function Palette() {
  const toolList = useFlow((s) => s.toolList);
  const categories = useFlow((s) => s.categories);
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

  const visibleTools = toolList.filter((t) => !q || t.label.toLowerCase().includes(q) || t.description.toLowerCase().includes(q));
  const visibleMenus = menus.map((m) => ({ ...m, items: filterItems(m.items, q) })).filter((m) => m.items.length);

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

  const renderItems = (items: MenuItem[], path: string, depth: number): React.ReactNode =>
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

  return (
    <aside className="palette">
      <input className="palette-search" placeholder="Search commands and tools" value={query} onChange={(e) => setQuery(e.target.value)} />
      {visibleMenus.length > 0 && (
        <Group label="Menu" open={isOpen("menu", true)} onToggle={() => toggle("menu", true)} depth={0}>
          {visibleMenus.map((m) => (
            <Group key={m.label} label={m.label} open={isOpen(`menu/${m.label}`, false)} onToggle={() => toggle(`menu/${m.label}`, false)} depth={1}>
              {renderItems(m.items, `menu/${m.label}`, 2)}
            </Group>
          ))}
        </Group>
      )}
      {visibleTools.length > 0 && (
        <Group label="Tools" open={isOpen("tools", true)} onToggle={() => toggle("tools", true)} depth={0}>
          <div className="palette-hint">Drag onto the canvas, or click to add after the selected tool.</div>
          {categories.map((cat) => {
            const items = visibleTools.filter((t) => t.category === cat);
            if (!items.length) return null;
            const key = `tools/${cat}`;
            return (
              <Group key={cat} label={cat} open={isOpen(key, true)} onToggle={() => toggle(key, true)} depth={1} color={CATEGORY_COLORS[cat]} count={items.length}>
                {items.map((t) => (
                  <button key={t.type} className="palette-item" draggable onDragStart={(e) => onDragStart(e, t.type)} onClick={() => onAddTool(t.type)} title={t.description}>
                    <span className="palette-icon" style={{ background: CATEGORY_COLORS[cat] }}>
                      <ToolIcon type={t.type} size={15} />
                    </span>
                    {t.label}
                  </button>
                ))}
              </Group>
            );
          })}
        </Group>
      )}
      {!visibleMenus.length && !visibleTools.length && <div className="muted pad">No matches.</div>}
    </aside>
  );
}
