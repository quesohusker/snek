import { isClipboardData, useFlow, type ClipboardData } from "./store";

type Point = { x: number; y: number };

export function isTyping(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  if (!el) return false;
  if (el instanceof HTMLInputElement) return !["checkbox", "radio", "button", "submit", "range", "color"].includes(el.type);
  return el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement || el.isContentEditable;
}

function hasTextSelection() {
  const sel = window.getSelection();
  return !!sel && !sel.isCollapsed && sel.toString().length > 0;
}

function serialize(data: ClipboardData) {
  return JSON.stringify(data);
}

function tableText(text: string) {
  const lines = text.replace(/\r\n/g, "\n").trim().split("\n");
  if (lines.length < 2) return null;
  const delimiter = lines[0].includes("\t") ? "\t" : lines[0].includes(",") ? "," : null;
  return delimiter ? { data: lines.join("\n"), delimiter } : null;
}

function pasteText(text: string, at?: Point) {
  const s = useFlow.getState();
  let parsed: unknown = null;
  try {
    parsed = JSON.parse(text);
  } catch {
    parsed = null;
  }
  if (isClipboardData(parsed)) {
    s.pasteData(parsed, at);
    return true;
  }
  const table = tableText(text);
  if (!table || !s.tools.text_input) return false;
  s.selectNone();
  const id = s.addNode("text_input", at);
  useFlow.getState().updateConfig(id, table);
  useFlow.setState((st) => ({ past: st.past.slice(0, -1) }));
  return true;
}

export async function copyTools() {
  const data = useFlow.getState().copySelection();
  if (data) await navigator.clipboard?.writeText(serialize(data)).catch(() => undefined);
}

export async function cutTools() {
  const data = useFlow.getState().cutSelected();
  if (data) await navigator.clipboard?.writeText(serialize(data)).catch(() => undefined);
}

export async function pasteTools(at?: Point) {
  const text = await navigator.clipboard?.readText().catch(() => "");
  if (text && pasteText(text, at)) return;
  const own = useFlow.getState().clipboard;
  if (own) useFlow.getState().pasteData(own, at);
}

export function installClipboardEvents() {
  const onCopy = (e: ClipboardEvent) => {
    if (isTyping(e.target) || hasTextSelection()) return;
    const data = useFlow.getState().copySelection();
    if (!data) return;
    e.clipboardData?.setData("text/plain", serialize(data));
    e.preventDefault();
  };
  const onCut = (e: ClipboardEvent) => {
    if (isTyping(e.target) || hasTextSelection()) return;
    const data = useFlow.getState().cutSelected();
    if (!data) return;
    e.clipboardData?.setData("text/plain", serialize(data));
    e.preventDefault();
  };
  const onPaste = (e: ClipboardEvent) => {
    if (isTyping(e.target)) return;
    const text = e.clipboardData?.getData("text/plain") ?? "";
    if (text && pasteText(text)) e.preventDefault();
    else if (!text && useFlow.getState().clipboard) {
      useFlow.getState().pasteData(useFlow.getState().clipboard!);
      e.preventDefault();
    }
  };
  document.addEventListener("copy", onCopy);
  document.addEventListener("cut", onCut);
  document.addEventListener("paste", onPaste);
  return () => {
    document.removeEventListener("copy", onCopy);
    document.removeEventListener("cut", onCut);
    document.removeEventListener("paste", onPaste);
  };
}
