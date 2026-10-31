import { useEffect } from "react";
import { useReactFlow } from "@xyflow/react";
import { useFlow } from "../store";
import { installClipboardEvents, isTyping } from "../editing";
import { runWorkflow, saveWorkflow, useCleanUp } from "../commands";

export default function Shortcuts() {
  const { fitView, zoomIn, zoomOut, zoomTo } = useReactFlow();
  const cleanUp = useCleanUp();
  const name = useFlow((s) => s.name);
  const dirty = useFlow((s) => s.dirty);

  useEffect(() => {
    document.title = `${dirty ? "• " : ""}${name ?? "Untitled"} — Snek`;
  }, [name, dirty]);

  useEffect(() => {
    const onLeave = (e: BeforeUnloadEvent) => {
      const s = useFlow.getState();
      if (!s.dirty || s.stopped) return;
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onLeave);
    return () => window.removeEventListener("beforeunload", onLeave);
  }, []);

  useEffect(() => installClipboardEvents(), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const s = useFlow.getState();
      const typing = isTyping(e.target);
      const mod = e.metaKey || e.ctrlKey;
      const key = e.key.toLowerCase();
      const act = (fn: () => void) => {
        e.preventDefault();
        fn();
      };
      if (s.dialog) return;
      if (mod && key === "enter") return act(() => runWorkflow());
      if (mod && key === "s" && e.shiftKey) return act(() => s.setDialog("saveFile"));
      if (mod && key === "s") return act(() => saveWorkflow());
      if (mod && key === "o") return act(() => s.setDialog("openFile"));
      if (mod && (key === "=" || key === "+")) return act(() => zoomIn({ duration: 150 }));
      if (mod && key === "-") return act(() => zoomOut({ duration: 150 }));
      if (mod && key === "0") return act(() => zoomTo(1, { duration: 150 }));
      if (mod && key === "/") return act(() => s.setDialog("shortcuts"));
      if (typing) return;
      if (mod && key === "z" && e.shiftKey) return act(s.redo);
      if (mod && key === "z") return act(s.undo);
      if (mod && key === "y") return act(s.redo);
      if (mod && key === "d") return act(s.duplicateSelected);
      if (mod && key === "a") return act(s.selectAll);
      if (!mod && e.shiftKey && (e.key === "!" || e.code === "Digit1")) return act(() => fitView({ padding: 0.2, maxZoom: 1.1, duration: 200 }));
      if (!mod && e.shiftKey && key === "l") return act(cleanUp);
      if (!mod && (e.key === "Delete" || e.key === "Backspace")) return act(() => s.deleteSelected());
      if (e.key === "Escape") s.selectNone();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fitView, zoomIn, zoomOut, zoomTo, cleanUp]);

  return null;
}
