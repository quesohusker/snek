import { LayoutGrid, Star } from "lucide-react";
import { useFlow } from "../store";
import { CATEGORY_COLORS } from "../icons";

export default function CategoryBar() {
  const categories = useFlow((s) => s.categories);
  const toolList = useFlow((s) => s.toolList);
  const favorites = useFlow((s) => s.favorites);
  const tab = useFlow((s) => s.paletteTab);
  const setTab = useFlow((s) => s.setPaletteTab);
  const known = new Set(toolList.map((t) => t.type));
  const tabs = [
    { key: "Favorites", count: favorites.filter((f) => known.has(f)).length, color: "var(--warn)" },
    { key: "All", count: toolList.length, color: "var(--muted)" },
    ...categories.map((c) => ({ key: c, count: toolList.filter((t) => t.category === c).length, color: CATEGORY_COLORS[c] ?? "var(--muted)" })).filter((t) => t.count > 0),
  ];
  return (
    <nav className="category-bar" role="tablist" aria-label="Tool categories">
      {tabs.map((t) => (
        <button key={t.key} role="tab" aria-selected={tab === t.key} className={tab === t.key ? "active" : ""} style={{ ["--tab-color" as string]: t.color }} onClick={() => setTab(t.key)}>
          {t.key === "Favorites" ? <Star size={13} /> : t.key === "All" ? <LayoutGrid size={13} /> : <span className="tab-dot" />}
          {t.key}
          <span className="tab-count">{t.count}</span>
        </button>
      ))}
    </nav>
  );
}
