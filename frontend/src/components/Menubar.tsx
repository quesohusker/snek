import { useEffect, useRef, useState } from "react";
import { ChevronRight } from "lucide-react";

export type MenuItem =
  | { type?: "item"; label: string; shortcut?: string; onSelect?: () => void; disabled?: boolean; submenu?: MenuItem[] }
  | { type: "separator" };

export type Menu = { label: string; items: MenuItem[] };

export default function Menubar({ menus, onOpen }: { menus: Menu[]; onOpen?: (label: string) => void }) {
  const [open, setOpen] = useState<string | null>(null);
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(null);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(null);
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const show = (label: string | null) => {
    setOpen(label);
    if (label) onOpen?.(label);
  };

  return (
    <nav className="menubar" ref={ref} role="menubar">
      {menus.map((m) => (
        <div key={m.label} className="menubar-entry">
          <button
            role="menuitem"
            aria-haspopup="menu"
            aria-expanded={open === m.label}
            className={open === m.label ? "open" : ""}
            onClick={() => show(open === m.label ? null : m.label)}
            onMouseEnter={() => open && open !== m.label && show(m.label)}
          >
            {m.label}
          </button>
          {open === m.label && <MenuList items={m.items} close={() => setOpen(null)} />}
        </div>
      ))}
    </nav>
  );
}

export function MenuList({ items, close, nested }: { items: MenuItem[]; close: () => void; nested?: boolean }) {
  const [active, setActive] = useState<number | null>(null);
  return (
    <ul className={`menu${nested ? " nested" : ""}`} role="menu">
      {items.map((item, i) => {
        if (item.type === "separator") return <li key={i} className="menu-sep" role="separator" />;
        const hasSub = !!item.submenu;
        const disabled = item.disabled || (!item.onSelect && !hasSub);
        return (
          <li key={i} role="none" className="menu-row" onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive((a) => (a === i ? null : a))}>
            <button
              role="menuitem"
              aria-haspopup={hasSub ? "menu" : undefined}
              aria-expanded={hasSub ? active === i : undefined}
              disabled={disabled}
              className={hasSub && active === i ? "open" : ""}
              onClick={() => {
                if (hasSub) return setActive(i);
                item.onSelect?.();
                close();
              }}
            >
              <span className="menu-label">{item.label}</span>
              {item.shortcut && <span className="menu-shortcut">{item.shortcut}</span>}
              {hasSub && <ChevronRight size={13} className="menu-arrow" />}
            </button>
            {hasSub && active === i && !disabled && (
              <MenuList items={item.submenu!.length ? item.submenu! : [{ label: "Nothing here yet", disabled: true }]} close={close} nested />
            )}
          </li>
        );
      })}
    </ul>
  );
}
