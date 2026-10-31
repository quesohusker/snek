import { useEffect, useRef } from "react";
import { MenuList, type MenuItem } from "./Menubar";

export type ContextMenuState = { x: number; y: number; items: MenuItem[] } | null;

export default function ContextMenu({ menu, onClose }: { menu: ContextMenuState; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menu) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    window.addEventListener("blur", onClose);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("blur", onClose);
    };
  }, [menu, onClose]);
  if (!menu) return null;
  const left = Math.min(menu.x, window.innerWidth - 240);
  const top = Math.min(menu.y, window.innerHeight - 24 * menu.items.length - 16);
  return (
    <div ref={ref} className="context-menu" style={{ left, top }} onContextMenu={(e) => e.preventDefault()}>
      <MenuList items={menu.items} close={onClose} />
    </div>
  );
}
